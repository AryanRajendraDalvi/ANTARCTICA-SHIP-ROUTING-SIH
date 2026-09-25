from typing import List, Dict, Any

class EmissionsChecker:
    """
    Checker for emissions, CII, and ECA compliance.
    Reference: Section 7.3
    """
    def __init__(self, hfo_co2_factor: float = 3.114):
        self.hfo_co2_factor = hfo_co2_factor
        
        # Hardcoded ECA bounds (simplified polygons/bounding boxes for demonstration)
        self.ecas = {
            "Indian_Ocean_Sulphur_ECA": {
                "lat_min": -20.0, "lat_max": 25.0,
                "lon_min": 40.0, "lon_max": 80.0
            },
            "North_American_ECA": {
                "lat_min": 25.0, "lat_max": 60.0,
                "lon_min": -130.0, "lon_max": -60.0
            }
        }

    def check_eca(self, lat: float, lon: float) -> bool:
        """
        Check if a point is within an ECA boundary.
        """
        for eca_name, bounds in self.ecas.items():
            if bounds["lat_min"] <= lat <= bounds["lat_max"] and bounds["lon_min"] <= lon <= bounds["lon_max"]:
                return True
        return False

    def compute_cii(self, total_fuel_kg: float, dwt: float, total_distance_nm: float) -> float:
        """
        Compute Carbon Intensity Indicator (CII).
        """
        # E_total = total_fuel_kg * 3.114 (kg CO2)
        e_total = total_fuel_kg * self.hfo_co2_factor
        
        if dwt * total_distance_nm == 0:
            return 0.0
            
        # CII = E_total / (DWT * D_total)
        cii = e_total / (dwt * total_distance_nm)
        return cii

    def check_voyage(self, waypoints: List[Dict[str, Any]], vessel_dwt: float) -> Dict[str, Any]:
        """
        Check entire voyage for ECA compliance and compute cumulative emissions and CII.
        """
        eca_flags = []
        total_fuel_kg = 0.0
        total_distance_nm = 0.0
        
        for wp in waypoints:
            lat = wp.get("lat", 0.0)
            lon = wp.get("lon", 0.0)
            if self.check_eca(lat, lon):
                eca_flags.append((lat, lon))
            
            total_fuel_kg += wp.get("fuel_leg_kg", 0.0)
            total_distance_nm += wp.get("distance_nm", 0.0)
            
        cii_attained = self.compute_cii(total_fuel_kg, vessel_dwt, total_distance_nm)
        
        # Simple threshold for CII warning
        cii_warning = cii_attained > 0.015  # Arbitrary threshold for warning
        
        return {
            "eca_flags": eca_flags,
            "cumulative_emissions": total_fuel_kg * self.hfo_co2_factor,
            "cii_attained": cii_attained,
            "cii_warning": cii_warning
        }
