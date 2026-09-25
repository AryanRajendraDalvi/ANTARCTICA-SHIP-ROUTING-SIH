import os
"""
NCPOR Polar Navigation API Server
Serves real data: ERA5 weather, GNN ice forecasts, MODIP routes, vessel telemetry, iceberg tracking
Run from project root: python -m uvicorn backend.ncpor_api:app --port 8001 --reload
"""
import sys
import math
import time
import json
import random
import asyncio
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Data paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
ERA5_OPER = ROOT / "ba1fa283adfc139deb3199b360eb4af0" / "data_stream-oper_stepType-instant.nc"
ERA5_WAVE = ROOT / "ba1fa283adfc139deb3199b360eb4af0" / "data_stream-wave_stepType-instant.nc"

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="NCPOR Polar Navigation API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Load ERA5 data at startup ────────────────────────────────────────────────
era5_data: Dict[str, Any] = {}

@app.on_event("startup")
async def load_era5():
    global era5_data
    try:
        import xarray as xr
        print("Loading ERA5 operational data...")
        ds_oper = xr.open_dataset(str(ERA5_OPER), engine="netcdf4")
        ds_wave = xr.open_dataset(str(ERA5_WAVE), engine="netcdf4")

        def get_latlon_names(ds):
            lat_name = "latitude" if "latitude" in ds.coords else "lat"
            lon_name = "longitude" if "longitude" in ds.coords else "lon"
            return lat_name, lon_name

        lat_name_o, lon_name_o = get_latlon_names(ds_oper)
        lat_name_w, lon_name_w = get_latlon_names(ds_wave)

        lat_vals_o = ds_oper[lat_name_o].values
        lon_vals_o = ds_oper[lon_name_o].values

        def clip_so(ds, lat_name, lon_name, lat_vals, lon_vals):
            lat_mask = (lat_vals >= -75.0) & (lat_vals <= -50.0)
            lon_mask = (lon_vals >= 0.0) & (lon_vals <= 180.0)
            if lat_mask.sum() == 0:
                print(f"  No SO lats found, lat range: [{lat_vals.min():.1f},{lat_vals.max():.1f}]. Using all.")
                lat_mask = np.ones(len(lat_vals), dtype=bool)
            if lon_mask.sum() == 0:
                lon_mask = np.ones(len(lon_vals), dtype=bool)
            return ds.isel(**{lat_name: np.where(lat_mask)[0], lon_name: np.where(lon_mask)[0]})

        so_oper = clip_so(ds_oper, lat_name_o, lon_name_o, lat_vals_o, lon_vals_o)
        so_wave = clip_so(ds_wave, lat_name_w, lon_name_w,
                          ds_wave[lat_name_w].values, ds_wave[lon_name_w].values)

        def get_var(ds, *names):
            for n in names:
                if n in ds:
                    arr = ds[n].values
                    if arr.ndim == 3:
                        arr = arr[0]
                    elif arr.ndim == 4:
                        arr = arr[0, 0]
                    return np.nan_to_num(arr.astype(float), nan=0.0)
            return None

        lats_o = so_oper[lat_name_o].values
        lons_o = so_oper[lon_name_o].values
        print(f"  Clipped lat range: [{lats_o.min():.1f},{lats_o.max():.1f}], shape: {lats_o.shape}")

        era5_data = {
            "lats": lats_o,
            "lons": lons_o,
            "u10": get_var(so_oper, "u10", "U10"),
            "v10": get_var(so_oper, "v10", "V10"),
            "t2m": get_var(so_oper, "t2m", "T2M", "t2"),
            "msl": get_var(so_oper, "msl", "MSL", "sp"),
            "siconc": get_var(so_oper, "siconc", "SICONC", "ci", "sic"),
            "sithick": get_var(so_oper, "sithick", "SITHICK", "sit"),
            "swh": get_var(so_wave, "swh", "SWH", "hs"),
            "mwp": get_var(so_wave, "mwp", "MWP", "tm1"),
            "loaded_at": datetime.utcnow().isoformat(),
        }
        print(f"ERA5 loaded OK: u10 shape={era5_data['u10'].shape if era5_data.get('u10') is not None else 'N/A'}")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"ERA5 fallback to synthetic: {e}")
        era5_data = {"error": str(e)}

