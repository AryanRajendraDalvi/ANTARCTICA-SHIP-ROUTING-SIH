import os
import sys
import yaml
import logging
from pathlib import Path
import numpy as np

# Ensure src is in the python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hard_filters.static_filter import StaticFilter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config(config_path="config/default.yaml"):
    """Load configuration from yaml file."""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"Config {config_path} not found. Using defaults.")
        return {}

def main():
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "config" / "default.yaml"
    config = load_config(config_path)

    # Paths
    # Using defaults from the problem description
    gebco_path = config.get('gebco_path', r"d:/downloads/SMART INDIA HACKATHON 2026/GEBCO_15_Aug_2026_ac6c6a430fde/gebco_2026_n18.445_s-36.867_w54.711_e116.586_geotiff.tif")
    gshhg_path = config.get('gshhg_path', r"d:/downloads/SMART INDIA HACKATHON 2026/GSHHS_i_L1.shp")
    cache_dir = project_root / "cache"
    cache_path = cache_dir / "static_filter.pkl"
    
    # Parameters
    draft_m = config.get('vessel', {}).get('draft_m', 15.0)
    margin_safety_m = config.get('static_filter', {}).get('margin_safety_m', 2.0)
    spacing_deg = config.get('static_filter', {}).get('spacing_deg', 0.25)
    
    # Box bounds based on GEBCO extent
    lat_range = (-36.867, 18.445)
    lon_range = (54.711, 116.586)

    logger.info("Initializing Static Filter...")
    filter_instance = StaticFilter(
        gebco_path=gebco_path,
        gshhg_path=gshhg_path,
        margin_safety_m=margin_safety_m
    )
    
    logger.info(f"Precomputing grid with spacing {spacing_deg} degrees for draft {draft_m}m...")
    grid = filter_instance.precompute_grid(lat_range, lon_range, spacing_deg, draft_m)
    
    total_nodes = grid.size
    valid_nodes = np.sum(grid)
    navigable_pct = (valid_nodes / total_nodes) * 100
    
    logger.info(f"Grid Statistics:")
    logger.info(f"  Total Nodes: {total_nodes}")
    logger.info(f"  Valid Nodes: {valid_nodes}")
    logger.info(f"  % Navigable: {navigable_pct:.2f}%")
    
    logger.info(f"Saving cache to {cache_path}...")
    cache_dir.mkdir(parents=True, exist_ok=True)
    filter_instance.save_cache(str(cache_path))
    
    logger.info("Precomputation completed successfully.")

if __name__ == "__main__":
    main()
