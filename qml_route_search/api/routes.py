"""
FastAPI Route Handlers — Connects API endpoints to the actual pipeline modules.

All heavy resources (filters, cost model, search engine, etc.) are injected
via set_pipeline_context() from api/main.py at startup.
"""
import time
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from api.schemas import PlanRouteRequest, ReplanRequest, VesselInfo, ErrorResponse
from src.output.route_schema import (
    WaypointRecord, RouteSummary, RouteOutput, PlanningResponse, SafetyFlag, SourceType,
)

logger = logging.getLogger("qml_route_search.api")

router = APIRouter()

# --- Pipeline context (injected at startup) ---
_ctx: Dict[str, Any] = {}


def set_pipeline_context(**kwargs):
    """Called by api/main.py to inject loaded pipeline components."""
    _ctx.update(kwargs)


def _resolve_location(loc_str: str) -> tuple:
    """
    Resolve a location string to (lat, lon).
    Accepts: port name (e.g. 'mumbai') or 'lat,lon' string.
    """
    config = _ctx.get("config", {})
    ports = config.get("ports", {})

    # Check if it's a known port name
    loc_lower = loc_str.strip().lower().replace(" ", "_")
    if loc_lower in ports:
        port = ports[loc_lower]
        return port["lat"], port["lon"]

    # Try parsing as 'lat,lon'
    try:
        parts = loc_str.split(",")
        return float(parts[0].strip()), float(parts[1].strip())
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resolve location '{loc_str}'. Use a port name ({list(ports.keys())}) or 'lat,lon'.",
        )


# --- In-memory route storage ---
_active_routes: Dict[str, RouteOutput] = {}


