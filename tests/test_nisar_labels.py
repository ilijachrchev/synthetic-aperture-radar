"""Checks for the NISAR water labels (pipeline.cv.labels) on small synthetic arrays.

Written with SI assistance (Claude Code), reviewed by the team.
"""

import numpy as np
import pytest
from rasterio.transform import from_origin

from pipeline.cv import labels as L
from pipeline.stack import Grid

NAN = np.nan


def test_classify_order_no_data_then_built_then_open_then_under_plants():
    p_open = np.array([[NAN, 0.9, 0.9, 0.9, 0.1, 0.1, 0.3, 0.29]])
    plants = np.array([[True, False, False, True, True, False, False, False]])
    cover = np.array([[40, 40, 50, 40, 40, 50, 40, 40]])
    sea = np.array([[False, True, False, False, False, False, False, False]])
    cls = L.classify(p_open, plants, cover, sea)
    # no data, sea, built-up wins over water, open wins over plants, plants, built-up dry, at 0.3, below 0.3
    assert cls.tolist() == [[255, 255, 3, 1, 2, 3, 1, 0]]
    assert cls.dtype == np.uint8


def test_under_plants_rule_hh_up_3_db_hv_within_1_5_db_on_vegetated_land():
    hh_med = np.full((1, 7), -12.0)
    hv_med = np.full((1, 7), -20.0)
    hh = np.array([[-9.0, -9.1, -9.0, -9.0, -9.0, -9.0, -9.0]])
    hv = np.array([[-18.5, -20.0, -18.4, -21.5, -20.0, -20.0, -20.0]])
    cover = np.array([[40, 40, 40, 90, 60, 50, 10]])
    got = L.under_plants(hh, hv, hh_med, hv_med, cover)
    # rise 3 and HV +1.5; rise 2.9; HV +1.6; HV -1.5 on wetland; bare; built-up; tree
    assert got.tolist() == [[True, False, False, True, False, False, True]]
    hh_med[0, 0] = NAN
    assert not L.under_plants(hh, hv, hh_med, hv_med, cover)[0, 0]


def test_agreement_is_half_at_the_threshold_and_linear_to_each_end():
    p = np.array([0.3, 1.0, 0.65, 0.0, 0.15, NAN])
    assert L.agreement(p, True).tolist() == pytest.approx([0.5, 1.0, 0.75, 0.0, 0.25, 0.5])
    assert L.agreement(p, False).tolist() == pytest.approx([0.5, 0.0, 0.25, 1.0, 0.75, 0.5])


def test_confidence_is_the_share_of_agreeing_checks_in_steps_of_5():
    cls = np.array([[1, 1, 0, 0, 2, 2, 2, 3, 255, 1]], "uint8")
    p_open = np.array([[1.0, 0.3, 0.0, 0.15, 0.0, 0.0, 0.0, 0.9, NAN, 1.0]])
    p_any = np.array([[1.0, 0.3, 0.0, 0.15, 1.0, 0.3, 0.0, 0.9, NAN, 1.0]])
    hh_db = np.array([[-20.0, -10.0, -10.0, -20.0, -5.0, -5.0, -5.0, -20.0, NAN, NAN]])
    coh = np.array([[0.1, 0.8, NAN, 0.8, 0.9, 0.9, 0.9, 0.1, NAN, NAN]])
    optical = np.array([[1, 0, 253, 1, 0, 0, 0, 1, 255, 255]], "uint8")
    conf = L.confidence(cls, p_open, p_any, hh_db, coh, optical)
    assert conf.tolist() == [[
        100,  # every check agrees with open water
        15,   # model at the threshold 0.5, the other three disagree: 12.5 rounds up to 15
        100,  # model sure and not dark; no coherence, optical cloud: both left out
        45,   # (0.75 + dark no + coherence yes + optical no) / 4 = 43.75
        50, 25, 0,  # under plants: the model's p(any water) only, capped at 50
        255, 255,   # not assessed, no data
        100,  # only the model is available
    ]]
    no_optical = L.confidence(cls, p_open, p_any, hh_db, coh, None)
    assert no_optical[0, 1] == 15 and no_optical[0, 3] == 60  # (0.75 + 0 + 1) / 3 = 58.3


def test_water_codes_match_the_prediction_model_labels():
    cls = np.array([[0, 1, 2, 3, 255]], "uint8")
    assert L.to_water(cls).tolist() == [[0, 1, 255, 255, 255]]
    assert L.to_water(cls, under_plants_as_wet=True).tolist() == [[0, 1, 1, 255, 255]]
    # PR #33's to_water (DSWx classes 1 and 3 wet, 0 dry, the rest unknown) leaves these codes unchanged
    codes = L.to_water(cls, under_plants_as_wet=True)
    theirs = np.where(codes == 0, 0, np.where(np.isin(codes, (1, 3)), 1, 255))
    assert theirs.tolist() == codes.tolist()