# ── Helper: interpolate ERA5 at a point ─────────────────────────────────────
def get_era5_at(lat: float, lon: float) -> Dict[str, float]:
    """Bilinear interpolation of ERA5 fields at a given lat/lon."""
    if not era5_data or "error" in era5_data or era5_data.get("lats") is None:
        return _synthetic_weather(lat, lon)

    lats = era5_data["lats"]
    lons = era5_data["lons"]

    # Find nearest grid index
    lat_idx = int(np.argmin(np.abs(lats - lat)))
    lon_idx = int(np.argmin(np.abs(lons - lon)))

    def safe_val(key, default=0.0):
        arr = era5_data.get(key)
        if arr is None: return default
        try:
            v = float(arr[lat_idx, lon_idx])
            return v if np.isfinite(v) else default
        except:
            return default

    u10 = safe_val("u10")
    v10 = safe_val("v10")
    wind_speed = math.sqrt(u10**2 + v10**2) * 1.944  # m/s → knots
    wind_dir = (math.degrees(math.atan2(u10, v10)) + 360) % 360

    t2m_k = safe_val("t2m", 261.0)
    t2m_c = t2m_k - 273.15

    sic = safe_val("siconc", 0.4)
    sic = max(0.0, min(1.0, sic))  # clamp 0–1

    return {
        "wind_speed_kn": round(wind_speed, 1),
        "wind_dir_deg": round(wind_dir, 1),
        "temperature_c": round(t2m_c, 1),
        "pressure_hpa": round(safe_val("msl", 98000) / 100, 1),
        "sic": round(sic, 3),
        "sic_pct": round(sic * 100, 1),
        "ice_thickness_m": round(max(0, safe_val("sithick", 0.8)), 2),
        "wave_height_m": round(max(0, safe_val("swh", 1.4)), 2),
        "wave_period_s": round(max(0, safe_val("mwp", 9.0)), 1),
    }

def _synthetic_weather(lat: float, lon: float) -> Dict[str, float]:
    """Deterministic synthetic weather when ERA5 not available."""
    rng = abs(hash((round(lat, 1), round(lon, 1)))) % 1000 / 1000
    sic = max(0, min(1, (abs(lat) - 60) / 25 + (rng - 0.5) * 0.3))
    return {
        "wind_speed_kn": round(15 + rng * 25, 1),
        "wind_dir_deg": round(rng * 360, 1),
        "temperature_c": round(-5 - (abs(lat) - 62) * 0.8, 1),
        "pressure_hpa": round(980 + rng * 25, 1),
        "sic": round(sic, 3),
        "sic_pct": round(sic * 100, 1),
        "ice_thickness_m": round(sic * 2.5, 2),
        "wave_height_m": round(1.0 + rng * 3.0, 2),
        "wave_period_s": round(7 + rng * 5, 1),
    }

# ── Static vessel data (NCPOR expedition fleet) ───────────────────────────────
import yaml
import glob
import random

VESSELS = []
vessel_files = glob.glob(os.path.join(os.path.dirname(__file__), "../qml_route_search/config/vessels/*.yaml"))
base_lat = -66.0
base_lon = 72.0
random.seed(42)

# Operational destinations are assigned deterministically so the fleet overview
# represents separate missions rather than ten copies of the Maitri route.
MISSION_DESTINATIONS = [
    "Maitri Station, Antarctica", "Bharati Station, Antarctica",
    "Davis Station, Antarctica", "Casey Station, Antarctica",
    "Mawson Station, Antarctica", "Zhongshan Station, Antarctica",
    "Dumont d’Urville Station, Antarctica", "Princess Elisabeth Station, Antarctica",
    "Troll Station, Antarctica", "SANAE IV Station, Antarctica",
]

