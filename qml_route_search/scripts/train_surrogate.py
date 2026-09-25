import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
import logging
from torch.utils.data import DataLoader, TensorDataset
from src.surrogate import SurrogateMLP
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

def main():
    logger.info("Loading distillation dataset...")
    data_path = PROJECT_ROOT / "data" / "distillation_dataset.pt"
    dataset = torch.load(data_path, map_location="cpu")
    
    train_data = dataset['train']
    val_data = dataset['val']
    
    # Scale labels for better MSE training (the outputs are physically bounded, but very different scales)
    # Actually, the QML outputs are already in their unscaled physical units.
    # We will use MSE loss directly.
    
    train_ds = TensorDataset(train_data['z_fusion'], train_data['theta_weather'], train_data['theta_ship'], train_data['labels'])
    val_ds = TensorDataset(val_data['z_fusion'], val_data['theta_weather'], val_data['theta_ship'], val_data['labels'])
    
    train_loader = DataLoader(train_ds, batch_size=256, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=256)
    
    model = SurrogateMLP(input_dim=98, hidden_dim=128, output_dim=10)
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()
    
    epochs = 100
    best_val_loss = float('inf')
    patience = 10
    patience_counter = 0
    
    with open(PROJECT_ROOT / "config" / "default.yaml") as f:
        readout_config = yaml.safe_load(f)["readout"]
    
    # max values: F_max=150.0, R_max=800.0, DV_max=8.0, S_max=500.0, R_wind_max=300.0, a_max=2.5
    # The others are [0, 1]. We need to create a scaling tensor.
    scales = torch.tensor([
        readout_config.get('F_max', 150.0),
        readout_config.get('R_max', 800.0),
        readout_config.get('DV_max', 8.0),
        1.0, # roll_risk
        readout_config.get('S_max', 500.0),
        readout_config.get('R_wind_max', 300.0),
        readout_config.get('a_max', 2.5),
        1.0, # green_water
        1.0, # prop_emerge
        1.0  # confidence
    ], dtype=torch.float32)
    
    logger.info(f"Starting surrogate training for max {epochs} epochs...")
    for epoch in range(epochs):
        model.train()
        train_loss = 0
        for z, tw, ts, y in train_loader:
            optimizer.zero_grad()
            preds = model(z, tw, ts)
            
            # Normalize for balanced loss
            preds_norm = preds / scales
            y_norm = y / scales
            loss = criterion(preds_norm, y_norm)
            
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * z.size(0)
            
        train_loss /= len(train_loader.dataset)
        
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for z, tw, ts, y in val_loader:
                preds = model(z, tw, ts)
                preds_norm = preds / scales
                y_norm = y / scales
                loss = criterion(preds_norm, y_norm)
                val_loss += loss.item() * z.size(0)
        val_loss /= len(val_loader.dataset)
        
        logger.info(f"Epoch {epoch+1:03d} | Train MSE: {train_loss:.4e} | Val MSE: {val_loss:.4e}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), PROJECT_ROOT / "checkpoints" / "surrogate_mlp.pt")
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                logger.info("Early stopping triggered.")
                break
                
    logger.info("Surrogate training complete!")

if __name__ == "__main__":
    main()