def test_dana_layer_codes_agree_with_the_hectares():
    before = np.array([[0, 1, 1, 0, 2, 1, 3, 255, 0, 2]], "uint8")
    after = np.array([[1, 1, 0, 0, 2, 1, 1, 1, 2, 1]], "uint8")
    permanent = np.array([[False] * 5 + [True] + [False] * 4])
    layer = L.dana_change(before, after, permanent)
    # new, both, gone, dry, dry (plants are not open water), permanent, built-up, no data, dry, new
    assert layer.tolist() == [[2, 1, 3, 0, 0, 4, 255, 255, 0, 2]]
    open_ = L.change(before, after, permanent)["open_water"]
    assert open_["new_ha"] == pytest.approx(np.count_nonzero(layer == 2) * 0.04)
    assert open_["on_both_ha"] == pytest.approx(np.count_nonzero(layer == 1) * 0.04)
    assert open_["gone_ha"] == pytest.approx(np.count_nonzero(layer == 3) * 0.04)


def test_merge_puts_passes_of_several_sources_in_time_order():
    s1 = (np.array([[[0]], [[1]], [[3]]], "uint8"),
          [{"pass_id": "s1a", "begin_utc": "2026-10-15T17:58:56.5Z"}, {"pass_id": "s1b", "begin_utc": "2026-10-20T17:58:56Z"},
           {"pass_id": "s1c", "begin_utc": "2026-10-29T06:00:00Z"}])
    nisar = (np.array([[[1]], [[255]]], "uint8"),
             [{"pass_id": "n16", "begin_utc": "2026-10-16T18:53:21Z"}, {"pass_id": "n28", "begin_utc": "2026-10-28T18:53:21Z"}])
    stack, passes = L.merge(s1, nisar)
    assert [p["pass_id"] for p in passes] == ["s1a", "n16", "s1b", "n28", "s1c"]
    assert stack[:, 0, 0].tolist() == [0, 1, 1, 255, 3]
    with pytest.raises(ValueError):
        L.merge(s1, (np.zeros((1, 2, 2), "uint8"), [{"begin_utc": "2026-10-16T00:00:00Z"}]))


def test_change_counts_new_both_and_gone_outside_permanent_water():
    before = np.array([[0, 1, 1, 0, 2, 1, 3, 255, 0]], "uint8")
    after = np.array([[1, 1, 0, 0, 2, 1, 1, 1, 2]], "uint8")
    permanent = np.array([[False, False, False, False, False, True, False, False, False]])
    out = L.change(before, after, permanent)
    assert out["compared_ha"] == pytest.approx(6 * 0.04)
    open_ = out["open_water"]
    assert (open_["before_ha"], open_["after_ha"], open_["new_ha"], open_["on_both_ha"], open_["gone_ha"]) == \
        pytest.approx((0.08, 0.08, 0.04, 0.04, 0.04))
    wide = out["open_water_or_under_plants"]
    assert (wide["new_ha"], wide["on_both_ha"]) == pytest.approx((0.08, 0.08))


def test_per_municipality_counts_and_order():
    before = np.array([[0, 0, 1, 0, 0, 0]], "uint8")
    after = np.array([[1, 2, 1, 1, 1, 1]], "uint8")
    ids = np.array([[0, 0, 0, 1, -1, 2]], "int32")
    permanent = np.array([[False] * 5 + [True]])
    names = [{"name": "A", "ine": "1"}, {"name": "B", "ine": "2"}, {"name": "C", "ine": "3"}]
    rows = L.per_municipality(before, after, permanent, ids, names)
    assert [r["name"] for r in rows] == ["A", "B"]  # C has only permanent water: nothing compared
    a = rows[0]
    assert a["compared_ha"] == pytest.approx(0.12) and a["open_water"]["new_ha"] == pytest.approx(0.04)
    assert a["open_water_or_under_plants"]["new_ha"] == pytest.approx(0.08)
    assert a["open_water"]["after_ha"] == pytest.approx(0.08) and rows[1]["open_water"]["new_ha"] == pytest.approx(0.04)


