"""Checks for the NISAR SME2 soil-moisture layers (storage, dates, the past-only lookup). Written with SI assistance (Claude Code)."""

import numpy as np
import pytest

from pipeline import soil_moisture as sm_mod
from pipeline.config import get_site
from pipeline.stack import site_grid


def test_uint16_round_trip_and_no_data():
    sm = np.array([[0.0, 0.2153, 0.6], [np.nan, -0.1, 1.2]], "float32")
    q = sm_mod.to_uint16(sm)
    assert q[1, 0] == sm_mod.NODATA and q[1, 1] == sm_mod.NODATA and q[1, 2] == sm_mod.NODATA
    back = sm_mod.from_uint16(q)
    assert back[0, 1] == pytest.approx(0.2153, abs=1e-4) and back[0, 2] == pytest.approx(0.6)
    assert np.isnan(back[1]).all()


def test_granule_day_reads_the_acquisition_start():
    ur = "NISAR_L3_PR_SME2_033_066_D_069_2005_DHDH_M_20261016T185318_20261016T185353_P05023_N_F_J_001"
    assert sm_mod.granule_day(ur) == "2026-10-16"


def test_coarse_grid_is_the_site_grid_with_ten_times_the_pixel():
    g = site_grid(get_site("pego_oliva"))
    crs, t, w, h = sm_mod.coarse_grid("pego_oliva")
    assert crs == g.crs and (t.c, t.f) == (g.transform.c, g.transform.f)
    assert t.a == pytest.approx(10 * g.transform.a) and t.e == pytest.approx(10 * g.transform.e)
    assert w * 10 >= g.width > (w - 1) * 10 and h * 10 >= g.height > (h - 1) * 10


def test_latest_before_uses_only_the_past():
    days = ["2026-10-04", "2026-10-11", "2026-10-16"]
    assert sm_mod.latest_day_before(days, "2026-10-18") == "2026-10-16"
    assert sm_mod.latest_day_before(days, "2026-10-16") == "2026-10-11"      # never the same day
    assert sm_mod.latest_day_before(days, "2026-10-05") == "2026-10-04"
    assert sm_mod.latest_day_before(days, "2026-10-04") is None
    assert sm_mod.latest_day_before(days, "2026-12-01", max_age_days=24) is None   # too old to use
