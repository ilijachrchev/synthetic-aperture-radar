"""Train the CV U-Net on one site; keep the checkpoint with the best validation score.

    python -m pipeline.cv.train                                       # v2 settings
    python -m pipeline.cv.train --name cv_unet_v3 --inputs current+ref --label-mode three

Training site: Albufera, both tracks, every date with a same-day water map.
Validation: held-out 5 km blocks of the same site on every date (no training
crop touches them), stratified so they hold a fair share of the changing water.
The blocks depend only on the DSWx classes, so every variant (inputs, label
mode, augmentation) is validated on the same blocks. The checkpoint is chosen by
IoU on changing open water in those blocks (sea and permanent water left out, as
in the evaluation), the same rule for every variant. Test: Pego-Oliva is never
loaded here; score it with python -m pipeline.cv.evaluate --model.

Writes data/models/<name>.pt (weights, channel statistics, split, history; not
committed) and data/metrics/<name>_train.json (the training record; committed).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from pipeline.config import DATA_DIR, STACK_DIR, STACKS
from pipeline.cv.data import open_stack
from pipeline.cv.dataset import (
    BLOCK_PX, IGNORE, INPUTS, LABEL_MODES, TILE_PX, WATER_CLASSES, CropDataset, Scene, TileDataset, blocks_mask,
    channel_stats, choose_validation_blocks, load_scenes,
)
from pipeline.cv.evaluate import DSWX_OPEN_WATER, permanent_water
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
    stratify: bool = True      # validation blocks get a fair share of the changing water
    focus_share: float = 0.5   # share of crops drawn from windows with changing water
    inputs: str = "current"    # key of pipeline.cv.dataset.INPUTS
    label_mode: str = "water13"
    jitter_db: float = 0.0     # random calibration offset per training crop, dB
    name: str = "cv_unet"


def n_classes(label_mode: str) -> int:
    return 3 if label_mode == "three" else 1


def masked_loss(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Binary cross-entropy plus soft Dice, on labelled pixels only. logits (B, H, W)."""
    keep = y != IGNORE
    target = (y == 1).float()[keep]
    logit = logits[keep]
    prob = torch.sigmoid(logit)
    dice = 1 - (2 * (prob * target).sum() + 1) / (prob.sum() + target.sum() + 1)
    return F.binary_cross_entropy_with_logits(logit, target) + dice