def test_municipality_polygon_from_overpass_ways_with_a_hole():
    def way(role, *points):
        return {"type": "way", "role": role, "geometry": [{"lon": x, "lat": y} for x, y in points]}

    members = [way("outer", (0, 0), (4, 0), (4, 4)), way("outer", (4, 4), (0, 4), (0, 0)),
               way("inner", (1, 1), (2, 1), (2, 2), (1, 2), (1, 1)), {"type": "node", "role": "admin_centre"}]
    shape = L._polygons(members, ("outer", "")).difference(L._polygons(members, ("inner",)))
    assert shape.area == pytest.approx(15.0)


def test_split_marks_the_dana_window_as_test():
    assert [L.split_of(d) for d in ("2026-10-11", "2026-10-15", "2026-10-28", "2026-11-15", "2026-11-16")] == \
        ["train", "test", "test", "test", "train"]


def test_pass_summary_hectares_and_check_shares():
    cls = np.array([[1, 1, 0, 0, 2, 3, 255, 255]], "uint8")
    conf = np.array([[100, 50, 100, 80, 0, 255, 255, 255]], "uint8")
    p_any = np.array([[1.0, 0.5, 0.4, 0.0, 0.0, 0.0, NAN, NAN]])
    coh = np.array([[0.1, 0.6, 0.7, NAN, NAN, NAN, NAN, NAN]])
    optical = np.array([[1, 0, 1, 253, 0, 0, 0, 0]], "uint8")
    permanent = np.zeros((1, 8), bool)
    sea = np.array([[False] * 7 + [True]])
    s = L.pass_summary(cls, conf, p_any, coh, optical, permanent, sea)
    ha = s["hectares"]
    assert (ha["open_water"], ha["not_water"], ha["water_under_plants"], ha["not_assessed_built"]) == \
        pytest.approx((0.08, 0.08, 0.04, 0.04))
    assert ha["no_data_on_land"] == pytest.approx(0.04) and ha["not_water_where_the_model_sees_inundated_vegetation"] == 0.04
    assert s["mean_confidence"] == {"not_water": 90.0, "open_water": 75.0, "water_under_plants": 0.0}
    c = s["checks"]
    assert c["share_with_optical"] == pytest.approx(4 / 5) and c["share_with_coherence"] == pytest.approx(3 / 5)
    assert c["share_with_optical_or_coherence"] == pytest.approx(4 / 5)
    assert c["changing_open_water_confirmed_by_optical"] == 0.5 and c["not_water_where_optical_sees_open_water"] == 1.0
    assert c["changing_open_water_with_low_coherence"] == 0.5


def test_layers_round_trip_and_load_in_the_shape_of_the_prediction_labels(tmp_path, monkeypatch):
    import json

    import rasterio

    grid = Grid("EPSG:32630", from_origin(719400.0, 4370420.0, 20.0, 20.0), 3, 2)
    monkeypatch.setattr(L, "OUT_DIR", tmp_path / "data" / "labels_nisar")
    monkeypatch.setattr(L, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(L, "site_grid", lambda site: grid)
    late = np.array([[1, 0, 255], [2, 3, 0]], "uint8")
    paths = {day: L.layer_paths("albufera", "066_D_069", day) for day in ("2026-06-18", "2026-10-28")}
    L.write_layer(paths["2026-10-28"]["class"], late, grid, "NISAR water class",
                  {"classes": L.CLASS_LEGEND, "note": L.SI_NOTE})
    L.write_layer(paths["2026-06-18"]["class"], np.zeros((2, 3), "uint8"), grid, "class", {})
    with rasterio.open(paths["2026-10-28"]["class"]) as src:
        assert src.read(1).tolist() == late.tolist() and src.nodata == 255 and src.dtypes == ("uint8",)
        assert src.tags()["note"] == L.SI_NOTE and src.compression.name.lower() == "deflate"

    passes = [{"pass_id": f"NISAR_066_D_069_{day}", "date": day, "begin_utc": f"{day}T18:53:21Z", "stack": "066_D_069",
               "class_file": L.repo_path(paths[day]["class"])} for day in ("2026-06-18", "2026-10-28")]
    L.passes_path("albufera").write_text(json.dumps(passes), encoding="utf-8")
    stack, got = L.load("albufera")
    assert stack.shape == (2, 2, 3) and stack.dtype == np.uint8 and [p["date"] for p in got] == ["2026-06-18", "2026-10-28"]
    assert stack[0].tolist() == [[0, 0, 0], [0, 0, 0]]
    assert stack[1].tolist() == [[1, 0, 255], [255, 255, 0]]
    assert L.load("albufera", under_plants_as_wet=True)[0][1].tolist() == [[1, 0, 255], [1, 255, 0]]