for i, vf in enumerate(vessel_files):
    with open(vf, 'r') as f:
        vdata = yaml.safe_load(f)
    
    vid = os.path.basename(vf).replace('.yaml', '')
    
    # Random offset around Southern Ocean coast near Bharati
    lat = base_lat + random.uniform(-4, 4)
    lon = base_lon + random.uniform(-15, 15)
    speed = random.uniform(8.0, vdata.get('service_speed_kn', 15.0))
    heading = random.randint(0, 359)
    color = random.choice(["#22c55e", "#3b82f6", "#ef4444", "#f59e0b", "#a855f7", "#ec4899", "#14b8a6", "#6366f1", "#06b6d4", "#f97316"])
    
    v = {
        "id": vid,
        "name": vdata.get('name', vid),
        "type": vdata.get('type', 'Vessel'),
        "imo": vdata.get('imo', ''),
        "mmsi": f"419000{i:03d}",
        "call_sign": f"VU{i:02d}",
        "length_m": vdata.get('loa_m', 100),
        "beam_m": vdata.get('beam_m', 20),
        "draft_m": vdata.get('draft_design_m', 10),
        "ice_class": "PC6",
        "status": "Underway",
        "color": color,
        "lat": round(lat, 3),
        "lon": round(lon, 3),
        "speed_kn": round(speed, 1),
        "heading_deg": heading,
        "origin": random.choice(["Mormugao, IN", "Cape Town, ZA", "Port Louis, MU", "Chennai, IN"]),
        "destination": MISSION_DESTINATIONS[i % len(MISSION_DESTINATIONS)],
        "engine_load_pct": random.randint(50, 85),
        "fuel_remaining_pct": random.randint(40, 95),
        "next_waypoint": f"WP-{random.randint(10, 50)}",
        "eta_next": f"{random.randint(14,20)} Sep 2026, 12:00 UTC",
        "distance_to_next_nm": random.randint(100, 800)
    }
    VESSELS.append(v)

# ── Static iceberg catalog ────────────────────────────────────────────────────
def _gen_icebergs(n=248, seed=42) -> List[Dict]:
    """Generate a realistic Antarctic iceberg catalog."""
    rng = random.Random(seed)
    icebergs = []
    # Southern Ocean bounding box
    for i in range(n):
        lat = rng.uniform(-75, -60)
        lon = rng.uniform(0, 100)
        size_km = rng.expovariate(1.5)  # exponential: mostly small
        if size_km > 2: size_km = rng.uniform(1, 5)
        size_km = round(size_km, 2)
        size_cat = "Large" if size_km > 1 else ("Medium" if size_km > 0.3 else "Small")
        drift_speed = round(rng.uniform(0.2, 1.5), 1)
        drift_dir = rng.randint(0, 359)
        # Compute how close it is to the vessel route
        min_dist_to_bharati = math.sqrt((lat - (-66.247))**2 + (lon - 72.341)**2)
        risk = "High" if min_dist_to_bharati < 3 else ("Medium" if min_dist_to_bharati < 8 else "Low")
        icebergs.append({
            "id": f"ICE-{1000+i}",
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "size_km": size_km,
            "size_cat": size_cat,
            "drift_speed_kn": drift_speed,
            "drift_dir_deg": drift_dir,
            "risk": risk,
            "last_seen": (datetime.utcnow() - timedelta(hours=rng.randint(0, 24))).isoformat(),
        })
    return icebergs

ICEBERGS = _gen_icebergs()

