"""Train the CV U-Net on one site; keep the checkpoint with the best validation score.

    python -m pipeline.cv.train               # Albufera, defaults below
    python -m pipeline.cv.train --epochs 40

Training site: Albufera, both tracks, every date with a same-day water map.
Validation: held-out 5 km blocks of the same site on every date (no training
crop touches them). The checkpoint is chosen by IoU on dynamic water in those
blocks (sea and permanent water left out, as in the evaluation). Test:
Pego-Oliva is never loaded here; score it with python -m pipeline.cv.evaluate --model.

Writes data/models/cv_unet.pt (weights, channel statistics, split, history; not
committed) and data/metrics/cv_unet_train.json (the training record; committed).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from pipeline.config import DATA_DIR, STACK_DIR, STACKS
from pipeline.cv.data import open_stack
from pipeline.cv.dataset import (
    BLOCK_PX, IGNORE, TILE_PX, CropDataset, Scene, TileDataset, blocks_mask, channel_stats,
    choose_validation_blocks, load_scenes,
)
from pipeline.cv.evaluate import permanent_water
from pipeline.cv.model import S1_WEIGHTS, build_unet

MODELS_DIR = DATA_DIR / "models"
METRICS_DIR = DATA_DIR / "metrics"


@dataclass
class TrainConfig:
    site: str = "albufera"
    epochs: int = 30
    samples_per_epoch: int = 1024
    batch: int = 16
    lr: float = 3e-4
    weight_decay: float = 1e-4
    val_share: float = 0.2
    block: int = BLOCK_PX
    tile: int = TILE_PX
    seed: int = 0
    encoder_weights: str | None = S1_WEIGHTS
    stratify: bool = True      # validation blocks get a fair share of the dynamic water
    focus_share: float = 0.5   # share of crops drawn from windows with dynamic water


def masked_loss(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Binary cross-entropy plus soft Dice, on labelled pixels only."""
    keep = y != IGNORE
    target = (y == 1).float()[keep]
    logit = logits[keep]
    prob = torch.sigmoid(logit)
    dice = 1 - (2 * (prob * target).sum() + 1) / (prob.sum() + target.sum() + 1)
    return F.binary_cross_entropy_with_logits(logit, target) + dice


@torch.no_grad()
def val_iou(model: torch.nn.Module, loader: DataLoader, device: torch.device) -> float | None:
    """IoU of the water class over labelled pixels of a validation loader."""
    model.eval()
    tp = fp = fn = 0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            pred = model(x)[:, 0] > 0
        keep, water = y != IGNORE, y == 1
        tp += int((pred & water & keep).sum())
        fp += int((pred & ~water & keep).sum())
        fn += int((~pred & water & keep).sum())
    return round(tp / (tp + fp + fn), 4) if tp + fp + fn else None


