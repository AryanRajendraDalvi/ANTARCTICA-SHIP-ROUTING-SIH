class WeatherQueryEngine:
    """
    Engine to interface with DynamicFilter to query weather at space-time points
    and compute speed over ground (SOG).
    """
    def __init__(self, dynamic_filter):
        self.dynamic_filter = dynamic_filter
        
    def query(self, lat: float, lon: float, t_depart: float, t_elapsed_s: float) -> dict:
        """
        Query interpolated weather at a specific point and time.
        """
        t_query = t_depart + t_elapsed_s
        return self.dynamic_filter.interpolate_weather(lat, lon, t_query)
        
    def compute_sog(self, v_stw: float, speed_loss_dv: float, lat: float, lon: float, heading: float, t_query: float) -> float:
        """
        Compute Speed Over Ground (SOG) from Speed Through Water (STW) and speed loss.
        """
        v_actual = v_stw - speed_loss_dv
        # For simplicity, current_projection is 0 if no dynamic current data available.
        current_projection = 0.0 
        sog = v_actual + current_projection
        return float(sog) if sog > 0 else 0.0

    def compute_elapsed_time(self, t_elapsed_parent: float, dist_nm: float, sog_kn: float) -> float:
        """
        Compute total elapsed time given the parent's elapsed time and new segment travel time.
        """
        if sog_kn <= 0:
            return float('inf')
        time_hours = dist_nm / sog_kn
        return t_elapsed_parent + (time_hours * 3600.0)
