"""
Benchmark Suite — Compares our QML MODIP pipeline against standard maritime routing baselines.

Baselines implemented:
  1. Great Circle Route (GCR)         — Shortest distance, zero weather awareness
  2. Dijkstra + Full Physics           — Classical grid search running Holtrop-Mennen at every node
  3. Classical Isochrone Method         — Traditional weather routing (isochrone expansion)
  4. QML MODIP Pipeline (Ours)          — Quantum ML cost model + 4D MODIP search

Metrics compared:
  - Total fuel consumption (kg)
  - Total voyage time (hours)
  - Maximum roll risk encountered
  - Maximum slamming force encountered
  - Average speed loss (knots)
  - Computation time (seconds)

Usage:
    python scripts/benchmark.py --vessel sci_chennai --origin mumbai --destination singapore
"""

import sys
import os
import math
import time
import logging
import argparse
import yaml
import torch
import numpy as np
import pyproj
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.vessel_loader import load_all_vessels
from src.label_generator import HoltropMennenLabels
from src.cost_model import QMLCostModel
from src.surrogate import SurrogateMLP
from src.vessel_mlp import vessel_features_from_profile, EdgeFeatures, encode_vessel_edge_features
from src.search.wavefront import WavefrontState
from src.search.pareto_pruning import pareto_prune

logging.basicConfig(level=logging.INFO, format="%(asctime)s [benchmark] %(levelname)s: %(message)s")
logger = logging.getLogger("benchmark")

GEOD = pyproj.Geod(ellps='WGS84')

# ─────────────────────────────────────────────────────────────────────────────
# Heuristics & Route Evaluation
# ─────────────────────────────────────────────────────────────────────────────

class SurrogateWrapper:
    """Wrapper to make SurrogateMLP compatible with candidate_gen which expects a QMLCostModel interface"""
    def __init__(self, surrogate_mlp):
        self.surrogate_mlp = surrogate_mlp
        
    def __call__(self, z_fusion, theta_weather, theta_ship):
        preds = self.surrogate_mlp(z_fusion, theta_weather, theta_ship)
        return self.surrogate_mlp.decode_predictions(preds)
        
    def forward_cached_cnn(self, z_weather, vessel_route_features, theta_weather, theta_ship):
        import torch
        # Fusion is accessible because we attach it below
        z_vessel = self.fusion.vessel_mlp(vessel_route_features)
        z_fusion = torch.cat([z_weather, z_vessel], dim=1)
        return self(z_fusion, theta_weather, theta_ship)

# ─────────────────────────────────────────────────────────────────────────────
# Common structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkWaypoint:
    lat: float
    lon: float
    heading_deg: float
    speed_kn: float
    fuel_leg_kg: float
    time_leg_hr: float
    roll_risk: float
    slam_force: float
    speed_loss_kn: float
    wave_drag_kn: float
    wind_resist_kn: float

@dataclass
class BenchmarkResult:
    method_name: str
    waypoints: List[BenchmarkWaypoint]
    total_fuel_kg: float
    total_time_hr: float
    total_distance_nm: float
    max_roll_risk: float
    max_slam_force: float
    max_comfort: float
    max_green_water: float
    max_prop_emerge: float
    avg_speed_loss_kn: float
    computation_time_s: float
    n_nodes_evaluated: int


