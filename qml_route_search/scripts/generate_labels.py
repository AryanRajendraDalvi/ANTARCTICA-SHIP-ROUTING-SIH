"""
Training dataset generation script.

Loads real ERA5 weather data + vessel profiles + CNN encoder,
runs Holtrop-Mennen / ITTC-78 formulas to produce ground-truth labels
for all 10 QML outputs, pre-computes CNN embeddings, and saves
the training dataset as a .pt file.

Usage:
    python scripts/generate_labels.py --vessel sci_chennai --n_samples 5000
"""
import sys
import os
import argparse
import logging
import torch
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.vessel_loader import load_all_vessels
from src.label_generator import TrainingDatasetGenerator
from src.cnn_wrapper import CNNWeatherEncoder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("generate_labels")


def main():
    parser = argparse.ArgumentParser(description="Generate training labels from ERA5 + vessel specs + CNN")
    parser.add_argument("--vessel", type=str, default="all", help="Vessel profile name, or 'all' to train on all vessels")
    parser.add_argument("--n_samples", type=int, default=10000, help="Total number of training samples")
    parser.add_argument("--output", type=str, default="data/training_dataset.pt", help="Output path")
    parser.add_argument("--cnn_checkpoint", type=str, default=None, help="CNN checkpoint path (optional)")
    args = parser.parse_args()

    # Load config
    config_path = PROJECT_ROOT / "config" / "default.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Load vessel
    vessels = load_all_vessels(str(PROJECT_ROOT / "config" / "vessels"))
    if args.vessel.lower() == "all":
        target_vessels = list(vessels.values())
        logger.info("Generating dataset across all %d vessels", len(target_vessels))
    else:
        if args.vessel not in vessels:
            logger.error("Vessel '%s' not found. Available: %s", args.vessel, list(vessels.keys()))
            sys.exit(1)
        target_vessels = [vessels[args.vessel]]
        logger.info("Vessel: %s (IMO %s)", target_vessels[0].name, target_vessels[0].imo)

    # Initialize CNN encoder
    cnn = CNNWeatherEncoder(checkpoint_path=args.cnn_checkpoint)
    cnn.freeze()
    logger.info("CNN encoder initialized (frozen)")

    # Generate dataset
    era5_oper = str(PROJECT_ROOT / config["data"]["era5_oper_path"])
    era5_wave = str(PROJECT_ROOT / config["data"]["era5_wave_path"])
    
    samples_per_vessel = args.n_samples // len(target_vessels)
    all_datasets = []

    for vessel in target_vessels:
        logger.info("Processing vessel: %s", vessel.name)
        generator = TrainingDatasetGenerator(vessel, cnn_encoder=cnn)
        ds = generator.generate_dataset(
            era5_oper_path=era5_oper,
            era5_wave_path=era5_wave,
            n_samples=samples_per_vessel,
            bbox=(
                config["region"]["lat_min"],
                config["region"]["lat_max"],
                config["region"]["lon_min"],
                config["region"]["lon_max"],
            ),
        )
        all_datasets.append(ds)
        
    # Merge datasets if multiple vessels
    if len(all_datasets) > 1:
        dataset = {'train': {}, 'val': {}, 'test': {}}
        keys = ['z_weather', 'vessel_route_features', 'theta_weather', 'theta_ship', 'labels']
        for split in ['train', 'val', 'test']:
            for k in keys:
                dataset[split][k] = torch.cat([ds[split][k] for ds in all_datasets])
    else:
        dataset = all_datasets[0]

    # Save
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(dataset, str(output_path))

    logger.info("Dataset saved to %s", output_path)
    for split_name, split_data in dataset.items():
        logger.info("  %s: %d samples, labels shape %s",
                     split_name, split_data['labels'].shape[0], split_data['labels'].shape)

    # Print label statistics
    train_labels = dataset['train']['labels']
    label_names = ['fuel_rate', 'wave_drag', 'speed_loss', 'roll_risk', 'slam_force',
                   'wind_resist', 'comfort', 'green_water', 'prop_emerge', 'confidence']
    logger.info("\nTraining label statistics:")
    logger.info("%-15s %10s %10s %10s %10s", "Label", "Min", "Max", "Mean", "Std")
    for i, name in enumerate(label_names):
        col = train_labels[:, i]
        logger.info("%-15s %10.4f %10.4f %10.4f %10.4f",
                     name, col.min().item(), col.max().item(), col.mean().item(), col.std().item())


if __name__ == "__main__":
    main()
