"""
era5_wind_wave_to_tensor.py
============================

Merges ERA5 NetCDF extracts -- an "oper" stream file (10m wind: u10,
v10) and a "wave" stream file (significant wave height / mean wave
period / mean wave direction: swh, mwp, mwd) -- with an optional CMEMS
ocean-currents/SSH file (uo, vo, zos), crops and regrids everything
onto a shared 64x64 lat/lon mesh, normalizes each physical channel, and
stacks the result into a PyTorch FloatTensor of shape (8, 64, 64).

Channel layout:
    0: u10  (ERA5 oper)              /25.0  -> [-1, 1]
    1: v10  (ERA5 oper)              /25.0  -> [-1, 1]
    2: swh / Hs (ERA5 wave)          /12.0  -> [0, 1]
    3: mwp / Tm (ERA5 wave)          /18.0  -> [0, 1]
    4: uo   (CMEMS, or 0 placeholder) /2.5  -> [-1, 1]
    5: vo   (CMEMS, or 0 placeholder) /2.5  -> [-1, 1]
    6: SSH / zos (CMEMS, or 0 placeholder) /2.0 -> [-1, 1]
    7: mwd / theta_w (ERA5 wave)     /360.0 -> [0, 1]

If no `--cmems` file is supplied, channels 4-6 are zero-filled
placeholders until a CMEMS source is wired in.

ECMWF's newer download format splits a single request across multiple
files by `stream` and `stepType`, e.g.:
    data_stream-oper_stepType-instant.nc   (u10, v10, ...)
    data_stream-wave_stepType-instant.nc   (swh, mwp, mwd, ...)
and commonly uses `valid_time`/`latitude`/`longitude` coordinate names
rather than the shorter `time`/`lat`/`lon` -- this script normalizes
both. CMEMS extracts are normalized the same way.

Usage
-----
# Single time-step (inference tensor):
    python ingestion_pipline.py

# ALL time-steps -> training tensor (N, 8, 64, 64) + labels (N, 2):
    python ingestion_pipline.py --all_timesteps

# Custom bounding box:
    python ingestion_pipline.py --all_timesteps --bbox 5.0,25.0,65.0,100.0

Dependencies: xarray, numpy, torch, and a NetCDF backend (netCDF4 and/or
h5netcdf).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import xarray as xr

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("era5_wind_wave_to_tensor")

BoundingBox = Tuple[float, float, float, float]
"""(lat_min, lat_max, lon_min, lon_max), longitudes in [-180, 180)."""

GRID_SIZE = 64


# --------------------------------------------------------------------------- #
# Step 1: Open files
# --------------------------------------------------------------------------- #

def open_dataset_safely(path: str) -> xr.Dataset:
    """
    Open a NetCDF file with `xr.open_dataset`, trying multiple backends,
    and fully load it into memory so the file handle can be released.

    Parameters
    ----------
    path : str
        Path to a `.nc` file.

    Returns
    -------
    xr.Dataset
        Fully materialized dataset.

    Raises
    ------
    FileNotFoundError
        If `path` does not exist.
    RuntimeError
        If no available engine could open the file.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"NetCDF file not found: {path}")

    last_error: Optional[Exception] = None
    for engine in ("netcdf4", "h5netcdf", "scipy"):
        try:
            with xr.open_dataset(file_path, engine=engine) as handle:
                ds = handle.load()
            logger.info("Opened '%s' via engine='%s'", path, engine)
            logger.info("  Coordinates: %s", list(ds.coords))
            logger.info("  Dimensions: %s", dict(ds.sizes))
            logger.info("  Data variables: %s", list(ds.data_vars))
            return ds
        except Exception as exc:  # noqa: BLE001 - trying multiple engines deliberately
            last_error = exc
            continue

    raise RuntimeError(f"Could not open '{path}' with any NetCDF engine. Last error: {last_error}")


# --------------------------------------------------------------------------- #
# Step 2: Time-dimension inspection + slicing
# --------------------------------------------------------------------------- #

