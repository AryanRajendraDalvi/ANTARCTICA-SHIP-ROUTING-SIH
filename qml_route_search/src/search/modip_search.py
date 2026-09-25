import torch
import pyproj
import numpy as np
from typing import List
import math
from src.search.wavefront import WavefrontState, Route, distance_nm
from src.search.candidate_gen import CandidateGenerator
from src.search.weather_query import WeatherQueryEngine
from src.search.pareto_pruning import pareto_prune
from src.vessel_mlp import vessel_features_from_profile, EdgeFeatures, encode_vessel_edge_features

class MODIPSearch:
    """
    Multi-Objective Dynamic Isocline Programming (MODIP) orchestrator.
    Explores the search space expanding a wavefront and pruning dominated paths.
    """
    def __init__(self, cost_model, static_filter, dynamic_filter, weather_engine: WeatherQueryEngine, config: dict):
        self.cost_model = cost_model
        self.static_filter = static_filter
        self.dynamic_filter = dynamic_filter
        self.weather_engine = weather_engine
        self.config = config
        self.geod = pyproj.Geod(ellps='WGS84')
        self.candidate_gen = CandidateGenerator(
            heading_fan_deg=config.get('heading_fan_deg', 60.0),
            heading_step_deg=config.get('heading_step_deg', 15.0),
            dt_hours=config.get('dt_hours', 6.0)
        )
        self.capture_radius_nm = config.get('capture_radius_nm', 20.0)
        self.max_iterations = config.get('max_iterations', 100)

    def search(self, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float, t_depart: float, vessel_profile) -> List[Route]:
        start_state = WavefrontState(
            lat=origin_lat,
            lon=origin_lon,
            heading=0.0,
            t_elapsed_s=0.0,
            objectives=np.zeros(9),
            confidence_min=1.0,
            speed_kn=vessel_profile.service_speed_kn,
            parent=None
        )
        
        frontier = [start_state]
        destination = (dest_lat, dest_lon)
        reached_destinations = []
        dest_state_dummy = WavefrontState(lat=dest_lat, lon=dest_lon, heading=0, t_elapsed_s=0, objectives=np.zeros(9), confidence_min=1.0, speed_kn=0)
        
        # Precompute static vessel ML features and regional weather tensor for search
        vf = vessel_features_from_profile(vessel_profile)
        if self.cost_model is not None:
            # We mock the 64x64 weather tensor for the region during search and let the 
            # frozen CNN encode it to a static z_weather (1, 64) for all edges
            mock_weather_tensor = torch.zeros(1, 8, 64, 64)
            with torch.no_grad():
                z_weather = self.cost_model.fusion.weather_cnn(mock_weather_tensor)

        
        with torch.no_grad():
            for _ in range(self.max_iterations):
                if not frontier:
                    break
                    
                next_frontier = []
                for state in frontier:
                    # Check if reached destination
                    dist_to_dest = distance_nm(state, dest_state_dummy)
                    if dist_to_dest <= self.capture_radius_nm:
                        reached_destinations.append(state)
                        continue
                        
                    weather = self.weather_engine.query(state.lat, state.lon, t_depart, state.t_elapsed_s)
                    
                    if self.cost_model is not None:
                        # Construct 28-D edge feature vector for ML
                        dist_to_dest = distance_nm(state, dest_state_dummy)
                        ef = EdgeFeatures(
                            lat=state.lat,
                            lon=state.lon,
                            heading_rad=math.radians(state.heading),
                            bearing_to_dest_rad=math.radians(0), # Approximation for search state
                            distance_to_dest_nm=dist_to_dest,
                            elapsed_time_hr=state.t_elapsed_s / 3600.0,
                            current_speed_kn=state.speed_kn,
                            ukc_m=50.0, # Safe deep water assumption
                            hs_m=weather.get('hs', 2.0),
                            wind_speed_ms=weather.get('wind_speed', 5.0),
                            encounter_angle_rad=math.radians(weather.get('encounter_angle', 0.0)),
                            wave_period_s=weather.get('wave_period', 8.0)
                        )
                        edge_vector = encode_vessel_edge_features(vf, ef).unsqueeze(0)
                        
                        # Forward pass through QML Pipeline (Fast cached path)
                        preds = self.cost_model.forward_cached_cnn(
                            z_weather=z_weather,
                            vessel_route_features=edge_vector,
                            theta_weather=torch.tensor([math.radians(weather.get('wave_dir', 0.0))]),
                            theta_ship=torch.tensor([math.radians(state.heading)])
                        )
                        cost_model_outputs = {
                            'fuel_rate_kg_h': preds['fuel_rate'].item() * state.speed_kn, # convert to per hour
                            'r_wave_kn': preds['wave_drag'].item(),
                            'r_wind_kn': preds['wind_resistance'].item(),
                            'roll_risk': preds['roll_risk'].item(),
                            'slam_force': preds['slam_force'].item(),
                            'speed_loss_dv': preds['speed_loss'].item(),
                            'confidence': preds['confidence'].item()
                        }
                    else:
                        # Fallback simple distance-based heuristic cost for testing without model
                        cost_model_outputs = {
                            'fuel_rate_kg_h': 1000.0,
                            'r_wave_kn': 0.0,
                            'r_wind_kn': 0.0,
                            'roll_risk': 0.0,
                            'slam_force': 0.0,
                            'speed_loss_dv': 0.0,
                            'confidence': 1.0
                        }
                        
                    sog = self.weather_engine.compute_sog(
                        v_stw=vessel_profile.service_speed_kn,
                        speed_loss_dv=cost_model_outputs.get('speed_loss_dv', 0.0),
                        lat=state.lat,
                        lon=state.lon,
                        heading=state.heading,
                        t_query=t_depart + state.t_elapsed_s
                    )
                    
                    candidates = self.candidate_gen.generate(state, destination, cost_model_outputs, weather, sog)
                    
                    for cand in candidates:
                        if self.static_filter and hasattr(self.static_filter, 'is_node_valid'):
                            if not self.static_filter.is_node_valid(cand.lat, cand.lon):
                                continue
                        if self.dynamic_filter and hasattr(self.dynamic_filter, 'is_no_go'):
                            if self.dynamic_filter.is_no_go(cand.lat, cand.lon, t_depart + cand.t_elapsed_s):
                                continue
                        next_frontier.append(cand)
                        
                frontier = pareto_prune(next_frontier)
                
        if not reached_destinations:
            return []
            
        final_destinations = pareto_prune(reached_destinations)
        
        routes = []
        for state in final_destinations:
            waypoints = []
            curr = state
            while curr is not None:
                waypoints.append(curr)
                curr = curr.parent
            waypoints.reverse()
            
            route = Route(
                waypoints=waypoints,
                label="ROUTE",
                total_distance_nm=sum(distance_nm(waypoints[i], waypoints[i+1]) for i in range(len(waypoints)-1)) if len(waypoints)>1 else 0.0,
                total_fuel_kg=state.objectives[0],
                total_time_hours=state.objectives[3],
                max_roll_risk=state.objectives[4],
                max_slam_force=state.objectives[5],
                max_comfort=state.objectives[6],
                max_green_water=state.objectives[7],
                max_prop_emerge=state.objectives[8]
            )
            routes.append(route)
            
        if routes:
            fastest_idx = min(range(len(routes)), key=lambda i: routes[i].total_time_hours)
            cheapest_idx = min(range(len(routes)), key=lambda i: routes[i].total_fuel_kg)
            comfort_idx = min(range(len(routes)), key=lambda i: routes[i].max_roll_risk + routes[i].max_slam_force)
            
            routes[fastest_idx].label = "FASTEST"
            routes[cheapest_idx].label = "CHEAPEST"
            routes[comfort_idx].label = "MOST_COMFORTABLE"
            
        return routes