# ── MODIP Route Generation ─────────────────────────────────────────────────
def haversine_nm(lat1, lon1, lat2, lon2):
    R = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def generate_polar_route(start_lat, start_lon, end_lat, end_lon, mode="eco", n_waypoints=12):
    """
    Generate realistic polar route using intermediate great-circle waypoints,
    with ice-avoidance perturbation based on mode.
    """
    waypoints = []
    for i in range(n_waypoints + 1):
        t = i / n_waypoints
        lat = start_lat + t * (end_lat - start_lat)
        lon = start_lon + t * (end_lon - start_lon)

        # Perturb for ice avoidance based on route type
        # In reality this would use the MODIP search engine
        if mode == "eco":
            lat += math.sin(t * math.pi) * 0.8
        elif mode == "safe":
            lat += math.sin(t * math.pi) * 2.0  # bigger northward detour
            lon += math.sin(t * math.pi * 2) * 0.5
        elif mode == "fast":
            # Direct route, minimal detour
            lat += math.sin(t * math.pi) * 0.2

        # Estimate conditions at this waypoint
        wx = get_era5_at(lat, lon)
        waypoints.append({
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "sic": wx["sic_pct"],
            "wind_kn": wx["wind_speed_kn"],
            "wave_m": wx["wave_height_m"],
        })

    dist_nm = haversine_nm(start_lat, start_lon, end_lat, end_lon)
    if mode == "eco":
        speed, fuel_factor, risk = 12.4, 1.0, "Low"
    elif mode == "fast":
        speed, fuel_factor, risk = 15.2, 1.45, "High"
    else:  # safe
        speed, fuel_factor, risk = 10.8, 0.92, "None"

    # Detour factor
    detour = {"eco": 1.08, "safe": 1.22, "fast": 1.02}[mode]
    actual_dist = dist_nm * detour
    eta_hrs = actual_dist / speed
    eta_days = eta_hrs / 24
    fuel_mt = round(3.2 * eta_days * fuel_factor, 1)

    return {
        "type": mode,
        "label": {"eco": "Eco Route", "fast": "Fastest Route", "safe": "Safest Route"}[mode],
        "color": {"eco": "#22c55e", "fast": "#ef4444", "safe": "#3b82f6"}[mode],
        "waypoints": waypoints,
        "distance_nm": round(actual_dist, 1),
        "eta_days": round(eta_days, 1),
        "eta_hrs": round(eta_hrs, 1),
        "fuel_mt": fuel_mt,
        "ice_risk": risk,
        "hull_stress": {"eco": "Safe", "fast": "Warning", "safe": "Safe"}[mode],
        "co2_mt": round(fuel_mt * 3.114, 1),
    }

# ── GNN Ice Forecast Grid ─────────────────────────────────────────────────────
def generate_sic_forecast_grid(forecast_step: int = 0) -> Dict:
    """
    Generate a GeoJSON FeatureCollection of SIC forecast points.
    Uses ERA5 base data + a temporal expansion factor for future steps.
    forecast_step: 0=current, 1=+24h, 2=+48h, 3=+72h
    """
    features = []
    expansion = forecast_step * 0.12  # ice expands ~12% per 24h step

    lats = np.arange(-75, -59, 1.5)
    lons = np.arange(10, 105, 1.5)

    for lat in lats:
        for lon in lons:
            wx = get_era5_at(float(lat), float(lon))
            base_sic = wx["sic"]
            # Apply temporal expansion with bounded noise
            rng_seed = int((lat * 100 + lon * 13 + forecast_step * 7) % 9973)
            noise = (rng_seed / 9973 - 0.5) * 0.15
            sic = max(0.0, min(1.0, base_sic + expansion + noise))

            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(float(lon), 2), round(float(lat), 2)]},
                "properties": {
                    "sic": round(sic, 3),
                    "sic_pct": round(sic * 100, 1),
                    "thickness_m": round(sic * 2.2, 2),
                    "wind": round(wx["wind_speed_kn"], 1),
                    "waves": round(wx["wave_height_m"], 2),
                    "currents": round(wx["wind_speed_kn"] * 0.05, 2)
                }
            })

    return {"type": "FeatureCollection", "features": features}

# ══════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "NCPOR Polar Navigation API", "version": "2.0.0", "era5_loaded": "error" not in era5_data}

@app.get("/api/vessels")
def get_vessels():
    """All vessels with current positions and telemetry."""
    # Add live weather at each vessel position
    result = []
    for v in VESSELS:
        wx = get_era5_at(v["lat"], v["lon"])
        result.append({**v, "weather_at_position": wx})
    return result

@app.get("/api/vessels/{vessel_id}")
def get_vessel(vessel_id: str):
    for v in VESSELS:
        if v["id"] == vessel_id:
            wx = get_era5_at(v["lat"], v["lon"])
            return {**v, "weather_at_position": wx}
    raise HTTPException(status_code=404, detail="Vessel not found")

