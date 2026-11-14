"""ML model checks: the failure modes that would give a wrong map without crashing.

Gaps and HH-only dates, a newer processing release on the last date, the sea,
label priority and no-data values, spatial leakage, and the full command on a
fake stack in the exact pipeline.stack format.

Written with SI assistance (Claude Code).
"""

import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import binary_dilation

from pipeline.config import get_site
from pipeline.ml import config, data, export, features, labels, split, synthetic, train
from pipeline.ml.__main__ import main
from pipeline.stack import Grid, site_grid

T = np.array(["2026-06-18", "2026-06-30", "2026-07-12", "2026-07-24"], dtype="datetime64[ns]")


def _px(values):
    return np.array(values, dtype=np.float32).reshape(-1, 1, 1)


# --- features -------------------------------------------------------------

def test_features_skip_missing_dates_and_find_drop():
    hh = _px([-8, -8, np.nan, -20])
    hv = _px([-15, -15, -15, -15])
    X, usable, _ = features.pixel_features(hh, hv, T, dark_threshold_db=-15)
    f = dict(zip(features.FEATURE_NAMES, X[0]))
    assert f["hh_max"] == -8
    assert f["hh_drop_size"] == pytest.approx(12)   # the step spans the missing date
    assert f["hh_drop_doy"] == 205                   # 24 Jul
    assert f["hh_variability"] == pytest.approx(6)   # steps 0 and -12
    assert f["dark_fraction"] == pytest.approx(1 / 3)
    assert f["n_valid_hh"] == 3 and usable[0]


def test_hh_only_date_still_counts_for_hh():
    hh = _px([-8, -9, -10, -11])
    hv = _px([-15, -15, np.nan, -15])
    X, usable, _ = features.pixel_features(hh, hv, T, dark_threshold_db=-15)
    f = dict(zip(features.FEATURE_NAMES, X[0]))
    assert f["n_valid_hh"] == 4 and f["n_valid_hv"] == 3
    assert f["hh_min"] == -11
    assert usable[0]


def test_too_few_dates_is_not_classified():
    hh = _px([-10, np.nan, np.nan, -10])
    _, usable, _ = features.pixel_features(hh, hh, T, dark_threshold_db=-15)
    assert not usable[0]


def test_otsu_splits_bimodal_sample_in_the_middle():
    rng = np.random.default_rng(0)
    v = np.concatenate([rng.normal(-22, 1, 5000), rng.normal(-8, 1, 5000)])
    assert -17 < features.otsu_threshold(v) < -13


# --- split -----------------------------------------------------------------

def test_split_has_gap_and_no_overlap():
    train_mask, test_mask = split.split_blocks((200, 200), block_px=50, gap_px=2, seed=1)
    assert test_mask.any() and train_mask.any()
    assert not (binary_dilation(test_mask, iterations=2) & train_mask).any()


def test_split_gives_a_rare_clustered_class_its_share_of_test():
    # 20 x 20 blocks of 10 px. Common class everywhere; "rice" only in a
    # 4 x 3 group of blocks in one corner (like the first Albufera polygons).
    y = np.full((200, 200), config.CLASS_INDEX["other_crops_shrub"], np.int16)
    y[0:40, 0:30] = config.CLASS_INDEX["rice_paddy"]
    rice = y == config.CLASS_INDEX["rice_paddy"]
    for seed in range(10):
        train_mask, test_mask = split.split_blocks(y.shape, block_px=10, gap_px=1, seed=seed, labels=y)
        share = (rice & test_mask).sum() / rice.sum()
        assert 0.2 <= share <= 0.4                              # about a quarter, never none
        assert (rice & train_mask).sum() >= 0.5 * rice.sum()    # training keeps enough
        assert abs(test_mask.mean() - 0.25) < 0.05              # overall test size unchanged
        assert not (train_mask & test_mask).any()


# --- data: the shared stack format ---------------------------------------------

@pytest.fixture(scope="module")
def fake_stack_path(tmp_path_factory):
    ds = synthetic.make_stack(size=120, parcel_px=10, sea_cols=12)
    return synthetic.write_stack(ds, tmp_path_factory.mktemp("stack") / "synthetic_066_D_069.nc")


