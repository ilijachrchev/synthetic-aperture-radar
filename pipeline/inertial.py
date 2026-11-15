"""A small 2D rain-on-terrain model: the local inertial shallow water scheme.

Bates, Horritt and Fewtrell (2010), "A simple inertial formulation of the
shallow water equations for efficient two-dimensional flood inundation
modelling", Journal of Hydrology 387, 33 to 45. Unit discharges on the cell
faces are updated explicitly with the water surface slope and Manning friction
(their eq. 11); depths follow from continuity; the time step is set by the
Courant condition dt = alpha * dx / sqrt(g * h_max) (their eq. 12, alpha 0.7).
A face carries water only where the free surface is above both beds
(h_flow = max(eta) - max(z)). Outflow from a cell is scaled down when it would
take more water than the cell holds, so depths never go negative.

Everything here is SIMULATED. No infiltration (all rain runs off), one
Manning's n everywhere, cells marked as sinks (grid edge, sea, permanent water)
remove the water that reaches them.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

G = 9.81
H_MIN = 1e-3  # m: faces with less flow depth carry nothing


@dataclass
class Run:
    z: np.ndarray              # bed elevation (m), float64 or float32
    sinks: np.ndarray          # bool: water reaching these cells leaves the model
    dx: float                  # cell size (m)
    n_manning: float = 0.05
    alpha: float = 0.7
    dt_max: float = 10.0
    h: np.ndarray = field(init=False)
    qx: np.ndarray = field(init=False)
    qy: np.ndarray = field(init=False)
    hmax: np.ndarray = field(init=False)
    t: float = 0.0
    rain_volume_m3: float = 0.0
    sink_volume_m3: float = 0.0

    def __post_init__(self):
        rows, cols = self.z.shape
        self.z = self.z.astype(np.float64)
        self.h = np.zeros((rows, cols))
        self.qx = np.zeros((rows, cols + 1))
        self.qy = np.zeros((rows + 1, cols))
        self.hmax = np.zeros((rows, cols), dtype=np.float32)

    def time_step(self) -> float:
        hm = float(self.h.max())
        if hm < 0.01:
            return self.dt_max
        return min(self.dt_max, self.alpha * self.dx / np.sqrt(G * hm))

    def _face_flux(self, q: np.ndarray, eta_a: np.ndarray, eta_b: np.ndarray, z_a: np.ndarray,
                   z_b: np.ndarray, dt: float) -> np.ndarray:
        """Bates et al. (2010) eq. 11 on interior faces between cells a and b (b after a)."""
        hflow = np.maximum(eta_a, eta_b) - np.maximum(z_a, z_b)
        wet = hflow > H_MIN
        slope = (eta_b - eta_a) / self.dx
        hf = np.where(wet, hflow, 1.0)
        qn = (q - G * hf * dt * slope) / (1.0 + G * dt * self.n_manning ** 2 * np.abs(q) / hf ** (7.0 / 3.0))
        return np.where(wet, qn, 0.0)

    def step(self, rain_rate: np.ndarray | float, dt: float | None = None) -> float:
        """Advance one step. rain_rate: m/s per cell (array or scalar). Returns dt."""
        dt = self.time_step() if dt is None else dt
        z, h, dx = self.z, self.h, self.dx
        eta = z + h
        qx, qy = self.qx, self.qy
        qx[:, 1:-1] = self._face_flux(qx[:, 1:-1], eta[:, :-1], eta[:, 1:], z[:, :-1], z[:, 1:], dt)
        qy[1:-1, :] = self._face_flux(qy[1:-1, :], eta[:-1, :], eta[1:, :], z[:-1, :], z[1:, :], dt)
        # outer faces carry nothing: the edge cells are sinks
        qx[:, 0] = qx[:, -1] = 0.0
        qy[0, :] = qy[-1, :] = 0.0
        # positivity: scale the outflow of any cell that would give more than it holds
        out = (np.maximum(qx[:, 1:], 0) + np.maximum(-qx[:, :-1], 0)
               + np.maximum(qy[1:, :], 0) + np.maximum(-qy[:-1, :], 0)) * dt / dx
        avail = h + rain_rate * dt
        ratio = np.where(out > avail, avail / np.maximum(out, 1e-12), 1.0)
        # a face flux leaves the cell on its upwind side
        qx[:, 1:-1] *= np.where(qx[:, 1:-1] > 0, ratio[:, :-1], ratio[:, 1:])
        qy[1:-1, :] *= np.where(qy[1:-1, :] > 0, ratio[:-1, :], ratio[1:, :])
        dh = (qx[:, :-1] - qx[:, 1:] + qy[:-1, :] - qy[1:, :]) * dt / dx
        rain = rain_rate * dt
        self.rain_volume_m3 += float(np.sum(rain)) * dx * dx if np.ndim(rain) else rain * h.size * dx * dx
        h += dh + rain
        np.maximum(h, 0.0, out=h)
        self.sink_volume_m3 += float(h[self.sinks].sum()) * dx * dx
        h[self.sinks] = 0.0
        np.maximum(self.hmax, h.astype(np.float32), out=self.hmax)
        self.t += dt
        return dt

    def stored_volume_m3(self) -> float:
        return float(self.h.sum()) * self.dx * self.dx

    def boundary_outflow(self, inside: np.ndarray) -> float:
        """Discharge (m3/s) leaving the `inside` cells across their boundary faces right now."""
        dx = self.dx
        qx, qy = self.qx, self.qy
        left_in, right_in = inside[:, :-1], inside[:, 1:]
        up_in, down_in = inside[:-1, :], inside[1:, :]
        fx = qx[:, 1:-1]
        fy = qy[1:-1, :]
        q = (fx[left_in & ~right_in].sum() - fx[~left_in & right_in].sum()
             + fy[up_in & ~down_in].sum() - fy[~up_in & down_in].sum())
        return float(q) * dx


def run_numpy(inp: dict) -> dict:
    """The driver of pipeline.inertial_kernel.run with the numpy scheme (slow; the reference)."""
    import time

    z = inp["z"].astype(np.float64)
    frac = inp["zone_frac"].astype(np.float64)
    rates = inp["zone_rates"].astype(np.float64)
    edges = inp["hour_edges_s"].astype(np.float64)
    t_end, every = float(inp["t_end_s"]), float(inp["record_every_s"])
    gauge = inp["gauge_mask"].astype(bool)
    run = Run(z=z, sinks=inp["sinks"].astype(bool), dx=float(inp["dx"]), n_manning=float(inp["n_manning"]),
              alpha=float(inp["alpha"]), dt_max=float(inp["dt_max"]))
    rec_t, rec_q, next_rec, hour, steps = [], [], 0.0, -1, 0
    rain = np.zeros(z.shape)
    wall = time.time()
    while run.t < t_end - 1e-9:
        k = int(np.searchsorted(edges, run.t, side="right")) - 1
        if k != hour:
            hour = k
            rain = np.zeros(z.shape)
            if 0 <= k < rates.shape[1]:
                for zi in range(frac.shape[0]):
                    rain += frac[zi] * rates[zi, k]
        dt = run.time_step()
        nxt = [t_end, next_rec] + ([edges[k + 1]] if 0 <= k + 1 < edges.size else [])
        dt = min(dt, min(v for v in nxt if v > run.t + 1e-9) - run.t)
        run.step(rain, dt)
        steps += 1
        if run.t >= next_rec - 1e-9:
            rec_t.append(run.t)
            rec_q.append(run.boundary_outflow(gauge))
            next_rec += every
    return {"hmax": run.hmax.astype(np.float32), "h_end": run.h.astype(np.float32), "gauge_t_s": np.array(rec_t),
            "gauge_q_m3s": np.array(rec_q), "rain_volume_m3": run.rain_volume_m3, "sink_volume_m3": run.sink_volume_m3,
            "stored_volume_m3": run.stored_volume_m3(), "steps": steps, "wall_s": time.time() - wall}