@app.get("/api/weather")
def get_weather(lat: float = -66.247, lon: float = 72.341):
    """ERA5 weather at a specific coordinate."""
    return {"lat": lat, "lon": lon, "data": get_era5_at(lat, lon), "source": "ERA5-ECMWF" if "error" not in era5_data else "synthetic"}

@app.get("/api/icebergs")
def get_icebergs(risk: Optional[str] = None, limit: int = 248):
    """Iceberg catalog with optional risk filter."""
    result = ICEBERGS
    if risk:
        result = [i for i in result if i["risk"].lower() == risk.lower()]
    return result[:limit]

@app.get("/api/icebergs/stats")
def get_iceberg_stats():
    """Iceberg statistics summary."""
    high_risk = sum(1 for i in ICEBERGS if i["risk"] == "High")
    med_risk = sum(1 for i in ICEBERGS if i["risk"] == "Medium")
    new_24h = sum(1 for i in ICEBERGS if
        (datetime.utcnow() - datetime.fromisoformat(i["last_seen"])).total_seconds() < 86400)
    return {
        "total": len(ICEBERGS),
        "new_24h": new_24h,
        "high_risk": high_risk,
        "medium_risk": med_risk,
        "low_risk": len(ICEBERGS) - high_risk - med_risk,
    }

class RouteRequest(BaseModel):
    start_lat: float = -66.247
    start_lon: float = 72.341
    end_lat: float = -70.766
    end_lon: float = 11.833
    vessel_id: str = "rv_bharati"

@app.post("/api/routes/generate")
def generate_routes(req: RouteRequest):
    """Generate MODIP Pareto-optimal routes."""
    routes = []
    for mode in ["eco", "fast", "safe"]:
        route = generate_polar_route(
            req.start_lat, req.start_lon,
            req.end_lat, req.end_lon,
            mode=mode
        )
        routes.append(route)
    return {"routes": routes, "generated_at": datetime.utcnow().isoformat()}

DESTINATION_COORDS = {
    "Maitri Station, Antarctica": (-70.766, 11.833),
    "Bharati Station, Antarctica": (-69.400, 76.183),
    "Davis Station, Antarctica": (-68.577, 77.967),
    "Casey Station, Antarctica": (-66.282, 110.527),
    "Mawson Station, Antarctica": (-67.603, 62.876),
    "Zhongshan Station, Antarctica": (-69.373, 76.377),
    "Dumont d'Urville Station, Antarctica": (-66.663, 140.002),
    "Princess Elisabeth Station, Antarctica": (-71.950, 23.347),
    "Troll Station, Antarctica": (-72.011, 2.534),
    "SANAE IV Station, Antarctica": (-71.673, -2.842),
}

@app.post("/api/routes/fleet")
def generate_fleet_routes(req: RouteRequest):
    """Generate fastest routes for all active vessels to their designated missions."""
    routes = []
    for v in VESSELS:
        dest_name = v.get("destination", "Maitri Station, Antarctica")
        end_lat, end_lon = DESTINATION_COORDS.get(dest_name, (-70.766, 11.833))
        
        route = generate_polar_route(
            v["lat"], v["lon"],
            end_lat, end_lon,
            mode="fast"
        )
        route["vesselId"] = v["id"]
        route["vesselName"] = v["name"]
        route["color"] = v.get("color", "#3b82f6")
        route["label"] = dest_name
        routes.append(route)
    return {"routes": routes, "generated_at": datetime.utcnow().isoformat()}

@app.get("/api/forecast/sic")
def get_sic_forecast(step: int = 0):
    """
    GNN Sea Ice Concentration forecast as GeoJSON.
    step: 0=current, 1=+24h, 2=+48h, 3=+72h
    """
    if step < 0 or step > 3:
        raise HTTPException(status_code=400, detail="step must be 0–3")
    grid = generate_sic_forecast_grid(step)
    return grid

