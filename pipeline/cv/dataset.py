"""Training data for the CV U-Net: NISAR HH/HV in, same-day Sentinel-1 water out.

Scenes: every acquisition of a site's stacks that has a same-day OPERA DSWx-S1
water map at most MAX_GAP_H hours from the NISAR pass and that has HV (HH-only
dates are skipped).

Inputs (INPUTS): HH and HV in dB of the date ("current"), optionally followed by
each pixel's usual backscatter over its whole stack: the median and the 90th
percentile of HH and HV ("current+ref"). On a single L-band date a dry, smooth
field is as dark as water; next to its usual, brighter self, new water stands
out. The reference uses no labels, only the radar time series of the same stack.

Targets (LABEL_MODES), from the DSWx-S1 classes:
- water13: 1 = open water or inundated vegetation, 0 = the rest (v1 and v2)
- open1:   1 = open water, 0 = the rest (inundated vegetation counts as not water)
- three:   0 = not water, 1 = open water, 2 = inundated vegetation
Everywhere IGNORE where NISAR is not usable or the water map is masked or fill.
Each scene also keeps the DSWx classes (cls), so every variant is scored alike.

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
from pipeline.cv.evaluate import (
    DSWX_INUNDATED_VEG, DSWX_INVALID, DSWX_OPEN_WATER, DSWX_RAW, MAX_GAP_H, date_index, dswx_files,
)

IGNORE = 255
WATER_CLASSES = (DSWX_OPEN_WATER, DSWX_INUNDATED_VEG)
BLOCK_PX = 256           # validation blocks: 5.12 km on the 20 m grid
TILE_PX = 256
DB_RANGE = (-35.0, 5.0)  # clip before standardizing (the sea can reach the noise floor)

INPUTS: dict[str, tuple[str, ...]] = {
    "current": ("hh", "hv"),
    "current+ref": ("hh", "hv", "hh_median", "hv_median", "hh_p90", "hv_p90"),
}
LABEL_MODES: tuple[str, ...] = ("water13", "open1", "three")


@dataclass
class Scene:
    site: str
    stack: str
    date: str
    x: np.ndarray  # (C, H, W) float32 in dB, NaN where not usable; C = len(INPUTS[inputs])
    y: np.ndarray  # (H, W) uint8 target of the label mode, IGNORE where not usable
    cls: np.ndarray | None = None  # (H, W) uint8 DSWx-S1 class, IGNORE where not usable or masked


def nan_quantile0(a: np.ndarray, q: float) -> np.ndarray:
    """Quantile along axis 0, ignoring NaN, with linear interpolation like numpy.

    np.nanpercentile along a short first axis of a huge array falls back to a
    Python loop over pixels; this sorts once (NaN sorts last) and interpolates.
    """
    s = np.sort(a, axis=0)
    n = np.isfinite(a).sum(axis=0)
    last = np.maximum(n - 1, 0)
    pos = q * last
    lo = np.floor(pos).astype(np.int64)
    hi = np.minimum(lo + 1, last)
    v_lo = np.take_along_axis(s, lo[None], axis=0)[0]
    v_hi = np.take_along_axis(s, hi[None], axis=0)[0]
    out = (v_lo + (pos - lo) * (v_hi - v_lo)).astype("float32")
    out[n == 0] = np.nan
    return out


def reference_db(ds: xr.Dataset) -> np.ndarray:
    """(4, H, W) float32: median HH, median HV, 90th percentile HH, 90th percentile HV (dB, usable dates)."""
    valid = ds["valid"].values.astype(bool)
    db = {}
    for pol in ("HH", "HV"):
        db[pol] = to_db(ds[pol].values)
        db[pol][~valid] = np.nan
    return np.stack([nan_quantile0(db["HH"], 0.5), nan_quantile0(db["HV"], 0.5),
                     nan_quantile0(db["HH"], 0.9), nan_quantile0(db["HV"], 0.9)])


def target(water_map: np.ndarray, usable: np.ndarray, label_mode: str = "water13") -> np.ndarray:
    """Per-pixel target of a label mode from the DSWx-S1 classes on the stack grid."""
    if label_mode == "water13":
        y = np.isin(water_map, WATER_CLASSES).astype("uint8")
    elif label_mode == "open1":
        y = (water_map == DSWX_OPEN_WATER).astype("uint8")
    elif label_mode == "three":
        y = np.select([water_map == DSWX_OPEN_WATER, water_map == DSWX_INUNDATED_VEG], [1, 2], 0).astype("uint8")
    else:
        raise ValueError(f"label_mode must be one of {LABEL_MODES}, not {label_mode!r}")
    y[~usable | np.isin(water_map, DSWX_INVALID)] = IGNORE
    return y


def scene_arrays(ds: xr.Dataset, t: int, water_map: np.ndarray | None = None, reference: np.ndarray | None = None,
                 label_mode: str = "water13") -> tuple[np.ndarray, np.ndarray | None]:
    """Model input (C, H, W) in dB for one acquisition and, given a DSWx map, its target (H, W).

    reference: the stack's reference_db, appended after HH and HV (the "current+ref" inputs).
    """
    x = np.stack([to_db(ds["HH"].values[t]), to_db(ds["HV"].values[t])]).astype("float32")
    usable = ds["valid"].values[t].astype(bool) & np.isfinite(x).all(axis=0)
    x[:, ~usable] = np.nan
    if reference is not None:
        ref = reference.copy()
        ref[:, ~usable] = np.nan
        x = np.concatenate([x, ref])
    if water_map is None:
        return x, None
    return x, target(water_map, usable, label_mode)


def load_scenes(site: str, stacks: tuple[str, ...] | None = None, max_gap_h: float = MAX_GAP_H,
                inputs: str = "current", label_mode: str = "water13") -> list[Scene]:
    """Every labelled acquisition of a site (same-day water map, HV present)."""
    if inputs not in INPUTS:
        raise ValueError(f"inputs must be one of {list(INPUTS)}, not {inputs!r}")
    index = {(e["stack_id"], e["date"]): e
             for e in json.loads((DSWX_RAW / site / "index.json").read_text(encoding="utf-8"))}
    scenes = []
    for stack_id in stacks or STACKS[site]:
        ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
        reference = reference_db(ds) if inputs == "current+ref" else None
        for day, t in date_index(ds).items():
            entry = index.get((stack_id, day))
            if not entry or entry["hours_from_nisar"] is None or entry["hours_from_nisar"] > max_gap_h:
                continue
            if not dswx_files(entry) or np.isnan(ds["HV"].values[t]).all():
                continue  # no label tiles, or an HH-only date
            water_map = dswx_on_grid(ds, dswx_files(entry))
            x, y = scene_arrays(ds, t, water_map, reference, label_mode)
            usable = np.isfinite(x[:2]).all(axis=0)
            cls = np.where(usable & ~np.isin(water_map, DSWX_INVALID), water_map, IGNORE).astype("uint8")
            scenes.append(Scene(site, stack_id, day, x, y, cls))
    return scenes


def changing_water(scene: Scene) -> np.ndarray:
    """Pixels that are water in the DSWx classes (any label mode), falling back to the target."""
    return np.isin(scene.cls, WATER_CLASSES) if scene.cls is not None else np.isin(scene.y, (1, 2))


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
    for c in range(scenes[0].x.shape[0]):
        values = np.concatenate([np.clip(s.x[c][region & (s.y != IGNORE)], *DB_RANGE) for s in scenes])
        values = values[np.isfinite(values)]
        stats_mean.append(values.mean())
        stats_std.append(max(values.std(), 1e-3))  # a constant channel must not divide by zero
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
    rare class is seen often enough to be learned. With `jitter_db`, every crop
    gets one random offset in [-jitter_db, jitter_db] dB on all channels, like a
    calibration difference between tracks, sites or processing releases.
    """

    def __init__(self, scenes: list[Scene], allowed: np.ndarray, mean: np.ndarray, std: np.ndarray,
                 samples: int, size: int = TILE_PX, seed: int = 0, focus: np.ndarray | None = None,
                 focus_share: float = 0.0, min_focus_px: int = 200, jitter_db: float = 0.0):
        self.scenes, self.mean, self.std, self.size, self.samples = scenes, mean, std, size, samples
        self.jitter_db = jitter_db
        self.pool = [(i, rc) for i, s in enumerate(scenes) for rc in windows(allowed, s.y, size)]
        if not self.pool:
            raise ValueError("no training windows: check the split and the labels")
        self.focus_share = focus_share
        self.focus_pool: list[tuple[int, tuple[int, int]]] = []
        if focus is not None and focus_share > 0:
            sums = [np.pad((changing_water(s) & focus).astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
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
        x = s.x[:, r:r + self.size, c:c + self.size]
        if self.jitter_db:
            x = x + np.float32(self.rng.uniform(-self.jitter_db, self.jitter_db))
        x = standardize(x, self.mean, self.std)
        y = s.y[r:r + self.size, c:c + self.size]
        k = int(self.rng.integers(4))
        x, y = np.rot90(x, k, axes=(1, 2)), np.rot90(y, k)
        if self.rng.random() < 0.5:
            x, y = x[:, :, ::-1], y[:, ::-1]
        return torch.from_numpy(x.copy()), torch.from_numpy(y.copy())


class TileDataset(torch.utils.data.Dataset):
    """Fixed, non-overlapping tiles inside `allowed` (validation), no augmentation.

    Returns the input and the DSWx classes of the tile, so every label mode is
    scored against the same reference.
    """

    def __init__(self, scenes: list[Scene], allowed: np.ndarray, mean: np.ndarray, std: np.ndarray,
                 size: int = TILE_PX):
        if any(s.cls is None for s in scenes):
            raise ValueError("validation scenes need their DSWx classes (Scene.cls)")
        self.mean, self.std, self.size = mean, std, size
        self.items = [(s, rc) for s in scenes for rc in windows(allowed, s.y, size, step=size)]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, k: int) -> tuple[torch.Tensor, torch.Tensor]:
        s, (r, c) = self.items[k]
        x = standardize(s.x[:, r:r + self.size, c:c + self.size], self.mean, self.std)
        return torch.from_numpy(x), torch.from_numpy(s.cls[r:r + self.size, c:c + self.size].copy())