@router.post("/plan-route", response_model=PlanningResponse)
async def plan_route(request: PlanRouteRequest):
    """
    Plan an optimal route between origin and destination.
    Returns a Pareto-optimal set of routes (FASTEST, CHEAPEST, MOST_COMFORTABLE).
    """
    t_start = time.time()

    # Resolve locations
    origin_lat, origin_lon = _resolve_location(request.origin)
    dest_lat, dest_lon = _resolve_location(request.destination)

    # Find vessel
    vessels = _ctx.get("vessels", {})
    vessel_id = request.vessel_id.strip().lower().replace(" ", "_")
    if vessel_id not in vessels:
        available = list(vessels.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Vessel '{request.vessel_id}' not found. Available: {available}",
        )
    vessel = vessels[vessel_id]

    # Run the search
    search_engine = _ctx.get("search_engine")
    if search_engine is None:
        raise HTTPException(status_code=503, detail="Search engine not initialized")

    t_depart = request.departure_time.timestamp()

    try:
        routes = search_engine.search(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            t_depart=t_depart,
            vessel_profile=vessel,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Route search failed: {str(e)}")

    # Apply safety checks to each route
    safety = _ctx.get("safety", {})
    route_outputs = []

    for route in routes:
        waypoint_records = []
        for i, wp in enumerate(route.waypoints):
            # Build waypoint record
            wr = WaypointRecord(
                lat=wp.lat,
                lon=wp.lon,
                eta=datetime.fromtimestamp(t_depart + wp.t_elapsed_s),
                heading=wp.heading,
                speed=wp.speed_kn,
                fuel_leg_kg=wp.objectives[0] - (route.waypoints[i - 1].objectives[0] if i > 0 else 0),
                resistance_kN=wp.objectives[1] - (route.waypoints[i - 1].objectives[1] if i > 0 else 0),
                roll_risk=wp.objectives[3],
                slam_force=wp.objectives[4],
                comfort_index=0.0,
                green_water_risk=0.0,
                prop_emergence_risk=0.0,
                confidence=wp.confidence_min,
                safety_flag=SafetyFlag.OK,
                source=SourceType.MODEL,
            )

            # Apply seakeeping check if weather data available
            if wp.weather_at_point and safety.get("seakeeping"):
                weather = wp.weather_at_point
                sk_result = safety["seakeeping"].check_leg(
                    hs=weather.get("hs", 0),
                    wave_period_tm=weather.get("wave_period", 8),
                    v_stw=wp.speed_kn * 0.5144,  # kn to m/s
                    theta_enc=weather.get("encounter_angle", 0),
                    vessel_t_roll=vessel_profile["t_roll"],
                )
                if sk_result.get("flagged"):
                    wr.safety_flag = SafetyFlag.PARAMETRIC_ROLL_RISK

            waypoint_records.append(wr)

        # Build summary
        route_id = str(uuid.uuid4())[:8]
        summary = RouteSummary(
            label=route.label,
            total_distance_nm=route.total_distance_nm,
            total_fuel_t=route.total_fuel_kg / 1000.0,
            total_time_hr=route.total_time_hours,
            cii_attained=0.0,
            last_update=datetime.now(),
        )

        # Compute CII if emissions checker available
        if safety.get("emissions"):
            cii = safety["emissions"].compute_cii(
                total_fuel_kg=route.total_fuel_kg,
                dwt=vessel_profile["dwt"],
                total_distance_nm=route.total_distance_nm,
            )
            summary.cii_attained = cii

        route_output = RouteOutput(
            route_id=route_id,
            summary=summary,
            waypoints=waypoint_records,
        )
        route_outputs.append(route_output)
        _active_routes[route_id] = route_output

    planning_time = time.time() - t_start

    return PlanningResponse(
        routes=route_outputs,
        planning_time_s=round(planning_time, 3),
        vessel_name=vessel.name,
    )


@router.post("/replan", response_model=PlanningResponse)
async def replan_route(request: ReplanRequest):
    """Re-plan route from current AIS position using rolling horizon."""
    rerouting = _ctx.get("rerouting_manager")
    if rerouting is None:
        raise HTTPException(status_code=503, detail="Re-routing manager not initialized")

    # Resolve destination
    dest_lat, dest_lon = _resolve_location(request.destination)

    vessels = _ctx.get("vessels", {})
    vessel_id = request.vessel_id.strip().lower().replace(" ", "_")
    if vessel_id not in vessels:
        raise HTTPException(status_code=404, detail=f"Vessel '{request.vessel_id}' not found")

    vessel = vessels[vessel_id]
    vessel_profile = {
        "v_stw": vessel.service_speed_kn,
        "draft_m": vessel.draft_max_m,
        "dwt": vessel.dwt_mt,
        "t_roll": vessel.t_roll_loaded_s,
    }

    t_start = time.time()
    try:
        search_engine = _ctx.get("search_engine")
        routes = search_engine.search(
            origin_lat=request.current_lat,
            origin_lon=request.current_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            t_depart=request.t_now.timestamp(),
            vessel_profile=vessel,
        )
    except Exception as e:
        logger.error(f"Replan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Replan failed: {str(e)}")

    # Convert routes to output (simplified — reuses plan_route logic)
    route_outputs = []
    for route in routes:
        waypoint_records = [
            WaypointRecord(
                lat=wp.lat, lon=wp.lon,
                eta=datetime.fromtimestamp(request.t_now.timestamp() + wp.t_elapsed_s),
                heading=wp.heading, speed=wp.speed_kn,
                fuel_leg_kg=0.0, resistance_kN=0.0,
                roll_risk=wp.objectives[3], slam_force=wp.objectives[4],
                comfort_index=0.0, green_water_risk=0.0, prop_emergence_risk=0.0,
                confidence=wp.confidence_min,
                safety_flag=SafetyFlag.OK, source=SourceType.MODEL,
            )
            for wp in route.waypoints
        ]
        route_id = str(uuid.uuid4())[:8]
        route_output = RouteOutput(
            route_id=route_id,
            summary=RouteSummary(
                label=route.label,
                total_distance_nm=route.total_distance_nm,
                total_fuel_t=route.total_fuel_kg / 1000.0,
                total_time_hr=route.total_time_hours,
                cii_attained=0.0,
                last_update=datetime.now(),
            ),
            waypoints=waypoint_records,
        )
        route_outputs.append(route_output)
        _active_routes[route_id] = route_output

    return PlanningResponse(
        routes=route_outputs,
        planning_time_s=round(time.time() - t_start, 3),
        vessel_name=vessel.name,
    )


@router.get("/vessels", response_model=List[VesselInfo])
async def list_vessels():
    """List all available vessel profiles."""
    vessels = _ctx.get("vessels", {})
    return [
        VesselInfo(
            name=v.name,
            imo=str(v.imo),
            type=v.vessel_type,
            loa=v.loa_m,
            beam=v.beam_m,
            draft=v.draft_max_m,
            dwt=v.dwt_mt,
            speed=v.service_speed_kn,
        )
        for v in vessels.values()
    ]


@router.get("/vessels/{vessel_id}", response_model=VesselInfo)
async def get_vessel(vessel_id: str):
    """Get detailed vessel profile."""
    vessels = _ctx.get("vessels", {})
    vid = vessel_id.strip().lower().replace(" ", "_")
    if vid not in vessels:
        raise HTTPException(status_code=404, detail=f"Vessel '{vessel_id}' not found")
    v = vessels[vid]
    return VesselInfo(
        name=v.name, imo=str(v.imo), type=v.vessel_type,
        loa=v.loa_m, beam=v.beam_m, draft=v.draft_max_m,
        dwt=v.dwt_mt, speed=v.service_speed_kn,
    )


@router.get("/route/{route_id}")
async def get_route(route_id: str):
    """Get a stored route by ID (for ship panel to fetch dispatched route)."""
    if route_id not in _active_routes:
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found")
    return _active_routes[route_id]


@router.get("/ports")
async def list_ports():
    """List all known Indian ports."""
    config = _ctx.get("config", {})
    return config.get("ports", {})


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "static_filter": _ctx.get("static_filter") is not None,
            "dynamic_filter": _ctx.get("dynamic_filter") is not None,
            "cost_model": _ctx.get("cost_model") is not None,
            "search_engine": _ctx.get("search_engine") is not None,
            "vessels_loaded": len(_ctx.get("vessels", {})),
        },
    }

from api.schemas import DispatchRequest
from api.websocket import manager as ws_manager

@router.post("/dispatch-route")
async def dispatch_route(request: DispatchRequest):
    """
    Onshore Agency uses this to push a selected route to the Ship over SATCOM.
    The ship panel listens on the websocket for this route_id.
    """
    if request.route_id not in _active_routes:
        raise HTTPException(status_code=404, detail=f"Route '{request.route_id}' not found")
        
    route_data = _active_routes[request.route_id].model_dump(mode='json')
    
    # Push to the ship's panel via WebSocket
    await ws_manager.broadcast_update(request.route_id, route_data)
    
    return {"status": "success", "message": f"Route {request.route_id} dispatched to ship."}