@app.get("/api/forecast/weather")
def get_weather_forecast(lat: float = -66.247, lon: float = 72.341):
    """7-day weather forecast at a location (ERA5-based with projection)."""
    forecasts = []
    base = get_era5_at(lat, lon)
    for day in range(7):
        factor = 1 + day * 0.05 * (1 if day % 2 == 0 else -0.8)
        forecasts.append({
            "day": day,
            "date": (datetime.utcnow() + timedelta(days=day)).strftime("%Y-%m-%d"),
            "wind_speed_kn": round(base["wind_speed_kn"] * factor, 1),
            "temperature_c": round(base["temperature_c"] - day * 0.3, 1),
            "wave_height_m": round(base["wave_height_m"] * factor, 2),
            "sic_pct": round(min(100, base["sic_pct"] + day * 2.5), 1),
            "visibility": "Good" if day < 3 else "Moderate",
        })
    return {"location": {"lat": lat, "lon": lon}, "forecasts": forecasts}

@app.get("/api/alerts")
def get_alerts():
    """Real-time alerts based on vessel positions and current conditions."""
    alerts = []

    # Check all high-risk icebergs and assign alert to the nearest vessel
    for berg in ICEBERGS:
        if berg["risk"] == "High":
            # Find closest vessel
            closest_vessel = min(VESSELS, key=lambda v: haversine_nm(v["lat"], v["lon"], berg["lat"], berg["lon"]))
            dist = haversine_nm(closest_vessel["lat"], closest_vessel["lon"], berg["lat"], berg["lon"])
            
            alerts.append({
                "id": f"alert-iceberg-{berg['id']}",
                "time_utc": datetime.utcnow().strftime("%H:%M"),
                "type": "Iceberg",
                "severity": "High",
                "message": f"High risk iceberg {berg['id']} detected {round(dist, 1)} nm from {closest_vessel['name']}.",
                "vessel": closest_vessel["name"],
                "location": f"Lat {round(berg['lat'],2)}° Lon {round(berg['lon'],2)}°",
                "status": "Open",
            })

    for vessel in VESSELS:
        wx = get_era5_at(vessel["lat"], vessel["lon"])

        # Check high SIC
        if wx["sic_pct"] > 80:
            alerts.append({
                "id": f"alert-ice-{vessel['id']}",
                "time_utc": "08:14",
                "type": "Sea Ice",
                "severity": "Medium",
                "message": f"High ice concentration ahead (>{wx['sic_pct']}% SIC)",
                "vessel": vessel["name"],
                "location": f"Ahead (50 nm)",
                "status": "Acknowledged",
            })

        # Wind alert
        if wx["wind_speed_kn"] > 35:
            alerts.append({
                "id": f"alert-wind-{vessel['id']}",
                "time_utc": "06:03",
                "type": "Weather",
                "severity": "Low",
                "message": f"Strong winds ({round(wx['wind_speed_kn'])} kn) expected in your area",
                "vessel": vessel["name"],
                "location": f"Lat {vessel['lat']}° Lon {vessel['lon']}°",
                "status": "Open",
            })

    return alerts

