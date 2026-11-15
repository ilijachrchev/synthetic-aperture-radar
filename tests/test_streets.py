"""Terrain flow and scoring on tiny synthetic grids (pipeline.terrain_flow, pipeline.streets).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np
import pytest

from pipeline import terrain_flow as tf
from pipeline.streets import block_mean


def flow_setup(z: np.ndarray, valid: np.ndarray | None = None, sinks: np.ndarray | None = None):
    valid = np.ones(z.shape, dtype=bool) if valid is None else valid
    outlets = tf.outlet_cells(valid, sinks)
    zf = tf.fill_depressions(z, valid, outlets)
    code = tf.d8_directions(zf, valid, outlets)
    code, info = tf.drain_flats(zf, code, valid, outlets)
    rec = tf.receivers(code)
    return zf, code, rec, outlets, info


def valley(rows: int = 9, cols: int = 7) -> np.ndarray:
    """A valley draining north to south: the channel is the middle column, sides rise 1 m per cell."""
    c = np.arange(cols)
    side = np.abs(c - cols // 2).astype(float)
    down = np.linspace(rows, 1, rows)[:, None] * 0.1
    return (side[None, :] + down).astype(np.float32)


def test_block_mean_ignores_nodata():
    a = np.arange(100, dtype=np.float32).reshape(10, 10)
    a[0, 0] = -9999.0
    out = block_mean(a, 5, -9999.0)
    assert out[0, 0] == pytest.approx(550.0 / 24)
    assert out[1, 1] == pytest.approx(a[5:, 5:].mean())
    a[:5, :5] = -9999.0
    a[0, 0] = 1.0
    assert block_mean(a, 5, -9999.0)[0, 0] == -9999.0


def test_fill_raises_a_pit_to_its_spill_level():
    z = np.full((5, 5), 5.0, dtype=np.float32)
    z[2, 2] = 1.0       # a pit
    z[2, 3] = 3.0       # its lowest rim
    z[2, 4] = 2.0       # an edge outlet behind the rim
    valid = np.ones(z.shape, dtype=bool)
    zf = tf.fill_depressions(z, valid, tf.outlet_cells(valid))
    assert zf[2, 2] == pytest.approx(3.0)
    assert zf[0, 0] == pytest.approx(5.0)
    assert (zf >= z).all()


def test_every_cell_drains_and_flats_point_to_their_outlet():
    z = np.full((6, 8), 2.0, dtype=np.float32)  # one wide flat
    z[:, 0] = 1.0                                # lower column on the west edge
    z[0, :] = 9.0
    z[-1, :] = 9.0
    z[:, -1] = 9.0
    z[0, 0] = z[-1, 0] = 9.0
    zf, code, rec, outlets, info = flow_setup(z)
    interior = ~outlets
    assert (code[interior] != tf.NO_DIR).all(), "every non-outlet cell drains"
    assert info["left_undrained"] == 0
    # the flat drains west, one step per round
    assert code[3, 6] == 3  # (0, -1): west
    acc = tf.accumulate(rec, np.ones(z.shape, dtype=bool))
    assert acc.max() <= z.size


def test_accumulation_and_hand_in_a_valley():
    z = valley()
    zf, code, rec, outlets, _ = flow_setup(z)
    acc = tf.accumulate(rec, np.ones(z.shape, dtype=bool))
    mid = z.shape[1] // 2
    # the channel collects more downstream; its last interior cell holds most of the grid
    assert acc[-2, mid] > acc[1, mid]
    drainage = np.zeros(z.shape, dtype=bool)
    drainage[:, mid] = True
    h, target = tf.hand(zf, rec, drainage)
    r, c = 4, mid + 2
    assert target.reshape(z.shape)[r, c] in np.flatnonzero(drainage.ravel())
    assert h[r, mid] == pytest.approx(0.0)
    assert h[r, c] == pytest.approx(zf[r, c] - zf.ravel()[target.reshape(z.shape)[r, c]])
    assert h[r, c] > 1.0


def test_hand_is_nan_where_no_drainage_is_met():
    z = valley()
    zf, code, rec, outlets, _ = flow_setup(z)
    h, _ = tf.hand(zf, rec, np.zeros(z.shape, dtype=bool))
    assert np.isnan(h).all()


def test_sinks_are_outlets():
    z = np.full((5, 5), 3.0, dtype=np.float32)
    z[2, 2] = 0.0
    sinks = np.zeros(z.shape, dtype=bool)
    sinks[2, 2] = True
    valid = np.ones(z.shape, dtype=bool)
    zf = tf.fill_depressions(z, valid, tf.outlet_cells(valid, sinks))
    assert zf[2, 2] == pytest.approx(0.0), "a sink is not filled"


def test_upstream_of_a_cell():
    z = valley()
    zf, code, rec, outlets, _ = flow_setup(z)
    mid = z.shape[1] // 2
    cell = 4 * z.shape[1] + mid
    up = tf.upstream_of(rec, cell).reshape(z.shape)
    assert up[4, mid] and up[1, mid]
    assert not up[7, mid]


def test_equal_area_pick_lowest_first_ties_by_upstream_area():
    score = np.array([3.0, 1.0, 1.0, np.nan, 0.5])
    tie = np.array([0.0, 10.0, 20.0, 0.0, 0.0])
    assert list(tf.equal_area_pick(score, tie, 3)) == [4, 2, 1]
    assert list(tf.equal_area_pick(score, tie, 5))[-1] == 3  # NaN last
    assert tf.equal_area_pick(score, tie, 0).size == 0



def test_metrics_on_a_tiny_pixel_set():
    from pipeline.streets import metrics

    # 10 scored pixels; the reference saw 4 flooded (2 water, 2 traces)
    fa = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0], dtype=bool)
    ft = np.array([0, 0, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)
    icv = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype=bool)
    refs = {"flooded_area": fa, "flood_trace": ft, "observed": fa | ft, "lb_observed": fa, "icv": icv}
    sel = np.array([0, 1, 1, 0, 1, 0, 0, 0, 0, 0], dtype=bool)  # 3 pixels, 2 of them flooded
    buildings = np.array([2, 3, 3, 9])  # positions; the same pixel can hold two buildings
    marks = np.array([4])
    m = metrics(sel, refs, buildings, marks)
    assert m["area_pct_of_scored"] == 30.0
    assert m["own_area_flooded_pct"] == pytest.approx(66.7)
    assert m["observed_covered_pct"] == 50.0
    assert m["flood_trace_covered_pct"] == 50.0
    assert m["flooded_area_covered_pct"] == 50.0
    assert m["buildings_covered_pct"] == 25.0
    assert m["water_marks_covered_pct"] == 100.0
    assert m["generalitat_footprint_covered_pct"] == 60.0
    assert m["own_area_in_generalitat_footprint_pct"] == 100.0
    assert m["chance_own_area_flooded_pct"] == 40.0
    assert m["area_ha"] == pytest.approx(3 * 25 / 1e4, abs=0.05)


def test_metrics_with_nothing_observed_gives_none():
    from pipeline.streets import metrics

    z = np.zeros(4, dtype=bool)
    refs = {"flooded_area": z, "flood_trace": z, "observed": z, "lb_observed": z, "icv": z}
    m = metrics(z.copy(), refs, np.zeros(0, dtype=int), np.zeros(0, dtype=int))
    assert m["own_area_flooded_pct"] is None and m["buildings_covered_pct"] is None


def test_large_water_keeps_lakes_and_drops_ponds():
    from pipeline.streets import CELL_M, large_water

    w = np.zeros((300, 300), dtype=bool)
    w[:250, :250] = True        # 250 x 250 cells of 25 m2: 1.5625 km2, a lake
    w[260:262, 260:262] = True  # a pond
    big = large_water(w, min_km2=1.0)
    assert big[:250, :250].all()
    assert not big[260:262, 260:262].any()
    assert CELL_M == 5.0


def test_burn_uses_cell_centres_and_points_find_their_cell():
    import shapely

    from pipeline import streets as s

    w, s_, e, n = s.GRID_BOUNDS
    # a 10 m square whose edges fall on cell edges covers exactly 2 x 2 cells
    sq = shapely.box(w + 10, n - 20, w + 20, n - 10)
    m = s.burn([sq])
    assert m.sum() == 4 and m[2:4, 2:4].all()
    cols = s.grid_shape()[1]
    idx = s.cells_of_points(np.array([w + 12.0, w - 1.0]), np.array([n - 17.0, n - 1.0]))
    assert idx[0] == 3 * cols + 2 and idx[1] == -1
