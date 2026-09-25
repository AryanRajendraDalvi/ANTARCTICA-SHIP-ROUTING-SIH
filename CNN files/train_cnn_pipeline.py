"""
train_cnn_pipeline.py
=====================
End-to-end PyTorch training pipeline for the OceanFeatureExtractorCNN.

The CNN converts spatial ocean/atmospheric fields (8 channels, 64x64)
into a compact 64-D latent embedding (z_weather) via supervised regression
against naval drag and fuel-cost targets.

Architecture:
  OceanFeatureExtractorCNN  ->  z_weather (B, 64)
  WeatherCostRegressor      ->  [R_wave (kN), fuel_rate (kg/NM)]

Usage
-----
# --- REAL DATA (NetCDF from Copernicus / ERA5 / CMEMS) ---
# Single .nc file containing all variables:
  python train_cnn_pipeline.py --mode train --nc_path data/ocean.nc --epochs 50

# Multiple .nc files (one per variable, or per time-step) — pass a folder:
  python train_cnn_pipeline.py --mode train --nc_path data/nc_folder/ --epochs 50

# Control patch stride (default 32 = 50% overlap):
  python train_cnn_pipeline.py --mode train --nc_path data/ocean.nc --nc_stride 64

# Use only every Nth time-step to reduce dataset size:
  python train_cnn_pipeline.py --mode train --nc_path data/ocean.nc --nc_time_step 6

# --- PRE-BUILT TENSORS ---
# Train supplying your own pre-built tensors and labels:
  python train_cnn_pipeline.py --mode train \
      --data_path ocean_weather_tensor.pt \
      --labels_path targets.pt

# --- SYNTHETIC (fallback, no real data) ---
  python train_cnn_pipeline.py --mode train --num_samples 500

# Extract 64-D latent vector from a saved tensor after training:
  python train_cnn_pipeline.py --mode extract \
      --data_path ocean_weather_tensor.pt \
      --model_weights model.pt \
      --output_path weather_latent_vector.pt

CLI Arguments
-------------
  --mode            {train, extract}            (default: train)
  -- NetCDF inputs (real data) --
  --nc_path         Path to .nc file OR folder of .nc files
  --nc_stride       Patch stride in pixels      (default: 32, i.e. 50% overlap)
  --nc_time_step    Use every Nth time-step      (default: 1 = all)
  -- Pre-built tensor inputs --
  --data_path       Path to .pt tensor of shape (N,8,64,64)
  --labels_path     Path to .pt label tensor of shape (N,2) [optional]
  -- Synthetic fallback --
  --num_samples     Samples to generate          (default: 500)
  -- Model --
  --model_weights   Weights save/load path       (default: model.pt)
  --output_path     Latent vector output path    (default: weather_latent_vector.pt)
  -- Training --
  --batch_size      Mini-batch size              (default: 16)
  --epochs          Training epochs              (default: 20)
  --lr              Adam learning rate           (default: 1e-3)
  --weight_decay    Adam weight decay            (default: 1e-4)
  --seed            Random seed                  (default: 42)
  --no_cuda         Force CPU inference/training
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ===========================================================================
# 1. MODEL DEFINITIONS
# ===========================================================================

class OceanFeatureExtractorCNN(nn.Module):
    """
    Multi-channel 2-D CNN that maps an 8-channel 64x64 ocean/atmospheric
    field to a compact 64-dimensional latent embedding z_weather.

    Input  : (B, 8, 64, 64)
    Output : (B, 64)

    Stage 1: Conv2d(8,16,3,p=1) -> BN -> LeakyReLU(0.1) -> MaxPool(2)  => (B,16,32,32)
    Stage 2: Conv2d(16,32,3,p=1) -> BN -> LeakyReLU(0.1) -> MaxPool(2) => (B,32,16,16)
    Stage 3: Conv2d(32,64,3,p=1) -> BN -> LeakyReLU(0.1)               => (B,64,16,16)
    Stage 4: AdaptiveAvgPool(1,1) -> Flatten -> Linear(64,64)           => (B,64)
    """

    def __init__(self) -> None:
        super().__init__()

        # Stage 1: (B,8,64,64) -> (B,16,32,32)
        self.stage1 = nn.Sequential(
            nn.Conv2d(8, 16, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.LeakyReLU(negative_slope=0.1, inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )

        # Stage 2: (B,16,32,32) -> (B,32,16,16)
        self.stage2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(negative_slope=0.1, inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )

        # Stage 3: (B,32,16,16) -> (B,64,16,16)
        self.stage3 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(negative_slope=0.1, inplace=True),
        )

        # Stage 4: (B,64,16,16) -> (B,64)
        self.stage4 = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(64, 64),
        )

        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(
                    m.weight, mode="fan_out", nonlinearity="leaky_relu"
                )
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        return x  # (B, 64)


class WeatherCostRegressor(nn.Module):
    """
    Wraps OceanFeatureExtractorCNN with a temporary regression head used
    only during training.

    Input  : (B, 8, 64, 64)
    Output : (B, 2)  ->  [R_wave (kN), fuel_rate (kg/NM)]
    """

    def __init__(self) -> None:
        super().__init__()
        self.backbone = OceanFeatureExtractorCNN()
        self.regression_head = nn.Sequential(
            nn.Linear(64, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, 2),
        )
        self._init_head()

    def _init_head(self) -> None:
        for m in self.regression_head.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.backbone(x)           # (B, 64)
        return self.regression_head(z) # (B, 2)

    def get_backbone(self) -> OceanFeatureExtractorCNN:
        """Return the backbone (without regression head)."""
        return self.backbone


# ===========================================================================
# 2. SYNTHETIC DATASET GENERATOR
# ===========================================================================

def _channel_spatial_mean(tensor: torch.Tensor, ch: int) -> torch.Tensor:
    """Spatial average of channel `ch` across the 64x64 grid. Shape: (N,)"""
    return tensor[:, ch, :, :].mean(dim=(-2, -1))


def generate_synthetic_dataset(
    num_samples: int = 500,
    seed: int = 42,
) -> tuple:
    """
    Build a synthetic dataset of ocean weather tensors and realistic naval
    regression targets.

    Channel layout (all values in normalised range):
        0 - u10  : east wind         [-1, 1]
        1 - v10  : north wind        [-1, 1]
        2 - swh  : sig. wave height  [ 0, 1]  => physical ~[0, 6] m
        3 - mwp  : mean wave period  [ 0, 1]  => physical ~[4, 16] s
        4 - uo   : east current      [-1, 1]
        5 - vo   : north current     [-1, 1]
        6 - ssh  : sea surface hgt   [-1, 1]
        7 - mwd  : wave direction    [ 0, 1]

    Target Labels:
        0 - R_wave     : added wave resistance (kN)
        1 - fuel_rate  : fuel consumption rate (kg/NM)

    Physics Approximations
    ----------------------
    R_wave  ~= alpha * Hs^2              (quadratic Bretschneider drag)
               Hs_physical = swh_norm * 6.0 m
               alpha = 45 kN/m^2  (representative 200 m bulk-carrier)

    fuel_rate ~= base + beta * |V_wind|^2 + gamma * R_wave
               V_wind in m/s = (u10/v10) * 15
               base   ~ U(1.8, 2.5) kg/NM
               beta   = 0.004 kg*s^2/(NM*m^2)
               gamma  = 0.012 kg/(NM*kN)
    """
    rng = torch.Generator()
    rng.manual_seed(seed)

    # Input tensors: (N, 8, 64, 64)
    X = torch.zeros(num_samples, 8, 64, 64)
    X[:, 0] = torch.empty(num_samples, 64, 64).uniform_(-1.0,  1.0, generator=rng)  # u10
    X[:, 1] = torch.empty(num_samples, 64, 64).uniform_(-1.0,  1.0, generator=rng)  # v10
    X[:, 2] = torch.empty(num_samples, 64, 64).uniform_( 0.0,  1.0, generator=rng)  # swh
    X[:, 3] = torch.empty(num_samples, 64, 64).uniform_( 0.0,  1.0, generator=rng)  # mwp
    X[:, 4] = torch.empty(num_samples, 64, 64).uniform_(-0.3,  0.3, generator=rng)  # uo
    X[:, 5] = torch.empty(num_samples, 64, 64).uniform_(-0.3,  0.3, generator=rng)  # vo
    X[:, 6] = torch.empty(num_samples, 64, 64).uniform_(-0.5,  0.5, generator=rng)  # ssh
    X[:, 7] = torch.empty(num_samples, 64, 64).uniform_( 0.0,  1.0, generator=rng)  # mwd

    # Physics-based regression targets
    swh_norm  = _channel_spatial_mean(X, 2)   # [0, 1]
    u10_norm  = _channel_spatial_mean(X, 0)   # [-1, 1]
    v10_norm  = _channel_spatial_mean(X, 1)   # [-1, 1]

    Hs_phys   = swh_norm * 6.0                # m
    u10_phys  = u10_norm * 15.0               # m/s
    v10_phys  = v10_norm * 15.0               # m/s
    V_wind_sq = u10_phys ** 2 + v10_phys ** 2 # m^2/s^2

    alpha    = 45.0
    R_wave   = alpha * (Hs_phys ** 2)          # kN

    base      = torch.empty(num_samples).uniform_(1.8, 2.5, generator=rng)
    beta      = 0.004
    gamma     = 0.012
    fuel_rate = base + beta * V_wind_sq + gamma * R_wave

    # Add mild noise to avoid a degenerate loss landscape
    R_wave    += torch.randn(num_samples, generator=rng) * 1.5
    fuel_rate += torch.randn(num_samples, generator=rng) * 0.05
    R_wave     = R_wave.clamp(min=0.0)
    fuel_rate  = fuel_rate.clamp(min=0.5)

    y = torch.stack([R_wave, fuel_rate], dim=1)  # (N, 2)

    log.info("Synthetic dataset: X %s | y %s", tuple(X.shape), tuple(y.shape))
    log.info("  R_wave    mean=%.2f kN,    std=%.2f kN",
             y[:, 0].mean().item(), y[:, 0].std().item())
    log.info("  fuel_rate mean=%.4f kg/NM, std=%.4f kg/NM",
             y[:, 1].mean().item(), y[:, 1].std().item())
    return X, y


# ===========================================================================
# 2.5  NETCDF INGESTION ENGINE  (real Copernicus / ERA5 / CMEMS data)
# ===========================================================================

# ---------------------------------------------------------------------------
# Variable name aliases
# ERA5 and CMEMS use different names for the same physical quantity.
# Each entry is (canonical_name, [alias1, alias2, …], norm_range)
# norm_range: "signed" -> [-1,1]  |  "positive" -> [0,1]
# ---------------------------------------------------------------------------
_VAR_ALIASES: list[tuple[str, list[str], str]] = [
    # Ch 0 – eastward wind
    ("u10",  ["u10", "10m_u_component_of_wind", "eastward_wind",
               "uas", "u_wind", "uwnd", "u10m"], "signed"),
    # Ch 1 – northward wind
    ("v10",  ["v10", "10m_v_component_of_wind", "northward_wind",
               "vas", "v_wind", "vwnd", "v10m"], "signed"),
    # Ch 2 – significant wave height
    ("swh",  ["swh", "VHM0", "significant_height_of_combined_wind_waves_and_swell",
               "hs", "Hs", "hwave", "VHMO", "significant_wave_height"], "positive"),
    # Ch 3 – mean wave period
    ("mwp",  ["mwp", "VTM02", "mean_wave_period", "tm02", "Tm",
               "mpts", "tm", "average_wave_period"], "positive"),
    # Ch 4 – eastward surface ocean current
    ("uo",   ["uo", "u_velocity", "u_curr", "ucurr", "vozocrtx",
               "u_eastward", "eastward_sea_water_velocity"], "signed"),
    # Ch 5 – northward surface ocean current
    ("vo",   ["vo", "v_velocity", "v_curr", "vcurr", "vomecrty",
               "v_northward", "northward_sea_water_velocity"], "signed"),
    # Ch 6 – sea surface height
    ("ssh",  ["ssh", "zos", "sea_surface_height", "sea_surface_height_above_geoid",
               "adt", "sla", "msla", "sea_surface_elevation"], "signed"),
    # Ch 7 – mean wave direction
    ("mwd",  ["mwd", "VMDR", "mean_wave_direction", "mdir",
               "theta_w", "mean_direction_of_total_swell"], "positive"),
]

# Physical ranges used for normalisation (conservative ocean-wide bounds)
_PHYS_RANGES: dict[str, tuple[float, float]] = {
    "u10": (-25.0,  25.0),   # m/s  (gale-force wind)
    "v10": (-25.0,  25.0),   # m/s
    "swh": (  0.0,  15.0),   # m    (extreme wave height)
    "mwp": (  2.0,  25.0),   # s
    "uo":  ( -2.0,   2.0),   # m/s  (surface current)
    "vo":  ( -2.0,   2.0),   # m/s
    "ssh": ( -2.0,   2.0),   # m
    "mwd": (  0.0, 360.0),   # degrees
}


def _find_var(ds, canonical: str, aliases: list[str]) -> str | None:
    """Return the first matching variable name found in dataset `ds`, or None."""
    for alias in aliases:
        if alias in ds.data_vars or alias in ds.coords:
            return alias
    return None


def _normalise_channel(
    arr: np.ndarray,
    canonical: str,
    norm_range: str,
    vmin: float,
    vmax: float,
) -> np.ndarray:
    """
    Clip to physical bounds then linearly scale.
      signed   -> [-1, 1]
      positive -> [ 0, 1]
    NaN values are filled with 0 (neutral).
    """
    arr = np.nan_to_num(arr, nan=0.0)
    arr = np.clip(arr, vmin, vmax)
    span = vmax - vmin
    if span < 1e-9:
        return np.zeros_like(arr)
    norm = (arr - vmin) / span        # [0, 1]
    if norm_range == "signed":
        norm = norm * 2.0 - 1.0       # [-1, 1]
    return norm.astype(np.float32)


def _physics_labels_from_real(
    patches: np.ndarray,             # (N, 8, 64, 64) normalised
) -> np.ndarray:                     # (N, 2)
    """
    Derive R_wave (kN) and fuel_rate (kg/NM) directly from real field values
    using the same Bretschneider physics as the synthetic generator.

    Ch 2 (swh) is in [0,1] -> Hs_physical = val * 15 m   (matches _PHYS_RANGES)
    Ch 0/1 (u10/v10) in [-1,1] -> wind_physical = val * 25 m/s
    """
    # Spatial mean per patch per channel
    swh_norm = patches[:, 2].mean(axis=(-2, -1))    # [0, 1]
    u10_norm = patches[:, 0].mean(axis=(-2, -1))    # [-1, 1]
    v10_norm = patches[:, 1].mean(axis=(-2, -1))    # [-1, 1]

    Hs_phys   = swh_norm * 15.0                     # m   (real range)
    u10_phys  = u10_norm * 25.0                     # m/s
    v10_phys  = v10_norm * 25.0                     # m/s
    V_wind_sq = u10_phys ** 2 + v10_phys ** 2       # m^2/s^2

    alpha     = 45.0                                # kN/m^2 Bretschneider
    R_wave    = alpha * (Hs_phys ** 2)

    base      = 2.15                                # kg/NM median base
    beta      = 0.004                               # kg s^2 / (NM m^2)
    gamma     = 0.012                               # kg / (NM kN)
    fuel_rate = base + beta * V_wind_sq + gamma * R_wave

    R_wave    = np.clip(R_wave,    0.0, None)
    fuel_rate = np.clip(fuel_rate, 0.5, None)
    return np.stack([R_wave, fuel_rate], axis=1).astype(np.float32)


def load_netcdf_dataset(
    nc_path: str,
    patch_size: int = 64,
    stride: int = 32,
    time_step: int = 1,
) -> tuple:
    """
    Load one or more NetCDF files and tile them into (N, 8, 64, 64) patches.

    Parameters
    ----------
    nc_path    : Path to a single .nc file, or a directory containing .nc files.
    patch_size : Spatial size of each square patch in grid cells (default 64).
    stride     : Step size between patch origins in grid cells (default 32).
                 stride == patch_size -> no overlap;
                 stride <  patch_size -> overlapping patches (more training samples).
    time_step  : Use every Nth time-step (default 1 = all time-steps).

    Returns
    -------
    X : torch.Tensor  (N, 8, 64, 64)  normalised inputs
    y : torch.Tensor  (N, 2)          physics-derived labels
    """
    try:
        import xarray as xr
    except ImportError:
        raise ImportError(
            "xarray is required for NetCDF loading: pip install xarray netCDF4"
        )

    nc_path = Path(nc_path)
    if nc_path.is_dir():
        nc_files = sorted(nc_path.glob("*.nc"))
        if not nc_files:
            raise FileNotFoundError(f"No .nc files found in directory '{nc_path}'.")
        log.info("Found %d .nc files in %s", len(nc_files), nc_path)
        ds = xr.open_mfdataset(
            [str(f) for f in nc_files],
            combine="by_coords",
            engine="netcdf4",
        )
    else:
        if not nc_path.exists():
            raise FileNotFoundError(f"NetCDF file not found: '{nc_path}'.")
        log.info("Opening NetCDF file: %s", nc_path)
        ds = xr.open_dataset(str(nc_path), engine="netcdf4")

    log.info("Dataset variables : %s", list(ds.data_vars))
    log.info("Dataset dimensions: %s", dict(ds.sizes))

    # ---- Detect time / lat / lon dimension names --------------------------
    time_dim = next((d for d in ds.sizes if d in
                     ("time", "valid_time", "t", "Times")), None)
    lat_dim  = next((d for d in ds.sizes if d in
                     ("latitude", "lat", "y", "nav_lat",
                      "rlat", "Y", "LAT")), None)
    lon_dim  = next((d for d in ds.sizes if d in
                     ("longitude", "lon", "x", "nav_lon",
                      "rlon", "X", "LON")), None)

    if lat_dim is None or lon_dim is None:
        raise ValueError(
            f"Cannot detect lat/lon dimensions. Found: {list(ds.sizes)}. "
            "Rename your dimensions to 'latitude'/'longitude' or 'lat'/'lon'."
        )

    n_lat  = ds.sizes[lat_dim]
    n_lon  = ds.sizes[lon_dim]
    n_time = ds.sizes[time_dim] if time_dim else 1
    log.info("Grid: %d lat x %d lon  |  %d time-steps  (using every %d)",
             n_lat, n_lon, n_time, time_step)

    if n_lat < patch_size or n_lon < patch_size:
        raise ValueError(
            f"Grid ({n_lat}x{n_lon}) is smaller than patch size ({patch_size}x{patch_size}). "
            "Lower --nc_stride / patch size, or use a larger domain."
        )

    # ---- Map variables to channels ----------------------------------------
    channel_arrays: list[np.ndarray | None] = [None] * 8
    missing_channels: list[str] = []

    for ch_idx, (canonical, aliases, norm_range) in enumerate(_VAR_ALIASES):
        var_name = _find_var(ds, canonical, aliases)
        if var_name is None:
            log.warning(
                "Ch %d (%s): NOT FOUND in NetCDF — filling with zeros. "
                "Available variables: %s",
                ch_idx, canonical, list(ds.data_vars),
            )
            missing_channels.append(canonical)
            channel_arrays[ch_idx] = None
            continue

        log.info("Ch %d  %-6s <- '%s'", ch_idx, canonical, var_name)
        da = ds[var_name]

        # Drop singleton depth/level dimension if present
        for extra_dim in ("depth", "level", "lev", "plev", "height",
                          "elevation", "depthv2"):
            if extra_dim in da.dims:
                da = da.isel({extra_dim: 0})

        # Load to numpy, sub-sample time axis
        if time_dim and time_dim in da.dims:
            da = da.isel({time_dim: slice(None, None, time_step)})
            arr = da.values   # (T, lat, lon)
        else:
            arr = da.values   # (lat, lon) -> expand
            arr = arr[np.newaxis]  # (1, lat, lon)

        # Make sure shape is (T, lat, lon)
        if arr.ndim == 2:
            arr = arr[np.newaxis]

        vmin, vmax = _PHYS_RANGES[canonical]
        # Normalise along time axis (each time-step independently)
        arr = _normalise_channel(arr, canonical, norm_range, vmin, vmax)
        channel_arrays[ch_idx] = arr   # (T, lat, lon)

    # Fill any missing channels with zero arrays
    t_len = next(a.shape[0] for a in channel_arrays if a is not None)
    for ch_idx, arr in enumerate(channel_arrays):
        if arr is None:
            channel_arrays[ch_idx] = np.zeros(
                (t_len, n_lat, n_lon), dtype=np.float32
            )

    # Stack -> (T, 8, lat, lon)
    full_grid = np.stack(channel_arrays, axis=1)  # (T, 8, lat, lon)
    log.info("Assembled grid: %s", full_grid.shape)

    if missing_channels:
        log.warning(
            "%d channel(s) were not found and are zero-padded: %s",
            len(missing_channels), missing_channels,
        )

    # ---- Tile into 64x64 patches ------------------------------------------
    patches: list[np.ndarray] = []
    T, C, H, W = full_grid.shape

    for t in range(T):
        for row in range(0, H - patch_size + 1, stride):
            for col in range(0, W - patch_size + 1, stride):
                patch = full_grid[t, :, row:row + patch_size, col:col + patch_size]
                patches.append(patch)

    if not patches:
        raise ValueError(
            f"No patches extracted. Grid {H}x{W} is smaller than "
            f"patch_size={patch_size}. Try --nc_stride with a smaller value."
        )

    X_np = np.stack(patches, axis=0)   # (N, 8, 64, 64)
    log.info(
        "Tiling: %d time-step(s) x %d spatial patches = %d total patches",
        T,
        len(patches) // T,
        len(patches),
    )

    # ---- Derive physics labels from real field values ----------------------
    y_np = _physics_labels_from_real(X_np)  # (N, 2)

    X = torch.from_numpy(X_np)
    y = torch.from_numpy(y_np)

    log.info("NetCDF dataset ready: X %s | y %s", tuple(X.shape), tuple(y.shape))
    log.info("  R_wave    mean=%.2f kN,    std=%.2f kN",
             y[:, 0].mean().item(), y[:, 0].std(correction=0).item())
    log.info("  fuel_rate mean=%.4f kg/NM, std=%.4f kg/NM",
             y[:, 1].mean().item(), y[:, 1].std(correction=0).item())

    ds.close()
    return X, y


# ===========================================================================
# 3. TRAINING ROUTINE
# ===========================================================================

def train(args: argparse.Namespace) -> None:
    """Full training loop with 80/20 train/val split and best-model checkpointing."""

    # Reproducibility
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    device = _get_device(args.no_cuda)
    log.info("Training device: %s", device)

    # ---- Dataset -----------------------------------------------------------
    #
    # Priority order:
    #   1. --nc_path  : real NetCDF data (Copernicus/ERA5/CMEMS) [PREFERRED]
    #   2. --data_path: pre-built .pt tensor
    #   3. synthetic   : auto-generated if neither is given
    #
    if args.nc_path:
        log.info("NetCDF mode: loading real ocean data from %s", args.nc_path)
        X, y = load_netcdf_dataset(
            nc_path=args.nc_path,
            patch_size=64,
            stride=args.nc_stride,
            time_step=args.nc_time_step,
        )
        # Labels always come from physics applied to the real fields;
        # ignore --labels_path when --nc_path is used.
        if args.labels_path:
            log.warning(
                "--labels_path is ignored when --nc_path is provided. "
                "Labels are derived from the real field values."
            )

    elif args.data_path and Path(args.data_path).exists():
        log.info("Tensor mode: loading input tensors from %s", args.data_path)
        X = torch.load(args.data_path, weights_only=True).float()
        if X.dim() == 3:
            X = X.unsqueeze(0)
        assert X.shape[1:] == (8, 64, 64), \
            f"Expected shape (N,8,64,64), got {tuple(X.shape)}"

        if args.labels_path:
            lp = Path(args.labels_path)
            if not lp.exists():
                raise FileNotFoundError(
                    f"labels_path '{lp.resolve()}' does not exist. "
                    "Provide a valid .pt file (shape (N,2)) or omit --labels_path "
                    "to use auto-generated synthetic targets."
                )
            log.info("Loading labels from %s", lp)
            y = torch.load(lp, weights_only=True).float()
            assert y.shape == (len(X), 2), \
                f"Labels must be shape ({len(X)},2), got {tuple(y.shape)}"
        else:
            log.info("No labels_path — deriving physics labels from tensor channels.")
            _, y = generate_synthetic_dataset(len(X), args.seed)

    else:
        log.info(
            "No --nc_path or --data_path given — generating %d synthetic samples.",
            args.num_samples,
        )
        X, y = generate_synthetic_dataset(args.num_samples, args.seed)

    X, y = X.float(), y.float()

    # ---- Minimum sample guard -------------------------------------------
    # Training requires at least 2 samples (1 train + 1 val).
    MIN_SAMPLES = 2
    if len(X) < MIN_SAMPLES:
        raise ValueError(
            f"Training requires at least {MIN_SAMPLES} samples, "
            f"but only {len(X)} were provided. "
            "Use --num_samples to generate a larger synthetic dataset, "
            "or supply a multi-sample data tensor."
        )

    # ---- Normalise targets (population std — safe for any N >= 1) -------
    y_mean = y.mean(dim=0)
    # correction=0 (population std) avoids NaN when N==1 or N==2
    y_std  = y.std(dim=0, correction=0).clamp(min=1e-8)
    y_norm = (y - y_mean) / y_std
    log.info("Target normalisation — mean: %s | std: %s",
             [f"{v:.4f}" for v in y_mean.tolist()],
             [f"{v:.4f}" for v in y_std.tolist()])

    dataset = TensorDataset(X, y_norm)
    # Safe split: guarantee at least 1 train sample regardless of N
    n_train = max(1, int(0.8 * len(dataset)))
    n_val   = max(1, len(dataset) - n_train)
    # If N is too small for both splits, duplicate the single sample for val
    if n_train + n_val > len(dataset):
        n_train = len(dataset)
        n_val   = 0  # skip validation for tiny datasets
        log.warning(
            "Dataset too small for an 80/20 split (%d sample(s)). "
            "Validation disabled — training on all samples.", len(dataset)
        )
        train_ds = dataset
        val_ds   = None
    else:
        train_ds, val_ds = random_split(
            dataset, [n_train, n_val],
            generator=torch.Generator().manual_seed(args.seed),
        )
    log.info("Split -> train: %d samples | val: %s samples",
             n_train, n_val if val_ds is not None else "N/A (disabled)")

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        drop_last=False, num_workers=0,
    )
    val_loader = (
        DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                   drop_last=False, num_workers=0)
        if val_ds is not None else None
    )

    # ---- Model / Optimiser / Scheduler / Loss ------------------------------
    model     = WeatherCostRegressor().to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=3
    )

    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    log.info("Trainable parameters: {:,}".format(total_params))

    # ---- Training Loop -----------------------------------------------------
    best_val_loss = float("inf")
    best_epoch    = 0
    weights_path  = Path(args.model_weights)

    log.info("=" * 65)
    log.info("Starting training  |  epochs=%d  batch=%d  lr=%.0e",
             args.epochs, args.batch_size, args.lr)
    log.info("=" * 65)

    for epoch in range(1, args.epochs + 1):

        # -- Train -----------------------------------------------------------
        model.train()
        train_loss_sum = 0.0
        for X_b, y_b in train_loader:
            X_b, y_b = X_b.to(device), y_b.to(device)
            optimizer.zero_grad()
            loss = criterion(model(X_b), y_b)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            train_loss_sum += loss.item() * len(X_b)

        train_loss = train_loss_sum / n_train

        # -- Validate --------------------------------------------------------
        val_loss   = float("nan")
        if val_loader is not None:
            model.eval()
            val_loss_sum = 0.0
            with torch.no_grad():
                for X_b, y_b in val_loader:
                    X_b, y_b = X_b.to(device), y_b.to(device)
                    val_loss_sum += criterion(model(X_b), y_b).item() * len(X_b)
            val_loss = val_loss_sum / n_val

        current_lr = optimizer.param_groups[0]["lr"]
        if val_loader is not None:
            scheduler.step(val_loss)

        # -- Checkpoint ------------------------------------------------------
        tag = ""
        if val_loader is None:
            # No validation: save every epoch (overwrite; keep latest)
            torch.save(
                {
                    "epoch":       epoch,
                    "model_state": model.state_dict(),
                    "val_loss":    float("nan"),
                    "y_mean":      y_mean,
                    "y_std":       y_std,
                },
                weights_path,
            )
            tag = "  <- saved"
        elif val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch    = epoch
            torch.save(
                {
                    "epoch":       epoch,
                    "model_state": model.state_dict(),
                    "val_loss":    val_loss,
                    "y_mean":      y_mean,
                    "y_std":       y_std,
                },
                weights_path,
            )
            tag = "  <- best"

        val_str = f"{val_loss:.6f}" if not (val_loss != val_loss) else "   N/A  "
        log.info(
            "Epoch [%3d/%d]  train_loss: %.6f  val_loss: %s  lr: %.2e%s",
            epoch, args.epochs, train_loss, val_str, current_lr, tag,
        )

    log.info("=" * 65)
    log.info("Training complete.  Best val_loss: %.6f  (epoch %d)",
             best_val_loss, best_epoch)
    log.info("Weights saved -> %s", weights_path.resolve())
    log.info("=" * 65)


# ===========================================================================
# 4. EXTRACTION UTILITY
# ===========================================================================

def extract_trained_vector(
    input_path: str,
    model_weights_path: str = "model.pt",
    output_path: str = "weather_latent_vector.pt",
    no_cuda: bool = False,
) -> torch.Tensor:
    """
    Load the trained CNN backbone (regression head is discarded), run a
    forward pass over the input tensor, and save the 64-D latent embedding.

    Parameters
    ----------
    input_path          : Path to a .pt tensor, shape (1,8,64,64) or (8,64,64).
    model_weights_path  : Path to the checkpoint saved by the training routine.
    output_path         : Destination for z_weather (shape (1,64)).
    no_cuda             : Force CPU inference.

    Returns
    -------
    z_weather : torch.Tensor of shape (1, 64)
    """
    device = _get_device(no_cuda)
    log.info("Extraction device: %s", device)

    # Load checkpoint
    ckpt_path = Path(model_weights_path)
    if not ckpt_path.exists():
        raise FileNotFoundError(
            f"Model weights not found at '{ckpt_path.resolve()}'. "
            "Run --mode train first."
        )
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    log.info("Checkpoint loaded  |  epoch=%d  val_loss=%.6f",
             ckpt.get("epoch", -1), ckpt.get("val_loss", float("nan")))

    # Rebuild full model, load weights, then keep only backbone
    full_model = WeatherCostRegressor()
    full_model.load_state_dict(ckpt["model_state"])
    backbone = full_model.get_backbone().to(device)
    backbone.eval()

    # Load input tensor
    in_path = Path(input_path)
    if not in_path.exists():
        raise FileNotFoundError(f"Input tensor not found: '{in_path.resolve()}'")

    X = torch.load(in_path, weights_only=True).float()
    if X.dim() == 3:
        X = X.unsqueeze(0)
    if X.shape[0] > 1:
        log.warning("Input has %d samples — using only the first for extraction.",
                    X.shape[0])
        X = X[:1]

    assert X.shape == (1, 8, 64, 64), \
        f"Expected shape (1,8,64,64), got {tuple(X.shape)}"
    X = X.to(device)

    # Forward pass (eval, no_grad)
    with torch.no_grad():
        z_weather = backbone(X)   # (1, 64)

    assert z_weather.shape == (1, 64), \
        f"Unexpected output shape {tuple(z_weather.shape)}"

    # Persist
    out_path = Path(output_path)
    torch.save(z_weather.cpu(), out_path)
    log.info("z_weather saved -> %s  shape=%s",
             out_path.resolve(), tuple(z_weather.shape))
    log.info("z_weather stats | min=%.4f  max=%.4f  mean=%.4f  std=%.4f",
             z_weather.min().item(), z_weather.max().item(),
             z_weather.mean().item(), z_weather.std().item())

    return z_weather.cpu()


# ===========================================================================
# 5. HELPERS
# ===========================================================================

def _get_device(no_cuda: bool = False) -> torch.device:
    if not no_cuda and torch.cuda.is_available():
        return torch.device("cuda")
    if not no_cuda and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _print_model_summary(model: nn.Module) -> None:
    """Print a concise per-layer trainable-parameter summary."""
    print("\n-- Model Architecture " + "-" * 44)
    for name, param in model.named_parameters():
        if param.requires_grad:
            print(f"  {name:<52s}  {str(list(param.shape)):<22s}  "
                  f"{param.numel():>8,d}")
    total = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  {'TOTAL':<52s}  {'':22s}  {total:>8,d}")
    print("-" * 72 + "\n")


# ===========================================================================
# 6. CLI
# ===========================================================================

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OceanFeatureExtractorCNN — Training & Extraction Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode", choices=["train", "extract"], default="train",
        help="'train' the CNN or 'extract' a latent vector.",
    )

    # Data
    g = parser.add_argument_group("Data — NetCDF (real data, preferred)")
    g.add_argument(
        "--nc_path", type=str, default=None,
        help="Path to a .nc file OR a directory of .nc files (Copernicus/ERA5/CMEMS).",
    )
    g.add_argument(
        "--nc_stride", type=int, default=32,
        help="Patch stride in pixels. 32=50%% overlap (more patches). 64=no overlap.",
    )
    g.add_argument(
        "--nc_time_step", type=int, default=1,
        help="Use every Nth time-step (1=all, 6=every 6th, etc.).",
    )

    g = parser.add_argument_group("Data — Pre-built tensors")
    g.add_argument("--data_path",   type=str, default=None,
                   help="Input tensor .pt file, shape (N,8,64,64).")
    g.add_argument("--labels_path", type=str, default=None,
                   help="Label tensor .pt file, shape (N,2). Train mode only.")
    g.add_argument("--num_samples", type=int, default=500,
                   help="Synthetic samples to generate when no nc_path/data_path given.")

    # Model
    g = parser.add_argument_group("Model")
    g.add_argument("--model_weights", type=str, default="model.pt",
                   help="Save (train) / load (extract) model weights path.")
    g.add_argument("--output_path",   type=str, default="weather_latent_vector.pt",
                   help="Destination for extracted 64-D vector. Extract mode only.")

    # Training hyper-parameters
    g = parser.add_argument_group("Training")
    g.add_argument("--batch_size",   type=int,   default=16)
    g.add_argument("--epochs",       type=int,   default=20)
    g.add_argument("--lr",           type=float, default=1e-3)
    g.add_argument("--weight_decay", type=float, default=1e-4)
    g.add_argument("--seed",         type=int,   default=42)
    g.add_argument("--no_cuda",      action="store_true",
                   help="Disable CUDA/MPS and force CPU.")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    log.info("OceanFeatureExtractorCNN Pipeline  |  mode=%s", args.mode)

    if args.mode == "train":
        _print_model_summary(WeatherCostRegressor())
        train(args)

    elif args.mode == "extract":
        if not args.data_path:
            log.error("--data_path is required for extract mode.")
            sys.exit(1)
        extract_trained_vector(
            input_path=args.data_path,
            model_weights_path=args.model_weights,
            output_path=args.output_path,
            no_cuda=args.no_cuda,
        )


if __name__ == "__main__":
    main()