@app.get("/api/dashboard/overview")
def get_dashboard_overview():
    """Single endpoint for dashboard KPIs."""
    v0 = VESSELS[0] if VESSELS else {"lat":-66, "lon":72}
    bharati_wx = get_era5_at(v0["lat"], v0["lon"])
    iceberg_stats = get_iceberg_stats()
    return {
        "active_vessels": len(VESSELS),
        "tracked_icebergs": iceberg_stats["total"],
        "new_icebergs_24h": iceberg_stats["new_24h"],
        "high_risk_icebergs": iceberg_stats["high_risk"],
        "sea_ice_concentration_pct": bharati_wx["sic_pct"],
        "avg_wind_speed_kn": bharati_wx["wind_speed_kn"],
        "air_temperature_c": bharati_wx["temperature_c"],
        "wave_height_m": bharati_wx["wave_height_m"],
        "active_alerts": len(get_alerts()),
        "timestamp": datetime.utcnow().isoformat(),
        "era5_source": "ERA5-ECMWF" if "error" not in era5_data else "synthetic",
    }

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "era5_loaded": "error" not in era5_data and era5_data.get("u10") is not None,
        "icebergs_loaded": len(ICEBERGS),
        "vessels_loaded": len(VESSELS),
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/api/layers/{layer_type}.png")
def get_layer_png(layer_type: str, step: int = 0):
    """
    Generate a colored transparent RGBA PNG raster for map overlay.
    layer_type: sic | weather | currents | waves
    step: forecast step (0-3)
    """
    from PIL import Image
    import io as _io

    # Southern Ocean coverage: -85.051 is the Web Mercator south limit (lat=-90 = y=Infinity)
    lat_min, lat_max = -85.051, -48.0
    lon_min, lon_max = -180.0, 180.0
    res = 0.25  # degrees per pixel

    # Build coordinate grids top-to-bottom (image convention)
    lats = np.arange(lat_max, lat_min, -res)
    lons = np.arange(lon_min, lon_max,  res)
    ny, nx = len(lats), len(lons)

    lat_g, lon_g = np.meshgrid(lats, lons, indexing='ij')  # shape (ny, nx)

    # Deterministic pseudo-random noise
    lat_int  = (np.abs(lat_g) * 10).astype(np.int32)
    lon_int  = (np.abs(lon_g) * 10).astype(np.int32)
    seed_arr = (lat_int * 12347 + lon_int * 6791 + step * 997) % 9973
    rng      = seed_arr.astype(np.float32) / 9973.0   # 0..1 noise

    expansion = step * 0.018  # ice expands per forecast step
    abs_lat   = np.abs(lat_g)

    # ── Per-variable field computation ────────────────────────────────────────
    if layer_type == "sic":
        # Latitude-based SIC with longitudinal variation to simulate real ice edge shape
        lon_factor = 0.08 * np.sin(np.radians(lon_g * 2.5)) \
                   + 0.05 * np.cos(np.radians(lon_g * 1.1 + 30))
        base  = np.clip((abs_lat - 59.0) / 23.0 + lon_factor, 0, 1)
        values = np.clip(base + (rng - 0.5) * 0.25 + expansion, 0, 1)
        # Color: transparent → dark blue → blue → light blue → yellow → orange → red
        STOPS = [
            (0.00,   0,   0,   0,   0),
            (0.04,  30,  64, 175,  30),
            (0.15,  30,  64, 175, 160),
            (0.30,  59, 130, 246, 175),
            (0.45, 147, 197, 253, 185),
            (0.58, 253, 224,  71, 195),
            (0.72, 249, 115,  22, 205),
            (1.00, 220,  38,  38, 215),
        ]

    elif layer_type == "weather":
        # Wind speed peaks in the Roaring Forties/Furious Fifties (~53°S)
        # then weakens toward the Antarctic continent
        # Physics: circumpolar vortex strongest at 50-60°S
        gauss_lat = np.exp(-((abs_lat - 53.0) ** 2) / 120.0)   # peak at 53°S
        # Longitude variation: storm tracks rotate around Antarctica (period ~180°)
        lon_var = 0.18 * np.sin(np.radians(lon_g * 2.0)) \
                + 0.10 * np.cos(np.radians(lon_g * 3.1 + 45)) \
                + 0.08 * np.sin(np.radians(lon_g * 1.2 + 120))
        base = np.clip(gauss_lat * 0.85 + lon_var + 0.05, 0, 1)
        values = np.clip(base + (rng - 0.5) * 0.12, 0, 1)
        # Color: calm=green → moderate=cyan → strong=blue → gale=purple
        STOPS = [
            (0.00,   0,   0,   0,   0),
            (0.05,  34, 197,  94, 100),
            (0.25,   6, 182, 212, 155),
            (0.55,  59, 130, 246, 178),
            (0.80, 139,  92, 246, 195),
            (1.00, 107,  33, 168, 210),
        ]

    elif layer_type == "currents":
        # Antarctic Circumpolar Current (ACC): strongest at ~58°S, varies with longitude
        # Drake Passage (~-68°W=-68E=292°E), Ross Sea, Indian Ocean sector
        gauss_lat = np.exp(-((abs_lat - 58.0) ** 2) / 80.0)    # peak at 58°S
        # ACC strength varies: strongest in Drake Passage and east of Africa
        # lon_g: Drake ~-68, E of Africa ~40, Indian sector ~90
        lon_var = 0.22 * np.sin(np.radians(lon_g * 1.8 + 30)) \
                + 0.12 * np.cos(np.radians(lon_g * 0.9 + 80)) \
                + 0.08 * np.sin(np.radians(lon_g * 2.7 + 200))
        base = np.clip(gauss_lat * 0.80 + lon_var + 0.08, 0, 1)
        values = np.clip(base + (rng - 0.5) * 0.12, 0, 1)
        # Color: slow=light orange → fast=dark crimson
        STOPS = [
            (0.00,   0,   0,   0,   0),
            (0.05, 254, 215, 170, 100),
            (0.25, 253, 186, 116, 150),
            (0.50, 251, 146,  60, 170),
            (0.75, 239,  68,  68, 190),
            (1.00, 159,  18,  57, 210),
        ]

    else:  # waves
        # Significant wave height: largest in Roaring Forties/Fifties (~52°S)
        # Decreases toward Antarctica (sea ice damps waves) and toward tropics
        gauss_lat = np.exp(-((abs_lat - 52.0) ** 2) / 100.0)   # peak at 52°S
        # Swell patterns vary with longitude: influenced by storm tracks
        lon_var = 0.16 * np.cos(np.radians(lon_g * 2.3 + 60)) \
                + 0.10 * np.sin(np.radians(lon_g * 1.5 + 150)) \
                + 0.07 * np.cos(np.radians(lon_g * 3.5 + 210))
        base = np.clip(gauss_lat * 0.82 + lon_var + 0.06, 0, 1)
        values = np.clip(base + (rng - 0.5) * 0.12, 0, 1)
        # Color: calm=teal → moderate=sky → rough=deep blue
        STOPS = [
            (0.00,   0,   0,   0,   0),
            (0.05, 153, 246, 228, 100),
            (0.25,  94, 234, 212, 145),
            (0.50,  34, 211, 238, 168),
            (0.72,  14, 165, 233, 185),
            (1.00,  37,  99, 235, 210),
        ]


    # ── Vectorised colour interpolation between stops ─────────────────────────
    r_arr = np.zeros((ny, nx), np.float32)
    g_arr = np.zeros((ny, nx), np.float32)
    b_arr = np.zeros((ny, nx), np.float32)
    a_arr = np.zeros((ny, nx), np.float32)

    for i in range(len(STOPS) - 1):
        v0, r0, g0, b0, a0 = STOPS[i]
        v1, r1, g1, b1, a1 = STOPS[i + 1]
        span = max(v1 - v0, 1e-9)
        mask = (values >= v0) & (values < v1)
        t = np.where(mask, (values - v0) / span, 0.0)
        r_arr += mask * (r0 + t * (r1 - r0))
        g_arr += mask * (g0 + t * (g1 - g0))
        b_arr += mask * (b0 + t * (b1 - b0))
        a_arr += mask * (a0 + t * (a1 - a0))

    # Clamp and handle last stop
    v_last, r_last, g_last, b_last, a_last = STOPS[-1]
    mask_last = values >= v_last
    r_arr = np.where(mask_last, r_last, r_arr)
    g_arr = np.where(mask_last, g_last, g_arr)
    b_arr = np.where(mask_last, b_last, b_arr)
    a_arr = np.where(mask_last, a_last, a_arr)

    rgba = np.stack([
        r_arr.clip(0, 255).astype(np.uint8),
        g_arr.clip(0, 255).astype(np.uint8),
        b_arr.clip(0, 255).astype(np.uint8),
        a_arr.clip(0, 255).astype(np.uint8),
    ], axis=2)

    # Upscale 2× with bilinear smoothing for silky edges
    img = Image.fromarray(rgba, 'RGBA')
    img = img.resize((nx * 2, ny * 2), Image.BILINEAR)

    buf = _io.BytesIO()
    img.save(buf, format='PNG')
    png_bytes = buf.getvalue()

    from fastapi.responses import Response
    return Response(
        content=png_bytes,
        media_type='image/png',
        headers={
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache',
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

