from typing import List, Dict, Any
from datetime import datetime
from src.output.route_schema import RouteOutput

class RollingHorizonManager:
    """
    Manager for replanning and rolling horizon checks.
    Reference: Section 8
    """
    def __init__(self, search_engine, safety_checker, config: Dict[str, Any]):
        self.search_engine = search_engine
        self.safety_checker = safety_checker
        self.config = config

    def check_triggers(self, current_ais: Dict[str, Any], planned_route: RouteOutput, latest_weather_time: datetime) -> List[str]:
        """
        Check for conditions that trigger a replan.
        """
        triggers = []
        
        # 1. 6-hourly forecast refresh (mock check)
        # In reality, compare latest_weather_time with route.summary.last_update
        if (latest_weather_time - planned_route.summary.last_update).total_seconds() >= 6 * 3600:
            triggers.append("6_HOURLY_FORECAST_REFRESH")
            
        # 2. AIS drift > 10 NM
        # Find closest point on planned route and check distance
        # Mock logic:
        drift_nm = current_ais.get("drift_nm", 0.0)
        if drift_nm > 10.0:
            triggers.append("AIS_DRIFT_EXCEEDS_10NM")
            
        # 3. No-go intersects remaining route (mock check)
        nogo_intersect = current_ais.get("nogo_intersect", False)
        if nogo_intersect:
            triggers.append("NOGO_INTERSECTS_ROUTE")
            
        return triggers

    def replan(self, current_lat: float, current_lon: float, current_sog: float, current_cog: float, 
               t_now: datetime, destination: Dict[str, float], vessel: Dict[str, Any], 
               existing_route: RouteOutput) -> RouteOutput:
        """
        Replan the route from the current position to the destination.
        """
        # Re-run dynamic filter, search, etc.
        # This is a mock implementation combining sailed portion with new search
        
        # In a full implementation, you would call self.search_engine.search()
        
        # Splice existing route up to t_now with new simulated route
        sailed_waypoints = [wp for wp in existing_route.waypoints if wp.eta <= t_now]
        
        # Create a mock updated route
        updated_route = RouteOutput(
            summary=existing_route.summary,
            waypoints=sailed_waypoints # plus new waypoints...
        )
        updated_route.summary.last_update = t_now
        
        return updated_route
