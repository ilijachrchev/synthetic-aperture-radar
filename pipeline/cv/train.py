"""Train the CV U-Net on one or more sites; keep the checkpoint with the best validation score.

    python -m pipeline.cv.train                                       # v2 settings, Albufera
    python -m pipeline.cv.train --name cv_unet_v3 --inputs current+ref --label-mode three
    python -m pipeline.cv.train --name cv_multi --sites albufera ebro camargue --inputs current+ref

Training sites: every track of each site, every date with a same-day water map.
Validation: held-out 5 km blocks of each training site on every date and track
(no training crop touches them), stratified so they hold a fair share of that
site's changing water. The blocks depend only on the DSWx classes, so every
variant (inputs, label mode, augmentation) is validated on the same blocks. The
checkpoint is chosen by IoU on changing open water pooled over those blocks (sea
and permanent water left out, as in the evaluation), the same rule for every
variant. Test sites (Pego-Oliva, Donana) are never loaded here; score them with
python -m pipeline.cv.evaluate --model.

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

from pipeline.config import DATA_DIR
from pipeline.cv.dataset import (
    BLOCK_PX, IGNORE, INPUTS, LABEL_MODES, TILE_PX, WATER_CLASSES, CropDataset, Scene, TileDataset, blocks_mask,
    channel_stats, choose_validation_blocks, load_scenes,
)
from pipeline.cv.evaluate import DSWX_OPEN_WATER, MAX_GAP_H, site_permanent_water
from pipeline.cv.model import S1_WEIGHTS, build_unet

MODELS_DIR = DATA_DIR / "models"
METRICS_DIR = DATA_DIR / "metrics"


@dataclass
class TrainConfig:
    site: str = "albufera"
    sites: tuple[str, ...] = ()  # several training sites; empty means just `site`
    epochs: int = 30
    samples_per_epoch: int = 1024
    batch: int = 16
    lr: float = 3e-4
    weight_decay: float = 1e-4
    val_share: float = 0.2
    block: int = BLOCK_PX
    tile: int = TILE_PX
    seed: int = 0              # weights and crops; a new seed is a new training run
    split_seed: int = 0        # validation blocks; keep it fixed so runs are scored on the same blocks
    encoder_weights: str | None = S1_WEIGHTS
    stratify: bool = True      # validation blocks get a fair share of the changing water
    focus_share: float = 0.5   # share of crops drawn from windows with changing water
    inputs: str = "current"    # key of pipeline.cv.dataset.INPUTS
    label_mode: str = "water13"
    jitter_db: float = 0.0     # random calibration offset per training crop, dB
    max_gap_h: float = MAX_GAP_H  # training labels at most this many hours from the NISAR pass
    name: str = "cv_unet"


def train_sites(cfg: TrainConfig) -> tuple[str, ...]:
    return tuple(cfg.sites) or (cfg.site,)


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
def val_counts(model: torch.nn.Module, loader: DataLoader, device: torch.device) -> dict[str, list[int]]:
    """(tp, fp, fn) of open water and of any water against the DSWx classes of validation tiles."""
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
    return counts


def iou_of(counts: dict[str, list[int]]) -> dict[str, float | None]:
    return {k: (round(tp / (tp + fp + fn), 4) if tp + fp + fn else None) for k, (tp, fp, fn) in counts.items()}


def val_scores(model: torch.nn.Module, loader: DataLoader, device: torch.device) -> dict[str, float | None]:
    """IoU of open water and of any water against the DSWx classes of validation tiles."""
    return iou_of(val_counts(model, loader, device))


def train(cfg: TrainConfig, scenes: list[Scene] | None = None,
          permanent: np.ndarray | dict[str, np.ndarray] | None = None,
          out: Path | None = None, device: str | None = None) -> dict:
    """Train, validate every epoch, save the best checkpoint to `out`; returns the training record.

    permanent: sea and permanent water, one mask per site (or one mask for all scenes).
    """
    if cfg.inputs not in INPUTS or cfg.label_mode not in LABEL_MODES:
        raise ValueError(f"inputs must be one of {list(INPUTS)} and label_mode one of {LABEL_MODES}")
    torch.manual_seed(cfg.seed)
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    if scenes is None:
        scenes = [s for site in train_sites(cfg)
                  for s in load_scenes(site, max_gap_h=cfg.max_gap_h, inputs=cfg.inputs, label_mode=cfg.label_mode)]
    sites = tuple(dict.fromkeys(s.site for s in scenes))
    if permanent is None:
        permanent = {site: site_permanent_water(site) for site in sites}
    elif not isinstance(permanent, dict):
        permanent = {site: permanent for site in sites}

    # Labels further than MAX_GAP_H from the NISAR pass (a --max-gap-h run) only add training
    # crops: the blocks and every validation score use the same-pass labels, as without them,
    # so such a run is chosen and compared on exactly the same pixels and labels.
    clean = [s for s in scenes if s.gap_h is None or s.gap_h <= MAX_GAP_H]

    # Per site: dates each pixel is changing water (from the DSWx classes, the same for every
    # label mode) and the held-out blocks, which then hold a fair share of that water.
    val_ids: dict[str, list[int]] = {}
    val: dict[str, np.ndarray] = {}
    val_share_water: dict[str, float] = {}
    for site in sites:
        here = [s for s in clean if s.site == site]
        if not here:
            raise ValueError(f"{site}: no scene with a label at most {MAX_GAP_H} h from the NISAR pass")
        changing = sum((np.isin(s.cls, WATER_CLASSES) & ~permanent[site]).astype("float64") for s in here)
        val_ids[site] = choose_validation_blocks(here[0].shape, cfg.val_share, cfg.split_seed, cfg.block,
                                                 changing if cfg.stratify else None)
        val[site] = blocks_mask(here[0].shape, val_ids[site], cfg.block)
        val_share_water[site] = round(float(changing[val[site]].sum() / max(changing.sum(), 1)), 3)
    train_region = {site: ~mask for site, mask in val.items()}
    mean, std = channel_stats(scenes, train_region)
    train_set = CropDataset(scenes, train_region, mean, std, cfg.samples_per_epoch, cfg.tile, cfg.seed,
                            focus={site: ~p for site, p in permanent.items()}, focus_share=cfg.focus_share,
                            jitter_db=cfg.jitter_db)
    val_all = TileDataset(clean, val, mean, std, cfg.tile)
    dynamic = [replace(s, cls=np.where(permanent[s.site], IGNORE, s.cls).astype("uint8")) for s in clean]
    loader = DataLoader(train_set, batch_size=cfg.batch, num_workers=0, drop_last=True)
    loader_all = DataLoader(val_all, batch_size=cfg.batch)
    loaders_dyn = {site: DataLoader(TileDataset([s for s in dynamic if s.site == site], val, mean, std, cfg.tile),
                                    batch_size=cfg.batch) for site in sites}
    classes = n_classes(cfg.label_mode)
    per_site = ", ".join(f"{site} {sum(s.site == site for s in scenes)} scenes, {len(val_ids[site])} blocks, "
                         f"{val_share_water[site]:.1%} of its changing water" for site in sites)
    older = f" ({len(scenes) - len(clean)} with labels over {MAX_GAP_H} h, training only)" if len(clean) < len(scenes) else ""
    print(f"{cfg.name}: {len(scenes)} scenes{older}, inputs {cfg.inputs} ({len(INPUTS[cfg.inputs])} channels), "
          f"labels {cfg.label_mode} ({classes} output) | training windows {len(train_set.pool)}, "
          f"{len(train_set.focus_pool)} with changing water | validation: {per_site}; {len(val_all)} tiles "
          f"| device {dev}", flush=True)
    # One site keeps the old list of block numbers, so older readers still work.
    blocks_record = val_ids if len(sites) > 1 else val_ids[sites[0]]

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
        by_site = {site: val_counts(model, loaders_dyn[site], dev) for site in sites}
        pooled = {k: [sum(c[k][i] for c in by_site.values()) for i in range(3)] for k in ("open", "any")}
        dyn, all_ = iou_of(pooled), val_scores(model, loader_all, dev)
        record = {
            "epoch": epoch, "train_loss": round(total / len(loader), 4),
            "val_open_dynamic": dyn["open"], "val_any_dynamic": dyn["any"], "val_open_all": all_["open"],
            "val_open_dynamic_by_site": {site: iou_of(c)["open"] for site, c in by_site.items()},
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
                    "config": asdict(cfg), "epoch": epoch, "val_blocks": blocks_record,
                    "train_sites": list(sites), "input_channels": list(INPUTS[cfg.inputs]),
                    "train_scenes": [_scene_name(s, sites) for s in scenes],
                    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "note": (f"Trained with SI assistance (Claude Code) on {', '.join(sites)}. "
                             "Test sites are never loaded here."),
                }, out)

    share = val_share_water if len(sites) > 1 else val_share_water[sites[0]]
    return {"config": asdict(cfg), "best_epoch": best_epoch, "best_val_open_dynamic": best_score,
            "train_sites": list(sites), "val_blocks": blocks_record, "val_share_of_changing_water": share,
            "input_channels": list(INPUTS[cfg.inputs]), "train_scenes": [_scene_name(s, sites) for s in scenes],
            "mean_db": mean.tolist(), "std_db": std.tolist(), "history": history}


def _scene_name(s: Scene, sites: tuple[str, ...]) -> str:
    """'stack date' as before for one site; with several, the site comes first."""
    return f"{s.stack} {s.date}" if len(sites) == 1 else f"{s.site} {s.stack} {s.date}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default=TrainConfig.name, help="output file stem in data/models and data/metrics")
    parser.add_argument("--site", default="albufera")
    parser.add_argument("--sites", nargs="+", help="several training sites (overrides --site)")
    parser.add_argument("--max-gap-h", type=float, default=TrainConfig.max_gap_h,
                        help="training labels at most this many hours from the NISAR pass")
    parser.add_argument("--epochs", type=int, default=TrainConfig.epochs)
    parser.add_argument("--samples", type=int, default=TrainConfig.samples_per_epoch, help="training crops per epoch")
    parser.add_argument("--batch", type=int, default=TrainConfig.batch)
    parser.add_argument("--lr", type=float, default=TrainConfig.lr)
    parser.add_argument("--seed", type=int, default=TrainConfig.seed, help="weights and crops")
    parser.add_argument("--split-seed", type=int, default=TrainConfig.split_seed, help="validation blocks (keep fixed)")
    parser.add_argument("--inputs", default=TrainConfig.inputs, choices=list(INPUTS))
    parser.add_argument("--label-mode", default=TrainConfig.label_mode, choices=list(LABEL_MODES))
    parser.add_argument("--jitter-db", type=float, default=TrainConfig.jitter_db)
    parser.add_argument("--random-init", action="store_true", help="no Sentinel-1 pretrained encoder")
    parser.add_argument("--models-dir", type=Path, default=MODELS_DIR, help="where the checkpoint goes")
    args = parser.parse_args()
    cfg = TrainConfig(site=args.sites[0] if args.sites else args.site, sites=tuple(args.sites or ()),
                      max_gap_h=args.max_gap_h, epochs=args.epochs, samples_per_epoch=args.samples, batch=args.batch,
                      lr=args.lr, seed=args.seed, split_seed=args.split_seed,
                      encoder_weights=None if args.random_init else S1_WEIGHTS,
                      inputs=args.inputs, label_mode=args.label_mode, jitter_db=args.jitter_db, name=args.name)
    out = args.models_dir / f"{cfg.name}.pt"
    summary = train(cfg, out=out)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    path = METRICS_DIR / f"{cfg.name}_train.json"
    path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"best epoch {summary['best_epoch']}: validation IoU on changing open water "
          f"{summary['best_val_open_dynamic']} -> {out} and {path}")


if __name__ == "__main__":
    main()
