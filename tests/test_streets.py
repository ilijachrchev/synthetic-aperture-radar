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


def test_inertial_rain_runs_downhill_and_conserves_mass():
    from pipeline.inertial import Run

    rows, cols = 12, 20
    z = np.tile(np.linspace(5.0, 0.0, cols), (rows, 1))  # slopes down to the east
    sinks = np.zeros((rows, cols), dtype=bool)
    sinks[:, -1] = True  # the east edge takes the water away
    run = Run(z=z, sinks=sinks, dx=10.0, n_manning=0.05)
    rain = np.zeros((rows, cols))
    rain[:, :5] = 50e-3 / 3600.0  # 50 mm/h on the west (high) part only
    while run.t < 1800.0:
        run.step(rain)
    stored, lost = run.stored_volume_m3(), run.sink_volume_m3
    assert run.rain_volume_m3 > 0
    assert stored + lost == pytest.approx(run.rain_volume_m3, rel=1e-9)
    assert (run.h >= 0).all()
    assert run.hmax[:, 10:-1].max() > 0, "water reached the dry east part"


def test_inertial_flat_pool_stays_still():
    from pipeline.inertial import Run

    z = np.zeros((8, 8))
    z[:, 0] = z[:, -1] = z[0, :] = z[-1, :] = 10.0  # a closed box
    run = Run(z=z, sinks=np.zeros(z.shape, dtype=bool), dx=5.0)
    run.h[1:-1, 1:-1] = 1.0
    for _ in range(200):
        run.step(0.0)
    assert np.abs(run.h[1:-1, 1:-1] - 1.0).max() < 1e-9


def small_simulation_inputs():
    rows, cols = 16, 24
    z = np.tile(np.linspace(6.0, 0.0, cols), (rows, 1)) + 0.3 * np.sin(np.arange(rows))[:, None]
    sinks = np.zeros((rows, cols), dtype=bool)
    sinks[0, :] = sinks[-1, :] = sinks[:, 0] = sinks[:, -1] = True
    frac = np.zeros((2, rows, cols), dtype=np.float32)
    frac[0, :, :8] = 1.0
    frac[1, :, 8:12] = 0.5
    rates = np.array([[20e-3, 60e-3, 0.0], [10e-3, 0.0, 5e-3]]) / 3600.0
    gauge = np.zeros((rows, cols), dtype=bool)
    gauge[:, :8] = True
    return {"z": z, "sinks": sinks, "zone_frac": frac, "zone_rates": rates,
            "hour_edges_s": np.array([0.0, 600.0, 1200.0, 1800.0]), "t_end_s": 2400.0, "dx": 10.0,
            "n_manning": 0.05, "alpha": 0.7, "dt_max": 10.0, "record_every_s": 300.0, "gauge_mask": gauge}


def test_simulation_driver_conserves_mass_and_records_the_gauge():
    from pipeline.inertial import run_numpy

    out = run_numpy(small_simulation_inputs())
    assert out["rain_volume_m3"] == pytest.approx(out["sink_volume_m3"] + out["stored_volume_m3"], rel=1e-9)
    assert out["gauge_t_s"].size == 9  # right after the first step, then every 300 s to 2400 s
    assert out["gauge_q_m3s"].max() > 0


def test_numba_kernel_matches_numpy_scheme():
    pytest.importorskip("numba")
    from pipeline.inertial import run_numpy
    from pipeline.inertial_kernel import run

    inp = small_simulation_inputs()
    a, b = run_numpy(inp), run(inp)
    assert a["steps"] == b["steps"]
    np.testing.assert_allclose(a["hmax"], b["hmax"], atol=1e-6)
    np.testing.assert_allclose(a["gauge_q_m3s"], b["gauge_q_m3s"], rtol=1e-6, atol=1e-9)
