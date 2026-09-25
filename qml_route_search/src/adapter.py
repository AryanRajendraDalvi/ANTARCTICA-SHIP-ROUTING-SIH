import torch
import torch.nn as nn
import math

class AdapterLayer(nn.Module):
    """
    Adapter Layer (§3.1).
    
    Transforms the augmented input vector (B, 98) into rotation angles (B, 15)
    for the quantum circuit. Uses LayerNorm, Linear transformation, and scaled tanh
    to ensure output is bound within (-pi, pi).
    """
    def __init__(self):
        super().__init__()
        self.layer_norm = nn.LayerNorm(98)
        # 98 * 15 + 15 = 1485 trainable parameters
        self.linear = nn.Linear(98, 15, bias=True)
        
    def forward(self, z_input: torch.Tensor) -> torch.Tensor:
        """
        Args:
            z_input (torch.Tensor): Augmented feature vector of shape (B, 98)
            
        Returns:
            torch.Tensor: Qubit rotation angles z_proj of shape (B, 15)
        """
        # Layer normalization
        x = self.layer_norm(z_input)
        
        # Linear projection to 15 dimensions
        x = self.linear(x)
        
        # Scale output to (-pi, pi) using pi * tanh(output)
        z_proj = math.pi * torch.tanh(x)
        
        return z_proj
