import pyproj
import numpy as np
from typing import List, Dict, Any
from src.search.wavefront import WavefrontState

class CandidateGenerator:
    """
    Generates successor states (candidates) for a given wavefront state using a heading fan.
    """
    def __init__(self, heading_fan_deg: float = 60.0, heading_step_deg: float = 15.0, dt_hours: float = 6.0):
        self.heading_fan_deg = heading_fan_deg
        self.heading_step_deg = heading_step_deg
        self.dt_hours = dt_hours
        self.geod = pyproj.Geod(ellps='WGS84')

    def generate(self, parent_state: WavefrontState, destination: tuple, cost_model_outputs: Dict[str, Any], weather: dict, sog: float) -> List[WavefrontState]:
        """
        Generates candidates along a heading fan towards the destination.
        """
        dest_lat, dest_lon = destination
        fwd_az, back_az, dist = self.geod.inv(parent_state.lon, parent_state.lat, dest_lon, dest_lat)
        bearing = fwd_az % 360.0

        candidates = []
        headings = np.arange(bearing - self.heading_fan_deg, bearing + self.heading_fan_deg + self.heading_step_deg, self.heading_step_deg)
        
        dist_nm = sog * self.dt_hours
        dist_meters = dist_nm * 1852.0

        for hdg in headings:
            hdg = hdg % 360.0
            new_lon, new_lat, _ = self.geod.fwd(parent_state.lon, parent_state.lat, hdg, dist_meters)
            
            F_rate = cost_model_outputs.get('fuel_rate_kg_h', 0.0)
            R_wave = cost_model_outputs.get('r_wave_kn', 0.0)
            R_wind = cost_model_outputs.get('r_wind_kn', 0.0)
            roll_risk = cost_model_outputs.get('roll_risk', 0.0)
            slam_force = cost_model_outputs.get('slam_force', 0.0)
            comfort = cost_model_outputs.get('comfort', 0.0)
            green_water = cost_model_outputs.get('green_water', 0.0)
            prop_emerge = cost_model_outputs.get('prop_emerge', 0.0)
            confidence = cost_model_outputs.get('confidence', 1.0)
            
            fuel_used = F_rate * self.dt_hours
            wave_accum = R_wave * dist_nm
            wind_accum = R_wind * dist_nm
            
            new_fuel = parent_state.objectives[0] + fuel_used
            new_wave = parent_state.objectives[1] + wave_accum
            new_wind = parent_state.objectives[2] + wind_accum
            new_time_hrs = parent_state.objectives[3] + self.dt_hours
            new_roll = max(parent_state.objectives[4], roll_risk)
            new_slam = max(parent_state.objectives[5], slam_force)
            new_comfort = max(parent_state.objectives[6], comfort)
            new_green = max(parent_state.objectives[7], green_water)
            new_prop = max(parent_state.objectives[8], prop_emerge)
            
            new_obj = np.array([new_fuel, new_wave, new_wind, new_time_hrs, new_roll, new_slam, new_comfort, new_green, new_prop])
            
            cand = WavefrontState(
                lat=new_lat,
                lon=new_lon,
                heading=hdg,
                t_elapsed_s=parent_state.t_elapsed_s + (self.dt_hours * 3600.0),
                objectives=new_obj,
                confidence_min=min(parent_state.confidence_min, confidence),
                speed_kn=sog,
                parent=parent_state,
                safety_flags=[],
                weather_at_point=weather
            )
            candidates.append(cand)
            
        return candidates
