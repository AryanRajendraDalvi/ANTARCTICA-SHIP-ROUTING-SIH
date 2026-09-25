import math

class ComfortChecker:
    """
    Checker for passenger and crew comfort based on vertical acceleration.
    Reference: Section 7.2
    """
    def __init__(self, k_v: float = 0.1):
        self.k_v = k_v
        self.g = 9.81
        
    def check_leg(self, hs: float, v_stw: float, theta_enc: float, leg_duration_hours: float, k_v: float = 0.1) -> dict:
        """
        Check a route leg for comfort limits.
        
        Args:
            hs: Significant wave height (m)
            v_stw: Speed through water (knots)
            theta_enc: Encounter angle (degrees)
            leg_duration_hours: Duration of leg (hours)
            k_v: Vertical acceleration constant
            
        Returns:
            dict with comfort assessment
        """
        # Convert encounter angle to radians
        theta_rad = math.radians(theta_enc)
        
        # Compute simplified g_func: 1 + V_stw/20 * |cos(theta_enc)|
        # Eq: 7.2.1
        g_func = 1.0 + (v_stw / 20.0) * abs(math.cos(theta_rad))
        
        # Compute vertical acceleration: a_v = k_v * H_s * g_func
        # Eq: 7.2.2
        a_v = k_v * hs * self.g * g_func
        
        # Compare to ISO 2631-1 reduced comfort boundary
        # fixed 0.5 m/s^2 threshold for simplicity, as suggested
        threshold = 0.5
        
        flagged = a_v > threshold
        recommended_speed_kn = v_stw
        
        if flagged:
            # Recommend speed reduction in 1-kn steps
            while recommended_speed_kn > 0:
                recommended_speed_kn -= 1.0
                new_g_func = 1.0 + (recommended_speed_kn / 20.0) * abs(math.cos(theta_rad))
                new_a_v = k_v * hs * self.g * new_g_func
                if new_a_v <= threshold:
                    break
                    
        return {
            "flagged": flagged,
            "a_v": a_v,
            "recommended_speed_kn": recommended_speed_kn,
            "safety_flag": "COMFORT_LIMIT" if flagged else "OK"
        }
