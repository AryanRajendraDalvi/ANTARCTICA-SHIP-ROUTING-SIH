import torch
import torch.nn as nn

class FeatureAugmentation(nn.Module):
    """
    Pure function module for feature augmentation (§2).
    
    Takes fused embedding (z_fusion) and headings, computes the encounter angle,
    and appends its sine and cosine representations to avoid circular discontinuities.
    """
    def __init__(self):
        super().__init__()
        
    def forward(self, z_fusion: torch.Tensor, theta_weather: torch.Tensor, theta_ship: torch.Tensor) -> torch.Tensor:
        """
        Args:
            z_fusion (torch.Tensor): Fused state embedding of shape (B, 96)
            theta_weather (torch.Tensor): Weather direction in radians of shape (B,)
            theta_ship (torch.Tensor): Ship heading in radians of shape (B,)
            
        Returns:
            torch.Tensor: Augmented input vector z_input of shape (B, 98)
        """
        # Eq/Sec: theta_enc = |theta_weather - theta_ship|
        theta_enc = torch.abs(theta_weather - theta_ship)
        
        # Encode as sin and cos to handle circular discontinuity
        sin_enc = torch.sin(theta_enc).unsqueeze(-1) # (B, 1)
        cos_enc = torch.cos(theta_enc).unsqueeze(-1) # (B, 1)
        
        # z_input = [z_fusion || sin(theta_enc) || cos(theta_enc)]
        z_input = torch.cat([z_fusion, sin_enc, cos_enc], dim=-1) # (B, 98)
        
        return z_input