def haversine_nm(lat1, lon1, lat2, lon2):
    """Haversine distance in nautical miles."""
    R = 3440.065
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def simulate_weather(lat, lon, seed=42, weather_intensity=0.0):
    """
    Deterministic synthetic weather for a point.
    Uses lat/lon as a hash to create spatially coherent weather patterns.
    """
    rng = np.random.RandomState(int(abs(lat * 1000 + lon * 100)) % (2**31))
    # Spatially varying wave height (Global background)
    base_hs = 1.0 + 2.5 * math.exp(-((lat + 10)**2) / 200)
    
    # Permanent moderate monsoon swells to force natural path divergence even in "Clear Weather"
    d_arabian = haversine_nm(lat, lon, 16.0, 65.0)
    if d_arabian < 900:
        base_hs += 5.5 * math.exp(-(d_arabian**2) / 100000)
        
    d_bengal = haversine_nm(lat, lon, 14.0, 88.0)
    if d_bengal < 900:
        base_hs += 5.5 * math.exp(-(d_bengal**2) / 100000)
    
    # If weather_intensity is > 0, we introduce massive cyclones to force MODIP divergence
    if weather_intensity > 0:
        # Cyclone 1: Arabian Sea (affects sci_chennai / ssl_bharat)
        d1 = haversine_nm(lat, lon, 14.0, 70.0) # Shifted west to block the direct path
        if d1 < 1200:
            base_hs += 35.0 * math.exp(-(d1**2) / 120000) * weather_intensity
            
        # Cyclone 2: West of India (affects desh_shobha)
        d2 = haversine_nm(lat, lon, 18.0, 69.5)
        if d2 < 1200:
            base_hs += 35.0 * math.exp(-(d2**2) / 120000) * weather_intensity
            
        # Cyclone 3: Bay of Bengal
        d3 = haversine_nm(lat, lon, 12.0, 85.0)
        if d3 < 1200:
            base_hs += 35.0 * math.exp(-(d3**2) / 120000) * weather_intensity
    
    hs = max(0.3, base_hs + rng.normal(0, 0.5))
    wave_period = max(4.0, 6.0 + 1.5 * hs + rng.normal(0, 1.0))
    wave_dir = (180 + 30 * math.sin(math.radians(lon * 3))) % 360
    wind_speed = max(1.0, 3.0 + 1.2 * hs + rng.normal(0, 1.5))
    wind_dir = (wave_dir + rng.normal(0, 20)) % 360
    return {
        'hs': hs,
        'wave_period': wave_period,
        'wave_dir': wave_dir,
        'wind_speed': wind_speed,
        'wind_dir': wind_dir,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Baseline 1: Great Circle Route (no weather awareness)
# ─────────────────────────────────────────────────────────────────────────────

def great_circle_route(origin, dest, vessel_profile, physics: HoltropMennenLabels, n_legs=20) -> BenchmarkResult:
    """
    Follow the geodesic great circle route with equal spacing.
    Still subject to weather effects (fuel/speed loss) but doesn't try to avoid them.
    """
    t0 = time.time()
    nodes_evaluated = 0

    lat1, lon1 = origin
    lat2, lon2 = dest

    # Generate waypoints along the great circle
    points = GEOD.npts(lon1, lat1, lon2, lat2, n_legs - 1)
    all_points = [(lat1, lon1)] + [(p[1], p[0]) for p in points] + [(lat2, lon2)]

    waypoints = []
    total_fuel = 0.0
    total_time = 0.0
    total_distance = 0.0
    max_roll = 0.0
    max_slam = 0.0
    max_comfort = 0.0
    max_green = 0.0
    max_prop = 0.0
    speed_losses = []

    for i in range(len(all_points) - 1):
        p1 = all_points[i]
        p2 = all_points[i + 1]
        leg_dist = haversine_nm(p1[0], p1[1], p2[0], p2[1])
        fwd_az, _, _ = GEOD.inv(p1[1], p1[0], p2[1], p2[0])
        heading = fwd_az % 360

        weather = simulate_weather(p1[0], p1[1])
        labels = physics.compute_labels(
            hs=weather['hs'],
            wave_period=weather['wave_period'],
            wave_dir_deg=weather['wave_dir'],
            wind_speed=weather['wind_speed'],
            wind_dir_deg=weather['wind_dir'],
            ship_heading_deg=heading,
        )
        nodes_evaluated += 1

        effective_speed = max(1.0, vessel_profile.service_speed_kn - labels['speed_loss'])
        leg_time = leg_dist / effective_speed
        leg_fuel = labels['fuel_rate'] * leg_dist  # fuel_rate is kg/NM

        waypoints.append(BenchmarkWaypoint(
            lat=p1[0], lon=p1[1], heading_deg=heading, speed_kn=effective_speed,
            fuel_leg_kg=leg_fuel, time_leg_hr=leg_time,
            roll_risk=labels['roll_risk'], slam_force=labels['slam_force'],
            speed_loss_kn=labels['speed_loss'],
            wave_drag_kn=labels['wave_drag'], wind_resist_kn=labels['wind_resistance'],
        ))

        total_fuel += leg_fuel
        total_time += leg_time
        total_distance += leg_dist
        max_roll = max(max_roll, labels['roll_risk'])
        max_slam = max(max_slam, labels['slam_force'])
        max_comfort = max(max_comfort, labels['comfort_index'])
        max_green = max(max_green, labels['green_water_risk'])
        max_prop = max(max_prop, labels['prop_emergence_risk'])
        speed_losses.append(labels['speed_loss'])

    return BenchmarkResult(
        method_name="Great Circle (No Weather Routing)",
        waypoints=waypoints,
        total_fuel_kg=total_fuel,
        total_time_hr=total_time,
        total_distance_nm=total_distance,
        max_roll_risk=max_roll,
        max_slam_force=max_slam,
        max_comfort=max_comfort,
        max_green_water=max_green,
        max_prop_emerge=max_prop,
        avg_speed_loss_kn=float(np.mean(speed_losses)) if speed_losses else 0.0,
        computation_time_s=time.time() - t0,
        n_nodes_evaluated=nodes_evaluated,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Baseline 2: Dijkstra + Full Physics (classical grid search)
# ─────────────────────────────────────────────────────────────────────────────

def dijkstra_full_physics(origin, dest, vessel_profile, physics: HoltropMennenLabels,
                          grid_res_deg=2.0, heading_fan_deg=60.0, heading_step_deg=15.0,
                          dt_hours=6.0) -> BenchmarkResult:
    """
    Classical Dijkstra on a spatial grid, evaluating the full Holtrop-Mennen physics
    at every expanded node. This is the 'gold standard' for accuracy but is slow.
    """
    import heapq
    t0 = time.time()
    nodes_evaluated = 0
    capture_radius_nm = 50.0

    # State: (cost, lat, lon, t_elapsed_hr, fuel_kg, max_roll, max_slam, speed_losses, path)
    start = (0.0, origin[0], origin[1], 0.0, 0.0, 0.0, 0.0, [], [(origin[0], origin[1])])
    heap = [start]
    visited = set()
    best_result = None

    while heap:
        cost, lat, lon, t_elapsed, fuel, m_roll, m_slam, s_losses, path = heapq.heappop(heap)

        # Discretize for visited check
        grid_key = (round(lat / grid_res_deg), round(lon / grid_res_deg))
        if grid_key in visited:
            continue
        visited.add(grid_key)

        dist_to_dest = haversine_nm(lat, lon, dest[0], dest[1])
        if dist_to_dest <= capture_radius_nm:
            best_result = BenchmarkResult(
                method_name="Dijkstra + Full Physics (Classical)",
                waypoints=[],  # Simplified
                total_fuel_kg=fuel,
                total_time_hr=t_elapsed,
                total_distance_nm=sum(
                    haversine_nm(path[i][0], path[i][1], path[i+1][0], path[i+1][1])
                    for i in range(len(path) - 1)
                ),
                max_roll_risk=m_roll,
                max_slam_force=m_slam,
                max_comfort=0.0,
                max_green_water=0.0,
                max_prop_emerge=0.0,
                avg_speed_loss_kn=float(np.mean(s_losses)) if s_losses else 0.0,
                computation_time_s=time.time() - t0,
                n_nodes_evaluated=nodes_evaluated,
            )
            break

        # Generate successors
        fwd_az, _, _ = GEOD.inv(lon, lat, dest[1], dest[0])
        bearing = fwd_az % 360

        for hdg_offset in np.arange(-heading_fan_deg, heading_fan_deg + heading_step_deg, heading_step_deg):
            hdg = (bearing + hdg_offset) % 360

            weather = simulate_weather(lat, lon)
            labels = physics.compute_labels(
                hs=weather['hs'],
                wave_period=weather['wave_period'],
                wave_dir_deg=weather['wave_dir'],
                wind_speed=weather['wind_speed'],
                wind_dir_deg=weather['wind_dir'],
                ship_heading_deg=hdg,
            )
            nodes_evaluated += 1

            effective_speed = max(1.0, vessel_profile.service_speed_kn - labels['speed_loss'])
            dist_step = effective_speed * dt_hours
            dist_m = dist_step * 1852.0

            new_lon, new_lat, _ = GEOD.fwd(lon, lat, hdg, dist_m)

            leg_fuel = labels['fuel_rate'] * dist_step
            new_fuel = fuel + leg_fuel
            new_time = t_elapsed + dt_hours
            new_roll = max(m_roll, labels['roll_risk'])
            new_slam = max(m_slam, labels['slam_force'])
            new_losses = s_losses + [labels['speed_loss']]

            # Multi-objective cost: weighted sum (fuel-dominated)
            node_cost = new_fuel + new_time * 100 + new_roll * 5000

            new_path = path + [(new_lat, new_lon)]
            heapq.heappush(heap, (node_cost, new_lat, new_lon, new_time, new_fuel, new_roll, new_slam, new_losses, new_path))

        if nodes_evaluated > 50000:
            logger.warning("Dijkstra: hit node limit (50000), returning best so far")
            break

    if best_result is None:
        # Fallback: didn't reach destination, report what we have
        best_result = BenchmarkResult(
            method_name="Dijkstra + Full Physics (Classical)",
            waypoints=[], total_fuel_kg=fuel, total_time_hr=t_elapsed,
            total_distance_nm=0, max_roll_risk=m_roll, max_slam_force=m_slam,
            max_comfort=0.0, max_green_water=0.0, max_prop_emerge=0.0,
            avg_speed_loss_kn=float(np.mean(s_losses)) if s_losses else 0.0,
            computation_time_s=time.time() - t0, n_nodes_evaluated=nodes_evaluated,
        )

    return best_result


# ─────────────────────────────────────────────────────────────────────────────
# Baseline 3: Classical Isochrone Method
# ─────────────────────────────────────────────────────────────────────────────

def isochrone_method(origin, dest, vessel_profile, physics: HoltropMennenLabels,
                     heading_fan_deg=90.0, heading_step_deg=10.0,
                     dt_hours=6.0, max_iterations=100) -> BenchmarkResult:
    """
    Traditional isochrone weather routing.
    Expands wavefronts at fixed time intervals, keeps the outermost points on each bearing,
    and iterates until reaching the destination.
    """
    t0 = time.time()
    nodes_evaluated = 0
    capture_radius_nm = 50.0

    # State: (lat, lon, cum_fuel, cum_time, max_roll, max_slam, speed_losses, path)
    frontier = [(origin[0], origin[1], 0.0, 0.0, 0.0, 0.0, [], [origin])]
    best_result = None

    for iteration in range(max_iterations):
        if not frontier:
            break

        next_frontier = []
        for state in frontier:
            lat, lon, fuel, t_elapsed, m_roll, m_slam, s_losses, path = state

            dist_to_dest = haversine_nm(lat, lon, dest[0], dest[1])
            if dist_to_dest <= capture_radius_nm:
                candidate = BenchmarkResult(
                    method_name="Classical Isochrone Method",
                    waypoints=[],
                    total_fuel_kg=fuel,
                    total_time_hr=t_elapsed,
                    total_distance_nm=sum(
                        haversine_nm(path[i][0], path[i][1], path[i+1][0], path[i+1][1])
                        for i in range(len(path) - 1)
                    ),
                    max_roll_risk=m_roll,
                    max_slam_force=m_slam,
                    max_comfort=0.0,
                    max_green_water=0.0,
                    max_prop_emerge=0.0,
                    avg_speed_loss_kn=float(np.mean(s_losses)) if s_losses else 0.0,
                    computation_time_s=time.time() - t0,
                    n_nodes_evaluated=nodes_evaluated,
                )
                if best_result is None or candidate.total_fuel_kg < best_result.total_fuel_kg:
                    best_result = candidate
                continue

            fwd_az, _, _ = GEOD.inv(lon, lat, dest[1], dest[0])
            bearing = fwd_az % 360

            for hdg_offset in np.arange(-heading_fan_deg, heading_fan_deg + heading_step_deg, heading_step_deg):
                hdg = (bearing + hdg_offset) % 360

                weather = simulate_weather(lat, lon)
                labels = physics.compute_labels(
                    hs=weather['hs'],
                    wave_period=weather['wave_period'],
                    wave_dir_deg=weather['wave_dir'],
                    wind_speed=weather['wind_speed'],
                    wind_dir_deg=weather['wind_dir'],
                    ship_heading_deg=hdg,
                )
                nodes_evaluated += 1

                effective_speed = max(1.0, vessel_profile.service_speed_kn - labels['speed_loss'])
                dist_step = effective_speed * dt_hours
                dist_m = dist_step * 1852.0
                new_lon, new_lat, _ = GEOD.fwd(lon, lat, hdg, dist_m)

                leg_fuel = labels['fuel_rate'] * dist_step
                new_fuel = fuel + leg_fuel
                new_time = t_elapsed + dt_hours
                new_roll = max(m_roll, labels['roll_risk'])
                new_slam = max(m_slam, labels['slam_force'])
                new_losses = s_losses + [labels['speed_loss']]
                new_path = path + [(new_lat, new_lon)]

                next_frontier.append((new_lat, new_lon, new_fuel, new_time, new_roll, new_slam, new_losses, new_path))

        # Isochrone pruning: keep only the furthest-progressed point per bearing sector
        if next_frontier:
            sector_best = {}
            for state in next_frontier:
                lat, lon = state[0], state[1]
                fwd_az, _, remaining = GEOD.inv(lon, lat, dest[1], dest[0])
                sector = int(fwd_az % 360) // 10  # 10-degree sectors
                if sector not in sector_best or remaining < sector_best[sector][1]:
                    sector_best[sector] = (state, remaining)
            frontier = [v[0] for v in sector_best.values()]
        else:
            frontier = []

        if best_result is not None:
            break

    if best_result is None:
        # Didn't reach destination
        best_state = min(frontier, key=lambda s: haversine_nm(s[0], s[1], dest[0], dest[1])) if frontier else frontier[0]
        best_result = BenchmarkResult(
            method_name="Classical Isochrone Method",
            waypoints=[], total_fuel_kg=best_state[2], total_time_hr=best_state[3],
            total_distance_nm=0, max_roll_risk=best_state[4], max_slam_force=best_state[5],
            max_comfort=0.0, max_green_water=0.0, max_prop_emerge=0.0,
            avg_speed_loss_kn=float(np.mean(best_state[6])) if best_state[6] else 0.0,
            computation_time_s=time.time() - t0, n_nodes_evaluated=nodes_evaluated,
        )

    return best_result


def manual_isochrone_route(origin, dest, vessel_profile, physics: HoltropMennenLabels,
                           heading_fan_deg=90.0, heading_step_deg=10.0,
                           dt_hours=6.0, max_iterations=100) -> BenchmarkResult:
    """
    Simulates the real-world manual routing process.
    The route is planned using a STALE weather forecast (seed=41) which
    is perfectly accurate for 12 hours ago, but wrong now.
    The chosen route is then evaluated in the TRUE weather (seed=42) as it executes.
    """
    t0 = time.time()
    nodes_evaluated = 0
    capture_radius_nm = 50.0

    # (lat, lon, fuel, t_elapsed, m_roll, m_slam, s_losses, path_points)
    frontier = [(origin[0], origin[1], 0.0, 0.0, 0.0, 0.0, [], [(origin[0], origin[1], 0.0)])]
    best_path = None

    for iteration in range(max_iterations):
        if not frontier:
            break

        next_frontier = []
        for state in frontier:
            lat, lon, fuel, t_elapsed, m_roll, m_slam, s_losses, path = state

            dist_to_dest = haversine_nm(lat, lon, dest[0], dest[1])
            if dist_to_dest <= capture_radius_nm:
                if best_path is None or fuel < best_path[2]:
                    best_path = state
                continue

            fwd_az, _, _ = GEOD.inv(lon, lat, dest[1], dest[0])
            bearing = fwd_az % 360

            for hdg_offset in np.arange(-heading_fan_deg, heading_fan_deg + heading_step_deg, heading_step_deg):
                hdg = (bearing + hdg_offset) % 360

                # USE STALE FORECAST FOR PLANNING (seed=41)
                weather = simulate_weather(lat, lon, seed=41)
                labels = physics.compute_labels(
                    hs=weather['hs'],
                    wave_period=weather['wave_period'],
                    wave_dir_deg=weather['wave_dir'],
                    wind_speed=weather['wind_speed'],
                    wind_dir_deg=weather['wind_dir'],
                    ship_heading_deg=hdg,
                )
                nodes_evaluated += 1

                effective_speed = max(1.0, vessel_profile.service_speed_kn - labels['speed_loss'])
                dist_step = effective_speed * dt_hours
                dist_m = dist_step * 1852.0
                new_lon, new_lat, _ = GEOD.fwd(lon, lat, hdg, dist_m)

                leg_fuel = labels['fuel_rate'] * dist_step
                new_fuel = fuel + leg_fuel
                new_time = t_elapsed + dt_hours
                new_roll = max(m_roll, labels['roll_risk'])
                new_slam = max(m_slam, labels['slam_force'])
                new_losses = s_losses + [labels['speed_loss']]
                new_path = path + [(new_lat, new_lon, hdg)]

                next_frontier.append((new_lat, new_lon, new_fuel, new_time, new_roll, new_slam, new_losses, new_path))

        # Isochrone pruning
        if next_frontier:
            sector_best = {}
            for state in next_frontier:
                lat, lon = state[0], state[1]
                fwd_az, _, remaining = GEOD.inv(lon, lat, dest[1], dest[0])
                sector = int(fwd_az % 360) // 10
                if sector not in sector_best or remaining < sector_best[sector][1]:
                    sector_best[sector] = (state, remaining)
            frontier = [v[0] for v in sector_best.values()]
        else:
            frontier = []

        if best_path is not None:
            break

    search_time = time.time() - t0

    if best_path is None:
        best_path = min(frontier, key=lambda s: haversine_nm(s[0], s[1], dest[0], dest[1])) if frontier else None
        if best_path is None:
            return BenchmarkResult("Real-World Manual (Stale Weather)", [], 0,0,0,0,0,0,0,0,0.0,search_time,nodes_evaluated)

    # RE-EVALUATE THE CHOSEN PATH IN TRUE WEATHER (seed=42)
    path_points = best_path[7]
    
    total_fuel_gt = 0.0
    total_time_gt = 0.0
    total_distance_gt = 0.0
    max_roll_gt = 0.0
    max_slam_gt = 0.0
    max_comfort_gt = 0.0
    max_green_gt = 0.0
    max_prop_gt = 0.0
    speed_losses_gt = []

    for i in range(len(path_points) - 1):
        p1 = path_points[i]
        p2 = path_points[i + 1]
        lat1, lon1 = p1[0], p1[1]
        lat2, lon2 = p2[0], p2[1]
        heading = p2[2] if len(p2) > 2 else 0.0

        leg_dist = haversine_nm(lat1, lon1, lat2, lon2)
        # TRUE WEATHER
        weather = simulate_weather(lat1, lon1, seed=42)

        labels = physics.compute_labels(
            hs=weather['hs'],
            wave_period=weather['wave_period'],
            wave_dir_deg=weather['wave_dir'],
            wind_speed=weather['wind_speed'],
            wind_dir_deg=weather['wind_dir'],
            ship_heading_deg=heading,
        )

        effective_speed = max(1.0, vessel_profile.service_speed_kn - labels['speed_loss'])
        leg_time = leg_dist / effective_speed
        leg_fuel = labels['fuel_rate'] * leg_dist

        total_fuel_gt += leg_fuel
        total_time_gt += leg_time
        total_distance_gt += leg_dist
        max_roll_gt = max(max_roll_gt, labels['roll_risk'])
        max_slam_gt = max(max_slam_gt, labels['slam_force'])
        max_comfort_gt = max(max_comfort_gt, labels['comfort_index'])
        max_green_gt = max(max_green_gt, labels['green_water_risk'])
        max_prop_gt = max(max_prop_gt, labels['prop_emergence_risk'])
        speed_losses_gt.append(labels['speed_loss'])

    return BenchmarkResult(
        method_name="Real-World Manual (Stale Weather)",
        waypoints=[],
        total_fuel_kg=total_fuel_gt,
        total_time_hr=total_time_gt,
        total_distance_nm=total_distance_gt,
        max_roll_risk=max_roll_gt,
        max_slam_force=max_slam_gt,
        max_comfort=max_comfort_gt,
        max_green_water=max_green_gt,
        max_prop_emerge=max_prop_gt,
        avg_speed_loss_kn=float(np.mean(speed_losses_gt)) if speed_losses_gt else 0.0,
        computation_time_s=search_time,
        n_nodes_evaluated=nodes_evaluated,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Method 5: QML MODIP Pipeline (Ours)
# ─────────────────────────────────────────────────────────────────────────────

def qml_modip_route(origin, dest, vessel_profile, physics: HoltropMennenLabels,
                    model: QMLCostModel,
                    heading_fan_deg=90.0, heading_step_deg=10.0,
                    dt_hours=6.0, max_iterations=100) -> BenchmarkResult:
    """
    Our QML pipeline: uses the trained Quantum ML model for cost evaluation
    during SEARCH, but then re-evaluates the chosen route with ground truth
    Holtrop-Mennen physics for fair benchmarking.
    
    This separates "route selection quality" from "prediction accuracy".
    """
    t0 = time.time()
    nodes_evaluated = 0
    capture_radius_nm = 50.0
    vf = vessel_features_from_profile(vessel_profile)

    # Pre-compute CNN embedding once (frozen during inference)
    with torch.no_grad():
        mock_weather = torch.zeros(1, 8, 64, 64)
        z_weather = model.fusion.weather_cnn(mock_weather)

    # State is now a WavefrontState. We store the path using the `parent` pointer.
    start_state = WavefrontState(
        lat=origin[0], lon=origin[1], heading=0.0, t_elapsed_s=0.0,
        objectives=np.zeros(9), confidence_min=1.0, speed_kn=0.0, parent=None
    )
    frontier = [start_state]
    best_path = None
    reached_destinations = []

    with torch.no_grad():
        for iteration in range(max_iterations):
            if not frontier:
                break

            next_frontier = []
            active_states = []
            
            for state in frontier:
                dist_to_dest = haversine_nm(state.lat, state.lon, dest[0], dest[1])
                if dist_to_dest <= capture_radius_nm:
                    reached_destinations.append(state)
                else:
                    active_states.append(state)

            if reached_destinations:
                # We stop as soon as we have reached destinations, or we could continue to find better ones.
                # For benchmark speed, we stop at first reach.
                break
                
            if not active_states:
                break

            # ── BATCH: Collect ALL candidates across ALL active frontier states ──
            candidate_meta = []  # Store metadata for each candidate
            edge_vectors = []    # Batched edge feature vectors
            theta_weathers = []  # Batched weather angles
            theta_ships = []     # Batched ship headings

            for state in active_states:
                dist_to_dest = haversine_nm(state.lat, state.lon, dest[0], dest[1])
                fwd_az, _, _ = GEOD.inv(state.lon, state.lat, dest[1], dest[0])
                bearing = fwd_az % 360
                weather = simulate_weather(state.lat, state.lon)

                for hdg_offset in np.arange(-heading_fan_deg, heading_fan_deg + heading_step_deg, heading_step_deg):
                    hdg = (bearing + hdg_offset) % 360

                    ef = EdgeFeatures(
                        lat=state.lat, lon=state.lon,
                        heading_rad=math.radians(hdg),
                        bearing_to_dest_rad=math.radians(bearing),
                        distance_to_dest_nm=dist_to_dest,
                        elapsed_time_hr=state.t_elapsed_s / 3600.0,
                        current_speed_kn=vessel_profile.service_speed_kn,
                        ukc_m=50.0,
                        hs_m=weather['hs'],
                        wind_speed_ms=weather['wind_speed'],
                        encounter_angle_rad=math.radians(abs(weather['wave_dir'] - hdg) % 180),
                        wave_period_s=weather['wave_period'],
                    )
                    edge_vectors.append(encode_vessel_edge_features(vf, ef))
                    theta_weathers.append(math.radians(weather['wave_dir']))
                    theta_ships.append(math.radians(hdg))
                    candidate_meta.append((state, hdg, weather, dist_to_dest))

            if not candidate_meta:
                break

            # ── SINGLE BATCHED forward pass through the entire QML pipeline ──
            batch_edge = torch.stack(edge_vectors)                          # (N, 28)
            batch_z_weather = z_weather.expand(len(candidate_meta), -1)     # (N, 64)
            batch_theta_w = torch.tensor(theta_weathers)                    # (N,)
            batch_theta_s = torch.tensor(theta_ships)                       # (N,)

            batch_preds = model.forward_cached_cnn(
                z_weather=batch_z_weather,
                vessel_route_features=batch_edge,
                theta_weather=batch_theta_w,
                theta_ship=batch_theta_s,
            )
            nodes_evaluated += len(candidate_meta)

            # ── Unpack batched results into individual successor states ──
            for idx, (parent_state, hdg, weather, dist_to_dest) in enumerate(candidate_meta):
                speed_loss = batch_preds['speed_loss'][idx].item()
                fuel_rate = batch_preds['fuel_rate'][idx].item()
                wave_drag = batch_preds['wave_drag'][idx].item()
                wind_resist = batch_preds['wind_resistance'][idx].item()
                roll_risk = batch_preds['roll_risk'][idx].item()
                slam_force = batch_preds['slam_force'][idx].item()
                comfort = batch_preds['comfort_index'][idx].item()
                green_water = batch_preds['green_water_risk'][idx].item()
                prop_emerge = batch_preds['prop_emergence_risk'][idx].item()
                confidence = batch_preds['confidence'][idx].item()

                effective_speed = max(1.0, vessel_profile.service_speed_kn - speed_loss)
                dist_step = effective_speed * dt_hours
                dist_m = dist_step * 1852.0
                new_lon, new_lat, _ = GEOD.fwd(parent_state.lon, parent_state.lat, hdg, dist_m)

                new_fuel = parent_state.objectives[0] + (fuel_rate * dist_step)
                new_wave = parent_state.objectives[1] + (wave_drag * dist_step)
                new_wind = parent_state.objectives[2] + (wind_resist * dist_step)
                new_time = parent_state.objectives[3] + dt_hours
                new_roll = max(parent_state.objectives[4], roll_risk)
                new_slam = max(parent_state.objectives[5], slam_force)
                new_comfort = max(parent_state.objectives[6], comfort)
                new_green = max(parent_state.objectives[7], green_water)
                new_prop = max(parent_state.objectives[8], prop_emerge)
                
                new_obj = np.array([new_fuel, new_wave, new_wind, new_time, new_roll, new_slam, new_comfort, new_green, new_prop])

                cand = WavefrontState(
                    lat=new_lat, lon=new_lon, heading=hdg,
                    t_elapsed_s=parent_state.t_elapsed_s + (dt_hours * 3600.0),
                    objectives=new_obj,
                    confidence_min=min(parent_state.confidence_min, confidence),
                    speed_kn=effective_speed,
                    parent=parent_state,
                    safety_flags=parent_state.safety_flags + [speed_loss] # store speed losses here temporarily
                )
                next_frontier.append(cand)

            # 10D Pareto Pruning!
            frontier = pareto_prune(next_frontier)

            # Cap frontier to avoid explosion
            if len(frontier) > 50:
                frontier.sort(key=lambda s: haversine_nm(s.lat, s.lon, dest[0], dest[1]))
                frontier = frontier[:50]

    search_time = time.time() - t0

    if not reached_destinations:
        if not frontier:
            return BenchmarkResult("QML MODIP Pipeline (Ours)", [], 0, 0, 0, 0, 0, 0.0, search_time, nodes_evaluated)
        # fallback to closest to dest
        best_state = min(frontier, key=lambda s: haversine_nm(s.lat, s.lon, dest[0], dest[1]))
    else:
        # Pareto prune the final destinations and pick the most fuel-efficient one
        final_dests = pareto_prune(reached_destinations)
        best_state = min(final_dests, key=lambda s: s.objectives[0])

    # ── RE-EVALUATE the QML-selected route with GROUND TRUTH physics ──
    # This is the key fairness fix: the QML model chose the route,
    # but we measure its quality using the same Holtrop-Mennen formulas
    # that the classical baselines use.
    curr = best_state
    path_points = []
    while curr is not None:
        path_points.append((curr.lat, curr.lon, curr.heading))
        curr = curr.parent
    path_points.reverse()
    
    total_fuel_gt = 0.0
    total_time_gt = 0.0
    total_distance_gt = 0.0
    max_roll_gt = 0.0
    max_slam_gt = 0.0
    max_comfort_gt = 0.0
    max_green_gt = 0.0
    max_prop_gt = 0.0
    speed_losses_gt = []

    for i in range(len(path_points) - 1):
        p1 = path_points[i]
        p2 = path_points[i + 1]
        lat1, lon1 = p1[0], p1[1]
        lat2, lon2 = p2[0], p2[1]
        heading = p2[2] if len(p2) > 2 else 0.0

        leg_dist = haversine_nm(lat1, lon1, lat2, lon2)
        weather = simulate_weather(lat1, lon1)

        # Ground truth physics evaluation
        labels = physics.compute_labels(
            hs=weather['hs'],
            wave_period=weather['wave_period'],
            wave_dir_deg=weather['wave_dir'],
            wind_speed=weather['wind_speed'],
            wind_dir_deg=weather['wind_dir'],
            ship_heading_deg=heading,
        )

        effective_speed = max(1.0, vessel_profile.service_speed_kn - labels['speed_loss'])
        leg_time = leg_dist / effective_speed
        leg_fuel = labels['fuel_rate'] * leg_dist

        total_fuel_gt += leg_fuel
        total_time_gt += leg_time
        total_distance_gt += leg_dist
        max_roll_gt = max(max_roll_gt, labels['roll_risk'])
        max_slam_gt = max(max_slam_gt, labels['slam_force'])
        max_comfort_gt = max(max_comfort_gt, labels['comfort_index'])
        max_green_gt = max(max_green_gt, labels['green_water_risk'])
        max_prop_gt = max(max_prop_gt, labels['prop_emergence_risk'])
        speed_losses_gt.append(labels['speed_loss'])

    return BenchmarkResult(
        method_name="QML MODIP Pipeline (Ours)",
        waypoints=[],
        total_fuel_kg=total_fuel_gt,
        total_time_hr=total_time_gt,
        total_distance_nm=total_distance_gt,
        max_roll_risk=max_roll_gt,
        max_slam_force=max_slam_gt,
        max_comfort=max_comfort_gt,
        max_green_water=max_green_gt,
        max_prop_emerge=max_prop_gt,
        avg_speed_loss_kn=float(np.mean(speed_losses_gt)) if speed_losses_gt else 0.0,
        computation_time_s=search_time,
        n_nodes_evaluated=nodes_evaluated,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

PORTS = {
    'mumbai': (18.9489, 72.8289),
    'singapore': (1.2644, 103.8198),
    'chennai': (13.0827, 80.2707),
    'colombo': (6.9271, 79.8612),
    'cochin': (9.9312, 76.2673),
    'dubai': (25.2048, 55.2708),
    'kolkata': (22.5726, 88.3639),
    'port_blair': (11.6234, 92.7265),
    'aden': (12.7855, 45.0187),
    'male': (4.1755, 73.5093),
}


def main():
    parser = argparse.ArgumentParser(description="Benchmark QML pipeline against classical routing methods")
    parser.add_argument("--vessel", type=str, default="sci_chennai")
    parser.add_argument("--origin", type=str, default="mumbai")
    parser.add_argument("--destination", type=str, default="colombo")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/qml_cost_model.pt")
    args = parser.parse_args()

    # Load config
    config_path = PROJECT_ROOT / "config" / "default.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Load vessel
    vessels = load_all_vessels(str(PROJECT_ROOT / "config" / "vessels"))
    if args.vessel not in vessels:
        logger.error("Vessel '%s' not found. Available: %s", args.vessel, list(vessels.keys()))
        sys.exit(1)
    vessel = vessels[args.vessel]
    logger.info("Vessel: %s (IMO %s, %s)", vessel.name, vessel.imo, vessel.vessel_type)

    # Resolve ports
    origin = PORTS.get(args.origin.lower())
    dest = PORTS.get(args.destination.lower())
    if origin is None or dest is None:
        logger.error("Unknown port. Available: %s", list(PORTS.keys()))
        sys.exit(1)

    gc_dist = haversine_nm(origin[0], origin[1], dest[0], dest[1])
    logger.info("Route: %s → %s (GC distance: %.1f NM)", args.origin, args.destination, gc_dist)

    # Physics engine (ground truth)
    physics = HoltropMennenLabels(vessel)

    # Load QML model
    checkpoint_path = PROJECT_ROOT / args.checkpoint
    qml_config = config.get('cost_model', {})
    model = QMLCostModel(
        config=qml_config, 
        cnn_checkpoint=str(PROJECT_ROOT / "checkpoints" / "cnn_surrogate.pt")
    )
    if checkpoint_path.exists():
        ckpt = torch.load(str(checkpoint_path), map_location='cpu', weights_only=False)
        if isinstance(ckpt, dict) and 'model_state_dict' in ckpt:
            model.load_state_dict(ckpt['model_state_dict'], strict=False)
        else:
            model.load_state_dict(ckpt, strict=False)
        logger.info("Loaded QML checkpoint from %s", checkpoint_path)
    else:
        logger.warning("No QML checkpoint found at %s, using random weights", checkpoint_path)
    model.eval()

    # Load Surrogate model
    surrogate = SurrogateMLP(input_dim=98, hidden_dim=128, output_dim=10)
    surrogate_path = PROJECT_ROOT / "checkpoints" / "surrogate_mlp.pt"
    if surrogate_path.exists():
        surrogate.load_state_dict(torch.load(surrogate_path, map_location='cpu'))
        logger.info("Loaded Knowledge Distilled Surrogate from %s", surrogate_path)
    surrogate.eval()
    surrogate_wrapper = SurrogateWrapper(surrogate)
    surrogate_wrapper.fusion = model.fusion # pass through fusion for candidate_gen

    # ── Run all 6 methods ──
    logger.info("\n" + "=" * 80)
    logger.info("Running benchmarks...")
    logger.info("=" * 80)

    results = []

    # 1. Great Circle
    logger.info("\n[1/6] Great Circle Route...")
    gcr = great_circle_route(origin, dest, vessel, physics)
    results.append(gcr)
    logger.info("  Done in %.2fs", gcr.computation_time_s)

    # 2. Dijkstra + Full Physics
    logger.info("\n[2/6] Dijkstra + Full Physics...")
    dijkstra = dijkstra_full_physics(origin, dest, vessel, physics)
    results.append(dijkstra)
    logger.info("  Done in %.2fs (%d nodes)", dijkstra.computation_time_s, dijkstra.n_nodes_evaluated)

    # 3. Classical Isochrone
    logger.info("\n[3/6] Classical Isochrone Method...")
    iso = isochrone_method(origin, dest, vessel, physics)
    results.append(iso)
    logger.info("  Done in %.2fs (%d nodes)", iso.computation_time_s, iso.n_nodes_evaluated)

    # 4. Real-World Manual (Stale Weather)
    logger.info("\n[4/6] Real-World Manual (Stale Weather)...")
    manual = manual_isochrone_route(origin, dest, vessel, physics)
    results.append(manual)
    logger.info("  Done in %.2fs (%d nodes)", manual.computation_time_s, manual.n_nodes_evaluated)

    # 5. QML MODIP
    logger.info("\n[5/6] QML MODIP Pipeline...")
    qml = qml_modip_route(origin, dest, vessel, physics, model)
    results.append(qml)
    logger.info("  Done in %.2fs (%d nodes)", qml.computation_time_s, qml.n_nodes_evaluated)

    # 6. KD MLP MODIP
    logger.info("\n[6/6] KD MLP (Surrogate) MODIP Pipeline...")
    # Wrap model but attach fusion module to the wrapper since modip_search accesses model.fusion
    kd_mlp = qml_modip_route(origin, dest, vessel, physics, surrogate_wrapper)
    kd_mlp.name = "Knowledge Distilled Surrogate"
    results.append(kd_mlp)
    logger.info("  Done in %.2fs (%d nodes)", kd_mlp.computation_time_s, kd_mlp.n_nodes_evaluated)

    # ── Print comparison table ──
    logger.info("\n" + "=" * 80)
    logger.info("BENCHMARK RESULTS: %s → %s | Vessel: %s", args.origin.upper(), args.destination.upper(), vessel.name)
    logger.info("=" * 80)

    header = f"{'Method':<35} {'Fuel(kg)':>9} {'Time(hr)':>9} {'MaxRoll':>7} {'MaxSlam':>7} {'Comfrt':>6} {'GrnWtr':>6} {'PropEm':>6} {'Compute(s)':>10} {'Nodes':>6}"
    logger.info(header)
    logger.info("-" * len(header))

    for r in results:
        logger.info(
            f"{r.method_name:<35} {r.total_fuel_kg:>9.0f} {r.total_time_hr:>9.1f} "
            f"{r.max_roll_risk:>7.3f} {r.max_slam_force:>7.1f} {r.max_comfort:>6.1f} "
            f"{r.max_green_water:>6.3f} {r.max_prop_emerge:>6.3f} "
            f"{r.computation_time_s:>10.2f} {r.n_nodes_evaluated:>6d}"
        )

    # ── Compute improvements vs Great Circle ──
    gcr_result = results[0]
    logger.info("\n" + "-" * 80)
    logger.info("IMPROVEMENTS vs GREAT CIRCLE (baseline):")
    logger.info("-" * 80)
    for r in results[1:]:
        fuel_save = (1 - r.total_fuel_kg / max(gcr_result.total_fuel_kg, 1)) * 100
        time_diff = (r.total_time_hr - gcr_result.total_time_hr) / max(gcr_result.total_time_hr, 1) * 100
        roll_imp = (1 - r.max_roll_risk / max(gcr_result.max_roll_risk, 0.001)) * 100
        logger.info(
            f"  {r.method_name:<40} Fuel: {fuel_save:>+6.1f}% | Time: {time_diff:>+6.1f}% | Roll Risk: {roll_imp:>+6.1f}%"
        )

    # ── Speed comparison (physics calls/sec) ──
    logger.info("\n" + "-" * 80)
    logger.info("INFERENCE SPEED COMPARISON:")
    logger.info("-" * 80)
    for r in results[1:]:
        if r.computation_time_s > 0:
            throughput = r.n_nodes_evaluated / r.computation_time_s
            logger.info(f"  {r.method_name:<40} {throughput:>8.1f} nodes/sec")

    logger.info("\n" + "=" * 80)
    logger.info("Benchmark complete.")


if __name__ == "__main__":
    main()
