"""
test_feature_extraction_diagnostics.py
========================================

Interpretability & diagnostics suite for `OceanFeatureExtractorCNN`.
Proves that the network is actively reading every one of the 8 input
channels -- rather than ignoring some of them, or suffering from dead
convolutional filters -- via three complementary probes:

1. Channel Occlusion Sensitivity Analysis
   Perturb one input channel at a time (+0.5 delta) and measure how
   much the output embedding moves (Euclidean + cosine distance).
   A channel the network ignores would produce ~zero shift.

2. Gradient-Based Feature Attribution (Input Saliency)
   Backpropagate the embedding norm to the input and inspect
   `|d(embedding)/d(input_channel)|` per channel. A channel with zero
   gradient contributes nothing to the output under any perturbation.

3. Spatial Feature Map Activation Check
   Hook Stage 1/2/3 outputs and measure the fraction of dead
   (all-zero) filters and elements, and the spatial variance of each
   stage's activation maps, to rule out dead layers.

Usage
-----
    pytest -v -s test_feature_extraction_diagnostics.py
    # or, run directly:
    python test_feature_extraction_diagnostics.py

Dependencies: torch, pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
import torch
import torch.nn as nn
import torch.nn.functional as F

# --------------------------------------------------------------------------- #
# Import the model under test from the sibling extraction script
# --------------------------------------------------------------------------- #

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from OceanFeatureExtractorCNN import OceanFeatureExtractorCNN, IN_CHANNELS, EMBED_DIM  # noqa: E402

INPUT_PATH = _SCRIPT_DIR / "ocean_weather_tensor.pt"
GRID_SIZE = 64

# Channel layout, matching era5_wind_wave_to_tensor.py's build_tensor().
CHANNEL_NAMES: Tuple[str, ...] = ("u10", "v10", "swh", "mwp", "uo", "vo", "ssh (zos)", "mwd")

# Channels that are always populated with real physical signal (ERA5).
# Channels 4-6 (uo, vo, ssh) may legitimately be zero-filled CMEMS
# placeholders, so they are reported but not required to shift.
REQUIRED_RESPONSIVE_CHANNELS: Tuple[int, ...] = (0, 1, 2, 3, 7)  # u10, v10, swh, mwp, mwd

OCCLUSION_DELTA = 0.5
MIN_EUCLIDEAN_SHIFT = 1e-6
MIN_GRADIENT_MAGNITUDE = 1e-8
MAX_DEAD_CHANNEL_FRACTION = 0.5  # per stage, fraction of fully-zero filters


# --------------------------------------------------------------------------- #
# Logging helpers
# --------------------------------------------------------------------------- #

def _log_header(title: str) -> None:
    print(f"\n{'=' * 78}")
    print(title)
    print("=" * 78)


def _log_pass(msg: str) -> None:
    print(f"  [PASSED] {msg}")


def _log_info(msg: str) -> None:
    print(f"  [INFO]   {msg}")


def _log_warn(msg: str) -> None:
    print(f"  [WARN]   {msg}")


# --------------------------------------------------------------------------- #
# Shared fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def model() -> OceanFeatureExtractorCNN:
    """A fresh, deterministically-initialized model in eval() mode."""
    torch.manual_seed(42)
    m = OceanFeatureExtractorCNN(in_channels=IN_CHANNELS, embed_dim=EMBED_DIM)
    m.eval()
    return m


@pytest.fixture(scope="module")
def input_tensor() -> torch.Tensor:
    """Load ocean_weather_tensor.pt from disk and add a batch dimension."""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input tensor not found: {INPUT_PATH}. "
            "Run era5_wind_wave_to_tensor.py first to generate it."
        )
    tensor = torch.load(INPUT_PATH, map_location="cpu").float()
    if tensor.dim() == 3:
        tensor = tensor.unsqueeze(0)
    assert tensor.shape == (1, IN_CHANNELS, GRID_SIZE, GRID_SIZE), (
        f"Expected shape (1, {IN_CHANNELS}, {GRID_SIZE}, {GRID_SIZE}), got {tuple(tensor.shape)}"
    )
    return tensor


# --------------------------------------------------------------------------- #
# Test 1: Channel Occlusion Sensitivity Analysis
# --------------------------------------------------------------------------- #

def test_1_channel_occlusion_sensitivity(model: OceanFeatureExtractorCNN, input_tensor: torch.Tensor):
    """
    Perturb one channel at a time (+0.5 delta) and confirm every
    physically-populated channel moves the output embedding.
    """
    _log_header("TEST 1: Channel Occlusion Sensitivity Analysis")

    with torch.no_grad():
        z_base = model(input_tensor)

    results: List[Dict[str, float]] = []
    for idx, name in enumerate(CHANNEL_NAMES):
        modified = input_tensor.clone()
        modified[0, idx, :, :] += OCCLUSION_DELTA

        with torch.no_grad():
            z_modified = model(modified)

        euclidean_dist = torch.norm(z_base - z_modified).item()
        cosine_dist = 1.0 - F.cosine_similarity(z_base, z_modified).item()

        results.append(
            {"idx": idx, "name": name, "euclidean": euclidean_dist, "cosine": cosine_dist}
        )

    print(f"\n  Perturbation applied: channel += {OCCLUSION_DELTA} (all other 7 channels held fixed)\n")
    print(f"  {'Idx':<5}{'Variable':<14}{'Euclidean Shift':>18}{'Cosine Distance':>18}")
    print(f"  {'-' * 5}{'-' * 14}{'-' * 18}{'-' * 18}")
    for r in results:
        print(f"  {r['idx']:<5}{r['name']:<14}{r['euclidean']:>18.6f}{r['cosine']:>18.6f}")

    for r in results:
        if r["idx"] in REQUIRED_RESPONSIVE_CHANNELS:
            assert r["euclidean"] > MIN_EUCLIDEAN_SHIFT, (
                f"Channel {r['idx']} ({r['name']}) produced a near-zero output shift "
                f"({r['euclidean']:.8f}) -- the model may be ignoring this channel."
            )
            _log_pass(
                f"Channel {r['idx']} ({r['name']}): shift={r['euclidean']:.6f} -- "
                "network is actively responding to this channel."
            )
        else:
            status = "responsive" if r["euclidean"] > MIN_EUCLIDEAN_SHIFT else "no measurable shift"
            _log_info(f"Channel {r['idx']} ({r['name']}, CMEMS/placeholder): {status} (shift={r['euclidean']:.6f})")


# --------------------------------------------------------------------------- #
# Test 2: Gradient-Based Feature Attribution (Input Saliency)
# --------------------------------------------------------------------------- #

def test_2_gradient_based_attribution(model: OceanFeatureExtractorCNN, input_tensor: torch.Tensor):
    """
    Backpropagate the embedding's norm to the input and confirm every
    channel carries non-zero gradient signal.
    """
    _log_header("TEST 2: Gradient-Based Feature Attribution (Input Saliency)")

    grad_input = input_tensor.clone().detach().requires_grad_(True)

    z_weather = model(grad_input)
    loss = z_weather.norm()
    loss.backward()

    assert grad_input.grad is not None, "No gradient was computed on the input tensor."

    # (1, 8, 64, 64) -> mean |grad| per channel -> (8,)
    channel_importance = grad_input.grad.abs().mean(dim=[2, 3]).squeeze(0)
    total_importance = channel_importance.sum().item()

    print(f"\n  loss = ||z_weather||_2 = {loss.item():.6f}\n")
    print(f"  {'Idx':<5}{'Variable':<14}{'Mean |Gradient|':>18}{'% of Total':>14}")
    print(f"  {'-' * 5}{'-' * 14}{'-' * 18}{'-' * 14}")
    for idx, name in enumerate(CHANNEL_NAMES):
        val = channel_importance[idx].item()
        pct = (val / total_importance * 100.0) if total_importance > 0 else 0.0
        print(f"  {idx:<5}{name:<14}{val:>18.8f}{pct:>13.2f}%")

    for idx, name in enumerate(CHANNEL_NAMES):
        val = channel_importance[idx].item()
        assert val > MIN_GRADIENT_MAGNITUDE, (
            f"Channel {idx} ({name}) has ~zero gradient magnitude ({val:.10f}) -- "
            "this channel appears disconnected from the output (dead pathway)."
        )
        _log_pass(f"Channel {idx} ({name}): mean|grad|={val:.8f} -- gradient flows from output back to this channel.")

    _log_pass(f"All {IN_CHANNELS} channels carry non-zero gradient attribution -- no dead input pathways.")


# --------------------------------------------------------------------------- #
# Test 3: Spatial Feature Map Activation Check
# --------------------------------------------------------------------------- #

def test_3_spatial_feature_map_activation_check(model: OceanFeatureExtractorCNN, input_tensor: torch.Tensor):
    """
    Hook Stage 1/2/3 outputs and confirm each stage maintains active,
    spatially-varying feature maps (no dead layers / collapsed filters).
    """
    _log_header("TEST 3: Spatial Feature Map Activation Check")

    activations: Dict[str, torch.Tensor] = {}
    handles = []

    def _make_hook(stage_name: str):
        def _hook(_module: nn.Module, _inp: Tuple[torch.Tensor, ...], out: torch.Tensor) -> None:
            activations[stage_name] = out.detach()
        return _hook

    for stage_name, stage_module in (("Stage 1", model.stage1), ("Stage 2", model.stage2), ("Stage 3", model.stage3)):
        handles.append(stage_module.register_forward_hook(_make_hook(stage_name)))

    try:
        with torch.no_grad():
            model(input_tensor)
    finally:
        for h in handles:
            h.remove()

    assert set(activations.keys()) == {"Stage 1", "Stage 2", "Stage 3"}, (
        f"Expected hooks to fire for Stage 1/2/3, got: {list(activations.keys())}"
    )

    print(f"\n  {'Stage':<10}{'Shape':<18}{'% Zero Elems':>14}{'Dead Channels':>16}{'Spatial Var':>14}")
    print(f"  {'-' * 10}{'-' * 18}{'-' * 14}{'-' * 16}{'-' * 14}")

    for stage_name in ("Stage 1", "Stage 2", "Stage 3"):
        fmap = activations[stage_name]  # (1, C, H, W)
        _, num_channels, _, _ = fmap.shape

        total_elems = fmap.numel()
        zero_elems = (fmap == 0).sum().item()
        pct_zero_elems = zero_elems / total_elems * 100.0

        # A "dead" filter/channel: every spatial location in that channel is exactly 0.
        per_channel_all_zero = (fmap == 0).all(dim=(0, 2, 3))  # (C,)
        dead_channels = int(per_channel_all_zero.sum().item())
        dead_fraction = dead_channels / num_channels

        spatial_variance = fmap.var().item()

        print(
            f"  {stage_name:<10}{str(tuple(fmap.shape)):<18}{pct_zero_elems:>13.2f}%"
            f"{dead_channels:>10d}/{num_channels:<5d}{spatial_variance:>14.6f}"
        )

        assert dead_fraction < MAX_DEAD_CHANNEL_FRACTION, (
            f"{stage_name}: {dead_channels}/{num_channels} ({dead_fraction:.1%}) filters are fully "
            f"dead (all-zero) -- exceeds the {MAX_DEAD_CHANNEL_FRACTION:.0%} budget."
        )
        assert spatial_variance > 0.0, (
            f"{stage_name}: feature map has zero spatial variance -- activations are constant "
            "across the receptive field."
        )

        _log_pass(
            f"{stage_name}: {dead_channels}/{num_channels} dead filters "
            f"({dead_fraction:.1%}, budget {MAX_DEAD_CHANNEL_FRACTION:.0%}), "
            f"spatial variance={spatial_variance:.6f} > 0 -- stage is actively producing "
            "spatially-varying features."
        )

    _log_pass("Stage 1/2/3 all maintain live, spatially-varying activations -- no dead layers detected.")


# --------------------------------------------------------------------------- #
# Direct execution entry point (in addition to `pytest`)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
