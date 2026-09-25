import torch
from typing import Dict, Any
from src.output.route_schema import RouteOutput, RouteSummary
from datetime import datetime

class FallbackManager:
    """
    Manager for fallbacks in case of model failure or infeasible paths.
    Reference: Section 10
    """
    
    @staticmethod
    def check_upstream_health(z_fusion: torch.Tensor) -> bool:
        """
        Check for NaN or shape mismatch in tensor.
        """
        if torch.isnan(z_fusion).any():
            return False
        if z_fusion.dim() == 0 or z_fusion.shape[-1] != 96:
            return False
        return True

    @staticmethod
    def get_holtrop_fallback_cost(weather: Dict[str, Any], vessel: Dict[str, Any]) -> Dict[str, float]:
        """
        Calm-water costs when QML unavailable.
        """
        # Simplified calm water fallback
        v_knots = vessel.get("speed", 15.0)
        p_calm = 10000.0 * (v_knots / 15.0)**3  # kW (mock)
        sfoc = 0.180  # kg/kWh
        f_rate = (p_calm * sfoc) / (v_knots * 1852) if v_knots > 0 else 0.0
        
        return {
            "fuel_rate": f_rate,
            "speed_loss": 0.0,
            "confidence": 0.1  # Low confidence due to fallback
        }

    @staticmethod
    def get_climatological_weather(lat: float, lon: float, month: int) -> Dict[str, float]:
        """
        Monthly average fallback for weather.
        """
        return {
            "hs": 2.0,  # Average wave height
            "v_wind": 10.0,
            "theta_enc": 90.0
        }

    @staticmethod
    def handle_no_feasible_path(search_engine: Any, origin: tuple, dest: tuple, 
                                t_depart: datetime, vessel: Dict[str, Any], 
                                relaxation_factor: float = 1.5) -> RouteOutput:
        """
        Relax constraints and find path with ELEVATED_RISK flag.
        """
        # Mocking relaxed search
        summary = RouteSummary(
            label="RELAXED_FALLBACK",
            total_distance_nm=1000.0,
            total_fuel_t=100.0,
            total_time_hr=100.0,
            cii_attained=0.01,
            last_update=datetime.now()
        )
        # Empty waypoints for mock
        return RouteOutput(summary=summary, waypoints=[])
