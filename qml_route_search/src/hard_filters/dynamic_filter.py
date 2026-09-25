import logging
import math
from typing import Tuple, Dict

import numpy as np
import xarray as xr
import pandas as pd

logger = logging.getLogger(__name__)

class DynamicFilter:
    """
    Dynamic weather and sea-state filter for maritime route optimization (§5.2).
    Evaluates weather conditions against vessel safety limits (Hs, Wind).
    """
    def __init__(self, era5_oper_path: str, era5_wave_path: str, hs_threshold: float = 8.0, wind_threshold: float = 25.7):
        """
        Initialize the DynamicFilter.

        Args:
            era5_oper_path: Path to ERA5 atmospheric data (NetCDF).
            era5_wave_path: Path to ERA5 wave data (NetCDF).
            hs_threshold: Maximum allowable significant wave height (meters).
            wind_threshold: Maximum allowable wind speed (m/s).
        """
        self.era5_oper_path = era5_oper_path
        self.era5_wave_path = era5_wave_path
        self.hs_threshold = hs_threshold
        self.wind_threshold = wind_threshold
        
        self._load_data()

    def _load_data(self):
        """Loads ERA5 atmospheric and wave datasets."""
        try:
            # We use xarray to load the netcdf datasets.
            # Using dask (chunks) could be useful for very large datasets, but keeping it simple.
            self.ds_oper = xr.open_dataset(self.era5_oper_path)
            self.ds_wave = xr.open_dataset(self.era5_wave_path)
            logger.info(f"Loaded ERA5 oper data from {self.era5_oper_path}")
            logger.info(f"Loaded ERA5 wave data from {self.era5_wave_path}")
            
            # Align coordinates to common time base if needed, though they should be aligned.
            # Convert time coordinates to pandas datetime index for easier manipulation.
            self.times = pd.DatetimeIndex(self.ds_oper.time.values)
        except Exception as e:
            logger.error(f"Failed to load ERA5 data: {e}")
            raise

    def get_time_range(self) -> Tuple[pd.Timestamp, pd.Timestamp]:
        """
        Get the available time range in the dataset.
        
        Returns:
            Tuple containing (min_time, max_time)
        """
        return self.times.min(), self.times.max()

    def interpolate_weather(self, lat: float, lon: float, time: pd.Timestamp) -> xr.Dataset:
        """
        Interpolates weather data spatially at a given time.
        For time, it selects the nearest or interpolates if desired.
        """
        # Select data for the given coordinates and time using interpolation
        try:
            oper_interp = self.ds_oper.interp(latitude=lat, longitude=lon, time=time, method="linear")
            wave_interp = self.ds_wave.interp(latitude=lat, longitude=lon, time=time, method="linear")
            return xr.merge([oper_interp, wave_interp])
        except Exception as e:
            logger.warning(f"Interpolation failed for lat={lat}, lon={lon}, time={time}: {e}")
            # Fallback to nearest if linear fails (e.g., at boundaries)
            oper_interp = self.ds_oper.sel(latitude=lat, longitude=lon, time=time, method="nearest")
            wave_interp = self.ds_wave.sel(latitude=lat, longitude=lon, time=time, method="nearest")
            return xr.merge([oper_interp, wave_interp])

    def get_weather_at(self, lat: float, lon: float, time: pd.Timestamp) -> Dict[str, float]:
        """
        Get all relevant weather fields interpolated at the specific location and time.
        
        Args:
            lat: Latitude
            lon: Longitude
            time: Timestamp for the query
            
        Returns:
            Dictionary containing hs, wind_speed, wind_dir, wave_dir, wave_period, 
            peak_period, wind_wave_height, swell_height.
        """
        ds_point = self.interpolate_weather(lat, lon, time)
        
        try:
            # Atmospheric variables
            u10 = float(ds_point.u10.values)
            v10 = float(ds_point.v10.values)
            wind_speed = math.sqrt(u10**2 + v10**2)
            # Meteorological convention: direction wind is blowing *from*
            wind_dir = (math.degrees(math.atan2(-u10, -v10)) + 360) % 360
            
            # Wave variables
            hs = float(ds_point.swh.values) if 'swh' in ds_point else 0.0
            wave_dir = float(ds_point.mwd.values) if 'mwd' in ds_point else 0.0
            wave_period = float(ds_point.mwp.values) if 'mwp' in ds_point else 0.0
            peak_period = float(ds_point.pp1d.values) if 'pp1d' in ds_point else 0.0
            wind_wave_height = float(ds_point.shww.values) if 'shww' in ds_point else 0.0
            swell_height = float(ds_point.shts.values) if 'shts' in ds_point else 0.0
            
            return {
                'hs': hs,
                'wind_speed': wind_speed,
                'wind_dir': wind_dir,
                'wave_dir': wave_dir,
                'wave_period': wave_period,
                'peak_period': peak_period,
                'wind_wave_height': wind_wave_height,
                'swell_height': swell_height
            }
        except Exception as e:
            logger.warning(f"Failed to extract weather variables at {lat},{lon},{time}: {e}")
            # Return defaults if out of bounds or missing data
            return {
                'hs': 0.0, 'wind_speed': 0.0, 'wind_dir': 0.0, 'wave_dir': 0.0,
                'wave_period': 0.0, 'peak_period': 0.0, 'wind_wave_height': 0.0, 'swell_height': 0.0
            }

    def is_no_go(self, lat: float, lon: float, time: pd.Timestamp) -> bool:
        """
        Checks if the weather conditions exceed safety thresholds (No-Go).
        
        Args:
            lat: Latitude
            lon: Longitude
            time: Timestamp for the query
            
        Returns:
            True if conditions are unsafe, False otherwise.
        """
        weather = self.get_weather_at(lat, lon, time)
        
        if weather['hs'] >= self.hs_threshold:
            return True
            
        if weather['wind_speed'] >= self.wind_threshold:
            return True
            
        return False