def test_load_converts_to_db_and_keeps_grid(fake_stack_path):
    st = data.load(fake_stack_path, crid="all")
    assert st.grid.crs == "EPSG:32630"
    assert st.grid.transform == from_origin(725_000, 4_365_000, 20, 20)
    assert st.hh_db.shape == (11, 120, 120)
    assert -30 < np.nanmedian(st.hh_db) < 0          # dB, not linear power
    assert np.isnan(st.hv_db[7]).all()               # the HH-only date
    assert np.isfinite(st.hh_db[7]).mean() > 0.9     # ... still has HH
    assert st.synthetic and "truth" in st.extra


def test_crid_filter_can_leave_out_the_newer_release(fake_stack_path):
    assert len(data.load(fake_stack_path).dates) == 11          # default keeps every date
    st = data.load(fake_stack_path, crid="majority")
    assert len(st.dates) == 10 and st.dates[-1] == "2026-10-16"
    assert st.dropped[0]["date"] == "2026-10-28" and "P05036" in st.dropped[0]["reason"]
    assert {r["crid"] for r in st.provenance} == {"P05023"}
    assert len(data.load(fake_stack_path, crid="P05036").dates) == 1


def test_explicit_crid_applies_to_a_single_release_stack(tmp_path):
    ds = synthetic.make_stack(size=30, new_release_step_db=0)   # every date is P05023
    path = synthetic.write_stack(ds, tmp_path / "synthetic_066_D_069.nc")
    assert len(data.load(path, crid="P05023").dates) == 11
    assert len(data.load(path, crid="majority").dates) == 11
    with pytest.raises(ValueError, match="no dates left"):
        data.load(path, crid="P05036")                          # a release the stack does not have


def test_load_rejects_a_stack_off_the_site_grid(tmp_path):
    ds = synthetic.make_stack(size=30)
    ds.attrs["site"] = "albufera"  # but on the synthetic grid
    path = synthetic.write_stack(ds, tmp_path / "albufera_066_D_069.nc")
    with pytest.raises(ValueError, match="site_grid"):
        data.load(path)


# --- labels ----------------------------------------------------------------

GRID = Grid("EPSG:32630", from_origin(725_000, 4_365_000, 20, 20), 10, 10)


def _write_tif(path, array, nodata):
    with rasterio.open(path, "w", driver="GTiff", height=10, width=10, count=1, dtype="uint8",
                       crs=GRID.crs, transform=GRID.transform, nodata=nodata) as dst:
        dst.write(array.astype("uint8"), 1)
    return path


def _square(x0, y0, size_m, props):
    ring = [[x0, y0], [x0 + size_m, y0], [x0 + size_m, y0 - size_m], [x0, y0 - size_m], [x0, y0]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props}


def _write_geojson(path, features_):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features_,
                                "crs": {"type": "name", "properties": {"name": "EPSG:32630"}}}))
    return path


def test_label_priority_and_jrc_nodata(tmp_path):
    # 10 x 10 px grid, 20 m pixels. Rows go down, columns go right.
    wc = np.full((10, 10), 40)               # cropland everywhere
    jrc = np.zeros((10, 10))
    jrc[9, 5] = 255                          # JRC no data: must NOT become permanent water
    jrc[6:8, 6:8] = 95                       # an inland pond, permanent
    jrc[8, 0] = 50                           # seasonal water: left unlabeled
    effis = _write_geojson(tmp_path / "effis.geojson", [
        _square(725_000, 4_365_000, 60, {}),        # rows/cols 0-2, under the rice polygon
        _square(725_140, 4_365_000, 40, {}),        # rows 0-1, cols 7-8
    ])
    drawn = _write_geojson(tmp_path / "drawn.geojson",
                           [_square(725_000, 4_365_000, 100, {"class": "rice_paddy"})])  # rows/cols 0-4
    y, sea = labels.build_labels(GRID, worldcover=_write_tif(tmp_path / "wc.tif", wc, 0),
                                 jrc_occurrence=_write_tif(tmp_path / "jrc.tif", jrc, 255),
                                 effis=effis, polygons=drawn)
    assert (y[:5, :5] == config.CLASS_INDEX["rice_paddy"]).all()       # drawn beats EFFIS
    assert (y[0:2, 7:9] == config.CLASS_INDEX["burned"]).all()         # EFFIS beats WorldCover
    assert (y[6:8, 6:8] == config.CLASS_INDEX["permanent_water"]).all()
    assert y[9, 5] == config.CLASS_INDEX["other_crops_shrub"]          # JRC no data ignored
    assert y[8, 0] == config.UNLABELED                                 # seasonal water
    assert y[9, 9] == config.CLASS_INDEX["other_crops_shrub"]          # WorldCover cropland
    assert not sea.any()                                                # pond does not touch the east edge


