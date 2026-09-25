"""
CNN Wrapper — Integrates the upstream OceanFeatureExtractorCNN into our pipeline.

Wraps the CNN from SIH/ocean_cnn_extractor.py so it can be imported cleanly
by the fusion module and cost model. Handles loading the CNN architecture,
optional checkpoint loading, and provides a consistent interface.

Data flow:
    ERA5 .nc files → ingestion_pipline.py → (8, 64, 64) tensor → CNN → (B, 64) z_weather
"""

import sys
import logging
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import numpy as np

logger = logging.getLogger("qml_route_search.cnn_wrapper")

# Path to the upstream CNN code
CNN_CODE_DIR = Path(__file__).resolve().parent.parent.parent / "SIH-20260816T081538Z-1-001" / "SIH"

# Inline the CNN architecture so we don't depend on sys.path manipulation at import time
IN_CHANNELS = 8
EMBED_DIM = 64


class OceanFeatureExtractorCNN(nn.Module):
    """
    4-stage CNN mapping (B, 8, 64, 64) ocean weather tensor to (B, 64) embedding.

    Architecture (from ocean_cnn_extractor.py):
        Stage 1: Conv2d(8→16) + BN + LeakyReLU(0.1) + MaxPool(2) → (16, 32, 32)
        Stage 2: Conv2d(16→32) + BN + LeakyReLU(0.1) + MaxPool(2) → (32, 16, 16)
        Stage 3: Conv2d(32→64) + BN + LeakyReLU(0.1)              → (64, 16, 16)
        Stage 4: AdaptiveAvgPool(1,1) + Flatten + Linear(64→64)   → (B, 64)

    Total trainable parameters: ~30,000
    """

    def __init__(self, in_channels: int = IN_CHANNELS, embed_dim: int = EMBED_DIM):
        super().__init__()
        self.stage1 = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.LeakyReLU(negative_slope=0.1),
            nn.MaxPool2d(2, 2),
        )
        self.stage2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(negative_slope=0.1),
            nn.MaxPool2d(2, 2),
        )
        self.stage3 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(negative_slope=0.1),
        )
        self.stage4 = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(64, embed_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, 8, 64, 64) normalized ocean weather tensor
        Returns:
            (B, 64) weather latent embedding
        """
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        return x


class CNNWeatherEncoder(nn.Module):
    """
    Production wrapper around OceanFeatureExtractorCNN.

    Provides:
    - Checkpoint loading/saving
    - Freeze/unfreeze for staged training
    - Integration with the ingestion pipeline for raw ERA5 data
    """

    def __init__(self, checkpoint_path: Optional[str] = None):
        super().__init__()
        self.cnn = OceanFeatureExtractorCNN(in_channels=IN_CHANNELS, embed_dim=EMBED_DIM)

        if checkpoint_path and Path(checkpoint_path).exists():
            ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            state_dict = ckpt["model_state"] if isinstance(ckpt, dict) and "model_state" in ckpt else ckpt
            
            # Filter out regression_head and remove "backbone." prefix
            new_state_dict = {}
            for k, v in state_dict.items():
                if k.startswith("backbone."):
                    new_state_dict[k.replace("backbone.", "")] = v
                elif not k.startswith("regression_head"):
                    new_state_dict[k] = v
                    
            self.cnn.load_state_dict(new_state_dict, strict=False)
            logger.info("CNN weights loaded from %s", checkpoint_path)
        else:
            logger.info("CNN initialized with random weights (no checkpoint)")

    def forward(self, weather_tensor: torch.Tensor) -> torch.Tensor:
        """
        Args:
            weather_tensor: (B, 8, 64, 64) normalized weather tensor
        Returns:
            (B, 64) weather embedding z_weather
        """
        return self.cnn(weather_tensor)

    def freeze(self):
        """Freeze all CNN parameters (for staged training — train MLP+Quantum only)."""
        for param in self.cnn.parameters():
            param.requires_grad = False
        self.cnn.eval()
        logger.info("CNN weights frozen")

    def unfreeze(self):
        """Unfreeze CNN parameters (for end-to-end fine-tuning)."""
        for param in self.cnn.parameters():
            param.requires_grad = True
        self.cnn.train()
        logger.info("CNN weights unfrozen")

    def save_checkpoint(self, path: str):
        """Save CNN weights."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.cnn.state_dict(), path)
        logger.info("CNN checkpoint saved to %s", path)