def slice_first_timestep(ds: xr.Dataset) -> xr.Dataset:
    """
    Inspect a dataset for a time-like dimension and slice to its first
    timestep, if present.

    ECMWF's newer NetCDF exports frequently use `valid_time` instead of
    `time` (and sometimes carry a `time` "forecast reference time"
    scalar alongside it), so both names are checked. Any remaining
    singleton dimensions (e.g. `expver`, `number`) are squeezed out too.

    Parameters
    ----------
    ds : xr.Dataset

    Returns
    -------
    xr.Dataset
        Dataset with the time dimension collapsed to `time=0` (if it
        existed) and singleton dimensions squeezed away.
    """
    time_candidates = ("time", "valid_time")
    time_dim = next((t for t in time_candidates if t in ds.dims), None)

    if time_dim is not None:
        n_steps = ds.sizes[time_dim]
        logger.info("Found time dimension '%s' with %d step(s); selecting index 0.", time_dim, n_steps)
        ds = ds.isel({time_dim: 0})
    else:
        logger.info("No time-like dimension found among %s; skipping time slicing.", time_candidates)

    squeezable = [d for d, size in ds.sizes.items() if size == 1]
    if squeezable:
        logger.info("Squeezing singleton dimensions: %s", squeezable)
        ds = ds.squeeze(dim=squeezable, drop=False)

    return ds


# --------------------------------------------------------------------------- #
# Step 3: Coordinate standardization + merge
# --------------------------------------------------------------------------- #

def standardize_coords(ds: xr.Dataset) -> xr.Dataset:
    """
    Rename latitude/longitude coordinate aliases to `lat`/`lon`, wrap
    longitudes from [0, 360) to [-180, 180), and sort both axes
    ascending so the two sources can be merged and interpolated
    predictably.

    Parameters
    ----------
    ds : xr.Dataset

    Returns
    -------
    xr.Dataset
        Dataset with coordinates named `lat`/`lon`, longitudes in
        [-180, 180), sorted ascending.
    """
    rename_map: Dict[str, str] = {}
    if "lat" not in ds.coords:
        for alias in ("latitude", "y", "Latitude"):
            if alias in ds.coords:
                rename_map[alias] = "lat"
                break
    if "lon" not in ds.coords:
        for alias in ("longitude", "x", "Longitude"):
            if alias in ds.coords:
                rename_map[alias] = "lon"
                break
    if rename_map:
        ds = ds.rename(rename_map)

    if "lat" not in ds.coords or "lon" not in ds.coords:
        raise KeyError(f"Could not find lat/lon coordinates. Available coords: {list(ds.coords)}")

    lon_vals = ds["lon"].values
    if np.nanmax(lon_vals) > 180.0:
        ds = ds.assign_coords(lon=((ds["lon"] + 180.0) % 360.0) - 180.0)

    ds = ds.sortby("lon").sortby("lat")
    return ds