def test_polygons_with_unknown_class_fail_loudly(tmp_path):
    bad = _write_geojson(tmp_path / "bad.geojson", [_square(725_000, 4_365_000, 100, {"class": "rice"})])
    with pytest.raises(ValueError, match="rice"):
        labels.rasterize_polygons(bad, GRID)


def test_sea_is_water_touching_the_east_edge_even_through_a_canal():
    wc = np.full((30, 30), 40.0)
    wc[:, 22:] = 80        # sea
    wc[8:18, 4:14] = 80    # lagoon
    wc[12, 14:22] = 80     # a 1 px canal joining the lagoon to the sea
    sea = labels.sea_mask(wc, None)
    assert sea[:, 23:].all()
    assert not sea[8:18, 4:14].any()


ALBUFERA_WC = config.CONTEXT_DIR / "albufera_worldcover_2021_20m.tif"


@pytest.mark.skipif(not ALBUFERA_WC.exists(), reason="committed context rasters not present")
def test_real_albufera_labels_on_the_site_grid():
    grid = site_grid(get_site("albufera"))
    src = labels.default_sources("albufera")
    assert src["sea"] is not None                     # committed by pipeline.context
    y, sea = labels.build_labels(grid, worldcover=src["worldcover"], jrc_occurrence=src["jrc_occurrence"],
                                 sea=src["sea"])
    _, sea_computed = labels.build_labels(grid, worldcover=src["worldcover"], jrc_occurrence=src["jrc_occurrence"])
    assert (sea != sea_computed).mean() < 0.001       # the file and the shared rule agree
    assert y.shape == (grid.height, grid.width)
    assert 0.2 < sea.mean() < 0.4                     # the Mediterranean, about 30 %
    water = y == config.CLASS_INDEX["permanent_water"]
    assert water.sum() * config.PIXEL_HA > 1_000      # the lagoon (about 2,400 ha) is kept
    assert not (water & sea).any()


# --- whole command ----------------------------------------------------------

def test_command_end_to_end_on_fake_stack(tmp_path):
    stack_dir, out_dir, manifest = tmp_path / "stack", tmp_path / "ml", tmp_path / "manifest.json"
    main(["synthetic", "--stack-dir", str(stack_dir), "--size", "150"])
    main(["run", "--site", "synthetic", "--stack", "066_D_069", "--truth-var", "truth",
          "--stack-dir", str(stack_dir), "--out-dir", str(out_dir), "--manifest", str(manifest),
          "--block-px", "25"])
    run = out_dir / "synthetic_066_D_069"
    m = json.loads((run / "metrics.json").read_text())
    assert m["overall_accuracy"] > 0.9                 # fake classes are easy by design
    # The saved model reloads and gives class probabilities without retraining.
    import lightgbm
    booster = lightgbm.Booster(model_file=str(run / "model.txt"))
    assert booster.num_feature() == len(m["feature_names"])
    assert set(m["model_classes"]) <= set(config.CLASSES)
    assert len(m["dates"]) == 11 and m["dates_left_out"] == []
    assert m["sea_pixels"] > 0
    assert not manifest.exists()                       # fake runs never touch the manifest

    cls = export.read_back(run / "class_utm.tif")
    truth = synthetic.make_stack(size=150)["truth"].values
    assert (cls[truth == synthetic.SEA] == config.NODATA_U8).all()
    with rasterio.open(run / "class.tif") as web:
        assert web.crs.to_epsg() == 3857
        assert web.colormap(1)[config.CLASS_INDEX["forest"]][:3] == config.CLASS_COLORS["forest"]