def build_weather_tensor_from_era5(
    oper_path: str,
    wave_path: str,
    bbox: tuple = (10.0, 20.0, 80.0, 95.0),
    cmems_path: Optional[str] = None,
    time_index: int = 0,
) -> torch.Tensor:
    """
    Run the ingestion pipeline to build an (8, 64, 64) weather tensor
    from raw ERA5 NetCDF files.

    This wraps the user's ingestion_pipline.py functionality.

    Args:
        oper_path: Path to ERA5 oper stream .nc file
        wave_path: Path to ERA5 wave stream .nc file
        bbox: (lat_min, lat_max, lon_min, lon_max)
        cmems_path: Optional CMEMS .nc file
        time_index: Which time step to use (0 = first)

    Returns:
        (8, 64, 64) FloatTensor
    """
    import xarray as xr

    GRID_SIZE = 64

    def _open_nc(path):
        for engine in ("netcdf4", "h5netcdf", "scipy"):
            try:
                with xr.open_dataset(path, engine=engine) as h:
                    return h.load()
            except Exception:
                continue
        raise RuntimeError(f"Cannot open {path}")

    def _standardize(ds):
        rename = {}
        if "latitude" in ds.coords:
            rename["latitude"] = "lat"
        if "longitude" in ds.coords:
            rename["longitude"] = "lon"
        if rename:
            ds = ds.rename(rename)

        # Handle time dimension
        for t in ("valid_time", "time"):
            if t in ds.dims and ds.sizes[t] > 1:
                ds = ds.isel({t: time_index})
                break
            elif t in ds.dims and ds.sizes[t] == 1:
                ds = ds.squeeze(t, drop=False)

        # Wrap longitudes
        lon_vals = ds["lon"].values
        if np.nanmax(lon_vals) > 180:
            ds = ds.assign_coords(lon=((ds["lon"] + 180) % 360) - 180)
        ds = ds.sortby("lat").sortby("lon")
        return ds

    def _normalize(arr, scale, clip):
        return np.clip(arr.astype(np.float32) / scale, clip[0], clip[1])

    # Load and standardize
    oper = _standardize(_open_nc(oper_path))
    wave = _standardize(_open_nc(wave_path))

    # Align grids
    if oper.sizes.get("lat") != wave.sizes.get("lat"):
        wave = wave.interp(lat=oper["lat"], lon=oper["lon"], method="nearest")
    else:
        wave = wave.assign_coords(lat=oper["lat"], lon=oper["lon"])

    merged = xr.merge([oper, wave], compat="override", join="inner")

    # Crop + regrid
    lat_min, lat_max, lon_min, lon_max = bbox
    cropped = merged.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))
    target_lats = np.linspace(lat_min, lat_max, GRID_SIZE)
    target_lons = np.linspace(lon_min, lon_max, GRID_SIZE)
    regridded = cropped.interp(lat=target_lats, lon=target_lons, method="linear").fillna(0.0)

    # Extract channels
    u10 = _normalize(regridded["u10"].values, 25.0, (-1, 1))
    v10 = _normalize(regridded["v10"].values, 25.0, (-1, 1))
    swh_name = "swh" if "swh" in regridded else "Hs"
    mwp_name = "mwp" if "mwp" in regridded else "Tm"
    mwd_name = "mwd" if "mwd" in regridded else "theta_w"
    swh = _normalize(regridded[swh_name].values, 12.0, (0, 1))
    mwp = _normalize(regridded[mwp_name].values, 18.0, (0, 1))
    mwd = _normalize(regridded[mwd_name].values, 360.0, (0, 1))

    # CMEMS placeholders
    z = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32)

    stacked = np.stack([u10, v10, swh, mwp, z, z, z, mwd], axis=0)
    return torch.from_numpy(stacked).float()
