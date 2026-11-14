"""Water probability maps from a trained CV U-Net, by sliding windows over a whole scene.

    from pipeline.cv.predict import load_model, predict_scene
    model, mean, std, checkpoint = load_model("data/models/cv_unet.pt")
    prob = predict_scene(model, x_db, mean, std)     # (H, W), NaN where not usable

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from pipeline.cv.dataset import TILE_PX, standardize
from pipeline.cv.model import build_unet


def load_model(path: str | Path, device: str | None = None) -> tuple[torch.nn.Module, np.ndarray, np.ndarray, dict]:
    """Model in eval mode, channel mean and std (dB), and the raw checkpoint dict."""
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    model = build_unet(None)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(dev).eval()
    return model, np.array(checkpoint["mean"], "float32"), np.array(checkpoint["std"], "float32"), checkpoint


@torch.no_grad()
def predict_scene(model: torch.nn.Module, x_db: np.ndarray, mean: np.ndarray, std: np.ndarray,
                  tile: int = TILE_PX, overlap: int = 64, batch: int = 8) -> np.ndarray:
    """Water probability (H, W) for one scene (2, H, W) in dB; overlapping windows are averaged."""
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
    prob = np.zeros((ph, pw), "float32")
    count = np.zeros((ph, pw), "float32")
    for i in range(0, len(windows), batch):
        chunk = windows[i:i + batch]
        xb = torch.from_numpy(np.stack([z[:, r:r + tile, c:c + tile] for r, c in chunk])).to(device)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            p = torch.sigmoid(model(xb)[:, 0].float()).cpu().numpy()
        for (r, c), pi in zip(chunk, p):
            prob[r:r + tile, c:c + tile] += pi
            count[r:r + tile, c:c + tile] += 1
    out = (prob / np.maximum(count, 1))[:h, :w]
    out[~np.isfinite(x_db).all(axis=0)] = np.nan
    return out
