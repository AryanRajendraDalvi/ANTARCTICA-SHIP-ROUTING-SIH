import time
import math
import torch
import numpy as np
import pyproj
from typing import Dict, Any, List

from src.vessel_mlp import vessel_features_from_profile, EdgeFeatures, encode_vessel_edge_features
from src.search.wavefront import WavefrontState
from src.search.pareto_pruning import pareto_prune
from scripts.benchmark import haversine_nm, simulate_weather

GEOD = pyproj.Geod(ellps='WGS84')

def generate_surrogate_routes(origin, dest, vessel_profile, surrogate_wrapper, 
                              heading_fan_deg=90.0, heading_step_deg=10.0,
                              dt_hours=6.0, max_iterations=100, weather_intensity=0.0) -> List[Dict[str, Any]]:
    """
    Runs the wavefront search using the SurrogateMLP wrapper and returns 3 distinct 
    Pareto-optimal paths (Eco, Fastest, Safest) with their full 10D metrics.
    """
    t0 = time.time()
    capture_radius_nm = 50.0
    vf = vessel_features_from_profile(vessel_profile)

    # Pre-compute CNN embedding once (frozen during inference)
    with torch.no_grad():
        mock_weather = torch.zeros(1, 8, 64, 64)
        z_weather = surrogate_wrapper.fusion.weather_cnn(mock_weather)

    start_state = WavefrontState(
        lat=origin[0], lon=origin[1], heading=0.0, t_elapsed_s=0.0,
        objectives=np.zeros(9), confidence_min=1.0, speed_kn=0.0, parent=None
    )
    frontier = [start_state]
    reached_destinations = []

    with torch.no_grad():
        for iteration in range(max_iterations):
            if not frontier: break

            active_states = []
            for state in frontier:
                if haversine_nm(state.lat, state.lon, dest[0], dest[1]) <= capture_radius_nm:
                    reached_destinations.append(state)
                else:
                    active_states.append(state)

            if reached_destinations and len(reached_destinations) >= 10:
                break # We have enough destinations to choose from
                
            if not active_states: break

            candidate_meta = []
            edge_vectors = []
            theta_weathers = []
            theta_ships = []

            for state in active_states:
                dist_to_dest = haversine_nm(state.lat, state.lon, dest[0], dest[1])
                fwd_az, _, _ = GEOD.inv(state.lon, state.lat, dest[1], dest[0])
                bearing = fwd_az % 360
                weather = simulate_weather(state.lat, state.lon, weather_intensity=weather_intensity)

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

            if not candidate_meta: break

            batch_edge = torch.stack(edge_vectors)
            batch_z_weather = z_weather.expand(len(candidate_meta), -1)
            batch_theta_w = torch.tensor(theta_weathers)
            batch_theta_s = torch.tensor(theta_ships)

            # Use Surrogate Wrapper
            batch_preds = surrogate_wrapper.forward_cached_cnn(
                z_weather=batch_z_weather,
                vessel_route_features=batch_edge,
                theta_weather=batch_theta_w,
                theta_ship=batch_theta_s,
            )

            next_frontier = []
            pred_keys = ['fuel_rate', 'wave_drag', 'speed_loss', 'roll_risk', 'slam_force', 
                         'wind_resistance', 'comfort_index', 'green_water_risk', 'prop_emergence_risk', 'confidence']

            for i, (state, hdg, weather, dist) in enumerate(candidate_meta):
                speed = max(0.0, vessel_profile.service_speed_kn - batch_preds['speed_loss'][i].item())
                if speed < 1.0: continue
                
                # dt depends on distance to move. Let's move dt_hours.
                dt_s = dt_hours * 3600
                dist_moved = speed * dt_hours
                if dist_moved > dist:
                    dist_moved = dist
                    dt_s = (dist_moved / speed) * 3600

                new_lon, new_lat, _ = GEOD.fwd(state.lon, state.lat, hdg, dist_moved * 1852.0)
                
                # compute 9D objectives for this edge
                edge_obj = np.zeros(9)
                edge_obj[0] = batch_preds['fuel_rate'][i].item() * (dt_s / 3600.0) # Fuel total
                edge_obj[1] = batch_preds['wave_drag'][i].item() # max wave drag
                edge_obj[2] = batch_preds['speed_loss'][i].item() # max speed loss
                edge_obj[3] = batch_preds['roll_risk'][i].item() # max roll risk
                edge_obj[4] = batch_preds['slam_force'][i].item() # max slam force
                edge_obj[5] = batch_preds['wind_resistance'][i].item() # max wind res
                edge_obj[6] = batch_preds['comfort_index'][i].item() # max comfort
                edge_obj[7] = batch_preds['green_water_risk'][i].item() # max gw
                edge_obj[8] = batch_preds['prop_emergence_risk'][i].item() # max prop
                # Confidence is tracked separately
                conf = batch_preds['confidence'][i].item()

                # Accumulate state objectives
                new_obj = np.copy(state.objectives)
                new_obj[0] += edge_obj[0] # accumulate fuel
                # For others, we take the MAX along the route
                for k in range(1, 9):
                    new_obj[k] = max(new_obj[k], edge_obj[k])
                new_conf = min(state.confidence_min, conf)
                next_state = WavefrontState(
                    lat=new_lat, lon=new_lon, heading=hdg,
                    t_elapsed_s=state.t_elapsed_s + dt_s,
                    objectives=new_obj, confidence_min=new_conf,
                    speed_kn=speed, parent=state
                )
                next_frontier.append(next_state)

            frontier = pareto_prune(next_frontier)

    if not reached_destinations:
        # fallback if exact destination not reached
        reached_destinations = [min(frontier, key=lambda s: haversine_nm(s.lat, s.lon, dest[0], dest[1]))]

    final_dests = pareto_prune(reached_destinations)
    
    # Pick 3 extreme paths
    # Eco: min fuel
    eco_state = min(final_dests, key=lambda s: s.objectives[0])
    # Fast: min time
    fast_state = min(final_dests, key=lambda s: s.t_elapsed_s)
    # Safe: min (Roll + Slam)
    safe_state = min(final_dests, key=lambda s: s.objectives[3]*100 + s.objectives[4]/10)

    routes = []
    types = [('eco', eco_state), ('fastest', fast_state), ('safest', safe_state)]
    
    for t, state in types:
        path = []
        curr = state
        while curr:
            path.append({'lat': curr.lat, 'lon': curr.lon})
            curr = curr.parent
        path.reverse()
        
        # Add final exact destination
        if haversine_nm(path[-1]['lat'], path[-1]['lon'], dest[0], dest[1]) > 1.0:
            path.append({'lat': dest[0], 'lon': dest[1]})
            
        routes.append({
            'type': t,
            'waypoints': path,
            'metrics': {
                'fuel_rate': float(state.objectives[0]),
                'wave_drag': float(state.objectives[1]),
                'speed_loss': float(state.objectives[2]),
                'roll_risk': float(state.objectives[3]),
                'slam_force': float(state.objectives[4]),
                'wind_resistance': float(state.objectives[5]),
                'comfort_index': float(state.objectives[6]),
                'green_water_risk': float(state.objectives[7]),
                'prop_emergence_risk': float(state.objectives[8]),
                'confidence': float(state.confidence_min),
                'eta_hrs': float(state.t_elapsed_s / 3600.0)
            }
        })

    return routes
