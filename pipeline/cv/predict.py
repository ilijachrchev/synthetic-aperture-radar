"""Water probability maps from a trained CV U-Net, by sliding windows over a whole scene.

    from pipeline.cv.predict import load_model, predict_scene, water_probabilities
    model, mean, std, checkpoint = load_model("data/models/cv_unet.pt")
    prob = predict_scene(model, x_db, mean, std)     # NaN where not usable
    p_open, p_any = water_probabilities(prob)        # open water, open water + flooded vegetation

x_db must be built with the checkpoint's inputs (pipeline.cv.dataset.scene_arrays,
with the stack's reference_db for "current+ref" models).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from pipeline.cv.dataset import INPUTS, TILE_PX, standardize
from pipeline.cv.model import build_unet


def model_spec(config: dict) -> tuple[str, str, int, int]:
    """(inputs, label_mode, input channels, output classes) of a training config; v1/v2 defaults."""
    inputs = config.get("inputs", "current")
    label_mode = config.get("label_mode", "water13")
    return inputs, label_mode, len(INPUTS[inputs]), 3 if label_mode == "three" else 1


def load_model(path: str | Path, device: str | None = None) -> tuple[torch.nn.Module, np.ndarray, np.ndarray, dict]:
    """Model in eval mode, channel mean and std (dB), and the raw checkpoint dict."""
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    _, _, in_channels, classes = model_spec(checkpoint["config"])
    model = build_unet(None, in_channels, classes)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(dev).eval()
    return model, np.array(checkpoint["mean"], "float32"), np.array(checkpoint["std"], "float32"), checkpoint


@torch.no_grad()
def predict_scene(model: torch.nn.Module, x_db: np.ndarray, mean: np.ndarray, std: np.ndarray,
                  tile: int = TILE_PX, overlap: int = 64, batch: int = 8) -> np.ndarray:
    """Probabilities for one scene (C, H, W) in dB; overlapping windows are averaged.

    One-output model: (H, W) water probability. Multi-class model: (K, H, W)
    class probabilities (softmax). NaN where the date itself is not usable.
    """
    device = next(model.parameters()).device
    z = standardize(x_db, mean, std)
    _, h, w = z.shape
    ph, pw = max(h, tile), max(w, tile)
    if (ph, pw) != (h, w):
        z = np.pad(z, ((0, 0), (0, ph - h), (0, pw - w)))
    step = tile - overlap
    rows = sorted({*range(0, ph - tile + 1, step), ph - tile})
    cols = sorted({*range(0, pw - tile + 1, step), pw - tile})
    windows = [(r, c) for r in rows for c in cols]
    prob = count = None
    for i in range(0, len(windows), batch):
        chunk = windows[i:i + batch]
        xb = torch.from_numpy(np.stack([z[:, r:r + tile, c:c + tile] for r, c in chunk])).to(device)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            out = model(xb).float()
        p = (torch.sigmoid(out) if out.shape[1] == 1 else torch.softmax(out, dim=1)).cpu().numpy()
        if prob is None:
            prob = np.zeros((p.shape[1], ph, pw), "float32")
            count = np.zeros((ph, pw), "float32")
        for (r, c), pi in zip(chunk, p):
            prob[:, r:r + tile, c:c + tile] += pi
            count[r:r + tile, c:c + tile] += 1
    out = (prob / np.maximum(count, 1))[:, :h, :w]
    out[:, ~np.isfinite(x_db[:2]).all(axis=0)] = np.nan
    return out[0] if out.shape[0] == 1 else out


def water_probabilities(prob: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(open water, open water + inundated vegetation) probabilities from predict_scene output."""
    if prob.ndim == 2:
        return prob, prob
    return prob[1], prob[1] + prob[2]
