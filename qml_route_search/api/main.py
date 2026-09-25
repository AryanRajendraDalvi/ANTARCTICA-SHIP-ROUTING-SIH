"""
FastAPI Application — Main Entry Point

Loads all pipeline components on startup and exposes route planning endpoints.
This is the core backend service that the onshore agency and ship panels connect to.
"""
import os
import sys
import logging
import yaml
import torch
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.routes import router, set_pipeline_context
from api.websocket import router as ws_router

logger = logging.getLogger("qml_route_search")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


def load_config():
    """Load the master configuration YAML."""
    config_path = PROJECT_ROOT / "config" / "default.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler — loads all heavy resources on startup,
    tears them down on shutdown.
    """
    logger.info("=" * 60)
    logger.info("QML Route Search Pipeline — Starting up")
    logger.info("=" * 60)

    # 1. Load configuration
    config = load_config()
    logger.info("✓ Configuration loaded")

    # 2. Load vessel profiles
    from src.vessel_loader import load_all_vessels
    vessels_dir = PROJECT_ROOT / "config" / "vessels"
    vessels = load_all_vessels(str(vessels_dir))
    logger.info(f"✓ Loaded {len(vessels)} vessel profiles")

    # 3. Load static filter (GEBCO + GSHHG)
    static_filter = None
    try:
        from src.hard_filters.static_filter import StaticFilter
        gebco_path = str(PROJECT_ROOT / config["data"]["gebco_path"])
        gshhg_path = str(PROJECT_ROOT / config["data"]["gshhg_path"])
        cache_path = str(PROJECT_ROOT / config["static_filter"]["cache_path"])

        if os.path.exists(cache_path):
            static_filter = StaticFilter.__new__(StaticFilter)
            static_filter.load_cache(cache_path)
            logger.info("✓ Static filter loaded from cache")
        else:
            static_filter = StaticFilter(
                gebco_path=gebco_path,
                gshhg_path=gshhg_path,
                margin_safety_m=config["static_filter"]["margin_safety_m"],
                sample_interval_nm=config["static_filter"]["sample_interval_nm"],
            )
            logger.info("✓ Static filter initialized (no cache — run precompute_static_filter.py for faster startup)")
    except Exception as e:
        logger.warning(f"✗ Static filter failed to load: {e}. Routing will proceed without bathymetry checks.")

    # 4. Load dynamic filter (ERA5 weather)
    dynamic_filter = None
    try:
        from src.hard_filters.dynamic_filter import DynamicFilter
        era5_oper = str(PROJECT_ROOT / config["data"]["era5_oper_path"])
        era5_wave = str(PROJECT_ROOT / config["data"]["era5_wave_path"])
        dynamic_filter = DynamicFilter(
            era5_oper_path=era5_oper,
            era5_wave_path=era5_wave,
            hs_threshold=config["dynamic_filter"]["hs_threshold"],
            wind_threshold=config["dynamic_filter"]["wind_threshold"],
        )
        logger.info("✓ Dynamic filter loaded (ERA5 weather data)")
    except Exception as e:
        logger.warning(f"✗ Dynamic filter failed to load: {e}. Routing will proceed without weather no-go gates.")

    # 5. Load QML cost model (if checkpoint exists)
    cost_model = None
    try:
        from src.cost_model import QMLCostModel
        readout_config = config["readout"]
        cost_model = QMLCostModel(readout_config)
        checkpoint_path = str(PROJECT_ROOT / config["data"]["model_checkpoint"])
        if os.path.exists(checkpoint_path):
            cost_model.load_state_dict(torch.load(checkpoint_path, map_location="cpu"))
            cost_model.eval()
            logger.info("✓ QML cost model loaded from checkpoint")
        else:
            cost_model.eval()
            logger.info("⚠ QML cost model initialized with random weights (no checkpoint found — run train.py)")
    except Exception as e:
        logger.warning(f"✗ QML cost model failed to load: {e}. Will use Holtrop-Mennen fallback costs.")

    # 6. Build search engine
    from src.search.weather_query import WeatherQueryEngine
    from src.search.modip_search import MODIPSearch

    weather_engine = WeatherQueryEngine(dynamic_filter) if dynamic_filter else None
    search_engine = MODIPSearch(
        cost_model=cost_model,
        static_filter=static_filter,
        dynamic_filter=dynamic_filter,
        weather_engine=weather_engine,
        config=config.get("search", {}),
    )
    logger.info("✓ 4D-MODIP search engine initialized")

    # 7. Build safety checkers
    from src.safety.seakeeping import SeakeepingChecker
    from src.safety.comfort import ComfortChecker
    from src.safety.emissions import EmissionsChecker

    safety = {
        "seakeeping": SeakeepingChecker(),
        "comfort": ComfortChecker(),
        "emissions": EmissionsChecker(hfo_co2_factor=config["safety"]["hfo_co2_factor"]),
    }
    logger.info("✓ Safety & compliance checkers initialized")

    # 8. Build re-routing manager
    from src.rerouting.rolling_horizon import RollingHorizonManager
    rerouting_manager = RollingHorizonManager(
        search_engine=search_engine,
        safety_checker=safety,
        config=config.get("rerouting", {}),
    )
    logger.info("✓ Rolling horizon re-routing manager initialized")

    # Pass all pipeline components to the routes module
    set_pipeline_context(
        config=config,
        vessels=vessels,
        static_filter=static_filter,
        dynamic_filter=dynamic_filter,
        cost_model=cost_model,
        search_engine=search_engine,
        weather_engine=weather_engine,
        safety=safety,
        rerouting_manager=rerouting_manager,
    )

    logger.info("=" * 60)
    logger.info("QML Route Search Pipeline — READY")
    logger.info("=" * 60)

    yield  # Application runs here

    # Shutdown
    logger.info("QML Route Search Pipeline — Shutting down")


# --- FastAPI Application ---
app = FastAPI(
    title="QML Maritime Route Search Engine",
    description=(
        "Quantum-Classical Cost Model with Hard Filters & "
        "Time-Dependent Multi-Objective Route Search for maritime navigation. "
        "Backend service for the Smart India Hackathon 2026."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
