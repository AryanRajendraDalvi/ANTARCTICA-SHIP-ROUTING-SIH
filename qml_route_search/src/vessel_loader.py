"""
Vessel loader module for QML Route Search Pipeline.
"""
import os
import glob
import yaml
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from scipy.interpolate import interp1d

@dataclass
class EngineProfile:
    model: str
    type: str
    mcr_kw: float
    ncr_kw: float
    rpm_mcr: Optional[float] = None

@dataclass
class RollProfile:
    gm_loaded_m: float
    gm_ballast_m: float
    t_roll_loaded_s: float
    t_roll_ballast_s: float
    k_xx_factor: float

@dataclass
class VesselProfile:
    name: str
    imo: str
    type: str
    loa_m: float
    beam_m: float
    draft_design_m: float
    draft_max_m: float
    dwt_mt: float
    depth_m: float
    service_speed_kn: float
    eco_speed_kn: float
    engine: EngineProfile
    sfoc_curve: Dict[int, float]
    roll: RollProfile

    _sfoc_interpolator: Optional[interp1d] = field(init=False, repr=False, default=None)

    def __post_init__(self):
        # Convert dictionaries to typed dataclasses if initialized from parsed yaml
        if isinstance(self.engine, dict):
            self.engine = EngineProfile(**self.engine)
        if isinstance(self.roll, dict):
            self.roll = RollProfile(**self.roll)
        
        # Setup SFOC interpolation (cubic interpolation over engine load curves)
        loads = sorted(list(self.sfoc_curve.keys()))
        sfocs = [self.sfoc_curve[l] for l in loads]
        
        kind = 'cubic' if len(loads) > 3 else 'linear'
        self._sfoc_interpolator = interp1d(loads, sfocs, kind=kind, fill_value="extrapolate")

    def get_sfoc(self, load_percentage: float) -> float:
        """Get Specific Fuel Oil Consumption (g/kWh) at a given load percentage."""
        return float(self._sfoc_interpolator(load_percentage))

    def get_fuel_burn_rate(self, load_percentage: float, speed_knots: float) -> float:
        """
        Compute fuel burn rate in kg/NM given engine load and speed.
        
        Power used = MCR * (load_percentage / 100)
        SFOC (g/kWh) * Power (kW) = Fuel burn rate (g/h)
        Fuel burn rate (g/h) / 1000 = Fuel burn rate (kg/h)
        Fuel burn rate (kg/h) / Speed (NM/h) = Fuel burn rate (kg/NM)
        """
        if speed_knots <= 0:
            return float('inf')
            
        power_kw = self.engine.mcr_kw * (load_percentage / 100.0)
        sfoc = self.get_sfoc(load_percentage)
        burn_rate_kg_per_h = (sfoc * power_kw) / 1000.0
        
        return burn_rate_kg_per_h / speed_knots

    def calculate_natural_roll_period(self, gm: float, draft: float) -> float:
        """
        Computes natural roll period T_roll from GM using the IMO formula:
        T_roll = 2 * C * B / sqrt(GM)
        where C = 0.373 + 0.023 * (B/d) - 0.043 * (L/100)
        """
        if gm <= 0:
            return float('inf')
            
        L = self.loa_m
        B = self.beam_m
        d = draft
        C = 0.373 + 0.023 * (B / d) - 0.043 * (L / 100.0)
        
        t_roll = (2 * C * B) / math.sqrt(gm)
        return t_roll

    @property
    def vessel_type(self) -> str:
        """Alias for the 'type' field for API compatibility."""
        return self.type

    @property
    def t_roll_loaded_s(self) -> float:
        """Natural roll period in loaded condition."""
        return self.roll.t_roll_loaded_s if isinstance(self.roll, RollProfile) else 15.0



class VesselLoader:
    def __init__(self, config_dir: str):
        """Initialize VesselLoader with a specific config directory for YAML files."""
        self.config_dir = config_dir
        self.vessels: Dict[str, VesselProfile] = {}
        self.load_all()

    def load_all(self) -> None:
        """Loads all vessel YAML profiles from the config directory."""
        search_pattern = os.path.join(self.config_dir, "*.yaml")
        for file_path in glob.glob(search_pattern):
            with open(file_path, "r") as f:
                data = yaml.safe_load(f)
                if not data:
                    continue
                vessel = VesselProfile(**data)
                self.vessels[vessel.name] = vessel

    def get_vessel(self, name: str) -> Optional[VesselProfile]:
        """Get a loaded vessel profile by its exact name."""
        return self.vessels.get(name)

    def list_vessels(self) -> List[str]:
        """Lists names of all available loaded vessels."""
        return list(self.vessels.keys())


def load_all_vessels(vessels_dir: str) -> Dict[str, VesselProfile]:
    """
    Convenience function: load all vessel YAML files from a directory.
    Returns dict keyed by filename stem (e.g., 'sci_chennai').
    """
    vessels = {}
    search_pattern = os.path.join(vessels_dir, "*.yaml")
    for file_path in glob.glob(search_pattern):
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
            if not data:
                continue
            vessel = VesselProfile(**data)
            key = os.path.splitext(os.path.basename(file_path))[0]
            vessels[key] = vessel
    return vessels