def test_command_truth_var_missing_fails_clearly(tmp_path):
    stack_dir = tmp_path / "stack"
    main(["synthetic", "--stack-dir", str(stack_dir), "--size", "80"])
    with pytest.raises(SystemExit, match=r"--truth-var 'nope' not found in stack; available variables: truth"):
        main(["run", "--site", "synthetic", "--stack", "066_D_069", "--truth-var", "nope",
              "--stack-dir", str(stack_dir), "--out-dir", str(tmp_path / "ml")])


def test_manifest_upsert_replaces_same_key(tmp_path):
    p = tmp_path / "manifest.json"
    export.upsert_manifest(p, [{"model": "cv", "site": "a", "layer": "water", "date": "d"}])
    export.upsert_manifest(p, [{"model": "ml", "site": "a", "layer": "class", "date": "d", "v": 1}])
    export.upsert_manifest(p, [{"model": "ml", "site": "a", "layer": "class", "date": "d", "v": 2}])
    rows = json.loads(p.read_text())
    assert len(rows) == 2 and rows[-1]["v"] == 2


def test_manifest_keeps_both_tracks_and_replaces_a_rerun(tmp_path):
    p = tmp_path / "manifest.json"
    base = {"model": "ml", "site": "albufera", "layer": "class", "date": "2026-06-18/2026-10-28"}
    export.upsert_manifest(p, [{**base, "stack": "066_D_069"}])
    export.upsert_manifest(p, [{**base, "stack": "058_A_021"}])        # same dates, other track: both stay
    export.upsert_manifest(p, [{**base, "stack": "066_D_069", "date": "2026-06-18/2026-10-16"}])  # rerun
    rows = json.loads(p.read_text())
    assert sorted((r["stack"], r["date"]) for r in rows) == [
        ("058_A_021", "2026-06-18/2026-10-28"), ("066_D_069", "2026-06-18/2026-10-16")]


# --- follow-up to the first real run (PR #7 review) -----------------------------

T8 = np.array(["2026-06-18", "2026-06-30", "2026-07-12", "2026-07-24",
               "2026-08-17", "2026-08-29", "2026-09-10", "2026-09-22"], dtype="datetime64[ns]")


def test_step_drop_finds_a_lasting_drop_and_its_date():
    hv = _px([-13, -13, -13, -13, -19, -19, -19, -19])   # a fire between 24 Jul and 17 Aug
    hh = _px([-8, -8, -8, -8, -8, -8, -8, -8])
    X, _, _ = features.pixel_features(hh, hv, T8, dark_threshold_db=-15)
    f = dict(zip(features.FEATURE_NAMES, X[0]))
    assert f["hv_step_drop"] == pytest.approx(6)
    assert f["hv_step_doy"] == 229                         # 17 Aug, the first date after
    assert f["hv_late_minus_early"] == pytest.approx(-6)
    assert f["hh_step_drop"] == pytest.approx(0)


def test_step_drop_ignores_a_single_dark_date():
    hv = _px([-13, -13, -13, -19, -13, -13, -13, -13])   # one noisy date, no lasting change
    X, _, _ = features.pixel_features(hv, hv, T8, dark_threshold_db=-15)
    f = dict(zip(features.FEATURE_NAMES, X[0]))
    assert f["hv_step_drop"] < 1.5                          # below the burned rule
    assert f["hv_drop_size"] == pytest.approx(6)            # the old single-step feature is fooled


def test_water_threshold_uses_the_sea_and_falls_back_on_land_only():
    rng = np.random.default_rng(0)
    land = rng.normal(-8, 1.5, 20_000)
    sea = rng.normal(-23, 1.5, 10_000)
    t, rule = features.water_threshold(np.concatenate([land, sea]))
    assert -18 < t < -12 and rule == "otsu with sea"
    t, rule = features.water_threshold(land)                # no water mode
    assert t == features.WATER_DB_FALLBACK and rule.startswith("fallback")


def test_burned_rule_only_allows_burned_after_an_hv_drop():
    X = np.zeros((2, len(features.FEATURE_NAMES)), np.float32)
    X[0, features.FEATURE_NAMES.index("hv_step_drop")] = 3.0
    X[1, features.FEATURE_NAMES.index("hv_step_drop")] = 0.5
    forbid = train.burned_rule(X, 1.5)[config.CLASS_INDEX["burned"]]
    assert list(forbid) == [False, True]
    assert train.burned_rule(X, None) == {}


