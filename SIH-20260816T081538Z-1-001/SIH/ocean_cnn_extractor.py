"""
ocean_cnn_extractor.py
=======================

Standalone feature-extraction pipeline for the 8-channel ocean weather
tensor produced by `era5_wind_wave_to_tensor.py`.

Defines `OceanFeatureExtractorCNN`, a small 4-stage CNN that maps an
(8, 64, 64) input tensor to a 64-dimensional latent embedding, then runs
inference on a saved `ocean_weather_tensor.pt` and writes the resulting
embedding to `weather_latent_vector.pt`.

Usage
-----
    python ocean_cnn_extractor.py \\
        --input ocean_weather_tensor.pt \\
        --output weather_latent_vector.pt

Dependencies: torch.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import torch
import torch.nn as nn

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ocean_cnn_extractor")

IN_CHANNELS = 8
EMBED_DIM = 64


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

class OceanFeatureExtractorCNN(nn.Module):
    """
    4-stage convolutional feature extractor mapping an
    (Batch, 8, 64, 64) ocean-weather tensor to a (Batch, 64) latent
    embedding.

    Architecture
    ------------
    Stage 1: Conv2d(8  -> 16) -> BatchNorm2d(16) -> LeakyReLU(0.1) -> MaxPool2d(2,2)   -> (16, 32, 32)
    Stage 2: Conv2d(16 -> 32) -> BatchNorm2d(32) -> LeakyReLU(0.1) -> MaxPool2d(2,2)   -> (32, 16, 16)
    Stage 3: Conv2d(32 -> 64) -> BatchNorm2d(64) -> LeakyReLU(0.1)                     -> (64, 16, 16)
    Stage 4: AdaptiveAvgPool2d((1,1)) -> Flatten() -> Linear(64 -> 64)                 -> (Batch, 64)
    """

    def __init__(self, in_channels: int = IN_CHANNELS, embed_dim: int = EMBED_DIM) -> None:
        super().__init__()

        # Stage 1: (B, in_channels, 64, 64) -> (B, 16, 32, 32)
        self.stage1 = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.LeakyReLU(negative_slope=0.1),
            nn.MaxPool2d(2, 2),
        )

        # Stage 2: (B, 16, 32, 32) -> (B, 32, 16, 16)
        self.stage2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(negative_slope=0.1),
            nn.MaxPool2d(2, 2),
        )

        # Stage 3: (B, 32, 16, 16) -> (B, 64, 16, 16) (no pooling)
        self.stage3 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(negative_slope=0.1),
        )

        # Stage 4: (B, 64, 16, 16) -> (B, 64)
        self.stage4 = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(64, embed_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        x : torch.Tensor
            Shape (Batch_Size, in_channels, 64, 64).

        Returns
        -------
        torch.Tensor
            Shape (Batch_Size, embed_dim).
        """
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        return x


# --------------------------------------------------------------------------- #
# Parameter counting
# --------------------------------------------------------------------------- #

