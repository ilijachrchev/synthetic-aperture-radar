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
from pipeline.ml import config, data, export, features, labels, split, synthetic
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
    assert len(m["dates"]) == 11 and m["dates_left_out"] == []
    assert m["sea_pixels"] > 0
    assert not manifest.exists()                       # fake runs never touch the manifest

    cls = export.read_back(run / "class_utm.tif")
    truth = synthetic.make_stack(size=150)["truth"].values
    assert (cls[truth == synthetic.SEA] == config.NODATA_U8).all()
    with rasterio.open(run / "class.tif") as web:
        assert web.crs.to_epsg() == 3857
        assert web.colormap(1)[config.CLASS_INDEX["forest"]][:3] == config.CLASS_COLORS["forest"]


def test_manifest_upsert_replaces_same_key(tmp_path):
    p = tmp_path / "manifest.json"
    export.upsert_manifest(p, [{"model": "cv", "site": "a", "layer": "water", "date": "d"}])
    export.upsert_manifest(p, [{"model": "ml", "site": "a", "layer": "class", "date": "d", "v": 1}])
    export.upsert_manifest(p, [{"model": "ml", "site": "a", "layer": "class", "date": "d", "v": 2}])
    rows = json.loads(p.read_text())
    assert len(rows) == 2 and rows[-1]["v"] == 2
