from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np
import math

@dataclass
class WavefrontState:
    """
    Represents a state in the 4D-MODIP search tree.
    Tracks position, time, and cumulative objectives.
    """
    lat: float
    lon: float
    heading: float  # degrees
    t_elapsed_s: float  # seconds since departure
    objectives: np.ndarray  # 9-D: [fuel, wave_drag, wind_drag, time, roll, slam, comfort, green_water, prop_emerge]
    confidence_min: float  # minimum confidence along path
    speed_kn: float  # current speed
    parent: Optional['WavefrontState'] = None
    safety_flags: List[str] = field(default_factory=list)
    weather_at_point: Optional[dict] = None

@dataclass  
class Route:
    """
    Reconstructed optimal route containing the sequence of states.
    """
    waypoints: List[WavefrontState]
    label: str  # e.g., FASTEST / CHEAPEST / MOST_COMFORTABLE
    total_distance_nm: float
    total_fuel_kg: float
    total_time_hours: float
    max_roll_risk: float
    max_slam_force: float
    max_comfort: float
    max_green_water: float
    max_prop_emerge: float

def distance_nm(state1: WavefrontState, state2: WavefrontState) -> float:
    """
    Computes the Haversine distance between two states in nautical miles.
    """
    R = 3440.065 # Radius of earth in nautical miles
    lat1, lon1 = math.radians(state1.lat), math.radians(state1.lon)
    lat2, lon2 = math.radians(state2.lat), math.radians(state2.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def bearing_deg(state1: WavefrontState, state2: WavefrontState) -> float:
    """
    Computes the initial bearing from state1 to state2 in degrees.
    """
    lat1, lon1 = math.radians(state1.lat), math.radians(state1.lon)
    lat2, lon2 = math.radians(state2.lat), math.radians(state2.lon)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    initial_bearing = math.atan2(x, y)
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360
    return compass_bearing