def test_speckle_filter_smooths_and_keeps_gaps(fake_stack_path):
    raw = data.load(fake_stack_path, filter_px=0)
    smooth = data.load(fake_stack_path, filter_px=5)
    # Urban is constant over time in the fake stack, so date-to-date wobble of one
    # pixel is pure speckle. Stay 3 px inside urban parcels so the window sees urban only.
    from scipy.ndimage import binary_erosion
    urban = binary_erosion(raw.extra["truth"] == config.CLASS_INDEX["urban"], iterations=3)
    wobble = lambda st: np.nanmedian(np.nanstd(st.hh_db[:, urban], axis=0))  # noqa: E731
    assert wobble(smooth) < 0.5 * wobble(raw)
    seen_raw, seen_smooth = np.isfinite(raw.hh_db), np.isfinite(smooth.hh_db)
    assert not (seen_smooth & ~seen_raw).any()          # never invents a pixel
    # boxcar_power drops pixels with under half a valid window (map corners, gaps)
    assert seen_smooth.sum() > 0.97 * seen_raw.sum()


def test_corine_splits_trees_and_adds_rice_but_not_over_towns_or_water(tmp_path):
    grid = Grid("EPSG:32630", from_origin(725_000, 4_365_000, 20, 20), 30, 30)
    wc = np.full((30, 30), 40)                  # cropland
    wc[0:10, 0:10] = 10                         # trees in an orchard area
    wc[0:10, 20:30] = 10                        # trees in a forest area
    wc[20:30, 0:10] = 10                        # trees in neither
    wc[15:18, 15:18] = 50                       # a village inside the rice area
    with rasterio.open(tmp_path / "wc.tif", "w", driver="GTiff", height=30, width=30, count=1,
                       dtype="uint8", crs=grid.crs, transform=grid.transform, nodata=0) as dst:
        dst.write(wc.astype("uint8"), 1)
    sq = lambda col, row, size, code: _square(725_000 + 20 * col, 4_365_000 - 20 * row, 20 * size,  # noqa: E731
                                              {"Code_18": code})
    clc = _write_geojson(tmp_path / "clc.geojson",
                         [sq(0, 0, 10, "222"), sq(20, 0, 10, "312"), sq(10, 10, 15, "213")])
    y, _ = labels.build_labels(grid, worldcover=tmp_path / "wc.tif", corine=clc)
    assert (y[0:10, 0:10] == config.CLASS_INDEX["orchard"]).all()
    assert (y[0:10, 20:30] == config.CLASS_INDEX["forest"]).all()
    assert (y[20:30, 0:10] == config.UNLABELED).all()        # trees we cannot name stay out
    assert (y[15:18, 15:18] == config.CLASS_INDEX["urban"]).all()
    assert y[14, 20] == config.CLASS_INDEX["rice_paddy"]     # well inside the shrunk rice area
    assert y[10, 10] != config.CLASS_INDEX["rice_paddy"]     # the 60 m edge is dropped


def test_ml_manifest_rerun_replaces_instead_of_duplicating(tmp_path):
    p = tmp_path / "manifest.json"
    cv = {"model": "cv", "site": "a", "stack": "s", "layer": "water", "date": "2026-10-16"}
    export.upsert_manifest(p, [cv, {**cv, "date": "2026-10-28"}], key_fields=export.DATED_MANIFEST_KEY)
    ml = {"model": "ml", "site": "a", "stack": "s", "layer": "class"}
    export.upsert_manifest(p, [{**ml, "date": "2026-06-18/2026-10-28"}], key_fields=export.ML_MANIFEST_KEY)
    export.upsert_manifest(p, [{**ml, "date": "2026-06-18/2026-10-16"}], key_fields=export.ML_MANIFEST_KEY)
    rows = json.loads(p.read_text())
    assert [r["model"] for r in rows].count("ml") == 1 and rows[-1]["date"].endswith("10-16")
    assert [r["model"] for r in rows].count("cv") == 2       # per-date CV entries untouched