def _align_and_merge(base_ds: xr.Dataset, other_ds: xr.Dataset, base_name: str, other_name: str) -> xr.Dataset:
    """
    Align `other_ds` onto `base_ds`'s lat/lon grid and merge them into a
    single `xr.Dataset`.

    Source files (ERA5 oper/wave streams, CMEMS extracts) are frequently
    exported on very slightly different lat/lon grids -- either
    genuinely different resolutions, or (more commonly) the *same*
    resolution/extent but with tiny floating-point coordinate offsets
    from separate extraction jobs (e.g. 9.0000000 vs 9.0000001).
    `xr.merge` performs *exact* coordinate matching, so either case can
    silently produce an empty result if not handled explicitly --
    `np.allclose`-style "close enough" grids are NOT automatically
    merge-compatible.

    Three cases are therefore handled explicitly:
    - Same shape AND coordinates already exactly equal: merge directly.
    - Same shape but coordinates only approximately equal (float
      precision drift): snap `other_ds`'s lat/lon onto `base_ds`'s
      exact coordinate values via `assign_coords` (no resampling
      needed -- these are the same physical grid points).
    - Different shape (genuinely different resolution/extent): regrid
      `other_ds` onto `base_ds`'s grid via nearest-neighbor
      interpolation before merging.

    Parameters
    ----------
    base_ds : xr.Dataset
        Standardized dataset whose grid is treated as the reference.
    other_ds : xr.Dataset
        Standardized dataset to align onto `base_ds`'s grid.
    base_name, other_name : str
        Human-readable labels for logging only.

    Returns
    -------
    xr.Dataset
        Single dataset containing all variables from both sources, with
        lat/lon exactly shared so no cells are lost during Step 4's
        cropping/regridding.
    """
    same_shape = (
        base_ds.sizes.get("lat") == other_ds.sizes.get("lat")
        and base_ds.sizes.get("lon") == other_ds.sizes.get("lon")
    )

    if same_shape:
        lat_exact = np.array_equal(base_ds["lat"].values, other_ds["lat"].values)
        lon_exact = np.array_equal(base_ds["lon"].values, other_ds["lon"].values)
        if lat_exact and lon_exact:
            logger.info("%s and %s grids are identical; merging directly.", base_name, other_name)
        else:
            logger.info(
                "%s and %s grids share shape but differ by floating-point precision; "
                "snapping %s coordinates onto the %s grid's exact values.",
                base_name, other_name, other_name, base_name,
            )
            other_ds = other_ds.assign_coords(lat=base_ds["lat"], lon=base_ds["lon"])
    else:
        logger.info(
            "%s and %s grids differ in shape; regridding %s onto the %s grid (nearest-neighbor).",
            base_name, other_name, other_name, base_name,
        )
        other_ds = other_ds.interp(lat=base_ds["lat"], lon=base_ds["lon"], method="nearest")

    merged = xr.merge([base_ds, other_ds], compat="override", join="inner")
    if merged.sizes.get("lat", 0) == 0 or merged.sizes.get("lon", 0) == 0:
        raise ValueError(
            f"Merging {base_name} and {other_name} datasets produced an empty lat/lon grid. "
            "This should not happen after grid alignment -- check that both files "
            "genuinely cover overlapping geography."
        )
    logger.info("Merged dataset variables: %s", list(merged.data_vars))
    return merged


def merge_sources(oper_ds: xr.Dataset, wave_ds: xr.Dataset, cmems_ds: Optional[xr.Dataset] = None) -> xr.Dataset:
    """
    Merge the standardized ERA5 "oper" (wind) and "wave" datasets, and
    optionally a standardized CMEMS (currents/SSH) dataset, into a
    single `xr.Dataset` aligned on shared `lat`/`lon` coordinates.

    Parameters
    ----------
    oper_ds : xr.Dataset
        Standardized wind dataset (u10, v10).
    wave_ds : xr.Dataset
        Standardized wave dataset (swh, mwp, mwd).
    cmems_ds : Optional[xr.Dataset]
        Standardized CMEMS dataset (uo, vo, zos), if available. When
        `None`, channels 4-6 are zero-filled downstream in
        `build_tensor`.

    Returns
    -------
    xr.Dataset
        Single dataset containing all variables from every supplied
        source, with lat/lon exactly shared so no cells are lost during
        Step 4's cropping/regridding.
    """
    merged = _align_and_merge(oper_ds, wave_ds, "oper", "wave")
    if cmems_ds is not None:
        merged = _align_and_merge(merged, cmems_ds, "oper+wave", "cmems")
    return merged


# --------------------------------------------------------------------------- #
# Step 4: Crop + bilinear regrid to the standardized 64x64 mesh
# --------------------------------------------------------------------------- #