def masked_loss_multi(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Cross-entropy plus the mean soft Dice of the water classes, on labelled pixels. logits (B, K, H, W)."""
    keep = y != IGNORE
    ce = F.cross_entropy(logits, torch.where(keep, y, torch.zeros_like(y)).long(), reduction="none")[keep].mean()
    prob = torch.softmax(logits, dim=1).permute(0, 2, 3, 1)[keep]
    target = y[keep].long()
    dice = 0.0
    for c in range(1, logits.shape[1]):
        p, g = prob[:, c], (target == c).float()
        dice = dice + 1 - (2 * (p * g).sum() + 1) / (p.sum() + g.sum() + 1)
    return ce + dice / (logits.shape[1] - 1)


def water_probs(out: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """(open water, open water + inundated vegetation) probabilities from raw model output."""
    if out.shape[1] == 1:
        p = torch.sigmoid(out[:, 0])
        return p, p
    p = torch.softmax(out, dim=1)
    return p[:, 1], p[:, 1] + p[:, 2]


@torch.no_grad()
def val_scores(model: torch.nn.Module, loader: DataLoader, device: torch.device) -> dict[str, float | None]:
    """IoU of open water and of any water against the DSWx classes of validation tiles."""
    model.eval()
    counts = {"open": [0, 0, 0], "any": [0, 0, 0]}
    for x, cls in loader:
        x, cls = x.to(device), cls.to(device)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            out = model(x).float()
        p_open, p_any = water_probs(out)
        keep = cls != IGNORE
        truth_any = torch.zeros_like(keep)
        for c in WATER_CLASSES:
            truth_any |= cls == c
        for name, pred, truth in (("open", p_open >= 0.5, cls == DSWX_OPEN_WATER), ("any", p_any >= 0.5, truth_any)):
            counts[name][0] += int((pred & truth & keep).sum())
            counts[name][1] += int((pred & ~truth & keep).sum())
            counts[name][2] += int((~pred & truth & keep).sum())
    return {k: (round(tp / (tp + fp + fn), 4) if tp + fp + fn else None) for k, (tp, fp, fn) in counts.items()}


def train(cfg: TrainConfig, scenes: list[Scene] | None = None, permanent: np.ndarray | None = None,
          out: Path | None = None, device: str | None = None) -> dict:
    """Train, validate every epoch, save the best checkpoint to `out`; returns the training record."""
    if cfg.inputs not in INPUTS or cfg.label_mode not in LABEL_MODES:
        raise ValueError(f"inputs must be one of {list(INPUTS)} and label_mode one of {LABEL_MODES}")
    torch.manual_seed(cfg.seed)
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    if scenes is None:
        scenes = load_scenes(cfg.site, inputs=cfg.inputs, label_mode=cfg.label_mode)
    if permanent is None:
        permanent = permanent_water(open_stack(STACK_DIR / f"{cfg.site}_{STACKS[cfg.site][0]}.nc"), cfg.site)

    shape = scenes[0].y.shape
    # Dates each pixel is changing water, from the DSWx classes: the same for every label mode.
    changing = sum((np.isin(s.cls, WATER_CLASSES) & ~permanent).astype("float64") for s in scenes)
    val_ids = choose_validation_blocks(shape, cfg.val_share, cfg.seed, cfg.block, changing if cfg.stratify else None)
    val = blocks_mask(shape, val_ids, cfg.block)
    mean, std = channel_stats(scenes, ~val)
    train_set = CropDataset(scenes, ~val, mean, std, cfg.samples_per_epoch, cfg.tile, cfg.seed,
                            focus=~permanent, focus_share=cfg.focus_share, jitter_db=cfg.jitter_db)
    val_all = TileDataset(scenes, val, mean, std, cfg.tile)
    dynamic = [replace(s, cls=np.where(permanent, IGNORE, s.cls).astype("uint8")) for s in scenes]
    val_dyn = TileDataset(dynamic, val, mean, std, cfg.tile)
    loader = DataLoader(train_set, batch_size=cfg.batch, num_workers=0, drop_last=True)
    loader_all = DataLoader(val_all, batch_size=cfg.batch)
    loader_dyn = DataLoader(val_dyn, batch_size=cfg.batch)
    val_share_water = float(changing[val].sum() / max(changing.sum(), 1))
    classes = n_classes(cfg.label_mode)
    print(f"{cfg.name}: {len(scenes)} scenes, inputs {cfg.inputs} ({len(INPUTS[cfg.inputs])} channels), "
          f"labels {cfg.label_mode} ({classes} output) | training windows {len(train_set.pool)}, "
          f"{len(train_set.focus_pool)} with changing water | validation {len(val_ids)} blocks, {val.mean():.1%} "
          f"of pixels, {val_share_water:.1%} of changing water, {len(val_all)} tiles | device {dev}", flush=True)

    model = build_unet(cfg.encoder_weights, len(INPUTS[cfg.inputs]), classes).to(dev)
    loss_fn = masked_loss if classes == 1 else masked_loss_multi
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=cfg.epochs * len(loader), pct_start=0.1)

    history, best_score, best_epoch = [], -1.0, None
    for epoch in range(1, cfg.epochs + 1):
        model.train()
        started, total = time.time(), 0.0
        for x, y in loader:
            x, y = x.to(dev), y.to(dev)
            with torch.autocast(device_type=dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                logits = model(x)
            loss = loss_fn(logits[:, 0].float() if classes == 1 else logits.float(), y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            total += float(loss)
        dyn, all_ = val_scores(model, loader_dyn, dev), val_scores(model, loader_all, dev)
        record = {
            "epoch": epoch, "train_loss": round(total / len(loader), 4),
            "val_open_dynamic": dyn["open"], "val_any_dynamic": dyn["any"], "val_open_all": all_["open"],
            "seconds": round(time.time() - started, 1),
        }
        history.append(record)
        print(json.dumps(record), flush=True)
        score = dyn["open"] if dyn["open"] is not None else -1.0
        if score > best_score:
            best_score, best_epoch = score, epoch
            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                torch.save({
                    "state_dict": model.state_dict(),
                    "mean": mean.tolist(), "std": std.tolist(),
                    "config": asdict(cfg), "epoch": epoch, "val_blocks": val_ids,
                    "input_channels": list(INPUTS[cfg.inputs]),
                    "train_scenes": [f"{s.stack} {s.date}" for s in scenes],
                    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "note": "Trained with SI assistance (Claude Code). Test site: pego_oliva, never used here.",
                }, out)

    return {"config": asdict(cfg), "best_epoch": best_epoch, "best_val_open_dynamic": best_score,
            "val_blocks": val_ids, "val_share_of_changing_water": round(val_share_water, 3),
            "input_channels": list(INPUTS[cfg.inputs]), "train_scenes": [f"{s.stack} {s.date}" for s in scenes],
            "mean_db": mean.tolist(), "std_db": std.tolist(), "history": history}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default=TrainConfig.name, help="output file stem in data/models and data/metrics")
    parser.add_argument("--site", default="albufera")
    parser.add_argument("--epochs", type=int, default=TrainConfig.epochs)
    parser.add_argument("--samples", type=int, default=TrainConfig.samples_per_epoch, help="training crops per epoch")
    parser.add_argument("--batch", type=int, default=TrainConfig.batch)
    parser.add_argument("--lr", type=float, default=TrainConfig.lr)
    parser.add_argument("--seed", type=int, default=TrainConfig.seed)
    parser.add_argument("--inputs", default=TrainConfig.inputs, choices=list(INPUTS))
    parser.add_argument("--label-mode", default=TrainConfig.label_mode, choices=list(LABEL_MODES))
    parser.add_argument("--jitter-db", type=float, default=TrainConfig.jitter_db)
    parser.add_argument("--random-init", action="store_true", help="no Sentinel-1 pretrained encoder")
    args = parser.parse_args()
    cfg = TrainConfig(site=args.site, epochs=args.epochs, samples_per_epoch=args.samples, batch=args.batch,
                      lr=args.lr, seed=args.seed, encoder_weights=None if args.random_init else S1_WEIGHTS,
                      inputs=args.inputs, label_mode=args.label_mode, jitter_db=args.jitter_db, name=args.name)
    out = MODELS_DIR / f"{cfg.name}.pt"
    summary = train(cfg, out=out)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    path = METRICS_DIR / f"{cfg.name}_train.json"
    path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"best epoch {summary['best_epoch']}: validation IoU on changing open water "
          f"{summary['best_val_open_dynamic']} -> {out} and {path}")


if __name__ == "__main__":
    main()
