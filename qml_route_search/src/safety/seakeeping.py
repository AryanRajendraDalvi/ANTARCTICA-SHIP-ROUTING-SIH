import math

class SeakeepingChecker:
    """
    Checker for seakeeping criteria, specifically focusing on parametric roll risk.
    Reference: Section 7.1
    """
    def __init__(self):
        self.g = 9.81  # m/s^2

    def check_leg(self, hs: float, wave_period_tm: float, v_stw: float, theta_enc: float, vessel_t_roll: float, hs_threshold: float = 4.0) -> dict:
        """
        Check a route leg for parametric roll risk.
        
        Args:
            hs: Significant wave height (m)
            wave_period_tm: Mean wave period (s)
            v_stw: Vessel speed through water (m/s)
            theta_enc: Encounter angle (degrees, 0 is head seas, 180 is following seas)
            vessel_t_roll: Vessel natural roll period (s)
            hs_threshold: Threshold for significant wave height (m)
            
        Returns:
            dict with seakeeping assessment
        """
        # Convert angle to radians
        theta_rad = math.radians(theta_enc)
        
        # Compute wave celerity: c = g * T_m / (2*pi)
        # Eq: 7.1.1
        c = (self.g * wave_period_tm) / (2 * math.pi)
        
        # Compute encounter period: T_enc = T_m / |1 - (V_stw * cos(theta_enc)) / c|
        # Eq: 7.1.2
        denominator = abs(1 - (v_stw * math.cos(theta_rad)) / c)
        t_enc = wave_period_tm / denominator if denominator > 1e-6 else float('inf')
        
        # Check risk conditions
        # 1. H_s > hs_threshold
        cond1 = hs > hs_threshold
        
        # 2. 0.8 * T_roll <= T_enc <= 1.2 * T_roll
        cond2 = (0.8 * vessel_t_roll) <= t_enc <= (1.2 * vessel_t_roll)
        
        # 3. theta_enc in following/quartering sector (0-45° or 135-180°)
        cond3 = (0 <= theta_enc <= 45) or (135 <= theta_enc <= 180)
        
        flagged = cond1 and cond2 and cond3
        
        recommended_speed_adjustment = 0.0
        if flagged:
            # Suggest a speed reduction or increase to break resonance
            recommended_speed_adjustment = -2.0  # e.g., drop by 2 m/s
            
        return {
            "flagged": flagged,
            "T_enc": t_enc,
            "recommended_speed_adjustment": recommended_speed_adjustment,
            "safety_flag": "PARAMETRIC_ROLL_RISK" if flagged else "OK"
        }