def train(cfg: TrainConfig, scenes: list[Scene] | None = None, permanent: np.ndarray | None = None,
          out: Path | None = MODELS_DIR / "cv_unet.pt", device: str | None = None) -> dict:
    """Train, validate every epoch, save the best checkpoint; returns the training record."""
    torch.manual_seed(cfg.seed)
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    if scenes is None:
        scenes = load_scenes(cfg.site)
    if permanent is None:
        permanent = permanent_water(open_stack(STACK_DIR / f"{cfg.site}_{STACKS[cfg.site][0]}.nc"), cfg.site)

    shape = scenes[0].y.shape
    dynamic_water = sum(((s.y == 1) & ~permanent).astype("float64") for s in scenes)  # dates each pixel is dynamic water
    val_ids = choose_validation_blocks(shape, cfg.val_share, cfg.seed, cfg.block,
                                       dynamic_water if cfg.stratify else None)
    val = blocks_mask(shape, val_ids, cfg.block)
    mean, std = channel_stats(scenes, ~val)
    train_set = CropDataset(scenes, ~val, mean, std, cfg.samples_per_epoch, cfg.tile, cfg.seed,
                            focus=~permanent, focus_share=cfg.focus_share)
    val_all = TileDataset(scenes, val, mean, std, cfg.tile)
    dynamic = [Scene(s.site, s.stack, s.date, s.x, np.where(permanent, IGNORE, s.y).astype("uint8")) for s in scenes]
    val_dyn = TileDataset(dynamic, val, mean, std, cfg.tile)
    loader = DataLoader(train_set, batch_size=cfg.batch, num_workers=0, drop_last=True)
    loader_all = DataLoader(val_all, batch_size=cfg.batch)
    loader_dyn = DataLoader(val_dyn, batch_size=cfg.batch)
    val_share_water = float(dynamic_water[val].sum() / max(dynamic_water.sum(), 1))
    print(f"{len(scenes)} scenes | training window pool {len(train_set.pool)}, {len(train_set.focus_pool)} with "
          f"dynamic water | validation: {len(val_ids)} blocks, {val.mean():.1%} of pixels, {val_share_water:.1%} "
          f"of dynamic water, tiles {len(val_all)} all / {len(val_dyn)} dynamic | device {dev}", flush=True)

    model = build_unet(cfg.encoder_weights).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=cfg.epochs * len(loader), pct_start=0.1)

    history, best_score, best_epoch = [], -1.0, None
    for epoch in range(1, cfg.epochs + 1):
        model.train()
        started, total = time.time(), 0.0
        for x, y in loader:
            x, y = x.to(dev), y.to(dev)
            with torch.autocast(device_type=dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                logits = model(x)[:, 0]
            loss = masked_loss(logits.float(), y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            total += float(loss)
        record = {
            "epoch": epoch, "train_loss": round(total / len(loader), 4),
            "val_iou_all": val_iou(model, loader_all, dev), "val_iou_dynamic": val_iou(model, loader_dyn, dev),
            "seconds": round(time.time() - started, 1),
        }
        history.append(record)
        print(json.dumps(record), flush=True)
        score = record["val_iou_dynamic"] if record["val_iou_dynamic"] is not None else -1.0
        if score > best_score:
            best_score, best_epoch = score, epoch
            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                torch.save({
                    "state_dict": model.state_dict(),
                    "mean": mean.tolist(), "std": std.tolist(),
                    "config": asdict(cfg), "epoch": epoch, "val_blocks": val_ids,
                    "train_scenes": [f"{s.stack} {s.date}" for s in scenes],
                    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "note": "Trained with SI assistance (Claude Code). Test site: pego_oliva, never used here.",
                }, out)

    summary = {"config": asdict(cfg), "best_epoch": best_epoch, "best_val_iou_dynamic": best_score,
               "val_blocks": val_ids, "val_share_of_dynamic_water": round(val_share_water, 3),
               "train_scenes": [f"{s.stack} {s.date}" for s in scenes],
               "mean_db": mean.tolist(), "std_db": std.tolist(), "history": history}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", default="albufera")
    parser.add_argument("--epochs", type=int, default=TrainConfig.epochs)
    parser.add_argument("--samples", type=int, default=TrainConfig.samples_per_epoch, help="training crops per epoch")
    parser.add_argument("--batch", type=int, default=TrainConfig.batch)
    parser.add_argument("--lr", type=float, default=TrainConfig.lr)
    parser.add_argument("--seed", type=int, default=TrainConfig.seed)
    parser.add_argument("--random-init", action="store_true", help="no Sentinel-1 pretrained encoder")
    args = parser.parse_args()
    cfg = TrainConfig(site=args.site, epochs=args.epochs, samples_per_epoch=args.samples, batch=args.batch,
                      lr=args.lr, seed=args.seed, encoder_weights=None if args.random_init else S1_WEIGHTS)
    summary = train(cfg)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    path = METRICS_DIR / "cv_unet_train.json"
    path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"best epoch {summary['best_epoch']}: validation IoU on dynamic water {summary['best_val_iou_dynamic']} "
          f"-> {MODELS_DIR / 'cv_unet.pt'} and {path}")


if __name__ == "__main__":
    main()
