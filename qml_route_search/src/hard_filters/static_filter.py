import pickle
import math
import logging
from typing import List, Tuple, Optional, Any

import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree
import pyproj

logger = logging.getLogger(__name__)

class StaticFilter:
    """
    Static filter for maritime route optimization (§5.1).
    Checks node and edge validity based on bathymetry (GEBCO) and landmass polygons (GSHHG).
    """
    def __init__(self, gebco_path: str, gshhg_path: str, margin_safety_m: float = 2.0, sample_interval_nm: float = 5.0):
        """
        Initialize the StaticFilter.
        
        Args:
            gebco_path: Path to the GEBCO GeoTIFF bathymetry data.
            gshhg_path: Path to the GSHHG ESRI Shapefile shoreline data.
            margin_safety_m: Under-keel clearance safety margin in meters.
            sample_interval_nm: Interval in nautical miles to sample great-circle arcs.
        """
        self.gebco_path = gebco_path
        self.gshhg_path = gshhg_path
        self.margin_safety_m = margin_safety_m
        self.sample_interval_nm = sample_interval_nm
        self.geod = pyproj.Geod(ellps='WGS84')
        self._load_gebco()
        self._load_gshhg()

    def _load_gebco(self):
        """Loads GEBCO bathymetry data."""
        try:
            self.gebco_ds = rasterio.open(self.gebco_path)
            self.gebco_band = self.gebco_ds.read(1)
            self.gebco_transform = self.gebco_ds.transform
            logger.info(f"Loaded GEBCO data from {self.gebco_path}")
        except Exception as e:
            logger.error(f"Failed to load GEBCO from {self.gebco_path}: {e}")
            raise

    def _load_gshhg(self):
        """Loads GSHHG land polygons and builds spatial index."""
        try:
            self.gshhg_gdf = gpd.read_file(self.gshhg_path)
            # Filter valid geometries if needed
            self.gshhg_gdf = self.gshhg_gdf[self.gshhg_gdf.is_valid]
            self.strtree = STRtree(self.gshhg_gdf.geometry)
            logger.info(f"Loaded GSHHG data from {self.gshhg_path}")
        except Exception as e:
            logger.error(f"Failed to load GSHHG from {self.gshhg_path}: {e}")
            raise

    def get_depth(self, lat: float, lon: float) -> float:
        """
        Get the water depth at a given coordinate.
        Negative values mean depth below MSL (meters).
        """
        try:
            row, col = self.gebco_ds.index(lon, lat)
            if 0 <= row < self.gebco_ds.height and 0 <= col < self.gebco_ds.width:
                return float(self.gebco_band[row, col])
            else:
                return 0.0  # Default to land if out of bounds
        except Exception as e:
            logger.warning(f"Error getting depth at {lat}, {lon}: {e}")
            return 0.0

    def get_ukc(self, lat: float, lon: float, draft_m: float) -> float:
        """
        Calculate Under-Keel Clearance (UKC).
        UKC = -depth - draft - margin_safety
        Since negative depth means water depth, depth should be < 0 for water.
        """
        depth = self.get_depth(lat, lon)
        water_depth = -depth if depth < 0 else 0.0
        return water_depth - draft_m - self.margin_safety_m

    def is_node_valid(self, lat: float, lon: float, draft_m: float) -> bool:
        """
        Check if a single node (lat, lon) is navigable.
        Must have sufficient UKC and not be on a GSHHG land polygon.
        """
        # 1. Check UKC
        if self.get_ukc(lat, lon, draft_m) <= 0:
            return False
            
        # 2. Check Land Polygon
        point = Point(lon, lat)
        idx = self.strtree.query(point)
        if len(idx) > 0:
            # Check exact intersection
            for i in idx:
                if self.gshhg_gdf.geometry.iloc[i].contains(point):
                    return False
        return True

    def _sample_great_circle(self, lat1: float, lon1: float, lat2: float, lon2: float, interval_nm: float) -> List[Tuple[float, float]]:
        """
        Sample points along the great-circle arc between two points.
        """
        interval_m = interval_nm * 1852.0
        az12, az21, dist = self.geod.inv(lon1, lat1, lon2, lat2)
        if dist <= interval_m:
            return [(lat1, lon1), (lat2, lon2)]
            
        num_points = int(math.ceil(dist / interval_m))
        # npts returns intermediate points, not including start/end
        lonlats = self.geod.npts(lon1, lat1, lon2, lat2, num_points - 1)
        points = [(lat1, lon1)] + [(lat, lon) for lon, lat in lonlats] + [(lat2, lon2)]
        return points

    def is_edge_valid(self, lat1: float, lon1: float, lat2: float, lon2: float, draft_m: float) -> bool:
        """
        Check if the path between two nodes is navigable.
        """
        points = self._sample_great_circle(lat1, lon1, lat2, lon2, self.sample_interval_nm)
        
        # Check nodes
        for lat, lon in points:
            if not self.is_node_valid(lat, lon, draft_m):
                return False
                
        # Check line against land polygons
        line = LineString([(lon, lat) for lat, lon in points])
        idx = self.strtree.query(line)
        if len(idx) > 0:
            for i in idx:
                if self.gshhg_gdf.geometry.iloc[i].intersects(line):
                    return False
        return True

    def precompute_grid(self, lat_range: Tuple[float, float], lon_range: Tuple[float, float], spacing_deg: float, draft_m: float) -> np.ndarray:
        """
        Precompute a validity grid for a given region.
        Returns a boolean 2D array where True means valid.
        """
        lats = np.arange(lat_range[0], lat_range[1] + spacing_deg/2, spacing_deg)
        lons = np.arange(lon_range[0], lon_range[1] + spacing_deg/2, spacing_deg)
        
        grid = np.zeros((len(lats), len(lons)), dtype=bool)
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                grid[i, j] = self.is_node_valid(lat, lon, draft_m)
        return grid

    def save_cache(self, path: str):
        """Save this object to a pickle file, removing unpicklable attributes."""
        # Clean up rasterio and spatial index before pickling
        gebco_ds = self.gebco_ds
        self.gebco_ds = None
        strtree = self.strtree
        self.strtree = None
        
        try:
            with open(path, 'wb') as f:
                pickle.dump(self, f)
            logger.info(f"Saved StaticFilter cache to {path}")
        except Exception as e:
            logger.error(f"Failed to save cache to {path}: {e}")
        finally:
            self.gebco_ds = gebco_ds
            self.strtree = strtree

    @classmethod
    def load_cache(cls, path: str, gebco_path: str, gshhg_path: str) -> 'StaticFilter':
        """Load a cached StaticFilter and restore unpicklable objects."""
        try:
            with open(path, 'rb') as f:
                obj = pickle.load(f)
            # Re-initialize unpicklable parts
            obj.gebco_path = gebco_path
            obj.gshhg_path = gshhg_path
            obj.geod = pyproj.Geod(ellps='WGS84')
            obj._load_gebco()
            obj.strtree = STRtree(obj.gshhg_gdf.geometry)
            logger.info(f"Loaded StaticFilter cache from {path}")
            return obj
        except Exception as e:
            logger.error(f"Failed to load cache from {path}: {e}")
            raise
