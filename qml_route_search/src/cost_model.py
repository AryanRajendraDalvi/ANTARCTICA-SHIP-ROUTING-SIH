"""
QML Cost Model (§3.4) — Full End-to-End Pipeline

Complete model combining:
    CNN Weather Encoder (64-D) + Vessel/Route MLP (32-D) → Fusion (96-D)
    → Feature Augmentation (98-D) → Adapter (15-D) → Quantum Circuit (10 outputs)
    → Physical readout decoding

Two operating modes:
    1. TRAINING MODE: Uses pre-computed CNN embeddings (z_weather cached) + MLP + Quantum
    2. INFERENCE MODE: Full pipeline from raw weather tensor + vessel features → route costs

Trainable parameter breakdown:
    - CNN:              ~30,000 (frozen in Phase 1, unfrozen in Phase 2)
    - Vessel/Route MLP:   6,944
    - Adapter:            1,485 (98*15 + 15)
    - Quantum Circuit:      180 (4 layers × 15 qubits × 3 angles)
    - Total (Phase 1):    8,609 (MLP + Adapter + Quantum)
    - Total (Phase 2):   ~38,609 (all)
"""

import torch
import torch.nn as nn
from typing import Dict, Optional, Any

from src.feature_augmentation import FeatureAugmentation
from src.adapter import AdapterLayer
from src.quantum_circuit import QuantumCircuit
from src.fusion import FusionModule


class QMLCostModel(nn.Module):
    """
    Complete Quantum-Classical Cost Model.

    For training with pre-computed CNN features:
        model.forward_from_fusion(z_fusion, theta_weather, theta_ship)

    For inference with raw data:
        model.forward_full(weather_tensor, vessel_route_features, theta_weather, theta_ship)

    For backward compatibility (just z_fusion input):
        model.forward(z_fusion, theta_weather, theta_ship)
    """

    def __init__(self, config: Dict[str, Any], cnn_checkpoint: Optional[str] = None, freeze_cnn: bool = True):
        super().__init__()
        self.config = config

        # Fusion: CNN (64-D) + MLP (32-D) → 96-D
        self.fusion = FusionModule(
            cnn_checkpoint=cnn_checkpoint,
            freeze_cnn=freeze_cnn,
        )

        # Feature augmentation: 96-D + 2 encounter angle features → 98-D
        self.feature_aug = FeatureAugmentation()

        # Adapter: 98-D → 15-D rotation angles
        self.adapter = AdapterLayer()

        # Quantum circuit: 15 qubits → 10 expectation values
        self.circuit = QuantumCircuit(n_qubits=15, n_layers=4, n_measured=10)

    def _decode_readout(self, exp: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Decode 10 qubit expectation values into physical quantities.

        Args:
            exp: (B, 10) raw expectation values in [-1, 1]

        Returns:
            Dict of physical outputs (each is (B,) tensor)
        """
        shifted = (exp + 1) / 2  # [-1,1] → [0,1]

        return {
            'fuel_rate': shifted[:, 0] * self.config.get('F_max', 150.0),
            'wave_drag': shifted[:, 1] * self.config.get('R_max', 800.0),
            'speed_loss': shifted[:, 2] * self.config.get('DV_max', 8.0),
            'roll_risk': shifted[:, 3],
            'slam_force': shifted[:, 4] * self.config.get('S_max', 500.0),
            'wind_resistance': shifted[:, 5] * self.config.get('R_wind_max', 300.0),
            'comfort_index': shifted[:, 6] * self.config.get('a_max', 2.5),
            'green_water_risk': shifted[:, 7],
            'prop_emergence_risk': shifted[:, 8],
            'confidence': torch.abs(exp[:, 9]),
        }

    def forward(self, z_fusion: torch.Tensor, theta_weather: torch.Tensor, theta_ship: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Forward pass from pre-formed z_fusion (96-D).
        Backward-compatible with the original interface.

        Args:
            z_fusion: (B, 96) fusion vector
            theta_weather: (B,) weather direction in radians
            theta_ship: (B,) ship heading in radians

        Returns:
            Dict of 10 physical outputs
        """
        z_input = self.feature_aug(z_fusion, theta_weather, theta_ship)  # (B, 98)
        z_proj = self.adapter(z_input)                                    # (B, 15)
        exp = self.circuit(z_proj)                                        # (B, 10)
        return self._decode_readout(exp)

    def forward_full(
        self,
        weather_tensor: torch.Tensor,
        vessel_route_features: torch.Tensor,
        theta_weather: torch.Tensor,
        theta_ship: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        """
        Full end-to-end forward pass from raw inputs.

        Args:
            weather_tensor: (B, 8, 64, 64) normalized weather grid
            vessel_route_features: (B, 28) vessel + edge features
            theta_weather: (B,) weather direction in radians
            theta_ship: (B,) ship heading in radians

        Returns:
            Dict of 10 physical outputs
        """
        z_fusion = self.fusion(weather_tensor, vessel_route_features)  # (B, 96)
        return self.forward(z_fusion, theta_weather, theta_ship)

    def forward_cached_cnn(
        self,
        z_weather: torch.Tensor,
        vessel_route_features: torch.Tensor,
        theta_weather: torch.Tensor,
        theta_ship: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        """
        Training-optimized forward pass using pre-computed CNN embeddings.
        Skips the CNN forward pass entirely (useful when CNN is frozen).

        Args:
            z_weather: (B, 64) pre-computed CNN weather embeddings
            vessel_route_features: (B, 28) vessel + edge features
            theta_weather: (B,) weather direction in radians
            theta_ship: (B,) ship heading in radians

        Returns:
            Dict of 10 physical outputs
        """
        z_fusion = self.fusion.forward_precomputed_cnn(z_weather, vessel_route_features)
        return self.forward(z_fusion, theta_weather, theta_ship)

    def predict_edge_cost(self, z_fusion: torch.Tensor, theta_weather: float, theta_ship: float) -> Dict[str, float]:
        """
        Convenience method for single-edge inference during search.

        Args:
            z_fusion: (96,) or (1, 96) fusion vector
            theta_weather: weather direction in radians
            theta_ship: ship heading in radians

        Returns:
            Dict of scalar float predictions
        """
        if z_fusion.dim() == 1:
            z_fusion = z_fusion.unsqueeze(0)
        tw = torch.tensor([theta_weather], dtype=z_fusion.dtype)
        ts = torch.tensor([theta_ship], dtype=z_fusion.dtype)

        with torch.no_grad():
            outputs = self.forward(z_fusion, tw, ts)

        return {k: v.item() for k, v in outputs.items()}

    def freeze_cnn(self):
        """Freeze CNN for Phase 1 training."""
        self.fusion.freeze_cnn()

    def unfreeze_cnn(self):
        """Unfreeze CNN for Phase 2 fine-tuning."""
        self.fusion.unfreeze_cnn()

    def get_trainable_param_count(self) -> Dict[str, int]:
        """Report trainable parameter count per component."""
        counts = {}
        counts['cnn'] = sum(p.numel() for p in self.fusion.weather_cnn.parameters() if p.requires_grad)
        counts['mlp'] = sum(p.numel() for p in self.fusion.vessel_mlp.parameters() if p.requires_grad)
        counts['adapter'] = sum(p.numel() for p in self.adapter.parameters() if p.requires_grad)
        counts['quantum'] = sum(p.numel() for p in self.circuit.parameters() if p.requires_grad)
        counts['feature_aug'] = sum(p.numel() for p in self.feature_aug.parameters() if p.requires_grad)
        counts['total'] = sum(counts.values())
        return counts
