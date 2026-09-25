"""
Staged Trainer (§4.2-4.3) — Two-Phase Training Pipeline

Phase 1 (Fast): CNN frozen → Train MLP + Adapter + Quantum Circuit
    - Uses pre-computed CNN z_weather embeddings (no CNN forward passes)
    - ~8,609 trainable parameters
    - ~2-4 hours for 10,000 samples × 200 epochs

Phase 2 (Optional Fine-tune): Unfreeze CNN → Train entire pipeline end-to-end
    - Lower learning rate
    - ~38,609 total parameters
    - Run only if Phase 1 converges and time permits

Loss: Multi-target MSE across 10 QML outputs with λ-weighting
Optimizer: Adam with cosine annealing
Early stopping: patience=15 on validation loss
"""

import time
import logging
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from typing import Dict, Any, Optional

logger = logging.getLogger("qml_route_search.trainer")


class StagedTrainer:
    """
    Two-phase trainer for the full CNN → MLP → Quantum pipeline.

    Phase 1: CNN is frozen, only MLP + Adapter + Quantum weights are trained.
             Uses pre-computed z_weather tensors (fast — no CNN forward pass).
    Phase 2: CNN is unfrozen, entire pipeline is fine-tuned with a reduced
             learning rate.
    """

    def __init__(
        self,
        model,  # QMLCostModel
        config: Dict[str, Any],
        device: str = 'cpu',
    ):
        self.model = model
        self.config = config
        self.device = device
        self.model.to(device)

        # Loss weights for each of the 10 outputs
        # Can be tuned to emphasize fuel/safety over comfort
        self.loss_weights = torch.tensor([
            2.0,   # fuel_rate — high weight (primary cost)
            1.0,   # wave_drag
            1.5,   # speed_loss — important for ETA
            2.0,   # roll_risk — safety critical
            1.0,   # slam_force
            1.0,   # wind_resistance
            0.5,   # comfort_index
            1.0,   # green_water_risk
            0.5,   # prop_emergence_risk
            0.5,   # confidence — regularization term
        ], device=device)

        self.loss_weights = self.loss_weights / self.loss_weights.sum()  # normalize

        # Label normalization stats — computed from training data in train_phase1()
        self.label_mean = None
        self.label_std = None

    def _normalize_labels(self, labels: torch.Tensor) -> torch.Tensor:
        """Normalize labels to zero-mean, unit-variance for balanced gradient flow."""
        if self.label_mean is not None and self.label_std is not None:
            # For variables with zero variance (e.g. constant confidence=1.0), 
            # set std to 1.0 so we don't artificially inflate their loss by dividing by a tiny epsilon.
            safe_std = torch.where(self.label_std < 1e-4, torch.ones_like(self.label_std), self.label_std)
            return (labels - self.label_mean) / safe_std
        return labels

    def _denormalize_predictions(self, predictions: dict) -> dict:
        """Denormalize predictions back to physical units for evaluation."""
        if self.label_mean is None:
            return predictions
        keys = ['fuel_rate', 'wave_drag', 'speed_loss', 'roll_risk', 'slam_force',
                'wind_resistance', 'comfort_index', 'green_water_risk', 'prop_emergence_risk', 'confidence']
        result = {}
        for i, key in enumerate(keys):
            if key in predictions:
                result[key] = predictions[key] * (self.label_std[i] + 1e-8) + self.label_mean[i]
        return result

    def _make_dataloader(self, dataset: Dict[str, torch.Tensor], batch_size: int, shuffle: bool = True):
        """Create a DataLoader from a dataset dict."""
        ds = TensorDataset(
            dataset['z_weather'].to(self.device),
            dataset['vessel_route_features'].to(self.device),
            dataset['theta_weather'].to(self.device),
            dataset['theta_ship'].to(self.device),
            dataset['labels'].to(self.device),
        )
        return DataLoader(ds, batch_size=batch_size, shuffle=shuffle)

    def _compute_loss(self, predictions: Dict[str, torch.Tensor], labels: torch.Tensor) -> torch.Tensor:
        """
        Multi-target weighted MSE loss across 10 outputs.
        """
        pred_keys = ['fuel_rate', 'wave_drag', 'speed_loss', 'roll_risk',
                     'slam_force', 'wind_resistance', 'comfort_index',
                     'green_water_risk', 'prop_emergence_risk', 'confidence']

        norm_labels = self._normalize_labels(labels)

        # Gather predictions into tensor for normalization
        pred_list = [predictions.get(key, torch.zeros_like(labels[:, 0])) for key in pred_keys]
        pred_tensor = torch.stack(pred_list, dim=1)
        norm_preds = self._normalize_labels(pred_tensor)

        total_loss = torch.tensor(0.0, device=self.device)
        for i, key in enumerate(pred_keys):
            mse = torch.mean((norm_preds[:, i] - norm_labels[:, i]) ** 2)
            total_loss = total_loss + self.loss_weights[i] * mse

        return total_loss

    def train_phase1(
        self,
        train_data: Dict[str, torch.Tensor],
        val_data: Dict[str, torch.Tensor],
        lr: float = 1e-3,
        batch_size: int = 32,
        max_epochs: int = 200,
        patience: int = 15,
    ) -> Dict[str, Any]:
        """
        Phase 1: Train MLP + Adapter + Quantum with frozen CNN.
        """
        logger.info("=" * 60)
        logger.info("PHASE 1: Training MLP + Adapter + Quantum (CNN frozen)")
        logger.info("=" * 60)

        # Compute label stats for normalization
        self.label_mean = train_data['labels'].mean(dim=0).to(self.device)
        self.label_std = train_data['labels'].std(dim=0).to(self.device)
        logger.info("Computed label normalization stats.")

        # Freeze CNN
        self.model.freeze_cnn()

        # Report trainable params
        param_counts = self.model.get_trainable_param_count()
        logger.info("Trainable parameters: %s", param_counts)

        # Setup optimizer (only non-frozen params)
        trainable_params = [p for p in self.model.parameters() if p.requires_grad]
        optimizer = torch.optim.Adam(trainable_params, lr=lr)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max_epochs)

        train_loader = self._make_dataloader(train_data, batch_size, shuffle=True)
        val_loader = self._make_dataloader(val_data, batch_size, shuffle=False)

        history = self._training_loop(
            optimizer, scheduler, train_loader, val_loader,
            max_epochs, patience, phase_name="Phase 1",
        )

        return history

    def train_phase2(
        self,
        train_data: Dict[str, torch.Tensor],
        val_data: Dict[str, torch.Tensor],
        lr: float = 1e-4,
        batch_size: int = 16,
        max_epochs: int = 50,
        patience: int = 10,
    ) -> Dict[str, Any]:
        """
        Phase 2: Fine-tune entire pipeline (CNN unfrozen) with reduced LR.
        Only run if Phase 1 converged well and time permits.

        Note: This is slower because CNN forward passes are now included
        in the backward graph.
        """
        logger.info("=" * 60)
        logger.info("PHASE 2: Fine-tuning entire pipeline (CNN unfrozen)")
        logger.info("=" * 60)

        # Compute label stats for normalization (in case skipped Phase 1)
        if self.label_mean is None:
            self.label_mean = train_data['labels'].mean(dim=0).to(self.device)
            self.label_std = train_data['labels'].std(dim=0).to(self.device)
            logger.info("Computed label normalization stats.")

        self.model.unfreeze_cnn()

        param_counts = self.model.get_trainable_param_count()
        logger.info("Trainable parameters: %s", param_counts)

        trainable_params = [p for p in self.model.parameters() if p.requires_grad]
        optimizer = torch.optim.Adam(trainable_params, lr=lr)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max_epochs)

        train_loader = self._make_dataloader(train_data, batch_size, shuffle=True)
        val_loader = self._make_dataloader(val_data, batch_size, shuffle=False)

        history = self._training_loop(
            optimizer, scheduler, train_loader, val_loader,
            max_epochs, patience, phase_name="Phase 2",
        )

        return history

    def _training_loop(
        self, optimizer, scheduler, train_loader, val_loader,
        max_epochs, patience, phase_name,
    ) -> Dict[str, Any]:
        """Core training loop shared by both phases."""

        train_losses = []
        val_losses = []
        best_val_loss = float('inf')
        best_epoch = 0
        best_state = None
        patience_counter = 0
        epoch_times = []

        for epoch in range(max_epochs):
            epoch_start = time.time()

            # --- Training ---
            self.model.train()
            # Keep CNN in eval mode even during training (for BatchNorm stability)
            self.model.fusion.weather_cnn.cnn.eval()

            epoch_train_loss = 0.0
            n_train_batches = 0

            for z_w, v_feat, t_w, t_s, labels in train_loader:
                optimizer.zero_grad()

                # Use cached CNN path (no CNN backward pass in Phase 1)
                predictions = self.model.forward_cached_cnn(z_w, v_feat, t_w, t_s)
                loss = self._compute_loss(predictions, labels)
                loss.backward()

                # Gradient clipping
                torch.nn.utils.clip_grad_norm_(
                    [p for p in self.model.parameters() if p.requires_grad],
                    max_norm=1.0,
                )
                optimizer.step()

                epoch_train_loss += loss.item()
                n_train_batches += 1

            scheduler.step()
            avg_train_loss = epoch_train_loss / max(n_train_batches, 1)
            train_losses.append(avg_train_loss)

            # --- Validation ---
            self.model.eval()
            epoch_val_loss = 0.0
            n_val_batches = 0

            with torch.no_grad():
                for z_w, v_feat, t_w, t_s, labels in val_loader:
                    predictions = self.model.forward_cached_cnn(z_w, v_feat, t_w, t_s)
                    loss = self._compute_loss(predictions, labels)
                    epoch_val_loss += loss.item()
                    n_val_batches += 1

            avg_val_loss = epoch_val_loss / max(n_val_batches, 1)
            val_losses.append(avg_val_loss)

            epoch_time = time.time() - epoch_start
            epoch_times.append(epoch_time)

            # --- Early stopping ---
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                best_epoch = epoch
                best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1

            # Logging
            if epoch % 10 == 0 or epoch == max_epochs - 1 or patience_counter == 0:
                lr_current = optimizer.param_groups[0]['lr']
                logger.info(
                    "%s Epoch %3d/%d | Train: %.6f | Val: %.6f | Best: %.6f (ep %d) | LR: %.2e | %.1fs",
                    phase_name, epoch + 1, max_epochs, avg_train_loss, avg_val_loss,
                    best_val_loss, best_epoch + 1, lr_current, epoch_time,
                )

            if patience_counter >= patience:
                logger.info("Early stopping at epoch %d (patience=%d)", epoch + 1, patience)
                break

        # Restore best model
        if best_state:
            self.model.load_state_dict(best_state)
            logger.info("Restored best model from epoch %d (val_loss=%.6f)", best_epoch + 1, best_val_loss)

        avg_epoch_time = sum(epoch_times) / max(len(epoch_times), 1)
        logger.info("Average epoch time: %.1f seconds", avg_epoch_time)

        return {
            'train_losses': train_losses,
            'val_losses': val_losses,
            'best_epoch': best_epoch,
            'best_val_loss': best_val_loss,
            'avg_epoch_time': avg_epoch_time,
            'total_epochs': len(train_losses),
        }