def crop_to_bbox(ds: xr.Dataset, bbox: BoundingBox) -> xr.Dataset:
    """
    Crop a standardized, merged dataset to a bounding box.

    Parameters
    ----------
    ds : xr.Dataset
    bbox : BoundingBox
        (lat_min, lat_max, lon_min, lon_max) in degrees.

    Returns
    -------
    xr.Dataset
        Spatially cropped dataset.

    Raises
    ------
    ValueError
        If the crop produces an empty region (bbox doesn't overlap the
        dataset's extent).
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    cropped = ds.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))
    if cropped.sizes.get("lat", 0) == 0 or cropped.sizes.get("lon", 0) == 0:
        raise ValueError(
            f"Bounding box {bbox} produced an empty crop. "
            f"Dataset extent: lat [{float(ds['lat'].min())}, {float(ds['lat'].max())}], "
            f"lon [{float(ds['lon'].min())}, {float(ds['lon'].max())}]."
        )
    return cropped


def regrid_bilinear(ds: xr.Dataset, bbox: BoundingBox, grid_size: int = GRID_SIZE) -> xr.Dataset:
    """
    Bilinearly interpolate a cropped dataset onto a regular `grid_size` x
    `grid_size` lat/lon mesh spanning the bbox, using `xr.Dataset.interp`
    (linear interpolation on a regular 2-D grid is bilinear).

    Parameters
    ----------
    ds : xr.Dataset
        Cropped dataset.
    bbox : BoundingBox
        (lat_min, lat_max, lon_min, lon_max) defining the target mesh extent.
    grid_size : int
        Output grid resolution along each spatial axis.

    Returns
    -------
    xr.Dataset
        Dataset regridded to shape (grid_size, grid_size) for every
        variable, dims (lat, lon).
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    target_lats = np.linspace(lat_min, lat_max, grid_size)
    target_lons = np.linspace(lon_min, lon_max, grid_size)
    regridded = ds.interp(lat=target_lats, lon=target_lons, method="linear", kwargs={"fill_value": np.nan})
    return regridded.fillna(0.0)


# --------------------------------------------------------------------------- #
# Step 5 & 6: Normalize channels, zero-fill CMEMS placeholders, stack
# --------------------------------------------------------------------------- #

def normalize(arr: np.ndarray, scale: float, clip: Tuple[float, float]) -> np.ndarray:
    """Divide by `scale` and clip into `clip`, returning a float32 array."""
    out = arr.astype(np.float32) / np.float32(scale)
    return np.clip(out, clip[0], clip[1])


def _extract_or_placeholder(
    ds: xr.Dataset, names: Tuple[str, ...], scale: float, clip: Tuple[float, float], grid_size: int, label: str
) -> np.ndarray:
    """
    Extract and normalize the first variable in `names` found in `ds`;
    if none are present (e.g. no CMEMS file was supplied), log and
    return a zero-filled placeholder of shape (grid_size, grid_size).
    """
    var_name = next((n for n in names if n in ds.data_vars), None)
    if var_name is None:
        logger.info("No CMEMS variable found for %s (looked for %s); zero-filling placeholder.", label, names)
        return np.zeros((grid_size, grid_size), dtype=np.float32)
    return normalize(ds[var_name].values, scale=scale, clip=clip)


def build_tensor(ds: xr.Dataset, grid_size: int = GRID_SIZE) -> torch.FloatTensor:
    """
    Extract, normalize, and stack the 8 output channels into a single
    PyTorch FloatTensor.

    Channel order: [u10, v10, swh, mwp, uo, vo, SSH/zos, mwd].
    Channels 4-6 (uo, vo, SSH/zos) are zero-filled placeholders unless a
    CMEMS dataset was merged in upstream (see `merge_sources`).

    Parameters
    ----------
    ds : xr.Dataset
        Regridded, gap-filled dataset containing at least u10, v10, swh,
        mwp, and mwd, optionally also uo, vo, zos from CMEMS.
    grid_size : int
        Spatial resolution of each channel.

    Returns
    -------
    torch.FloatTensor
        Shape (8, grid_size, grid_size).
    """
    u10 = normalize(ds["u10"].values, scale=25.0, clip=(-1.0, 1.0))
    v10 = normalize(ds["v10"].values, scale=25.0, clip=(-1.0, 1.0))

    swh_name = "swh" if "swh" in ds.data_vars else "Hs"
    mwp_name = "mwp" if "mwp" in ds.data_vars else "Tm"
    mwd_name = "mwd" if "mwd" in ds.data_vars else "theta_w"
    swh = normalize(ds[swh_name].values, scale=12.0, clip=(0.0, 1.0))
    mwp = normalize(ds[mwp_name].values, scale=18.0, clip=(0.0, 1.0))
    mwd = normalize(ds[mwd_name].values, scale=360.0, clip=(0.0, 1.0))

    uo = _extract_or_placeholder(ds, ("uo",), scale=2.5, clip=(-1.0, 1.0), grid_size=grid_size, label="uo")
    vo = _extract_or_placeholder(ds, ("vo",), scale=2.5, clip=(-1.0, 1.0), grid_size=grid_size, label="vo")
    ssh = _extract_or_placeholder(ds, ("zos", "ssh"), scale=2.0, clip=(-1.0, 1.0), grid_size=grid_size, label="SSH/zos")

    stacked = np.stack([u10, v10, swh, mwp, uo, vo, ssh, mwd], axis=0)
    assert stacked.shape == (8, grid_size, grid_size), f"Unexpected shape {stacked.shape}"

    return torch.from_numpy(stacked).float()


