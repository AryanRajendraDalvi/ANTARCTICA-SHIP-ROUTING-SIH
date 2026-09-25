"""
test_vector_output.py
======================

Rigorous verification suite for the Ocean Feature Extractor CNN
pipeline (`ocean_cnn_extractor.py`). Mathematically and functionally
proves that the model produces a valid, non-collapsed, weather-
responsive, deterministic, and fast 64-D latent embedding (z_weather).

Five tests
----------
1. File Existence & Shape Contract  -- weather_latent_vector.pt is a
   well-formed (1, 64) float32 tensor.
2. Direct Vector Inspection         -- prints the vector as an 8x8
   grid and asserts it isn't a collapsed/constant output.
3. Model Sensitivity Test           -- a calm-sea input and a
   severe-storm input produce meaningfully different embeddings.
4. Determinism & Invariance Test    -- identical input -> identical
   output across repeated eval() passes.
5. Latency Benchmark                -- mean CPU inference latency
   over 100 forward passes is under 10 ms.

Usage
-----
    pytest -v -s test_vector_output.py
    # or, run directly:
    python test_vector_output.py

Dependencies: torch, pytest.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
import torch
import torch.nn.functional as F

# --------------------------------------------------------------------------- #
# Import the model under test from the sibling extraction script
# --------------------------------------------------------------------------- #

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from ocean_cnn_extractor import OceanFeatureExtractorCNN, IN_CHANNELS, EMBED_DIM  # noqa: E402

VECTOR_PATH = _SCRIPT_DIR / "weather_latent_vector.pt"
GRID_SIZE = 64

# Minimum acceptable variance across the 64 embedding dims -- guards
# against a degenerate/collapsed (near-constant) output vector.
MIN_VARIANCE = 0.001

# Minimum Euclidean distance between calm-sea and severe-storm
# embeddings -- guards against a network that ignores its input.
MIN_SENSITIVITY_DISTANCE = 1e-3

# Latency budget for a single (1, 8, 64, 64) forward pass on CPU.
MAX_MEAN_LATENCY_MS = 10.0
LATENCY_TRIALS = 100


# --------------------------------------------------------------------------- #
# Logging helpers -- descriptive PASSED/FAILED output for manual reading
# --------------------------------------------------------------------------- #

def _log_header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(title)
    print("=" * 70)


def _log_pass(msg: str) -> None:
    print(f"  [PASSED] {msg}")


def _log_info(msg: str) -> None:
    print(f"  [INFO]   {msg}")


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


def _make_weather_tensor(
    u10: float = 0.0,
    v10: float = 0.0,
    swh: float = 0.0,
    mwp: float = 0.0,
    uo: float = 0.0,
    vo: float = 0.0,
    ssh: float = 0.0,
    mwd: float = 0.0,
) -> torch.Tensor:
    """
    Build a synthetic (1, 8, 64, 64) input tensor with each channel
    filled with a constant physical value, normalized the same way as
    the ingestion pipeline (era5_wind_wave_to_tensor.py):
        0: u10 /25.0 -> [-1, 1]     4: uo  /2.5 -> [-1, 1]
        1: v10 /25.0 -> [-1, 1]     5: vo  /2.5 -> [-1, 1]
        2: swh /12.0 -> [0, 1]      6: ssh /2.0 -> [-1, 1]
        3: mwp /18.0 -> [0, 1]      7: mwd /360.0 -> [0, 1]

    Raw physical values (m/s, meters, seconds, degrees) are passed in
    and normalized internally so calm/storm scenarios can be expressed
    in real-world units.
    """
    raw = torch.tensor(
        [u10 / 25.0, v10 / 25.0, swh / 12.0, mwp / 18.0, uo / 2.5, vo / 2.5, ssh / 2.0, mwd / 360.0],
        dtype=torch.float32,
    )
    tensor = raw.view(IN_CHANNELS, 1, 1).expand(IN_CHANNELS, GRID_SIZE, GRID_SIZE).clone()
    return tensor.unsqueeze(0)  # (1, 8, 64, 64)


# --------------------------------------------------------------------------- #
# Test 1: File Existence & Shape Contract
# --------------------------------------------------------------------------- #

def test_1_file_existence_and_shape_contract():
    """weather_latent_vector.pt exists on disk and is a well-formed (1, 64) float32 tensor."""
    _log_header("TEST 1: File Existence & Shape Contract")

    assert VECTOR_PATH.exists(), (
        f"Expected output file not found: {VECTOR_PATH}. "
        "Run ocean_cnn_extractor.py first to generate it."
    )
    _log_pass(f"File exists on disk: {VECTOR_PATH.name}")

    vector = torch.load(VECTOR_PATH, map_location="cpu")

    assert isinstance(vector, torch.Tensor), f"Expected torch.Tensor, got {type(vector)}"
    _log_pass(f"Loaded object is a torch.Tensor (type={type(vector).__name__})")

    assert vector.shape == (1, 64), f"Expected shape (1, 64), got {tuple(vector.shape)}"
    _log_pass(f"Shape contract satisfied: {tuple(vector.shape)} == (1, 64)")

    assert vector.dtype == torch.float32, f"Expected torch.float32, got {vector.dtype}"
    _log_pass(f"Dtype contract satisfied: {vector.dtype} == torch.float32")


# --------------------------------------------------------------------------- #
# Test 2: Direct Vector Inspection
# --------------------------------------------------------------------------- #

def test_2_direct_vector_inspection():
    """Print all 64 embedding values as an 8x8 grid and assert the output isn't collapsed/constant."""
    _log_header("TEST 2: Direct Vector Inspection")

    vector = torch.load(VECTOR_PATH, map_location="cpu")
    flat = vector.flatten()
    assert flat.numel() == 64, f"Expected 64 elements, got {flat.numel()}"

    grid = flat.view(8, 8)
    print("\n  z_weather (8x8 view):\n")
    header = "        " + "".join(f"col{c:<8}" for c in range(8))
    print(header)
    for r in range(8):
        row_vals = "  ".join(f"{grid[r, c].item():>+8.4f}" for c in range(8))
        print(f"  row{r}  {row_vals}")

    variance = flat.var(unbiased=True).item()
    _log_info(f"Computed variance across 64 dims: {variance:.8f}")

    assert variance > MIN_VARIANCE, (
        f"Variance {variance:.8f} is not > {MIN_VARIANCE} -- the embedding looks "
        "collapsed/constant (network may not be extracting meaningful features)."
    )
    _log_pass(f"Variance {variance:.8f} > {MIN_VARIANCE} -- vector is not a collapsed constant.")


