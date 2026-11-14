"""Training data for the CV U-Net: NISAR HH/HV in, same-day Sentinel-1 water out.

Scenes: every acquisition of a site's stacks that has a same-day OPERA DSWx-S1
water map at most MAX_GAP_H hours from the NISAR pass and that has HV (HH-only
dates are skipped). Input: HH and HV in dB (2 channels, NaN where not usable).
Target per pixel: 1 water (DSWx open water or inundated vegetation), 0 not
water, IGNORE where NISAR is not usable or the water map is masked or fill.

No leakage between training and validation: each site grid is cut into
BLOCK_PX blocks (about 5 km) and a fixed, seeded share of blocks is held out on
every date; training crops come only from windows that lie entirely inside
training blocks. The test site is never loaded for training.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import torch
import xarray as xr

from pipeline.config import STACK_DIR, STACKS
from pipeline.cv.data import dswx_on_grid, open_stack, to_db
from pipeline.cv.evaluate import DSWX_INVALID, DSWX_RAW, MAX_GAP_H, date_index, dswx_files

IGNORE = 255
WATER_CLASSES = (1, 3)   # DSWx-S1 open water, inundated vegetation
BLOCK_PX = 256           # validation blocks: 5.12 km on the 20 m grid
TILE_PX = 256
DB_RANGE = (-35.0, 5.0)  # clip before standardizing (the sea can reach the noise floor)


@dataclass
class Scene:
    site: str
    stack: str
    date: str
    x: np.ndarray  # (2, H, W) float32: HH and HV in dB, NaN where not usable
    y: np.ndarray  # (H, W) uint8: 0 not water, 1 water, IGNORE


def scene_arrays(ds: xr.Dataset, t: int, water_map: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    """Model input (2, H, W) in dB for one acquisition and, given a DSWx map, its target (H, W)."""
    x = np.stack([to_db(ds["HH"].values[t]), to_db(ds["HV"].values[t])]).astype("float32")
    usable = ds["valid"].values[t].astype(bool) & np.isfinite(x).all(axis=0)
    x[:, ~usable] = np.nan
    if water_map is None:
        return x, None
    y = np.isin(water_map, WATER_CLASSES).astype("uint8")
    y[~usable | np.isin(water_map, DSWX_INVALID)] = IGNORE
    return x, y


def load_scenes(site: str, stacks: tuple[str, ...] | None = None, max_gap_h: float = MAX_GAP_H) -> list[Scene]:
    """Every labelled acquisition of a site (same-day water map, HV present)."""
    index = {(e["stack_id"], e["date"]): e
             for e in json.loads((DSWX_RAW / site / "index.json").read_text(encoding="utf-8"))}
    scenes = []
    for stack_id in stacks or STACKS[site]:
        ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
        for day, t in date_index(ds).items():
            entry = index.get((stack_id, day))
            if not entry or entry["hours_from_nisar"] is None or entry["hours_from_nisar"] > max_gap_h:
                continue
            if not dswx_files(entry) or np.isnan(ds["HV"].values[t]).all():
                continue  # no label tiles, or an HH-only date
            x, y = scene_arrays(ds, t, dswx_on_grid(ds, dswx_files(entry)))
            scenes.append(Scene(site, stack_id, day, x, y))
    return scenes


def block_ids(shape: tuple[int, int], block: int = BLOCK_PX) -> np.ndarray:
    """Block number of every pixel (row-major over block x block cells)."""
    h, w = shape
    return (np.arange(h)[:, None] // block) * math.ceil(w / block) + (np.arange(w)[None, :] // block)


def choose_validation_blocks(shape: tuple[int, int], share: float = 0.2, seed: int = 0, block: int = BLOCK_PX,
                             weight: np.ndarray | None = None) -> list[int]:
    """Block numbers held out for validation.

    Without weight: a seeded random draw. With a weight map (for example, how often
    each pixel is dynamic water), blocks are ranked by their weight and every k-th
    block is taken from a seeded start, so the held-out set gets about `share` of
    the weight instead of whatever a random draw gives (a stratified split).
    """
    h, w = shape
    n = math.ceil(h / block) * math.ceil(w / block)
    k = max(1, round(share * n))
    rng = np.random.default_rng(seed)
    if weight is None:
        return sorted(int(b) for b in rng.permutation(n)[:k])
    sums = np.bincount(block_ids(shape, block).ravel(), weights=weight.ravel().astype("float64"), minlength=n)
    order = np.argsort(-sums, kind="stable")
    step = n / k
    start = rng.uniform(0, step)
    return sorted({int(order[min(n - 1, int(start + i * step))]) for i in range(k)})


def blocks_mask(shape: tuple[int, int], ids: list[int], block: int = BLOCK_PX) -> np.ndarray:
    """Boolean (H, W) mask of the given blocks."""
    return np.isin(block_ids(shape, block), ids)


def validation_blocks(shape: tuple[int, int], share: float = 0.2, seed: int = 0, block: int = BLOCK_PX,
                      weight: np.ndarray | None = None) -> np.ndarray:
    """Boolean (H, W) mask of the held-out validation blocks (the same blocks on every date)."""
    return blocks_mask(shape, choose_validation_blocks(shape, share, seed, block, weight), block)


def channel_stats(scenes: list[Scene], region: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean and std of each input channel (clipped dB) over labelled pixels inside region."""
    stats_mean, stats_std = [], []
    for c in range(2):
        values = np.concatenate([np.clip(s.x[c][region & (s.y != IGNORE)], *DB_RANGE) for s in scenes])
        stats_mean.append(values.mean())
        stats_std.append(values.std())
    return np.array(stats_mean, "float32"), np.array(stats_std, "float32")


