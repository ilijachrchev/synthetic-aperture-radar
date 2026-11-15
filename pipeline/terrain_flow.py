"""Terrain flow on a grid: depressions filled, flats drained, D8 flow, accumulation, HAND.

Plain numpy, scipy and scikit-image (the shared stack), written for grids of
tens of millions of cells with little memory: one int8 direction code per cell,
int32 cell indices, and loops over the 8 neighbours instead of 8 stacked copies.

- fill_depressions: morphological reconstruction by erosion (Soille 2004), the
  same surface a priority flood gives: every cell can drain to an outlet.
- d8_directions: steepest descent to one of the 8 neighbours.
- drain_flats: cells left without a lower neighbour (flat areas, often filled
  depressions) drain along the shortest path inside their flat to a cell of the
  same height that can drain (a breadth-first search from the flat's outlets),
  in the spirit of Garbrecht and Martz (1997).
- accumulate: D8 flow accumulation in topological order (Kahn's algorithm).
- hand: height above the nearest drainage (Nobre et al. 2011) by pointer jumping
  along the flow paths.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np

# D8 neighbours: (row offset, column offset); code k is the index in this list.
OFFSETS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
DIST = tuple(float(np.hypot(dr, dc)) for dr, dc in OFFSETS)
NO_DIR = -1  # no receiver: an outlet (water leaves the grid) or an undrained cell


def _shift(a: np.ndarray, dr: int, dc: int, fill) -> np.ndarray:
    """out[r, c] = a[r + dr, c + dc]; `fill` outside the grid."""
    out = np.full(a.shape, fill, dtype=a.dtype)
    rows, cols = a.shape
    r0, r1 = max(0, -dr), min(rows, rows - dr)
    c0, c1 = max(0, -dc), min(cols, cols - dc)
    out[r0:r1, c0:c1] = a[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
    return out


def outlet_cells(valid: np.ndarray, sinks: np.ndarray | None = None) -> np.ndarray:
    """Valid cells where water can leave: on the grid edge, next to a missing cell, or a sink (permanent water)."""
    out = np.zeros(valid.shape, dtype=bool)
    out[0, :] = out[-1, :] = True
    out[:, 0] = out[:, -1] = True
    for dr, dc in OFFSETS:
        out |= ~_shift(valid, dr, dc, False)
    out &= valid
    if sinks is not None:
        out |= sinks & valid
    return out


def fill_depressions(z: np.ndarray, valid: np.ndarray, outlets: np.ndarray) -> np.ndarray:
    """Lowest surface at or above z from which every valid cell can drain to an outlet.

    Missing cells are left as they are (they are outside the computation).
    """
    from skimage.morphology import reconstruction

    z = z.astype(np.float32, copy=False)  # float32 keeps scikit-image's work arrays at half the size
    low = np.float32(z[valid].min() - 1.0)
    high = np.float32(z[valid].max() + 1.0)
    mask = np.where(valid, z, low).astype(np.float32, copy=False)
    seed = np.where(outlets | ~valid, mask, high).astype(np.float32, copy=False)
    filled = reconstruction(seed, mask, method="erosion", footprint=np.ones((3, 3), dtype=bool))
    del seed, mask
    out = np.where(valid, filled, z).astype(np.float32, copy=False)
    return out


def d8_directions(zf: np.ndarray, valid: np.ndarray, outlets: np.ndarray) -> np.ndarray:
    """Steepest-descent neighbour code (0 to 7) of every valid cell; NO_DIR where no neighbour is lower.

    Outlet cells that are sinks keep NO_DIR only if they have no lower neighbour; water
    on a grid-edge outlet with no lower neighbour leaves the grid.
    """
    best = np.zeros(zf.shape, dtype=np.float32)
    code = np.full(zf.shape, NO_DIR, dtype=np.int8)
    for k, (dr, dc) in enumerate(OFFSETS):
        nb = _shift(zf, dr, dc, np.float32(np.inf))
        nbv = _shift(valid, dr, dc, False)
        drop = (zf - nb) / np.float32(DIST[k])
        better = valid & nbv & (drop > best)
        best[better] = drop[better]
        code[better] = k
        del nb, nbv, drop, better
    return code


def flat_index_offsets(cols: int) -> np.ndarray:
    return np.array([dr * cols + dc for dr, dc in OFFSETS], dtype=np.int64)


def neighbour_ok(r: np.ndarray, c: np.ndarray, k: int, shape: tuple[int, int]) -> np.ndarray:
    dr, dc = OFFSETS[k]
    rr, cc = r + dr, c + dc
    return (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])


def drain_flats(zf: np.ndarray, code: np.ndarray, valid: np.ndarray, outlets: np.ndarray) -> tuple[np.ndarray, dict]:
    """Give a direction to valid non-outlet cells without one (flats).

    Breadth-first from the flat's outlets: a flat cell points to a neighbour of the
    same height that already drains, the cells next to the outlets first. Adjacent
    undrained cells always have the same height (otherwise the higher one would have
    a lower neighbour), so the search never crosses into another flat. Returns the
    updated codes and a few counts.
    """
    shape = zf.shape
    cols = shape[1]
    code = code.copy()
    todo = np.flatnonzero((valid & (code == NO_DIR) & ~outlets).ravel())
    info = {"flat_cells": int(todo.size), "rounds": 0, "left_undrained": 0}
    if todo.size == 0:
        return code, info
    zflat = zf.ravel()
    cflat = code.ravel()
    vflat = valid.ravel()
    oflat = outlets.ravel()
    offs = flat_index_offsets(cols)
    # "drains": has a direction or is an outlet. Flat cells look for a draining
    # neighbour of exactly the same height.
    drains = (cflat != NO_DIR) | (oflat & vflat)
    while todo.size:
        r, c = np.divmod(todo, cols)
        got = np.full(todo.size, NO_DIR, dtype=np.int8)
        for k in (1, 3, 4, 6, 0, 2, 5, 7):  # straight neighbours first, then diagonals
            free = got == NO_DIR
            if not free.any():
                break
            ok = free & neighbour_ok(r, c, k, shape)
            nb = todo[ok] + offs[k]
            hit = vflat[nb] & drains[nb] & (zflat[nb] == zflat[todo[ok]])
            idx = np.flatnonzero(ok)[hit]
            got[idx] = k
        assigned = got != NO_DIR
        if not assigned.any():
            break
        cflat[todo[assigned]] = got[assigned]
        drains[todo[assigned]] = True
        todo = todo[~assigned]
        info["rounds"] += 1
    info["left_undrained"] = int(todo.size)
    return cflat.reshape(shape), info


def receivers(code: np.ndarray) -> np.ndarray:
    """Flat index of each cell's receiver (int64), -1 where there is none."""
    rows, cols = code.shape
    offs = flat_index_offsets(cols)
    flat = code.ravel()
    rec = np.full(flat.size, -1, dtype=np.int64)
    has = flat != NO_DIR
    idx = np.flatnonzero(has)
    rec[idx] = idx + offs[flat[idx]]
    return rec