def count_trainable_params(model: nn.Module) -> int:
    """Return the total number of trainable (requires_grad=True) parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# --------------------------------------------------------------------------- #
# Load / validate input tensor
# --------------------------------------------------------------------------- #

def load_input_tensor(path: str, expected_channels: int = IN_CHANNELS) -> torch.Tensor:
    """
    Load the preprocessed ocean weather tensor from disk and validate
    its shape.

    Parameters
    ----------
    path : str
        Path to a `.pt` file containing a FloatTensor of shape
        (expected_channels, H, W).
    expected_channels : int
        Number of channels the model expects.

    Returns
    -------
    torch.Tensor
        The loaded tensor, unmodified (no batch dimension yet).

    Raises
    ------
    FileNotFoundError
        If `path` does not exist.
    ValueError
        If the tensor's channel dimension doesn't match `expected_channels`.
    """
    tensor_path = Path(path)
    if not tensor_path.exists():
        raise FileNotFoundError(f"Input tensor not found: {path}")

    tensor = torch.load(tensor_path, map_location="cpu")
    if not isinstance(tensor, torch.Tensor):
        raise TypeError(f"Expected a torch.Tensor in '{path}', got {type(tensor)}")

    if tensor.dim() != 3 or tensor.shape[0] != expected_channels:
        raise ValueError(
            f"Expected a tensor of shape ({expected_channels}, H, W), got {tuple(tensor.shape)}"
        )

    logger.info("Loaded input tensor '%s' with shape %s", path, tuple(tensor.shape))
    return tensor.float()


# --------------------------------------------------------------------------- #
# Save output embedding
# --------------------------------------------------------------------------- #

def save_embedding(embedding: torch.Tensor, output_path: str) -> None:
    """Save the embedding tensor to disk via `torch.save`, creating parent dirs as needed."""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(embedding, out_path)
    logger.info("Saved latent vector to '%s'", out_path)


# --------------------------------------------------------------------------- #
# Terminal validation output
# --------------------------------------------------------------------------- #

def print_validation_summary(model: nn.Module, embedding: torch.Tensor) -> None:
    """
    Print total trainable parameters, output shape, and summary
    statistics (min/max/mean/std) for the embedding, and assert it
    contains no NaN or Inf values.
    """
    n_params = count_trainable_params(model)
    print(f"\nTotal trainable parameters: {n_params:,}")
    if n_params >= 100_000:
        logger.warning("Parameter count %d is not below the 100k target.", n_params)

    print(f"Output vector shape: {tuple(embedding.shape)} -> {embedding.shape}")

    has_nan = torch.isnan(embedding).any().item()
    has_inf = torch.isinf(embedding).any().item()
    assert not has_nan, "Embedding contains NaN values!"
    assert not has_inf, "Embedding contains Inf values!"

    print("\nEmbedding summary statistics:")
    print(f"  min:  {embedding.min().item(): .6f}")
    print(f"  max:  {embedding.max().item(): .6f}")
    print(f"  mean: {embedding.mean().item(): .6f}")
    print(f"  std:  {embedding.std().item(): .6f}")
    print("  NaN check: PASSED (no NaNs found)")
    print("  Inf check: PASSED (no Infs found)\n")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run(input_path: str, output_path: str, seed: int = 42) -> torch.Tensor:
    """
    Execute the full load -> model -> inference -> save -> validate flow.

    Parameters
    ----------
    input_path : str
        Path to the (8, 64, 64) `ocean_weather_tensor.pt` file.
    output_path : str
        Where to save the resulting (1, 64) `weather_latent_vector.pt` file.
    seed : int
        Random seed for reproducible (untrained) weight initialization.

    Returns
    -------
    torch.Tensor
        The extracted (1, 64) embedding.
    """
    torch.manual_seed(seed)

    logger.info("=== Step 1: Loading input tensor ===")
    tensor = load_input_tensor(input_path, expected_channels=IN_CHANNELS)

    logger.info("=== Step 2: Adding batch dimension ===")
    batched = tensor.unsqueeze(0)  # (8, 64, 64) -> (1, 8, 64, 64)
    logger.info("Batched input shape: %s", tuple(batched.shape))

    logger.info("=== Step 3: Building model ===")
    model = OceanFeatureExtractorCNN(in_channels=IN_CHANNELS, embed_dim=EMBED_DIM)
    model.eval()

    logger.info("=== Step 4: Running inference (eval mode, no_grad) ===")
    with torch.no_grad():
        embedding = model(batched)

    logger.info("=== Step 5: Saving embedding ===")
    save_embedding(embedding, output_path)

    logger.info("=== Step 6: Validation ===")
    print_validation_summary(model, embedding)

    return embedding


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocean_cnn_extractor",
        description="Extract a 64-D latent embedding from an (8, 64, 64) ocean weather tensor.",
    )
    parser.add_argument(
        "--input", type=str, default="ocean_weather_tensor.pt",
        help="Path to the input (8, 64, 64) tensor (default: ocean_weather_tensor.pt).",
    )
    parser.add_argument(
        "--output", type=str, default="weather_latent_vector.pt",
        help="Output path for the (1, 64) embedding (default: weather_latent_vector.pt).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for model weight initialization (default: 42).",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    run(input_path=args.input, output_path=args.output, seed=args.seed)
