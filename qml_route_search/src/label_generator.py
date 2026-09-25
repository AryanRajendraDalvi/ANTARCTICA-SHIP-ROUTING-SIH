"""
Label Generator (§4.1) — Holtrop-Mennen / ITTC-78 Ground Truth Labels

Generates training data by:
1. Loading real ERA5 weather data
2. Running the ingestion pipeline → CNN → z_weather (64-D)
3. Building vessel/route features → z_vessel_route (28-D)
4. Computing 10 physics-based ground truth labels using Holtrop-Mennen/ITTC-78
5. Packaging everything into train/val/test PyTorch datasets

The CNN outputs are pre-computed and cached so that training only needs
to run the MLP + Adapter + Quantum Circuit forward passes.
"""

import math
import random
import logging
import numpy as np
import torch
import xarray as xr
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

logger = logging.getLogger("qml_route_search.label_generator")

# Physical constants
RHO_WATER = 1025.0   # kg/m³ — seawater density
RHO_AIR = 1.225      # kg/m³ — air density at sea level
G = 9.81             # m/s² — gravitational acceleration


class HoltropMennenLabels:
    """
    Computes 10 ground-truth labels using Holtrop-Mennen added wave resistance
    and ITTC-78 wind resistance formulas.

    These labels are used to train the QML circuit to predict ship performance
    factors from weather + vessel data without running the full physics model
    at inference time.
    """

    def __init__(self, vessel_profile):
        """
        Args:
            vessel_profile: VesselProfile dataclass from vessel_loader.py
        """
        self.vessel = vessel_profile

        # Pre-compute vessel constants
        self.loa = vessel_profile.loa_m
        self.beam = vessel_profile.beam_m
        self.draft = vessel_profile.draft_max_m
        self.depth = vessel_profile.depth_m
        self.dwt = vessel_profile.dwt_mt
        self.speed_kn = vessel_profile.service_speed_kn
        self.speed_ms = self.speed_kn * 0.51444

        # Block coefficient (estimated)
        self.cb = min(max(
            self.dwt / (self.loa * self.beam * self.draft * RHO_WATER), 0.5
        ), 0.95)

        # Transverse projected area for wind resistance
        self.a_t = self.beam * self.depth * 0.4  # m²

        # Wind drag coefficient
        self.c_d = 0.8

        # Propulsive efficiency
        self.eta_prop = 0.7

        # SFOC at operational load
        self.sfoc = vessel_profile.get_sfoc(85.0) / 1000.0  # Convert g/kWh → kg/kWh

        # Engine MCR
        self.mcr_kw = vessel_profile.engine.mcr_kw

        # Roll parameters
        self.gm = vessel_profile.roll.gm_loaded_m
        self.t_roll = vessel_profile.roll.t_roll_loaded_s

        # Calm-water resistance estimate (Holtrop simplified)
        # R_calm ≈ 0.5 * rho * V² * S * Cf * (1+k1)
        # Simplified: use power-speed cube law from MCR
        self.r_calm = (0.85 * self.mcr_kw * 1000.0 * self.eta_prop) / max(self.speed_ms, 1.0)

    def compute_labels(
        self,
        hs: float,
        wave_period: float,
        wave_dir_deg: float,
        wind_speed: float,
        wind_dir_deg: float,
        ship_heading_deg: float,
        ship_speed_kn: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Compute all 10 ground-truth labels for one edge/sample.

        Args:
            hs: Significant wave height (m)
            wave_period: Mean wave period (s)
            wave_dir_deg: Mean wave direction (degrees, meteorological convention)
            wind_speed: 10m wind speed (m/s)
            wind_dir_deg: Wind direction (degrees)
            ship_heading_deg: Ship heading (degrees)
            ship_speed_kn: Ship speed in knots (defaults to service speed)

        Returns:
            Dict with 10 labeled outputs matching QML circuit outputs
        """
        v_kn = ship_speed_kn if ship_speed_kn else self.speed_kn
        v_ms = v_kn * 0.51444

        # Encounter angle (angle between wave direction and ship heading)
        theta_enc_deg = abs(wave_dir_deg - ship_heading_deg) % 360
        if theta_enc_deg > 180:
            theta_enc_deg = 360 - theta_enc_deg
        theta_enc_rad = math.radians(theta_enc_deg)

        # Wind encounter angle
        wind_enc_deg = abs(wind_dir_deg - ship_heading_deg) % 360
        if wind_enc_deg > 180:
            wind_enc_deg = 360 - wind_enc_deg
        wind_enc_rad = math.radians(wind_enc_deg)

        # --- 1. Added Wave Resistance (Holtrop-Mennen, Eq. 4.1.1) ---
        # R_wave = (1/16) * ρ_w * g * B * Hs² * Cb * cos(θ_enc)
        r_wave = (1.0 / 16.0) * RHO_WATER * G * self.beam * (hs ** 2) * self.cb * abs(math.cos(theta_enc_rad))
        r_wave = max(r_wave, 0.0)

        # --- 2. Wind Resistance (ITTC-78, Eq. 4.1.2) ---
        # Relative wind speed considering ship motion
        v_rel = math.sqrt(
            wind_speed ** 2 + v_ms ** 2 + 2 * wind_speed * v_ms * math.cos(wind_enc_rad)
        )
        r_wind = 0.5 * RHO_AIR * (v_rel ** 2) * self.a_t * self.c_d
        r_wind = max(r_wind, 0.0)

        # --- 3. Total power and fuel rate ---
        p_total = (self.r_calm + r_wave + r_wind) * v_ms / self.eta_prop  # Watts
        p_total_kw = p_total / 1000.0
        # Fuel rate in kg/NM
        fuel_rate = (p_total_kw * self.sfoc) / max(v_kn, 0.1)

        # --- 4. Speed loss ---
        # ΔV ≈ (R_added / R_calm) * V
        r_added = r_wave + r_wind
        speed_loss_kn = (r_added / max(self.r_calm, 1.0)) * v_kn
        speed_loss_kn = min(speed_loss_kn, v_kn * 0.5)  # Cap at 50% speed loss

        # --- 5. Roll risk (parametric roll proxy) ---
        # Higher in beam/quartering seas with large waves
        beam_factor = abs(math.sin(theta_enc_rad))  # Maximum at beam seas (90°)
        roll_risk = min(1.0, (hs / 8.0) * beam_factor)

        # Resonance check: if encounter period ≈ T_roll, amplify risk
        if wave_period > 0 and v_ms > 0:
            c_wave = G * wave_period / (2 * math.pi)
            denom = abs(1.0 - (v_ms * math.cos(theta_enc_rad)) / max(c_wave, 0.1))
            t_enc = wave_period / max(denom, 0.01)
            resonance_ratio = t_enc / max(self.t_roll, 1.0)
            if 0.8 <= resonance_ratio <= 1.2:
                roll_risk = min(1.0, roll_risk * 2.0)

        # --- 6. Slamming force (bow impact) ---
        # Higher in head seas with large, short-period waves
        head_factor = max(0, math.cos(theta_enc_rad))  # Maximum at head seas (0°)
        slam_risk = min(1.0, (hs / 10.0) * head_factor * (12.0 / max(wave_period, 4.0)))

        # --- 7. Comfort index (vertical acceleration) ---
        # Simplified ISO 2631 proxy
        comfort = min(1.0, hs / 6.0 * (1 + v_kn / 20.0 * abs(math.cos(theta_enc_rad))))

        # --- 8. Green water risk (deck wetness) ---
        freeboard = self.depth - self.draft
        green_water = min(1.0, max(0, (hs - freeboard) / max(freeboard, 1.0)) * head_factor)

        # --- 9. Propeller emergence risk ---
        prop_depth = self.draft * 0.7  # Approximate propeller tip depth
        prop_emergence = min(1.0, max(0, (hs * 0.5 - prop_depth) / max(prop_depth, 1.0)))

        # --- 10. Confidence ---
        confidence = 1.0  # Ground truth is always confident

        return {
            'fuel_rate': fuel_rate,
            'wave_drag': r_wave / 1000.0,  # Convert N → kN
            'speed_loss': speed_loss_kn,
            'roll_risk': roll_risk,
            'slam_force': slam_risk * 500.0,  # Scale to match S_max
            'wind_resistance': r_wind / 1000.0,  # Convert N → kN
            'comfort_index': comfort * 2.5,  # Scale to match a_max
            'green_water_risk': green_water,
            'prop_emergence_risk': prop_emergence,
            'confidence': confidence,
        }


class TrainingDatasetGenerator:
    """
    Generates complete training datasets by sampling ERA5 weather conditions,
    running the CNN to extract weather embeddings, building vessel/route
    features, and computing Holtrop-Mennen ground truth labels.
    """

    def __init__(self, vessel_profile, cnn_encoder=None):
        """
        Args:
            vessel_profile: VesselProfile from vessel_loader.py
            cnn_encoder: CNNWeatherEncoder instance (optional — if None, uses random z_weather)
        """
        self.vessel = vessel_profile
        self.label_gen = HoltropMennenLabels(vessel_profile)
        self.cnn = cnn_encoder

    def generate_dataset(
        self,
        era5_oper_path: str,
        era5_wave_path: str,
        n_samples: int = 10000,
        bbox: tuple = (-37.0, 19.0, 54.0, 117.0),
        seed: int = 42,
    ) -> Dict[str, Dict[str, torch.Tensor]]:
        """
        Generate a complete training dataset.

        Returns a dict with 'train', 'val', 'test' splits, each containing:
        - z_weather: (N, 64) pre-computed CNN embeddings
        - vessel_route_features: (N, 28) vessel + edge features
        - theta_weather: (N,) weather direction
        - theta_ship: (N,) ship heading
        - labels: (N, 10) ground truth labels
        """
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

        logger.info("Loading ERA5 data for label generation...")

        # Load ERA5 data for weather sampling
        weather_samples = self._sample_weather_from_era5(
            era5_oper_path, era5_wave_path, n_samples, bbox
        )

        logger.info("Generating %d training samples...", n_samples)

        # Pre-compute CNN weather embeddings
        if self.cnn is not None:
            logger.info("Running CNN to extract weather embeddings...")
            z_weather_list = self._compute_cnn_embeddings(
                era5_oper_path, era5_wave_path, weather_samples, bbox
            )
        else:
            logger.info("No CNN provided — using random z_weather placeholders")
            z_weather_list = [torch.randn(64) for _ in range(n_samples)]

        # Build features and labels
        all_z_weather = []
        all_vessel_features = []
        all_theta_weather = []
        all_theta_ship = []
        all_labels = []

        for i, weather in enumerate(weather_samples):
            # Random ship heading
            ship_heading_deg = random.uniform(0, 360)
            ship_speed_kn = random.uniform(
                self.vessel.eco_speed_kn * 0.8,
                self.vessel.service_speed_kn
            )

            # Compute labels
            labels = self.label_gen.compute_labels(
                hs=weather['hs'],
                wave_period=weather['wave_period'],
                wave_dir_deg=weather['wave_dir'],
                wind_speed=weather['wind_speed'],
                wind_dir_deg=weather['wind_dir'],
                ship_heading_deg=ship_heading_deg,
                ship_speed_kn=ship_speed_kn,
            )

            # Build vessel/route features (28-D)
            encounter_angle = abs(weather['wave_dir'] - ship_heading_deg) % 360
            if encounter_angle > 180:
                encounter_angle = 360 - encounter_angle

            vessel_route = self._build_vessel_route_vector(
                weather=weather,
                ship_heading_deg=ship_heading_deg,
                ship_speed_kn=ship_speed_kn,
                encounter_angle_deg=encounter_angle,
            )

            theta_weather = math.radians(weather['wave_dir'])
            theta_ship = math.radians(ship_heading_deg)

            all_z_weather.append(z_weather_list[i])
            all_vessel_features.append(vessel_route)
            all_theta_weather.append(theta_weather)
            all_theta_ship.append(theta_ship)
            all_labels.append(list(labels.values()))

        # Stack into tensors
        z_weather_tensor = torch.stack(all_z_weather)
        vessel_features_tensor = torch.stack(all_vessel_features)
        theta_weather_tensor = torch.tensor(all_theta_weather, dtype=torch.float32)
        theta_ship_tensor = torch.tensor(all_theta_ship, dtype=torch.float32)
        labels_tensor = torch.tensor(all_labels, dtype=torch.float32)

        # Split 70/15/15
        n_train = int(0.7 * n_samples)
        n_val = int(0.15 * n_samples)

        def _slice(tensor, start, end):
            return tensor[start:end]

        splits = {}
        for name, s, e in [('train', 0, n_train), ('val', n_train, n_train + n_val), ('test', n_train + n_val, n_samples)]:
            splits[name] = {
                'z_weather': _slice(z_weather_tensor, s, e),
                'vessel_route_features': _slice(vessel_features_tensor, s, e),
                'theta_weather': _slice(theta_weather_tensor, s, e),
                'theta_ship': _slice(theta_ship_tensor, s, e),
                'labels': _slice(labels_tensor, s, e),
            }

        logger.info("Dataset: train=%d, val=%d, test=%d", n_train, n_val, n_samples - n_train - n_val)
        return splits

    def _sample_weather_from_era5(
        self, oper_path: str, wave_path: str, n_samples: int, bbox: tuple
    ) -> List[Dict[str, float]]:
        """Sample random weather conditions from real ERA5 data."""
        samples = []

        try:
            oper_ds = xr.open_dataset(oper_path)
            wave_ds = xr.open_dataset(wave_path)

            # Standardize coordinate names
            for ds in [oper_ds, wave_ds]:
                if 'latitude' in ds.coords:
                    ds = ds.rename({'latitude': 'lat', 'longitude': 'lon'})

            # Get coordinate ranges
            lat_min, lat_max, lon_min, lon_max = bbox

            # Get available time steps
            time_dim = 'valid_time' if 'valid_time' in wave_ds.dims else 'time'
            n_times = wave_ds.sizes.get(time_dim, 1)

            for _ in range(n_samples):
                # Random location and time
                lat = random.uniform(max(lat_min, -30), min(lat_max, 15))
                lon = random.uniform(max(lon_min, 55), min(lon_max, 115))
                t_idx = random.randint(0, max(n_times - 1, 0))

                try:
                    # Extract weather at point
                    wave_point = wave_ds.isel({time_dim: t_idx}).sel(
                        latitude=lat, longitude=lon, method='nearest'
                    ) if 'latitude' in wave_ds.coords else wave_ds.isel(
                        {time_dim: t_idx}
                    ).sel(lat=lat, lon=lon, method='nearest')

                    oper_point = oper_ds.isel({time_dim: t_idx}).sel(
                        latitude=lat, longitude=lon, method='nearest'
                    ) if 'latitude' in oper_ds.coords else oper_ds.isel(
                        {time_dim: t_idx}
                    ).sel(lat=lat, lon=lon, method='nearest')

                    hs = float(wave_point.get('swh', wave_point.get('hs', 2.0)).values) if hasattr(wave_point, 'swh') or hasattr(wave_point, 'hs') else 2.0
                    # Handle different variable names
                    for var_name in ['swh', 'hs', 'Hs']:
                        if var_name in wave_point:
                            hs = float(wave_point[var_name].values)
                            break

                    wave_period = 8.0
                    for var_name in ['mwp', 'Tm']:
                        if var_name in wave_point:
                            wave_period = float(wave_point[var_name].values)
                            break

                    wave_dir = 180.0
                    for var_name in ['mwd', 'theta_w']:
                        if var_name in wave_point:
                            wave_dir = float(wave_point[var_name].values)
                            break

                    u10 = float(oper_point['u10'].values) if 'u10' in oper_point else 5.0
                    v10 = float(oper_point['v10'].values) if 'v10' in oper_point else 5.0

                    wind_speed = math.sqrt(u10**2 + v10**2)
                    wind_dir = math.degrees(math.atan2(v10, u10)) % 360

                    # Replace NaN with defaults
                    if math.isnan(hs): hs = 2.0
                    if math.isnan(wave_period): wave_period = 8.0
                    if math.isnan(wave_dir): wave_dir = 180.0
                    if math.isnan(wind_speed): wind_speed = 5.0

                    samples.append({
                        'lat': lat, 'lon': lon,
                        'hs': max(hs, 0.1),
                        'wave_period': max(wave_period, 2.0),
                        'wave_dir': wave_dir,
                        'wind_speed': max(wind_speed, 0.1),
                        'wind_dir': wind_dir,
                    })
                except Exception:
                    # Fallback: random realistic weather
                    samples.append(self._random_weather_sample(lat, lon))

            oper_ds.close()
            wave_ds.close()

        except Exception as e:
            logger.warning("Could not load ERA5 data: %s. Using random weather samples.", e)
            for _ in range(n_samples):
                lat = random.uniform(-30, 15)
                lon = random.uniform(55, 115)
                samples.append(self._random_weather_sample(lat, lon))

        return samples

    def _random_weather_sample(self, lat: float, lon: float) -> Dict[str, float]:
        """Generate a realistic random weather sample."""
        return {
            'lat': lat, 'lon': lon,
            'hs': random.uniform(0.5, 8.0),
            'wave_period': random.uniform(4.0, 14.0),
            'wave_dir': random.uniform(0, 360),
            'wind_speed': random.uniform(1.0, 20.0),
            'wind_dir': random.uniform(0, 360),
        }

    def _compute_cnn_embeddings(
        self, oper_path, wave_path, weather_samples, bbox
    ) -> List[torch.Tensor]:
        """
        Pre-compute CNN weather embeddings for all samples.
        Uses a single weather tensor for the region (since CNN processes spatial grids).
        """
        from src.cnn_wrapper import build_weather_tensor_from_era5

        # Build one weather tensor for the region
        try:
            weather_tensor = build_weather_tensor_from_era5(
                oper_path, wave_path, bbox=bbox
            )
            weather_batch = weather_tensor.unsqueeze(0)  # (1, 8, 64, 64)

            with torch.no_grad():
                z_weather = self.cnn(weather_batch)  # (1, 64)

            # For now, use the same regional embedding for all samples
            # (In production, would crop per-edge bboxes)
            return [z_weather.squeeze(0).clone() for _ in weather_samples]

        except Exception as e:
            logger.warning("CNN embedding failed: %s. Using random z_weather.", e)
            return [torch.randn(64) for _ in weather_samples]

    def _build_vessel_route_vector(
        self, weather, ship_heading_deg, ship_speed_kn, encounter_angle_deg
    ) -> torch.Tensor:
        """Build the 28-D vessel/route feature vector for one sample."""
        heading_rad = math.radians(ship_heading_deg)
        bearing_rad = math.radians(random.uniform(0, 360))  # Random bearing during training
        enc_rad = math.radians(encounter_angle_deg)

        features = [
            # Vessel features (13)
            self.vessel.loa_m / 400.0,
            self.vessel.beam_m / 70.0,
            self.vessel.draft_max_m / 25.0,
            math.log10(max(self.vessel.dwt_mt, 1.0)) / 6.0,
            self.vessel.depth_m / 35.0,
            self.vessel.service_speed_kn / 25.0,
            self.label_gen.cb,
            math.log10(max(self.vessel.engine.mcr_kw, 1.0)) / 5.0,
            self.vessel.get_sfoc(85.0) / 200.0,
            self.vessel.roll.gm_loaded_m / 10.0,
            self.vessel.roll.t_roll_loaded_s / 30.0,
            self.vessel.roll.k_xx_factor,
            0.85,  # Engine load fraction (default 85%)

            # Route/edge features (15)
            weather['lat'] / 90.0,
            weather['lon'] / 180.0,
            math.sin(heading_rad),
            math.cos(heading_rad),
            math.sin(bearing_rad),
            math.cos(bearing_rad),
            random.uniform(0.1, 1.0),  # Normalized distance to dest
            random.uniform(0.0, 0.5),  # Normalized elapsed time
            ship_speed_kn / 25.0,
            random.uniform(0.1, 1.0),  # UKC normalized
            min(weather['hs'] / 12.0, 1.0),
            min(weather['wind_speed'] / 25.0, 1.0),
            math.sin(enc_rad),
            math.cos(enc_rad),
            min(weather['wave_period'] / 18.0, 1.0),
        ]

        return torch.tensor(features, dtype=torch.float32)
