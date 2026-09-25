import torch
import torch.nn as nn

class SurrogateMLP(nn.Module):
    """
    Classical Knowledge Distillation Surrogate for the QML Cost Model.
    Takes the CNN fusion vector (96) and angles (theta_weather, theta_ship) and directly predicts the 10D cost vector.
    """
    def __init__(self, input_dim=98, hidden_dim=64, output_dim=10):
        super().__init__()
        
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )
        
    def forward(self, z_fusion, theta_weather, theta_ship):
        """
        Args:
            z_fusion (torch.Tensor): (B, 96) from CNN
            theta_weather (torch.Tensor): (B,) or (B, 1)
            theta_ship (torch.Tensor): (B,) or (B, 1)
        Returns:
            torch.Tensor: (B, 10) physical outputs
        """
        if theta_weather.dim() == 1:
            theta_weather = theta_weather.unsqueeze(1)
        if theta_ship.dim() == 1:
            theta_ship = theta_ship.unsqueeze(1)
            
        # compute encounter angle just like in feature_augmentation
        theta_enc = torch.abs(theta_weather - theta_ship)
        sin_enc = torch.sin(theta_enc)
        cos_enc = torch.cos(theta_enc)
        
        # combine (B, 96) + (B, 1) + (B, 1) -> (B, 98)
        x = torch.cat([z_fusion, sin_enc, cos_enc], dim=1)
        
        return self.net(x)
        
    def decode_predictions(self, preds: torch.Tensor) -> dict:
        """
        Convert (B, 10) tensor into the dictionary format expected by the search algorithm.
        """
        return {
            'fuel_rate': preds[:, 0],
            'wave_drag': preds[:, 1],
            'speed_loss': preds[:, 2],
            'roll_risk': preds[:, 3],
            'slam_force': preds[:, 4],
            'wind_resistance': preds[:, 5],
            'comfort_index': preds[:, 6],
            'green_water_risk': preds[:, 7],
            'prop_emergence_risk': preds[:, 8],
            'confidence': preds[:, 9]
        }
