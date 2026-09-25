"""
QML Cost Model Training Script — Staged Training Pipeline

Phase 1: Freeze CNN, train MLP + Adapter + Quantum Circuit (~2-4 hrs)
Phase 2: Optionally unfreeze CNN and fine-tune everything (~1-2 hrs)

Usage:
    # Phase 1 only (recommended for 2-day deadline):
    python scripts/train.py --phase 1 --epochs 200

    # Both phases:
    python scripts/train.py --phase both --epochs 200 --phase2_epochs 50

    # Resume from checkpoint:
    python scripts/train.py --phase 1 --resume checkpoints/qml_cost_model.pt
"""
import sys
import argparse
import logging
import time
import torch
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.cost_model import QMLCostModel
from src.trainer import StagedTrainer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("train")


def main():
    parser = argparse.ArgumentParser(description="Train the QML cost model (staged training)")
    parser.add_argument("--dataset", type=str, default="data/training_dataset.pt")
    parser.add_argument("--phase", type=str, default="1", choices=["1", "2", "both"])
    parser.add_argument("--epochs", type=int, default=200, help="Phase 1 max epochs")
    parser.add_argument("--phase2_epochs", type=int, default=50, help="Phase 2 max epochs")
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3, help="Phase 1 learning rate")
    parser.add_argument("--lr2", type=float, default=1e-4, help="Phase 2 learning rate")
    parser.add_argument("--checkpoint_dir", type=str, default="checkpoints")
    parser.add_argument("--resume", type=str, default=None, help="Resume from checkpoint")
    args = parser.parse_args()

    # Load config
    config_path = PROJECT_ROOT / "config" / "default.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Load dataset
    dataset_path = PROJECT_ROOT / args.dataset
    if not dataset_path.exists():
        logger.error("Dataset not found: %s. Run scripts/generate_labels.py first.", dataset_path)
        sys.exit(1)

    dataset = torch.load(str(dataset_path), map_location="cpu")
    logger.info("Dataset loaded: train=%d, val=%d, test=%d",
                dataset['train']['labels'].shape[0],
                dataset['val']['labels'].shape[0],
                dataset['test']['labels'].shape[0])

    # Create model
    readout_config = config["readout"]
    model = QMLCostModel(
        config=readout_config, 
        cnn_checkpoint=str(PROJECT_ROOT / "checkpoints" / "cnn_surrogate.pt"),
        freeze_cnn=True
    )

    if args.resume and Path(args.resume).exists():
        model.load_state_dict(torch.load(args.resume, map_location="cpu"))
        logger.info("Resumed from checkpoint: %s", args.resume)

    param_counts = model.get_trainable_param_count()
    logger.info("Model parameter counts: %s", param_counts)

    # Create trainer
    trainer = StagedTrainer(model=model, config=config, device="cpu")

    checkpoint_dir = PROJECT_ROOT / args.checkpoint_dir
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    total_start = time.time()

    # --- Phase 1 ---
    if args.phase in ("1", "both"):
        logger.info("\n" + "=" * 60)
        logger.info("Starting Phase 1 training...")

        history1 = trainer.train_phase1(
            train_data=dataset['train'],
            val_data=dataset['val'],
            lr=args.lr,
            batch_size=args.batch_size,
            max_epochs=args.epochs,
            patience=15,
        )

        # Save Phase 1 checkpoint
        p1_path = checkpoint_dir / "qml_cost_model_phase1.pt"
        torch.save(model.state_dict(), str(p1_path))
        logger.info("Phase 1 checkpoint saved: %s", p1_path)
        logger.info("Phase 1 results: best_epoch=%d, best_val_loss=%.6f, total_epochs=%d",
                     history1['best_epoch'] + 1, history1['best_val_loss'], history1['total_epochs'])

    # --- Phase 2 ---
    if args.phase in ("2", "both"):
        logger.info("\n" + "=" * 60)
        logger.info("Starting Phase 2 training (CNN fine-tuning)...")

        history2 = trainer.train_phase2(
            train_data=dataset['train'],
            val_data=dataset['val'],
            lr=args.lr2,
            batch_size=max(args.batch_size // 2, 8),  # Smaller batch for CNN
            max_epochs=args.phase2_epochs,
            patience=10,
        )

        # Save Phase 2 checkpoint
        p2_path = checkpoint_dir / "qml_cost_model_phase2.pt"
        torch.save(model.state_dict(), str(p2_path))
        logger.info("Phase 2 checkpoint saved: %s", p2_path)

    # Save final model as the production checkpoint
    final_path = checkpoint_dir / "qml_cost_model.pt"
    torch.save(model.state_dict(), str(final_path))
    logger.info("Final model saved: %s", final_path)

    total_time = time.time() - total_start
    logger.info("Total training time: %.1f seconds (%.1f minutes)", total_time, total_time / 60)

    # --- Test evaluation ---
    logger.info("\n" + "=" * 60)
    logger.info("Evaluating on test set...")
    model.eval()

    test_data = dataset['test']
    with torch.no_grad():
        predictions = model.forward_cached_cnn(
            test_data['z_weather'],
            test_data['vessel_route_features'],
            test_data['theta_weather'],
            test_data['theta_ship'],
        )

    labels = test_data['labels']
    label_names = ['fuel_rate', 'wave_drag', 'speed_loss', 'roll_risk', 'slam_force',
                   'wind_resist', 'comfort', 'green_water', 'prop_emerge', 'confidence']
    pred_keys = ['fuel_rate', 'wave_drag', 'speed_loss', 'roll_risk', 'slam_force',
                 'wind_resistance', 'comfort_index', 'green_water_risk', 'prop_emergence_risk', 'confidence']

    logger.info("%-15s %10s %10s", "Output", "Test MSE", "Test MAE")
    for i, (name, key) in enumerate(zip(label_names, pred_keys)):
        mse = torch.mean((predictions[key] - labels[:, i]) ** 2).item()
        mae = torch.mean(torch.abs(predictions[key] - labels[:, i])).item()
        logger.info("%-15s %10.6f %10.6f", name, mse, mae)


if __name__ == "__main__":
    main()
