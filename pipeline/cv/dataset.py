"""Training data for the CV U-Net: NISAR HH/HV in, same-day Sentinel-1 water out.

Scenes: every acquisition of a site's stacks that has a same-day OPERA DSWx-S1
water map at most MAX_GAP_H hours from the NISAR pass and that has HV (HH-only
dates are skipped).

Inputs (INPUTS): HH and HV in dB of the date ("current"), optionally followed by
each pixel's usual backscatter over its whole stack: the median and the 90th
percentile of HH and HV ("current+ref"). On a single L-band date a dry, smooth
field is as dark as water; next to its usual, brighter self, new water stands
out. The reference uses no labels, only the radar time series of the same stack.
The "+coh" inputs add the 12-day coherence of the date (pipeline.cv.coherence):
water loses it, dry and stable ground keeps it, even where both are equally dark.
It comes right after HH and HV; where no pair covers a pixel it is NaN, which
standardizing turns into the channel mean.

Targets (LABEL_MODES), from the DSWx-S1 classes:
- water13: 1 = open water or inundated vegetation, 0 = the rest (v1 and v2)
- open1:   1 = open water, 0 = the rest (inundated vegetation counts as not water)
- three:   0 = not water, 1 = open water, 2 = inundated vegetation
Everywhere IGNORE where NISAR is not usable or the water map is masked or fill.
Each scene also keeps the DSWx classes (cls), so every variant is scored alike.

Optical label cleanup (clean_with_optical, pre-registered in docs/CV_BENCHMARK.md):
where the optical water map of the date (data/optical, OPERA DSWx-HLS within 1 day)
is clear and contradicts the Sentinel-1 map (Sentinel-1 open water where optical
sees no water, or Sentinel-1 no water where optical sees open water), the pixel
is not trained on and not scored in validation (Scene.dropped). Inundated
vegetation is kept: optical cannot see water under plants. The validation blocks
still come from the uncleaned classes, so every variant keeps the same blocks.

No leakage between training and validation: each site grid is cut into
BLOCK_PX blocks (about 5 km) and a fixed, seeded share of blocks is held out on
every date and every track of that site; training crops come only from windows
that lie entirely inside training blocks. Test sites are never loaded for training.

Memory: a scene keeps only its own HH and HV (float16, steps of about 0.02 dB, far
below speckle); the four reference channels are one array per stack, shared by
all its scenes, and appended crop by crop (Scene.crop). Several sites fit in RAM.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import torch
import xarray as xr

from pipeline.config import DATA_DIR, STACK_DIR, site_stacks
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
    "current+coh": ("hh", "hv", "coh"),
    "current+ref+coh": ("hh", "hv", "coh", "hh_median", "hv_median", "hh_p90", "hv_p90"),
}
COH_CHANNEL = 2  # position of "coh" in the inputs that have it (right after HH and HV)
OPTICAL_DIR = DATA_DIR / "optical"
OPTICAL_NOT_WATER, OPTICAL_OPEN_WATER = 0, 1  # OPERA DSWx-HLS B01_WTR classes


def uses_reference(inputs: str) -> bool:
    return "hh_median" in INPUTS[inputs]


def uses_coherence(inputs: str) -> bool:
    return "coh" in INPUTS[inputs]
LABEL_MODES: tuple[str, ...] = ("water13", "open1", "three")


@dataclass
class Scene:
    site: str
    stack: str
    date: str
    x: np.ndarray  # (C, H, W) dB, NaN where not usable; with ref: only the date's HH and HV
    y: np.ndarray  # (H, W) uint8 target of the label mode, IGNORE where not usable
    cls: np.ndarray | None = None  # (H, W) uint8 DSWx-S1 class, IGNORE where not usable or masked
    ref: np.ndarray | None = None  # (4, H, W) reference_db of the stack, the same array for all its scenes
    gap_h: float | None = None     # hours between the label and the NISAR pass (None: unknown)
    coh_channel: int | None = None  # input channel that holds coherence (not shifted by the dB jitter)
    dropped: np.ndarray | None = None  # (H, W) bool, labels the optical cleanup drops (not trained, not scored)
    cleaned_px: int = 0            # how many labels the optical cleanup drops

    @property
    def shape(self) -> tuple[int, int]:
        return self.y.shape

    @property
    def n_channels(self) -> int:
        return self.x.shape[0] + (0 if self.ref is None else self.ref.shape[0])

    def crop(self, r: int, c: int, size: int) -> np.ndarray:
        """(C, size, size) float32 inputs of one window; the reference is NaN where the date is not usable."""
        x = self.x[:, r:r + size, c:c + size].astype("float32")
        if self.ref is None:
            return x
        ref = self.ref[:, r:r + size, c:c + size].astype("float32")
        ref[:, ~np.isfinite(x[:2]).all(axis=0)] = np.nan  # HH and HV decide; coherence may be missing
        return np.concatenate([x, ref])

    def full(self) -> np.ndarray:
        """(C, H, W) float32 inputs of the whole scene."""
        return self.crop(0, 0, max(self.shape))


Region = np.ndarray | dict[str, np.ndarray]  # one mask for every scene, or one per site


def region_of(region: Region, scene: Scene) -> np.ndarray:
    return region[scene.site] if isinstance(region, dict) else region


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
                 label_mode: str = "water13", coherence: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    """Model input (C, H, W) in dB for one acquisition and, given a DSWx map, its target (H, W).

    coherence: the date's coherence (0 to 1, NaN where no pair), right after HH and HV ("+coh").
    reference: the stack's reference_db, appended after those (the "current+ref" inputs).
    Usable pixels are set by HH and HV only; a missing coherence does not drop a pixel.
    """
    x = np.stack([to_db(ds["HH"].values[t]), to_db(ds["HV"].values[t])]).astype("float32")
    usable = ds["valid"].values[t].astype(bool) & np.isfinite(x).all(axis=0)
    x[:, ~usable] = np.nan
    if coherence is not None:
        coh = coherence.astype("float32").copy()
        coh[~usable] = np.nan
        x = np.concatenate([x, coh[None]])
    if reference is not None:
        ref = reference.copy()
        ref[:, ~usable] = np.nan
        x = np.concatenate([x, ref])
    if water_map is None:
        return x, None
    return x, target(water_map, usable, label_mode)


def optical_classes(site: str, stack_id: str, day: str) -> np.ndarray | None:
    """OPERA DSWx-HLS classes of one NISAR date on the stack grid (data/optical, band 1), or None."""
    path = OPTICAL_DIR / f"{site}_{stack_id}" / f"{day}.tif"
    if not path.exists():
        return None
    import rasterio

    with rasterio.open(path) as src:
        return src.read(1)


def optical_disagreement(water_map: np.ndarray, optical: np.ndarray) -> np.ndarray:
    """Pixels where a clear optical map contradicts the Sentinel-1 map: Sentinel-1 open water where
    optical sees no water, or Sentinel-1 no water where optical sees open water. Partial water,
    cloud, inundated vegetation and masked labels are left alone."""
    s1_open = water_map == DSWX_OPEN_WATER
    s1_dry = ~np.isin(water_map, DSWX_INVALID) & ~np.isin(water_map, WATER_CLASSES)
    return (s1_open & (optical == OPTICAL_NOT_WATER)) | (s1_dry & (optical == OPTICAL_OPEN_WATER))


def load_scenes(site: str, stacks: tuple[str, ...] | None = None, max_gap_h: float = MAX_GAP_H,
                inputs: str = "current", label_mode: str = "water13",
                clean_with_optical: bool = False) -> list[Scene]:
    """Every labelled acquisition of a site (same-day water map, HV present), stored compactly."""
    from pipeline.cv.coherence import coherence_for

    if inputs not in INPUTS:
        raise ValueError(f"inputs must be one of {list(INPUTS)}, not {inputs!r}")
    index = {(e["stack_id"], e["date"]): e
             for e in json.loads((DSWX_RAW / site / "index.json").read_text(encoding="utf-8"))}
    scenes = []
    for stack_id in stacks or site_stacks(site):
        ds = open_stack(STACK_DIR / f"{site}_{stack_id}.nc")
        reference = reference_db(ds).astype("float16") if uses_reference(inputs) else None
        for day, t in date_index(ds).items():
            entry = index.get((stack_id, day))
            if not entry or entry["hours_from_nisar"] is None or entry["hours_from_nisar"] > max_gap_h:
                continue
            if not dswx_files(entry) or np.isnan(ds["HV"].values[t]).all():
                continue  # no label tiles, or an HH-only date
            water_map = dswx_on_grid(ds, dswx_files(entry))
            if np.isin(water_map, DSWX_INVALID).all():
                continue  # the pass's tiles touch the box but its swath misses the site: no label at all
            coherence = coherence_for(site, stack_id, day, water_map.shape) if uses_coherence(inputs) else None
            x, y = scene_arrays(ds, t, water_map, None, label_mode, coherence)  # the reference is added per crop
            usable = np.isfinite(x[:2]).all(axis=0)
            cls = np.where(usable & ~np.isin(water_map, DSWX_INVALID), water_map, IGNORE).astype("uint8")
            dropped, cleaned = None, 0
            if clean_with_optical:
                optical = optical_classes(site, stack_id, day)
                if optical is not None:
                    dropped = optical_disagreement(water_map, optical) & (y != IGNORE)
                    cleaned = int(dropped.sum())
                    dropped = dropped if cleaned else None
            # y and cls stay uncleaned, so windows, blocks and channel statistics match an uncleaned
            # variant; the dropped labels are masked crop by crop (CropDataset, TileDataset).
            scenes.append(Scene(site, stack_id, day, x.astype("float16"), y, cls, reference, entry["hours_from_nisar"],
                                COH_CHANNEL if coherence is not None else None, dropped, cleaned))
        del ds
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


def channel_stats(scenes: list[Scene], region: Region) -> tuple[np.ndarray, np.ndarray]:
    """Mean and std of each input channel (clipped dB) over labelled pixels inside region.

    Running float64 sums, one scene at a time, so many sites need no big concatenation.
    """
    n_ch = scenes[0].n_channels
    total, total_sq, count = np.zeros(n_ch), np.zeros(n_ch), np.zeros(n_ch)
    for s in scenes:
        keep = region_of(region, s) & (s.y != IGNORE)
        x = s.full()
        for c in range(n_ch):
            v = np.clip(x[c][keep], *DB_RANGE)
            v = v[np.isfinite(v)].astype("float64")
            total[c] += v.sum()
            total_sq[c] += (v * v).sum()
            count[c] += v.size
    mean = total / count
    std = np.sqrt(np.maximum(total_sq / count - mean * mean, 0.0))
    return mean.astype("float32"), np.maximum(std, 1e-3).astype("float32")  # a constant channel must not divide by 0


def standardize(x: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Clip dB, standardize per channel, and set unusable pixels to the channel mean (0)."""
    z = (np.clip(x, *DB_RANGE) - mean[:, None, None]) / std[:, None, None]
    return np.nan_to_num(z, nan=0.0).astype("float32")


