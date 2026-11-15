"""The rain-on-terrain model (pipeline.inertial, pipeline.inertial_kernel) on tiny grids.

Imports only numpy (and numba for the last test), so it also runs in the
separate numba venv of the simulation.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np
import pytest


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
