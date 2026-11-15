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