def accumulate(rec: np.ndarray, valid: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """D8 accumulation: each cell's own weight plus everything that flows into it (float64 per cell)."""
    vflat = valid.ravel()
    n = rec.size
    acc = (np.ones(n) if weights is None else weights.ravel().astype(np.float64)).copy()
    acc[~vflat] = 0.0
    has = rec >= 0
    indeg = np.bincount(rec[has], minlength=n).astype(np.int32)
    frontier = np.flatnonzero((indeg == 0) & vflat)
    while frontier.size:
        r = rec[frontier]
        m = r >= 0
        src, dst = frontier[m], r[m]
        np.add.at(acc, dst, acc[src])
        np.subtract.at(indeg, dst, 1)
        dst = np.unique(dst)
        frontier = dst[indeg[dst] == 0]
    if (indeg[vflat] > 0).any():
        raise RuntimeError("flow directions contain a loop")
    return acc.reshape(valid.shape)


def follow_to(rec: np.ndarray, stop: np.ndarray) -> np.ndarray:
    """For every cell, the first cell on its flow path (itself included) where `stop` holds,
    or the end of its path (a cell with no receiver). Pointer jumping: about log2(path length) rounds."""
    n = rec.size
    sflat = stop.ravel()
    target = np.where(sflat | (rec < 0), np.arange(n, dtype=np.int64), rec)
    for _ in range(64):
        nxt = target[target]
        if np.array_equal(nxt, target):
            return target
        target = nxt
    raise RuntimeError("flow paths did not converge (a loop?)")


def hand(zf: np.ndarray, rec: np.ndarray, drainage: np.ndarray, heights: np.ndarray | None = None
         ) -> tuple[np.ndarray, np.ndarray]:
    """Height above the nearest drainage along the flow path.

    heights: the surface to measure on (default zf). Cells whose path ends without
    meeting a drainage cell get NaN. Returns (hand, drainage cell index per cell).
    """
    target = follow_to(rec, drainage)
    h = (heights if heights is not None else zf).ravel().astype(np.float32)
    out = h - h[target]
    out[~drainage.ravel()[target]] = np.nan
    return out.reshape(zf.shape), target


def upstream_of(rec: np.ndarray, cell: int) -> np.ndarray:
    """Boolean mask (flat) of the cells whose flow path passes through `cell` (itself included)."""
    stop = np.zeros(rec.size, dtype=bool)
    stop[cell] = True
    return follow_to(rec, stop) == cell


def equal_area_pick(score: np.ndarray, tiebreak: np.ndarray, count: int) -> np.ndarray:
    """Indices of the `count` entries with the lowest score; ties: larger tiebreak first, then lower index.

    NaN scores rank last.
    """
    if count <= 0:
        return np.zeros(0, dtype=np.int64)
    s = np.where(np.isfinite(score), score, np.inf)
    order = np.lexsort((np.arange(s.size), -tiebreak, s))
    return order[:count]