# --------------------------------------------------------------------------- #
# Step 7: Save + summary stats
# --------------------------------------------------------------------------- #

CHANNEL_NAMES = ("u10", "v10", "swh", "mwp", "uo", "vo", "SSH (zos)", "mwd")


def save_tensor(tensor: torch.FloatTensor, output_path: str) -> None:
    """Save the tensor to disk via `torch.save`, creating parent dirs as needed."""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(tensor, out_path)
    logger.info("Saved tensor to '%s'", out_path)


def print_summary(tensor: torch.FloatTensor) -> None:
    """Print shape, dtype, and per-channel summary statistics for verification."""
    print(f"\nTensor shape: {tuple(tensor.shape)}")
    print(f"Tensor dtype: {tensor.dtype}\n")
    print(f"{'Channel':<20}{'min':>10}{'max':>10}{'mean':>10}{'std':>10}")
    print("-" * 60)
    for i, name in enumerate(CHANNEL_NAMES):
        ch = tensor[i]
        print(f"{name:<20}{ch.min().item():>10.4f}{ch.max().item():>10.4f}{ch.mean().item():>10.4f}{ch.std().item():>10.4f}")
    print()


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run(
    oper_path: str, wave_path: str, bbox: BoundingBox, output_path: str,
    cmems_path: Optional[str] = None, time_index: int = 0
) -> torch.FloatTensor:
    """
    Execute the full oper+wave(+cmems) -> tensor pipeline for a single
    time-step index.

    Parameters
    ----------
    oper_path : str
        Path to the ERA5 "oper" stream file (u10, v10).
    wave_path : str
        Path to the ERA5 "wave" stream file (swh, mwp, mwd).
    bbox : BoundingBox
        (lat_min, lat_max, lon_min, lon_max) target region.
    output_path : str
        Where to save the resulting `.pt` tensor.
    cmems_path : Optional[str]
        Path to a CMEMS ocean-currents/SSH file (uo, vo, zos). If
        omitted, channels 4-6 are zero-filled placeholders.
    time_index : int
        Which time-step index to extract (default 0 = first).

    Returns
    -------
    torch.FloatTensor
        Shape (8, 64, 64).
    """
    logger.info("=== Step 1: Opening files ===")
    oper_raw = open_dataset_safely(oper_path)
    wave_raw = open_dataset_safely(wave_path)
    cmems_raw = open_dataset_safely(cmems_path) if cmems_path else None

    # Select the requested time-step (not just first)
    def _select_time(ds: xr.Dataset, idx: int) -> xr.Dataset:
        time_dim = next((t for t in ("valid_time", "time") if t in ds.dims), None)
        if time_dim is not None:
            ds = ds.isel({time_dim: idx})
        squeezable = [d for d, size in ds.sizes.items() if size == 1]
        if squeezable:
            ds = ds.squeeze(dim=squeezable, drop=False)
        return ds

    logger.info("=== Step 2: Slicing to time-step %d ===", time_index)
    oper_t = _select_time(oper_raw, time_index)
    wave_t = _select_time(wave_raw, time_index)
    cmems_t = _select_time(cmems_raw, time_index) if cmems_raw is not None else None

    logger.info("=== Step 3: Standardizing coordinates + merging ===")
    oper_std = standardize_coords(oper_t)
    wave_std = standardize_coords(wave_t)
    cmems_std = standardize_coords(cmems_t) if cmems_t is not None else None
    merged = merge_sources(oper_std, wave_std, cmems_std)

    logger.info("=== Step 4: Cropping + bilinear regridding to %dx%d ===", GRID_SIZE, GRID_SIZE)
    cropped = crop_to_bbox(merged, bbox)
    regridded = regrid_bilinear(cropped, bbox, GRID_SIZE)

    logger.info(
        "=== Step 5 & 6: Normalizing channels + stacking (uo/vo/SSH %s) ===",
        "from CMEMS" if cmems_std is not None else "zero-filled",
    )
    tensor = build_tensor(regridded, GRID_SIZE)

    logger.info("=== Step 7: Saving + summary ===")
    save_tensor(tensor, output_path)
    print_summary(tensor)

    return tensor