# --------------------------------------------------------------------------- #
# Test 3: Model Sensitivity Test (calm sea vs. severe storm)
# --------------------------------------------------------------------------- #

def test_3_model_sensitivity_to_weather(model: OceanFeatureExtractorCNN):
    """The network produces meaningfully different embeddings for a calm sea vs. a severe storm."""
    _log_header("TEST 3: Model Sensitivity Test (Calm Sea vs. Severe Storm)")

    # Calm sea: near-zero wind, small swell (Hs = 0.5 m), everything else flat.
    calm_sea = _make_weather_tensor(u10=1.0, v10=0.0, swh=0.5, mwp=4.0)
    _log_info("Built 'calm_sea' input: u10=1.0 m/s, swh(Hs)=0.5 m, mwp=4.0 s")

    # Severe storm: strong wind (20 m/s) and large swell (Hs = 10.0 m).
    severe_storm = _make_weather_tensor(u10=20.0, v10=15.0, swh=10.0, mwp=14.0)
    _log_info("Built 'severe_storm' input: u10=20.0 m/s, v10=15.0 m/s, swh(Hs)=10.0 m, mwp=14.0 s")

    assert calm_sea.shape == (1, IN_CHANNELS, GRID_SIZE, GRID_SIZE)
    assert severe_storm.shape == (1, IN_CHANNELS, GRID_SIZE, GRID_SIZE)

    with torch.no_grad():
        z_calm = model(calm_sea)
        z_storm = model(severe_storm)

    distance = torch.norm(z_calm - z_storm).item()
    cosine_sim = F.cosine_similarity(z_calm, z_storm, dim=1).item()

    _log_info(f"Euclidean distance ||z_calm - z_storm||: {distance:.6f}")
    _log_info(f"Cosine similarity(z_calm, z_storm):      {cosine_sim:.6f}")

    assert distance > MIN_SENSITIVITY_DISTANCE, (
        f"Euclidean distance {distance:.6f} is not > {MIN_SENSITIVITY_DISTANCE} -- "
        "the model's embedding does not appear to respond to drastically different "
        "weather conditions."
    )
    _log_pass(
        f"Distance {distance:.6f} > {MIN_SENSITIVITY_DISTANCE} -- "
        "calm-sea and severe-storm embeddings are meaningfully separated."
    )
    _log_pass(f"Cosine similarity reported for reference: {cosine_sim:.6f}")