def _integral(a: np.ndarray) -> np.ndarray:
    return np.pad(a.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def _box(s: np.ndarray, r: int, c: int, size: int) -> int:
    return int(s[r + size, c + size] - s[r, c + size] - s[r + size, c] + s[r, c])


def windows(allowed: np.ndarray, y: np.ndarray, size: int = TILE_PX, step: int = 32,
            min_labelled: float = 0.3) -> list[tuple[int, int]]:
    """Top-left corners of size x size windows that lie fully inside `allowed` and are labelled enough."""
    inside, labelled = _integral(allowed), _integral(y != IGNORE)
    h, w = allowed.shape
    return [(r, c) for r in range(0, h - size + 1, step) for c in range(0, w - size + 1, step)
            if _box(inside, r, c, size) == size * size and _box(labelled, r, c, size) >= min_labelled * size * size]


class CropDataset(torch.utils.data.Dataset):
    """Random training crops with flips and 90 degree turns; a fresh crop every item.

    With `focus` (where water is rare and matters, for example everything but the
    sea and permanent water), a `focus_share` of the crops is drawn from windows
    that hold at least `min_focus_px` water pixels inside the focus area, so the
    rare class is seen often enough to be learned. With `jitter_db`, every crop
    gets one random offset in [-jitter_db, jitter_db] dB on all channels, like a
    calibration difference between tracks, sites or processing releases.
    """

    def __init__(self, scenes: list[Scene], allowed: Region, mean: np.ndarray, std: np.ndarray,
                 samples: int, size: int = TILE_PX, seed: int = 0, focus: Region | None = None,
                 focus_share: float = 0.0, min_focus_px: int = 200, jitter_db: float = 0.0,
                 coh_dropout: float = 0.0):
        self.scenes, self.mean, self.std, self.size, self.samples = scenes, mean, std, size, samples
        self.jitter_db = jitter_db
        self.coh_dropout = coh_dropout  # share of crops whose coherence is blanked, as on dates with no pair
        self.focus_share = focus_share
        self.pool: list[tuple[int, tuple[int, int]]] = []
        self.focus_pool: list[tuple[int, tuple[int, int]]] = []
        for i, s in enumerate(scenes):
            corners = windows(region_of(allowed, s), s.y, size)
            self.pool += [(i, rc) for rc in corners]
            if focus is not None and focus_share > 0:
                sums = _integral(changing_water(s) & region_of(focus, s))  # one scene at a time
                self.focus_pool += [(i, (r, c)) for r, c in corners if _box(sums, r, c, size) >= min_focus_px]
        if not self.pool:
            raise ValueError("no training windows: check the split and the labels")
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return self.samples

    def __getitem__(self, _: int) -> tuple[torch.Tensor, torch.Tensor]:
        pool = self.focus_pool if self.focus_pool and self.rng.random() < self.focus_share else self.pool
        i, (r, c) = pool[int(self.rng.integers(len(pool)))]
        s = self.scenes[i]
        x = s.crop(r, c, self.size)
        if self.jitter_db:
            shift = np.float32(self.rng.uniform(-self.jitter_db, self.jitter_db))
            if s.coh_channel is None:
                x = x + shift
            else:  # a calibration offset moves the dB channels, never the coherence
                db = np.ones(x.shape[0], dtype=bool)
                db[s.coh_channel] = False
                x[db] += shift
        if s.coh_channel is not None and self.coh_dropout and self.rng.random() < self.coh_dropout:
            x[s.coh_channel] = np.nan  # the newest dates have no GUNW pair yet: learn to work without it
        x = standardize(x, self.mean, self.std)
        y = s.y[r:r + self.size, c:c + self.size]
        if s.dropped is not None:
            y = np.where(s.dropped[r:r + self.size, c:c + self.size], IGNORE, y).astype("uint8")
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

    def __init__(self, scenes: list[Scene], allowed: Region, mean: np.ndarray, std: np.ndarray,
                 size: int = TILE_PX):
        if any(s.cls is None for s in scenes):
            raise ValueError("validation scenes need their DSWx classes (Scene.cls)")
        self.mean, self.std, self.size = mean, std, size
        self.items = [(s, rc) for s in scenes for rc in windows(region_of(allowed, s), s.y, size, step=size)]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, k: int) -> tuple[torch.Tensor, torch.Tensor]:
        s, (r, c) = self.items[k]
        x = standardize(s.crop(r, c, self.size), self.mean, self.std)
        cls = s.cls[r:r + self.size, c:c + self.size]
        if s.dropped is not None:  # labels the optical cleanup drops are not scored either
            cls = np.where(s.dropped[r:r + self.size, c:c + self.size], IGNORE, cls)
        return torch.from_numpy(x), torch.from_numpy(cls.astype("uint8").copy())
