import torch
import yaml
import logging
from pathlib import Path
from tqdm import tqdm
from src.cost_model import QMLCostModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

def generate_distillation_dataset(num_samples=1000, batch_size=200):
    logger.info("Initializing models for distillation data generation...")
    
    with open(PROJECT_ROOT / "config" / "default.yaml") as f:
        config = yaml.safe_load(f)["readout"]
        
    model = QMLCostModel(
        config=config,
        cnn_checkpoint=str(PROJECT_ROOT / "checkpoints" / "cnn_surrogate.pt")
    )
    model.load_state_dict(torch.load(PROJECT_ROOT / "checkpoints" / "qml_cost_model.pt", map_location="cpu"))
    model.eval()
    logger.info("Loaded QML Cost Model with frozen CNN.")
    
    all_z_fusion = []
    all_theta_w = []
    all_theta_s = []
    all_labels = []
    
    logger.info(f"Generating {num_samples} samples...")
    with torch.no_grad():
        for _ in tqdm(range(0, num_samples, batch_size)):
            # Random valid inputs
            # weather grid: (B, 8, 21, 21) normalized around N(0,1)
            weather_grid = torch.randn(batch_size, 8, 21, 21)
            # ship features: (B, 28) mostly within [0, 1] after normalization in reality
            ship_features = torch.rand(batch_size, 28)
            # angles in [-pi, pi]
            theta_weather = (torch.rand(batch_size) * 2 - 1) * torch.pi
            theta_ship = (torch.rand(batch_size) * 2 - 1) * torch.pi
            
            # Extract CNN features
            z_fusion = model.fusion(weather_grid, ship_features) # (B, 96)
            
            # Get QML predictions
            predictions = model(z_fusion, theta_weather, theta_ship)
            
            # Convert predictions dict to tensor of shape (B, 10)
            pred_keys = ['fuel_rate', 'wave_drag', 'speed_loss', 'roll_risk', 'slam_force',
                         'wind_resistance', 'comfort_index', 'green_water_risk', 'prop_emergence_risk', 'confidence']
            
            labels = torch.stack([predictions[k] for k in pred_keys], dim=1)
            
            all_z_fusion.append(z_fusion)
            all_theta_w.append(theta_weather)
            all_theta_s.append(theta_ship)
            all_labels.append(labels)
            
    dataset = {
        'z_fusion': torch.cat(all_z_fusion, dim=0),
        'theta_weather': torch.cat(all_theta_w, dim=0),
        'theta_ship': torch.cat(all_theta_s, dim=0),
        'labels': torch.cat(all_labels, dim=0)
    }
    
    # Split into train/val
    split_idx = int(num_samples * 0.9)
    final_ds = {
        'train': {k: v[:split_idx] for k, v in dataset.items()},
        'val': {k: v[split_idx:] for k, v in dataset.items()}
    }
    
    out_path = PROJECT_ROOT / "data" / "distillation_dataset.pt"
    out_path.parent.mkdir(exist_ok=True)
    torch.save(final_ds, out_path)
    logger.info(f"Saved distillation dataset to {out_path}")

if __name__ == "__main__":
    generate_distillation_dataset()
