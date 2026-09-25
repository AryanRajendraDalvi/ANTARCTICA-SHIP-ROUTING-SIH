"""
Vessel & Route MLP (§3.0 — new integration layer)

Small MLP that encodes static vessel characteristics and per-edge route/weather
state into a 32-D embedding, which gets concatenated with the CNN's 64-D weather
embedding to form the 96-D z_fusion vector.

Input features (28-D):
  Vessel (13):  LOA, beam, draft, DWT, depth, speed, Cb, MCR, SFOC, GM, T_roll, k_xx, engine_load
  Route  (15):  lat, lon, heading(sin/cos), bearing(sin/cos), dist_to_dest,
                elapsed_time, current_speed, UKC, Hs, wind_speed, encounter_angle(sin/cos), wave_period

Output: 32-D embedding → concatenated with CNN 64-D → 96-D z_fusion
"""

import math
import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class VesselFeatures:
    """Static vessel characteristics (constant for entire voyage)."""
    loa_m: float
    beam_m: float
    draft_m: float
    dwt_mt: float
    depth_m: float
    service_speed_kn: float
    block_coeff: float      # Cb — estimated from vessel dimensions
    mcr_kw: float
    sfoc_85pct: float       # g/kWh at 85% MCR
    gm_loaded_m: float
    t_roll_loaded_s: float
    k_xx_factor: float
    engine_load_frac: float  # 0-1, current engine load


@dataclass
class EdgeFeatures:
    """Per-edge route/navigation state (changes for each search candidate)."""
    lat: float               # current position latitude
    lon: float               # current position longitude
    heading_rad: float       # edge heading in radians
    bearing_to_dest_rad: float  # bearing to destination in radians
    distance_to_dest_nm: float  # remaining distance
    elapsed_time_hr: float   # time since departure
    current_speed_kn: float  # current SOG
    ukc_m: float             # under-keel clearance (depth - draft)
    hs_m: float              # local significant wave height
    wind_speed_ms: float     # local wind speed
    encounter_angle_rad: float  # wave encounter angle
    wave_period_s: float     # local mean wave period


def vessel_features_from_profile(profile, engine_load_frac: float = 0.85) -> VesselFeatures:
    """
    Extract VesselFeatures from a VesselProfile dataclass (from vessel_loader.py).
    """
    # Estimate block coefficient from vessel dimensions
    # Cb = DWT / (LOA * Beam * Draft * rho_seawater)
    cb = profile.dwt_mt / (profile.loa_m * profile.beam_m * profile.draft_max_m * 1.025)
    cb = min(max(cb, 0.5), 0.95)  # clamp to reasonable range

    # Get SFOC at 85% MCR
    sfoc_85 = profile.get_sfoc(85.0) if hasattr(profile, 'get_sfoc') else 166.0

    return VesselFeatures(
        loa_m=profile.loa_m,
        beam_m=profile.beam_m,
        draft_m=profile.draft_max_m,
        dwt_mt=profile.dwt_mt,
        depth_m=profile.depth_m,
        service_speed_kn=profile.service_speed_kn,
        block_coeff=cb,
        mcr_kw=profile.engine.mcr_kw if hasattr(profile.engine, 'mcr_kw') else 20000.0,
        sfoc_85pct=sfoc_85,
        gm_loaded_m=profile.roll.gm_loaded_m if hasattr(profile.roll, 'gm_loaded_m') else 2.0,
        t_roll_loaded_s=profile.roll.t_roll_loaded_s if hasattr(profile.roll, 't_roll_loaded_s') else 15.0,
        k_xx_factor=profile.roll.k_xx_factor if hasattr(profile.roll, 'k_xx_factor') else 0.38,
        engine_load_frac=engine_load_frac,
    )


def encode_vessel_edge_features(
    vessel: VesselFeatures,
    edge: EdgeFeatures,
) -> torch.Tensor:
    """
    Encode vessel + edge features into a normalized 28-D tensor.

    All features are normalized to roughly [-1, 1] or [0, 1] range
    using domain-appropriate scaling constants.

    Returns:
        torch.Tensor of shape (28,)
    """
    features = [
        # --- Vessel features (13) ---
        vessel.loa_m / 400.0,                          # 0: LOA normalized
        vessel.beam_m / 70.0,                           # 1: Beam normalized
        vessel.draft_m / 25.0,                          # 2: Draft normalized
        math.log10(max(vessel.dwt_mt, 1.0)) / 6.0,     # 3: DWT log-normalized
        vessel.depth_m / 35.0,                          # 4: Depth normalized
        vessel.service_speed_kn / 25.0,                 # 5: Speed normalized
        vessel.block_coeff,                             # 6: Cb already in [0.5, 0.95]
        math.log10(max(vessel.mcr_kw, 1.0)) / 5.0,     # 7: MCR log-normalized
        vessel.sfoc_85pct / 200.0,                      # 8: SFOC normalized
        vessel.gm_loaded_m / 10.0,                      # 9: GM normalized
        vessel.t_roll_loaded_s / 30.0,                  # 10: T_roll normalized
        vessel.k_xx_factor,                             # 11: k_xx already ~0.36-0.41
        vessel.engine_load_frac,                        # 12: Load fraction [0, 1]

        # --- Route/edge features (15) ---
        edge.lat / 90.0,                                # 13: Latitude normalized
        edge.lon / 180.0,                               # 14: Longitude normalized
        math.sin(edge.heading_rad),                     # 15: Heading sin
        math.cos(edge.heading_rad),                     # 16: Heading cos
        math.sin(edge.bearing_to_dest_rad),             # 17: Bearing sin
        math.cos(edge.bearing_to_dest_rad),             # 18: Bearing cos
        min(edge.distance_to_dest_nm / 5000.0, 1.0),   # 19: Distance normalized
        min(edge.elapsed_time_hr / 720.0, 1.0),         # 20: Time normalized (30 days)
        edge.current_speed_kn / 25.0,                   # 21: Speed normalized
        min(max(edge.ukc_m, 0.0) / 100.0, 1.0),         # 22: UKC normalized
        min(edge.hs_m / 12.0, 1.0),                     # 23: Hs normalized
        min(edge.wind_speed_ms / 25.0, 1.0),            # 24: Wind normalized
        math.sin(edge.encounter_angle_rad),             # 25: Encounter sin
        math.cos(edge.encounter_angle_rad),             # 26: Encounter cos
        min(edge.wave_period_s / 18.0, 1.0),            # 27: Wave period normalized
    ]

    return torch.tensor(features, dtype=torch.float32)


def batch_encode_features(
    vessel: VesselFeatures,
    edges: list,
) -> torch.Tensor:
    """
    Encode vessel features + a batch of edge features into a (B, 28) tensor.

    Args:
        vessel: Static vessel characteristics
        edges: List of EdgeFeatures, one per candidate edge

    Returns:
        torch.Tensor of shape (B, 28)
    """
    return torch.stack([encode_vessel_edge_features(vessel, e) for e in edges])


class VesselRouteMLP(nn.Module):
    """
    MLP that maps 28-D vessel/route features to a 32-D embedding.

    Architecture: Linear(28→64) → LayerNorm → GELU → Linear(64→64) → LayerNorm → GELU → Linear(64→32)

    Total trainable parameters: 28*64+64 + 64*64+64 + 64*32+32 = 6,944
    """

    def __init__(self, input_dim: int = 28, hidden_dim: int = 64, output_dim: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, 28) vessel + route feature vector

        Returns:
            (B, 32) vessel/route embedding
        """
        return self.net(x)