def _physics_labels(tensor: torch.FloatTensor) -> torch.FloatTensor:
    """
    Compute Bretschneider-based naval drag labels from a single
    (8, 64, 64) normalised tensor.

    Returns a 1-D tensor [R_wave (kN), fuel_rate (kg/NM)].
    """
    # Ch 2: swh normalised by /12.0  ->  Hs_phys = val * 12.0 m
    # Ch 0/1: wind normalised by /25.0 -> wind_phys = val * 25.0 m/s
    Hs_phys   = tensor[2].mean().item() * 12.0        # m
    u10_phys  = tensor[0].mean().item() * 25.0        # m/s
    v10_phys  = tensor[1].mean().item() * 25.0        # m/s
    V_wind_sq = u10_phys ** 2 + v10_phys ** 2        # m^2/s^2

    alpha     = 45.0                                  # kN/m^2
    R_wave    = max(0.0, alpha * Hs_phys ** 2)        # kN

    beta      = 0.004
    gamma     = 0.012
    base      = 2.15
    fuel_rate = max(0.5, base + beta * V_wind_sq + gamma * R_wave)

    return torch.tensor([R_wave, fuel_rate], dtype=torch.float32)


def run_all(
    oper_path: str,
    wave_path: str,
    bbox: BoundingBox,
    output_path: str,
    labels_path: str,
    cmems_path: Optional[str] = None,
) -> None:
    """
    Process ALL time-steps in the ERA5 files and save:
      - A stacked training tensor  (N, 8, 64, 64) -> `output_path`
      - Physics-derived labels     (N, 2)          -> `labels_path`

    These two files are ready to pass directly to train_cnn_pipeline.py:

        python train_cnn_pipeline.py --mode train \\
            --data_path training_tensor.pt \\
            --labels_path training_labels.pt \\
            --epochs 50
    """
    logger.info("=== run_all: opening files to count time-steps ===")
    oper_raw = open_dataset_safely(oper_path)
    wave_raw = open_dataset_safely(wave_path)
    cmems_raw = open_dataset_safely(cmems_path) if cmems_path else None

    time_dim_oper = next((t for t in ("valid_time", "time") if t in oper_raw.dims), None)
    n_steps = oper_raw.sizes[time_dim_oper] if time_dim_oper else 1
    logger.info("Total time-steps to process: %d", n_steps)

    tensors: list[torch.FloatTensor] = []
    labels:  list[torch.FloatTensor] = []

    def _select_time(ds: xr.Dataset, idx: int) -> xr.Dataset:
        time_dim = next((t for t in ("valid_time", "time") if t in ds.dims), None)
        if time_dim is not None:
            ds = ds.isel({time_dim: idx})
        squeezable = [d for d, size in ds.sizes.items() if size == 1]
        if squeezable:
            ds = ds.squeeze(dim=squeezable, drop=False)
        return ds

    for i in range(n_steps):
        if i % 10 == 0:
            logger.info("Processing time-step %d / %d ...", i + 1, n_steps)
        try:
            oper_t  = _select_time(oper_raw, i)
            wave_t  = _select_time(wave_raw, i)
            cmems_t = _select_time(cmems_raw, i) if cmems_raw is not None else None

            oper_std  = standardize_coords(oper_t)
            wave_std  = standardize_coords(wave_t)
            cmems_std = standardize_coords(cmems_t) if cmems_t is not None else None
            merged    = merge_sources(oper_std, wave_std, cmems_std)

            cropped   = crop_to_bbox(merged, bbox)
            regridded = regrid_bilinear(cropped, bbox, GRID_SIZE)
            tensor    = build_tensor(regridded, GRID_SIZE)  # (8, 64, 64)

            tensors.append(tensor)
            labels.append(_physics_labels(tensor))

        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping time-step %d due to error: %s", i, exc)
            continue

    if not tensors:
        raise RuntimeError("No time-steps could be processed successfully. Check your files / bbox.")

    X = torch.stack(tensors, dim=0)  # (N, 8, 64, 64)
    y = torch.stack(labels,  dim=0)  # (N, 2)

    out_p    = Path(output_path)
    label_p  = Path(labels_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    label_p.parent.mkdir(parents=True, exist_ok=True)

    torch.save(X, out_p)
    torch.save(y, label_p)

    logger.info("=" * 60)
    logger.info("Training tensor saved -> %s  shape=%s", out_p, tuple(X.shape))
    logger.info("Labels tensor  saved  -> %s  shape=%s", label_p, tuple(y.shape))
    logger.info("R_wave    mean=%.2f kN   std=%.2f kN",
                y[:, 0].mean().item(), y[:, 0].std().item())
    logger.info("fuel_rate mean=%.4f kg/NM std=%.4f kg/NM",
                y[:, 1].mean().item(), y[:, 1].std().item())
    logger.info("=" * 60)
    logger.info("Next step -> train the CNN:")
    logger.info("  python train_cnn_pipeline.py --mode train ")
    logger.info("      --data_path %s ", out_p)
    logger.info("      --labels_path %s ", label_p)
    logger.info("      --epochs 50")
    logger.info("=" * 60)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _parse_bbox(bbox_str: str) -> BoundingBox:
    """Parse '--bbox' of the form 'lat_min,lat_max,lon_min,lon_max'."""
    parts = [p.strip() for p in bbox_str.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"--bbox must be 4 comma-separated floats, got: '{bbox_str}'")
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--bbox values must be floats: '{bbox_str}'") from exc


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="era5_wind_wave_to_tensor",
        description="Merge ERA5 oper (wind) + wave (+ optional CMEMS) NetCDF files into a normalized (8, 64, 64) PyTorch tensor.",
    )
    parser.add_argument(
        "--oper", type=str, default="C:/Users/Admin/OneDrive/Desktop/SIH/SIH data/data_stream-oper_stepType-instant.nc",
        help="Path to the ERA5 oper-stream .nc file (u10, v10).",
    )
    parser.add_argument(
        "--wave", type=str, default="C:/Users/Admin/OneDrive/Desktop/SIH/SIH data/data_stream-wave_stepType-instant.nc",
        help="Path to the ERA5 wave-stream .nc file (swh, mwp, mwd).",
    )
    parser.add_argument(
        "--cmems", type=str, default=None,
        help="Optional path to a CMEMS .nc file (uo, vo, zos). If omitted, channels 4-6 are zero-filled placeholders.",
    )
    parser.add_argument(
        "--bbox", type=_parse_bbox, default=(10.0, 20.0, 80.0, 95.0),
        help="Target region as 'lat_min,lat_max,lon_min,lon_max' (default: 10.0,20.0,80.0,95.0).",
    )
    parser.add_argument(
        "--output", type=str, default="ocean_weather_tensor.pt",
        help="Output .pt filepath for single time-step (default: ocean_weather_tensor.pt).",
    )
    # ---- New: multi-timestep training data export -------------------------
    parser.add_argument(
        "--all_timesteps", action="store_true",
        help=(
            "Process ALL time-steps and save a training tensor (N,8,64,64) + "
            "physics labels (N,2). Output filenames are controlled by "
            "--output (tensor) and --labels_output (labels)."
        ),
    )
    parser.add_argument(
        "--labels_output", type=str, default="training_labels.pt",
        help="Output .pt filepath for labels when --all_timesteps is used (default: training_labels.pt).",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()

    if args.all_timesteps:
        # Multi-step mode: build full (N,8,64,64) training dataset
        out_tensor = args.output if args.output != "ocean_weather_tensor.pt" else "training_tensor.pt"
        run_all(
            oper_path=args.oper,
            wave_path=args.wave,
            bbox=args.bbox,
            output_path=out_tensor,
            labels_path=args.labels_output,
            cmems_path=args.cmems,
        )
    else:
        # Single time-step mode (original behaviour): inference tensor
        run(
            oper_path=args.oper,
            wave_path=args.wave,
            bbox=args.bbox,
            output_path=args.output,
            cmems_path=args.cmems,
        )