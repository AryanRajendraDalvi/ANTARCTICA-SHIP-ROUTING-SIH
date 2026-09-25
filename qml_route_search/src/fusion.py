"""
Fusion Module — Combines CNN weather embedding + MLP vessel/route embedding.

Data flow:
    CNN(weather_tensor) → z_weather (B, 64)
    MLP(vessel_route_features) → z_vessel (B, 32)
    Fusion: z_fusion = [z_weather ‖ z_vessel] → (B, 96)

This 96-D z_fusion is the input to the QML pipeline's Feature Augmentation (§2),
which adds 2 encounter angle features to produce the 98-D input for the Adapter (§3.1).
"""

import torch
import torch.nn as nn
from typing import Optional

from src.cnn_wrapper import CNNWeatherEncoder
from src.vessel_mlp import VesselRouteMLP


class FusionModule(nn.Module):
    """
    Produces the 96-D z_fusion vector by concatenating:
    - z_weather (64-D) from the CNN weather encoder
    - z_vessel_route (32-D) from the vessel/route MLP

    This replaces the abstract "CNN+MLP fusion" from the spec.

    Trainable parameters:
    - CNN: ~30,000 (frozen during Phase 1 training)
    - MLP: ~6,944
    - Total when CNN frozen: 6,944
    """

    def __init__(
        self,
        cnn_checkpoint: Optional[str] = None,
        freeze_cnn: bool = True,
        mlp_input_dim: int = 28,
        mlp_hidden_dim: int = 64,
        mlp_output_dim: int = 32,
    ):
        super().__init__()

        # Weather CNN: (B, 8, 64, 64) → (B, 64)
        self.weather_cnn = CNNWeatherEncoder(checkpoint_path=cnn_checkpoint)
        if freeze_cnn:
            self.weather_cnn.freeze()

        # Vessel/route MLP: (B, 28) → (B, 32)
        self.vessel_mlp = VesselRouteMLP(
            input_dim=mlp_input_dim,
            hidden_dim=mlp_hidden_dim,
            output_dim=mlp_output_dim,
        )

        self.output_dim = 64 + mlp_output_dim  # 96

    def forward(
        self,
        weather_tensor: torch.Tensor,
        vessel_route_features: torch.Tensor,
    ) -> torch.Tensor:
        """
        Fuse CNN weather embedding with MLP vessel/route embedding.

        Args:
            weather_tensor: (B, 8, 64, 64) normalized ocean weather grid
            vessel_route_features: (B, 28) vessel + route feature vector

        Returns:
            z_fusion: (B, 96) fused embedding for the QML pipeline
        """
        z_weather = self.weather_cnn(weather_tensor)       # (B, 64)
        z_vessel = self.vessel_mlp(vessel_route_features)  # (B, 32)
        z_fusion = torch.cat([z_weather, z_vessel], dim=1)  # (B, 96)
        return z_fusion

    def forward_precomputed_cnn(
        self,
        z_weather: torch.Tensor,
        vessel_route_features: torch.Tensor,
    ) -> torch.Tensor:
        """
        Fast fusion path when CNN outputs are pre-computed (cached).
        Used during training when CNN is frozen — avoids redundant forward passes.

        Args:
            z_weather: (B, 64) pre-computed CNN weather embeddings
            vessel_route_features: (B, 28) vessel + route feature vector

        Returns:
            z_fusion: (B, 96) fused embedding
        """
        z_vessel = self.vessel_mlp(vessel_route_features)  # (B, 32)
        z_fusion = torch.cat([z_weather, z_vessel], dim=1)  # (B, 96)
        return z_fusion

    def freeze_cnn(self):
        """Freeze CNN for staged training."""
        self.weather_cnn.freeze()

    def unfreeze_cnn(self):
        """Unfreeze CNN for end-to-end fine-tuning."""
        self.weather_cnn.unfreeze()