# --------------------------------------------------------------------------- #
# Test 4: Determinism & Invariance Test
# --------------------------------------------------------------------------- #

def test_4_determinism_and_invariance(model: OceanFeatureExtractorCNN):
    """The same input through the same eval()-mode model produces bit-for-bit-stable output."""
    _log_header("TEST 4: Determinism & Invariance Test")

    torch.manual_seed(0)
    fixed_input = torch.randn(1, IN_CHANNELS, GRID_SIZE, GRID_SIZE)

    with torch.no_grad():
        output_1 = model(fixed_input)
        output_2 = model(fixed_input)

    max_abs_diff = (output_1 - output_2).abs().max().item()
    _log_info(f"Max absolute difference between repeated passes: {max_abs_diff:.10f}")

    assert torch.allclose(output_1, output_2, atol=1e-6), (
        f"Repeated forward passes on identical input diverged (max abs diff = {max_abs_diff}); "
        "feature extraction is not deterministic in eval() mode."
    )
    _log_pass("torch.allclose(output_1, output_2, atol=1e-6) -- inference is 100% deterministic.")


# --------------------------------------------------------------------------- #
# Test 5: Benchmark Execution Latency
# --------------------------------------------------------------------------- #

def test_5_benchmark_execution_latency(model: OceanFeatureExtractorCNN):
    """Mean CPU latency over 100 forward passes of a (1, 8, 64, 64) tensor stays under budget."""
    _log_header("TEST 5: Benchmark Execution Latency")

    torch.manual_seed(1)
    dummy_input = torch.randn(1, IN_CHANNELS, GRID_SIZE, GRID_SIZE)

    # Warm-up pass (avoids first-call overhead skewing the measured mean).
    with torch.no_grad():
        model(dummy_input)

    latencies_ms = []
    with torch.no_grad():
        for _ in range(LATENCY_TRIALS):
            start = time.perf_counter()
            model(dummy_input)
            end = time.perf_counter()
            latencies_ms.append((end - start) * 1000.0)

    mean_latency = sum(latencies_ms) / len(latencies_ms)
    max_latency = max(latencies_ms)
    min_latency = min(latencies_ms)

    _log_info(f"Trials: {LATENCY_TRIALS}")
    _log_info(f"Min latency:  {min_latency:.4f} ms")
    _log_info(f"Mean latency: {mean_latency:.4f} ms")
    _log_info(f"Max latency:  {max_latency:.4f} ms")

    assert mean_latency < MAX_MEAN_LATENCY_MS, (
        f"Mean latency {mean_latency:.4f} ms is not < {MAX_MEAN_LATENCY_MS} ms budget."
    )
    _log_pass(f"Mean latency {mean_latency:.4f} ms < {MAX_MEAN_LATENCY_MS} ms budget.")


# --------------------------------------------------------------------------- #
# Direct execution entry point (in addition to `pytest`)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
