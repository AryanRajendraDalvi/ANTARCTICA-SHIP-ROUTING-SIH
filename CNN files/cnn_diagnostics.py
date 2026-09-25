"""
cnn_diagnostics.py
==================
Visual diagnostics for the trained OceanFeatureExtractorCNN.

Produces a single high-resolution figure (cnn_diagnostics.png) with:

  Panel A — Input Ocean Fields
      8-channel heatmap of a real ERA5 snapshot showing exactly what
      the CNN receives as input.

  Panel B — Latent Embedding Space (PCA)
      All z_weather vectors projected to 2-D via PCA, coloured by:
        * Significant wave height (Hs)
        * Wind speed magnitude
        * Predicted R_wave (kN)
      Demonstrates that the CNN has learned to separate calm / moderate /
      stormy ocean states in its latent space.

  Panel C — Regression Accuracy + Intrinsic Dimensionality
      Predicted vs. actual scatter plots for both targets, plus a
      cumulative-variance plot showing how many dimensions of the 64-D
      embedding carry meaningful information.

Usage
-----
  python cnn_diagnostics.py

  # Custom paths:
  python cnn_diagnostics.py \
      --model_weights model.pt \
      --data_path training_tensor.pt \
      --labels_path training_labels.pt \
      --output cnn_diagnostics.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
import numpy as np
import torch
import torch.nn as nn


# ===========================================================================
# Inline model (mirrors train_cnn_pipeline.py — standalone, no import needed)
# ===========================================================================

class OceanFeatureExtractorCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.stage1 = nn.Sequential(
            nn.Conv2d(8, 16, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(16), nn.LeakyReLU(0.1, inplace=True),
            nn.MaxPool2d(2, 2),
        )
        self.stage2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32), nn.LeakyReLU(0.1, inplace=True),
            nn.MaxPool2d(2, 2),
        )
        self.stage3 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64), nn.LeakyReLU(0.1, inplace=True),
        )
        self.stage4 = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(64, 64),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.stage4(self.stage3(self.stage2(self.stage1(x))))


class WeatherCostRegressor(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.backbone = OceanFeatureExtractorCNN()
        self.regression_head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(inplace=True), nn.Linear(32, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.regression_head(self.backbone(x))

    def get_backbone(self) -> OceanFeatureExtractorCNN:
        return self.backbone


# ===========================================================================
# Design tokens — premium dark aesthetic
# ===========================================================================
BG       = "#0d1117"
PANEL_BG = "#161b22"
GRID_C   = "#21262d"
TEXT     = "#e6edf3"
ACCENT   = "#58a6ff"
GOOD_C   = "#3fb950"
STORM_C  = "#f85149"

CHANNEL_NAMES = [
    "u10  (East Wind)",  "v10  (North Wind)",
    "swh  (Wave Height)","mwp  (Wave Period)",
    "uo   (East Current)","vo  (North Current)",
    "SSH  (Sea Surf. Hgt)","mwd (Wave Dir.)",
]
CHANNEL_CMAPS = [
    "RdBu_r","RdBu_r","Blues","YlOrBr",
    "PuOr","PuOr","RdYlBu","twilight",
]


# ===========================================================================
# Core helpers
# ===========================================================================

def _get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _load_all(weights_path, data_path, labels_path, device):
    ckpt = torch.load(weights_path, map_location=device, weights_only=False)
    model = WeatherCostRegressor()
    model.load_state_dict(ckpt["model_state"])
    model.eval().to(device)
    y_mean = ckpt.get("y_mean", torch.zeros(2))
    y_std  = ckpt.get("y_std",  torch.ones(2))
    X = torch.load(data_path,   weights_only=True).float()
    y = torch.load(labels_path, weights_only=True).float()
    return model, X, y, y_mean, y_std


@torch.no_grad()
def _embeddings_and_preds(model, X, y_mean, y_std, device, bs=64):
    embs, preds = [], []
    for i in range(0, len(X), bs):
        b = X[i:i+bs].to(device)
        z = model.backbone(b)
        p = model.regression_head(z)
        embs.append(z.cpu()); preds.append(p.cpu())
    embs  = torch.cat(embs).numpy()
    preds = torch.cat(preds).numpy() * y_std.cpu().numpy() + y_mean.cpu().numpy()
    return embs, preds


def _pca2d(Z: np.ndarray):
    Zc = Z - Z.mean(0)
    C  = (Zc.T @ Zc) / (len(Zc) - 1)
    vals, vecs = np.linalg.eigh(C)
    idx = np.argsort(vals)[::-1]
    pcs = vecs[:, idx[:2]]
    var1 = vals[idx[0]] / vals.sum() * 100
    var2 = vals[idx[1]] / vals.sum() * 100
    return Zc @ pcs, var1, var2, vals[idx] / vals.sum() * 100


def _r2(yt, yp):
    ss_res = ((yt - yp)**2).sum()
    ss_tot = ((yt - yt.mean())**2).sum()
    return float(1 - ss_res / (ss_tot + 1e-12))


# ===========================================================================
# Figure builder
# ===========================================================================

def make_figure(X, y_np, embs, preds, sample_idx=0, output_path="cnn_diagnostics.png"):
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": PANEL_BG,
        "axes.edgecolor": GRID_C, "axes.labelcolor": TEXT,
        "xtick.color": TEXT, "ytick.color": TEXT,
        "text.color": TEXT, "grid.color": GRID_C,
        "font.family": "DejaVu Sans",
    })

    pca2d, var1, var2, all_var = _pca2d(embs)
    cumvar = np.cumsum(all_var)
    d90 = int(np.searchsorted(cumvar, 90)) + 1
    d95 = int(np.searchsorted(cumvar, 95)) + 1

    Hs_mean    = X[:, 2].mean(dim=(-2,-1)).numpy()
    wind_speed = (X[:,0]**2 + X[:,1]**2).mean(dim=(-2,-1)).sqrt().numpy()
    sample     = X[sample_idx].numpy()
    N          = len(X)

    fig = plt.figure(figsize=(22, 15), facecolor=BG)
    fig.suptitle(
        "OceanFeatureExtractorCNN — Visual Diagnostic Dashboard\n"
        f"ERA5 Indian Ocean / Arabian Sea  |  {N} training samples  |  "
        "z_weather: 64-D latent embedding",
        fontsize=13, fontweight="bold", color=TEXT, y=0.99,
    )

    outer = gridspec.GridSpec(3, 1, figure=fig,
        height_ratios=[2.2, 2.5, 2.5],
        hspace=0.40, left=0.055, right=0.97, top=0.94, bottom=0.05,
    )

    # ── Row A: input channel heatmaps ──────────────────────────────────────
    row_a = gridspec.GridSpecFromSubplotSpec(2, 4, subplot_spec=outer[0],
                                             wspace=0.28, hspace=0.42)
    for ch in range(8):
        ax = fig.add_subplot(row_a[ch//4, ch%4])
        d  = sample[ch]
        im = ax.imshow(d, cmap=CHANNEL_CMAPS[ch], origin="lower",
                       vmin=d.min(), vmax=d.max(), interpolation="bilinear")
        cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
        cb.ax.tick_params(labelsize=6, colors=TEXT)
        ax.set_title(CHANNEL_NAMES[ch], fontsize=8, color=ACCENT, pad=3)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values(): s.set_edgecolor(GRID_C)

    fig.text(0.012, 0.81, "A\n\nInput\nFields\n(64x64\nArabian\nSea)",
             fontsize=8, color=TEXT, va="center", fontweight="bold", ha="center")

    # ── Row B: PCA embedding space ─────────────────────────────────────────
    row_b = gridspec.GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[1], wspace=0.32)

    pca_cfgs = [
        (Hs_mean,        "Blues",    "Sig. Wave Height (normalised)",  "Calm → Stormy Seas (Hs)"),
        (wind_speed,     "YlOrRd",   "Wind Speed (normalised)",        "Light Wind → Gale"),
        (preds[:,0],     "RdYlGn_r", "Predicted R_wave (kN)",          "Low → High Wave Drag"),
    ]
    for col, (cv, cmap, cbar_lbl, title) in enumerate(pca_cfgs):
        ax   = fig.add_subplot(row_b[col])
        norm = Normalize(vmin=cv.min(), vmax=cv.max())
        ax.scatter(pca2d[:,0], pca2d[:,1], c=cv, cmap=cmap, norm=norm,
                   s=60, alpha=0.85, linewidths=0.3, edgecolors="white")
        cb = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax,
                          pad=0.02, fraction=0.046)
        cb.set_label(cbar_lbl, fontsize=7, color=TEXT)
        cb.ax.tick_params(labelsize=6, colors=TEXT)
        ax.set_title(f"Embedding Space — {title}", color=ACCENT,
                     fontsize=9, fontweight="bold", pad=5)
        ax.set_xlabel(f"PC 1  ({var1:.1f}% var.)", fontsize=8)
        ax.set_ylabel(f"PC 2  ({var2:.1f}% var.)", fontsize=8)
        ax.grid(True, alpha=0.25)
        for s in ax.spines.values(): s.set_edgecolor(GRID_C)

    fig.text(0.012, 0.53, "B\n\nLatent\nEmbedding\nSpace\n(PCA 2-D)",
             fontsize=8, color=TEXT, va="center", fontweight="bold", ha="center")

    # ── Row C: regression accuracy + dimensionality ────────────────────────
    row_c = gridspec.GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[2], wspace=0.32)

    reg_cfgs = [
        (y_np[:,0], preds[:,0], "R_wave — Wave Resistance (kN)",
         "YlOrRd", "R_wave actual (kN)", "R_wave predicted (kN)"),
        (y_np[:,1], preds[:,1], "Fuel Consumption Rate (kg/NM)",
         "Blues",  "fuel_rate actual (kg/NM)", "fuel_rate predicted (kg/NM)"),
    ]
    for col, (yt, yp, title, cmap, xl, yl) in enumerate(reg_cfgs):
        ax   = fig.add_subplot(row_c[col])
        r2   = _r2(yt, yp)
        lims = [min(yt.min(), yp.min())*0.94, max(yt.max(), yp.max())*1.06]
        norm = Normalize(vmin=yt.min(), vmax=yt.max())
        ax.scatter(yt, yp, c=yt, cmap=cmap, norm=norm,
                   s=55, alpha=0.82, linewidths=0.3, edgecolors="white", zorder=3)
        ax.plot(lims, lims, "--", color=GOOD_C, lw=1.8,
                label="Perfect prediction", zorder=4)
        ax.set_xlim(lims); ax.set_ylim(lims)
        ax.set_xlabel(xl, fontsize=8); ax.set_ylabel(yl, fontsize=8)
        ax.set_title(f"{title}\nR² = {r2:.4f}",
                     color=ACCENT, fontsize=9, fontweight="bold", pad=5)
        ax.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C,
                  labelcolor=TEXT)
        ax.grid(True, alpha=0.25)
        for s in ax.spines.values(): s.set_edgecolor(GRID_C)
        res = yp - yt
        ax.annotate(
            f"MAE  = {np.abs(res).mean():.3f}\n"
            f"RMSE = {np.sqrt((res**2).mean()):.3f}\n"
            f"Max  = {np.abs(res).max():.3f}",
            xy=(0.04, 0.72), xycoords="axes fraction", fontsize=7.5,
            color=TEXT,
            bbox=dict(boxstyle="round,pad=0.4", facecolor=BG,
                      edgecolor=GRID_C, alpha=0.85),
        )

    # Intrinsic dimensionality panel
    ax_d = fig.add_subplot(row_c[2])
    dims = np.arange(1, 65)
    ax_d.fill_between(dims, cumvar, alpha=0.2, color=ACCENT)
    ax_d.plot(dims, cumvar, color=ACCENT, lw=2)
    ax_d.axhline(90, ls="--", color=GOOD_C,  lw=1.3, label=f"90% var. (dim {d90})")
    ax_d.axhline(95, ls="--", color=STORM_C, lw=1.3, label=f"95% var. (dim {d95})")
    ax_d.axvline(d90, ls=":", color=GOOD_C,  lw=1.0)
    ax_d.axvline(d95, ls=":", color=STORM_C, lw=1.0)
    ax_d.text(d90+0.5, 55, f"{d90} dims\n→90%", color=GOOD_C,  fontsize=7.5)
    ax_d.text(d95+0.5, 35, f"{d95} dims\n→95%", color=STORM_C, fontsize=7.5)
    ax_d.set_xlim(1, 64); ax_d.set_ylim(0, 105)
    ax_d.set_xlabel("z_weather Dimension Index", fontsize=8)
    ax_d.set_ylabel("Cumulative Variance Explained (%)", fontsize=8)
    ax_d.set_title(
        "64-D Embedding — Intrinsic Dimensionality\n"
        "(How many dimensions carry real information)",
        color=ACCENT, fontsize=9, fontweight="bold", pad=5,
    )
    ax_d.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C,
                labelcolor=TEXT, loc="lower right")
    ax_d.grid(True, alpha=0.25)
    for s in ax_d.spines.values(): s.set_edgecolor(GRID_C)

    fig.text(0.012, 0.23, "C\n\nRegression\nAccuracy\n&\nEmbedding\nDim.",
             fontsize=8, color=TEXT, va="center", fontweight="bold", ha="center")

    # Save
    out = Path(output_path)
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)

    print(f"\n  Saved -> {out.resolve()}")
    print(f"  PCA: PC1={var1:.1f}%  PC2={var2:.1f}% variance")
    print(f"  R_wave  R2 = {_r2(y_np[:,0], preds[:,0]):.4f}")
    print(f"  Fuel    R2 = {_r2(y_np[:,1], preds[:,1]):.4f}")
    print(f"  Intrinsic dim: {d90} dims -> 90%  |  {d95} dims -> 95%")


# ===========================================================================
# CLI
# ===========================================================================

def _parse_args():
    p = argparse.ArgumentParser(
        description="CNN Diagnostics — visual dashboard for OceanFeatureExtractorCNN",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model_weights", default="model.pt")
    p.add_argument("--data_path",     default="training_tensor.pt")
    p.add_argument("--labels_path",   default="training_labels.pt")
    p.add_argument("--sample_idx",    type=int, default=0,
                   help="ERA5 snapshot index for input field heatmap (Panel A).")
    p.add_argument("--output",        default="cnn_diagnostics.png")
    return p.parse_args()


def main():
    args   = _parse_args()
    device = _get_device()
    print(f"Device: {device}")

    for fp in (args.model_weights, args.data_path, args.labels_path):
        if not Path(fp).exists():
            print(f"[ERROR] Not found: {fp}", file=sys.stderr); sys.exit(1)

    print("Loading model + data ...")
    model, X, y, y_mean, y_std = _load_all(
        args.model_weights, args.data_path, args.labels_path, device
    )
    print(f"Dataset: {len(X)} samples  |  Extracting embeddings ...")
    embs, preds = _embeddings_and_preds(model, X, y_mean, y_std, device)

    print("Rendering figure ...")
    make_figure(X, y.numpy(), embs, preds,
                sample_idx=args.sample_idx,
                output_path=args.output)


if __name__ == "__main__":
    main()