ALBUFERA_CLC = config.LABELS_DIR / "albufera_clc2018.geojson"
ALBUFERA_DRAWN = config.LABELS_DIR / "albufera_drawn.geojson"


@pytest.mark.skipif(not (ALBUFERA_WC.exists() and ALBUFERA_CLC.exists()), reason="label files not present")
def test_real_albufera_labels_with_corine():
    grid = site_grid(get_site("albufera"))
    y, _ = labels.build_labels(grid, **labels.default_sources("albufera"))
    ha = {n: (y == i).sum() * config.PIXEL_HA for i, n in enumerate(config.CLASSES)}
    assert ha["rice_paddy"] > 10_000                          # CORINE 213 shrunk: about 14,400 ha
    assert ha["orchard"] > 5 * ha["forest"]                   # Albufera trees are mostly orchards
    if ALBUFERA_DRAWN.exists():                               # every hand-drawn field stays rice
        drawn = labels.rasterize_polygons(ALBUFERA_DRAWN, grid)
        assert (y[drawn == config.CLASS_INDEX["rice_paddy"]] == config.CLASS_INDEX["rice_paddy"]).all()


def test_majority_filter_clears_specks_and_keeps_shapes_and_nodata():
    m = np.full((20, 20), config.CLASS_INDEX["forest"], np.uint8)
    m[5, 5] = config.CLASS_INDEX["permanent_water"]            # a lone speck
    m[10:18, 10:18] = config.CLASS_INDEX["permanent_water"]    # a real lake
    m[0:3, 15:20] = config.NODATA_U8                           # sea / not classified
    out = train.majority_filter(m)
    assert out[5, 5] == config.CLASS_INDEX["forest"]
    assert (out[11:17, 11:17] == config.CLASS_INDEX["permanent_water"]).all()
    assert (out[0:3, 15:20] == config.NODATA_U8).all()         # nodata never filled
    assert np.array_equal(train.majority_filter(m, size=1), m)


def test_sieve_removes_specks_with_mixed_neighbours():
    m = np.full((12, 12), config.CLASS_INDEX["forest"], np.uint8)
    m[:, 6:] = config.CLASS_INDEX["orchard"]
    m[4:8, 4:8] = config.CLASS_INDEX["other_crops_shrub"]     # a 16 px field: stays
    m[1, 6] = config.CLASS_INDEX["permanent_water"]            # speck between forest and orchard
    m[0, 0] = config.NODATA_U8
    out = train.sieve_small_patches(m, 5)
    assert out[1, 6] != config.CLASS_INDEX["permanent_water"]
    assert (out[4:8, 4:8] == config.CLASS_INDEX["other_crops_shrub"]).all()
    assert out[0, 0] == config.NODATA_U8


def test_crosscheck_marks_only_overlapping_classes_reliable(tmp_path):
    from pipeline.ml import crosscheck
    grid = Grid("EPSG:32630", from_origin(725_000, 4_365_000, 20, 20), 20, 20)
    a = np.full((20, 20), config.CLASS_INDEX["orchard"], np.uint8)
    a[:10] = config.CLASS_INDEX["rice_paddy"]
    b = a.copy()
    b[10:, :10] = config.CLASS_INDEX["urban"]          # half of the orchard disagrees
    b[0, 0] = config.NODATA_U8                         # not classified in one map: ignored
    for stack, m in (("A", a), ("B", b)):
        d = tmp_path / f"site_{stack}"
        d.mkdir()
        with rasterio.open(d / "class_utm.tif", "w", driver="GTiff", height=20, width=20, count=1,
                           dtype="uint8", crs=grid.crs, transform=grid.transform, nodata=255) as dst:
            dst.write(m, 1)
        per_class = {n: {"f1": 0.5} for n in config.CLASSES}
        (d / "metrics.json").write_text(json.dumps({"overall_accuracy": 0.8, "macro_f1": 0.7, "per_class": per_class}))
    r = crosscheck.compare("site", "A", "B", ml_dir=tmp_path)
    assert r["reliable_classes"] == ["rice_paddy"]
    assert r["classes"]["orchard"]["overlap_iou"] == pytest.approx(0.5)
    assert r["pixels_agree"] == pytest.approx(299 / 399, abs=1e-3)
