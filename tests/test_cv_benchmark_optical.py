"""Checks for the optical-answer-key benchmark (spot filter, pooling, parameter choice, paired intervals). Written with SI assistance (Claude Code)."""

import numpy as np
import pytest

from pipeline.cv import benchmark_optical as bo


def test_spot_filter_keeps_only_regions_with_a_sure_pixel():
    water = np.zeros((8, 8), bool)
    water[1:3, 1:3] = True          # region A, has a sure pixel
    water[5:7, 5:7] = True          # region B, none
    water[3, 3] = True              # touches A diagonally: same region with 8 neighbours
    sure = np.zeros((8, 8), bool)
    sure[1, 1] = True
    kept = bo.spot_filter(water, sure)
    assert kept[1:3, 1:3].all() and kept[3, 3] and not kept[5:7, 5:7].any()
    assert not bo.spot_filter(np.zeros((4, 4), bool), np.ones((4, 4), bool)).any()


def test_probability_cache_round_trip():
    p = np.array([[0.0, 0.3, 1.0, np.nan]], "float32")
    back = bo._dq(bo._q(p))
    assert back[0, 1] == pytest.approx(0.3, abs=0.002) and back[0, 2] == 1.0 and np.isnan(back[0, 3])


def _row(site, stack, date, method, tn, fn, fp, tp, set_name="all_dates", land="cropland"):
    counts = {s: [0, 0, 0, 0] for s in bo.STRATA}
    counts[land] = [tn, fn, fp, tp]
    return {"site": site, "stack": stack, "date": date, "set": set_name, "method": method, "counts": counts}


def test_pooled_scores_and_false_water_share():
    c = bo._sum([_row("a", "s", "d1", "m", 90, 2, 4, 4), _row("a", "s", "d2", "m", 10, 0, 0, 6)], bo.STRATA)
    p = bo.pooled(c)
    assert p["iou"] == pytest.approx(10 / 16, abs=1e-4) and p["precision"] == pytest.approx(10 / 14, abs=1e-4)
    assert p["recall"] == pytest.approx(10 / 12, abs=1e-4) and p["false_water_share_of_dry"] == pytest.approx(4 / 104, abs=1e-5)
    assert p["dates"] == 2


def test_select_uses_training_sites_only_and_ties_go_to_the_first_value():
    rows = []
    for c in bo.C_GRID:
        tp = 10 if c in (0.3, 0.4) else 5          # tie between 0.3 and 0.4: 0.3 wins
        rows.append(_row("albufera", "s", "d", f"nisar_dark_lowcoh@{c}", 100, 2, 2, tp))
        rows.append(_row("donana", "s", "d", f"nisar_dark_lowcoh@{c}", 100, 0, 0, 100 if c == 0.5 else 0))
    choice = bo.select(rows)
    assert choice["nisar_dark_lowcoh"]["c"] == 0.3       # the test site's perfect 0.5 is never looked at
    assert "v1" not in choice                             # no cached model set in these rows


def test_paired_difference_uses_the_same_draws():
    rows = []
    for i, d in enumerate(("d1", "d2", "d3", "d4")):
        for key, tp in (("sentinel1_dswx", 5), ("nisar_threshold_15db", 5 + i), ("nisar_otsu", 5),
                        ("nisar_dark_lowcoh@0.3", 6 + i), ("v1@0.3", 5)):
            rows.append(_row("donana", "s", d, key, 100, 5, 5, tp, set_name="with_sentinel1"))
    choice = {"nisar_dark_lowcoh": {"c": 0.3}}
    tables = bo.score(rows, choice)
    t = next(e for e in tables if e["group"] == "donana" and e["land"] == "all")
    diff = t["paired_iou_difference_95"]["nisar_dark_lowcoh - nisar_threshold_15db"]
    assert diff["point"] > 0 and diff["interval"][0] > 0   # always one more hit on every date: clear gain
