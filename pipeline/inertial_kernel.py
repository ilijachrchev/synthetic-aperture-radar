"""Fast version of pipeline.inertial (the same local inertial scheme) with numba.

Run as a script by an interpreter that has numpy and numba (numba is not in the
shared stack; `python -m pipeline.streets simulate` makes a separate venv for it
under data/interim/streets/ and falls back to the slow numpy version without it):

    python inertial_kernel.py inputs.npz outputs.npz

Imports only numpy and numba. tests/test_streets.py checks it against
pipeline.inertial.Run step by step when numba is available.

SIMULATED: no infiltration, one Manning's n, sinks remove the water that reaches them.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import sys
import time

import numpy as np
from numba import njit, prange

G = 9.81
H_MIN = 1e-3


@njit(parallel=True)
def step(z, h, qx, qy, sinks, rain, dx, dt, n2, hmax, ratio):
    """One step; returns (rain volume, sink volume) in m3. Same order of operations as Run.step."""
    rows, cols = h.shape
    for i in prange(rows):
        for j in range(1, cols):
            ea = z[i, j - 1] + h[i, j - 1]
            eb = z[i, j] + h[i, j]
            hf = max(ea, eb) - max(z[i, j - 1], z[i, j])
            if hf > H_MIN:
                q = qx[i, j]
                qx[i, j] = (q - G * hf * dt * (eb - ea) / dx) / (1.0 + G * dt * n2 * abs(q) / hf ** (7.0 / 3.0))
            else:
                qx[i, j] = 0.0
        qx[i, 0] = 0.0
        qx[i, cols] = 0.0
    for i in prange(1, rows):
        for j in range(cols):
            ea = z[i - 1, j] + h[i - 1, j]
            eb = z[i, j] + h[i, j]
            hf = max(ea, eb) - max(z[i - 1, j], z[i, j])
            if hf > H_MIN:
                q = qy[i, j]
                qy[i, j] = (q - G * hf * dt * (eb - ea) / dx) / (1.0 + G * dt * n2 * abs(q) / hf ** (7.0 / 3.0))
            else:
                qy[i, j] = 0.0
    for j in range(cols):
        qy[0, j] = 0.0
        qy[rows, j] = 0.0
    for i in prange(rows):
        for j in range(cols):
            o = (max(qx[i, j + 1], 0.0) + max(-qx[i, j], 0.0) + max(qy[i + 1, j], 0.0) + max(-qy[i, j], 0.0)) * dt / dx
            avail = h[i, j] + rain[i, j] * dt
            ratio[i, j] = avail / max(o, 1e-12) if o > avail else 1.0
    for i in prange(rows):
        for j in range(1, cols):
            q = qx[i, j]
            qx[i, j] = q * (ratio[i, j - 1] if q > 0 else ratio[i, j])
    for i in prange(1, rows):
        for j in range(cols):
            q = qy[i, j]
            qy[i, j] = q * (ratio[i - 1, j] if q > 0 else ratio[i, j])
    rain_row = np.zeros(rows)
    sink_row = np.zeros(rows)
    for i in prange(rows):
        rr = 0.0
        ss = 0.0
        for j in range(cols):
            r = rain[i, j] * dt
            rr += r
            hn = h[i, j] + (qx[i, j] - qx[i, j + 1] + qy[i, j] - qy[i + 1, j]) * dt / dx + r
            if hn < 0.0:
                hn = 0.0
            if sinks[i, j]:
                ss += hn
                hn = 0.0
            h[i, j] = hn
            if hn > hmax[i, j]:
                hmax[i, j] = hn
        rain_row[i] = rr
        sink_row[i] = ss
    return rain_row.sum() * dx * dx, sink_row.sum() * dx * dx


@njit
def boundary_outflow(qx, qy, inside, dx):
    rows, cols = inside.shape
    q = 0.0
    for i in range(rows):
        for j in range(1, cols):
            a, b = inside[i, j - 1], inside[i, j]
            if a and not b:
                q += qx[i, j]
            elif b and not a:
                q -= qx[i, j]
    for i in range(1, rows):
        for j in range(cols):
            a, b = inside[i - 1, j], inside[i, j]
            if a and not b:
                q += qy[i, j]
            elif b and not a:
                q -= qy[i, j]
    return q * dx


def run(inp: dict, progress: bool = False) -> dict:
    """The whole simulation: hourly rain per zone, CFL time steps, gauge record every `record_every_s`."""
    z = inp["z"].astype(np.float64)
    rows, cols = z.shape
    sinks = inp["sinks"].astype(np.bool_)
    frac = inp["zone_frac"].astype(np.float64)        # (zones, rows, cols)
    rates = inp["zone_rates"].astype(np.float64)       # (zones, hours) m/s
    edges = inp["hour_edges_s"].astype(np.float64)     # (hours + 1,)
    t_end = float(inp["t_end_s"])
    dx = float(inp["dx"])
    n2 = float(inp["n_manning"]) ** 2
    alpha = float(inp["alpha"])
    dt_max = float(inp["dt_max"])
    every = float(inp["record_every_s"])
    gauge = inp["gauge_mask"].astype(np.bool_)
    h = np.zeros((rows, cols))
    qx = np.zeros((rows, cols + 1))
    qy = np.zeros((rows + 1, cols))
    hmax = np.zeros((rows, cols))
    ratio = np.ones((rows, cols))
    t, steps, rain_v, sink_v = 0.0, 0, 0.0, 0.0
    rec_t, rec_q = [], []
    next_rec = 0.0
    hour = -1
    rain = np.zeros((rows, cols))
    wall = time.time()
    while t < t_end - 1e-9:
        k = int(np.searchsorted(edges, t, side="right")) - 1
        if k != hour:
            hour = k
            if progress:
                print(f"hour {k}: t {t / 3600:.2f} h, steps {steps}, max depth {h.max():.2f} m, "
                      f"wall {time.time() - wall:.0f} s", flush=True)
            rain[:] = 0.0
            if 0 <= k < rates.shape[1]:
                for zi in range(frac.shape[0]):
                    rain += frac[zi] * rates[zi, k]
        hm = h.max()
        dt = dt_max if hm < 0.01 else min(dt_max, alpha * dx / np.sqrt(G * hm))
        nxt = [t_end, next_rec]
        if 0 <= k + 1 < edges.size:
            nxt.append(edges[k + 1])
        dt = min(dt, min(v for v in nxt if v > t + 1e-9) - t)
        r, s = step(z, h, qx, qy, sinks, rain, dx, dt, n2, hmax, ratio)
        rain_v += r
        sink_v += s
        t += dt
        steps += 1
        if t >= next_rec - 1e-9:
            rec_t.append(t)
            rec_q.append(boundary_outflow(qx, qy, gauge, dx))
            next_rec += every
    return {"hmax": hmax.astype(np.float32), "h_end": h.astype(np.float32), "gauge_t_s": np.array(rec_t),
            "gauge_q_m3s": np.array(rec_q), "rain_volume_m3": rain_v, "sink_volume_m3": sink_v,
            "stored_volume_m3": float(h.sum()) * dx * dx, "steps": steps, "wall_s": time.time() - wall}


if __name__ == "__main__":
    data = dict(np.load(sys.argv[1]))
    out = run(data, progress=True)
    np.savez_compressed(sys.argv[2], **out)
    print(f"steps {out['steps']}, wall {out['wall_s']:.0f} s, rain {out['rain_volume_m3'] / 1e6:.2f} hm3, "
          f"to sinks {out['sink_volume_m3'] / 1e6:.2f} hm3, stored {out['stored_volume_m3'] / 1e6:.2f} hm3")