def standardize(x: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Clip dB, standardize per channel, and set unusable pixels to the channel mean (0)."""
    z = (np.clip(x, *DB_RANGE) - mean[:, None, None]) / std[:, None, None]
    return np.nan_to_num(z, nan=0.0).astype("float32")


def windows(allowed: np.ndarray, y: np.ndarray, size: int = TILE_PX, step: int = 32,
            min_labelled: float = 0.3) -> list[tuple[int, int]]:
    """Top-left corners of size x size windows that lie fully inside `allowed` and are labelled enough."""
    def integral(a: np.ndarray) -> np.ndarray:
        return np.pad(a.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    inside, labelled = integral(allowed), integral(y != IGNORE)

    def box(s: np.ndarray, r: int, c: int) -> int:
        return int(s[r + size, c + size] - s[r, c + size] - s[r + size, c] + s[r, c])

    h, w = allowed.shape
    return [(r, c) for r in range(0, h - size + 1, step) for c in range(0, w - size + 1, step)
            if box(inside, r, c) == size * size and box(labelled, r, c) >= min_labelled * size * size]


class CropDataset(torch.utils.data.Dataset):
    """Random training crops with flips and 90 degree turns; a fresh crop every item.

    With `focus` (where water is rare and matters, for example everything but the
    sea and permanent water), a `focus_share` of the crops is drawn from windows
    that hold at least `min_focus_px` water pixels inside the focus area, so the
    rare class is seen often enough to be learned.
    """

    def __init__(self, scenes: list[Scene], allowed: np.ndarray, mean: np.ndarray, std: np.ndarray,
                 samples: int, size: int = TILE_PX, seed: int = 0, focus: np.ndarray | None = None,
                 focus_share: float = 0.0, min_focus_px: int = 200):
        self.scenes, self.mean, self.std, self.size, self.samples = scenes, mean, std, size, samples
        self.pool = [(i, rc) for i, s in enumerate(scenes) for rc in windows(allowed, s.y, size)]
        if not self.pool:
            raise ValueError("no training windows: check the split and the labels")
        self.focus_share = focus_share
        self.focus_pool: list[tuple[int, tuple[int, int]]] = []
        if focus is not None and focus_share > 0:
            sums = [np.pad(((s.y == 1) & focus).astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
                    for s in scenes]
            for i, (r, c) in self.pool:
                s = sums[i]
                n = s[r + size, c + size] - s[r, c + size] - s[r + size, c] + s[r, c]
                if n >= min_focus_px:
                    self.focus_pool.append((i, (r, c)))
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return self.samples

    def __getitem__(self, _: int) -> tuple[torch.Tensor, torch.Tensor]:
        pool = self.focus_pool if self.focus_pool and self.rng.random() < self.focus_share else self.pool
        i, (r, c) = pool[int(self.rng.integers(len(pool)))]
        s = self.scenes[i]
        x = standardize(s.x[:, r:r + self.size, c:c + self.size], self.mean, self.std)
        y = s.y[r:r + self.size, c:c + self.size]
        k = int(self.rng.integers(4))
        x, y = np.rot90(x, k, axes=(1, 2)), np.rot90(y, k)
        if self.rng.random() < 0.5:
            x, y = x[:, :, ::-1], y[:, ::-1]
        return torch.from_numpy(x.copy()), torch.from_numpy(y.copy())


class TileDataset(torch.utils.data.Dataset):
    """Fixed, non-overlapping tiles inside `allowed` (validation), no augmentation."""

    def __init__(self, scenes: list[Scene], allowed: np.ndarray, mean: np.ndarray, std: np.ndarray,
                 size: int = TILE_PX):
        self.mean, self.std, self.size = mean, std, size
        self.items = [(s, rc) for s in scenes for rc in windows(allowed, s.y, size, step=size)]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, k: int) -> tuple[torch.Tensor, torch.Tensor]:
        s, (r, c) = self.items[k]
        x = standardize(s.x[:, r:r + self.size, c:c + self.size], self.mean, self.std)
        return torch.from_numpy(x), torch.from_numpy(s.y[r:r + self.size, c:c + self.size].copy())
