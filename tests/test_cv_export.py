"""Checks for the CV map layers (class rule, web COG, manifest keys). Written with SI assistance (Claude Code)."""

import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from pipeline.cv.export import COLORMAP, DOY_NEVER, DOY_NODATA, KEY_FIELDS, NODATA, water_classes, water_days, write_cog
from pipeline.ml.export import upsert_manifest
from pipeline.stack import Grid


def test_water_classes_binary_and_three_class():
    p = np.array([[0.9, 0.2, np.nan]], "float32")
    assert water_classes(p, p, 0.5, three=False).tolist() == [[1, 0, NODATA]]
    p_open = np.array([[0.9, 0.2, 0.1]], "float32")
    p_any = np.array([[0.95, 0.8, 0.3]], "float32")      # pixel 1: water, mostly flooded vegetation
    assert water_classes(p_open, p_any, 0.5, three=True).tolist() == [[1, 2, 0]]
    sea = np.array([[True, False, False]])
    assert water_classes(p_open, p_any, 0.5, three=True, sea=sea).tolist() == [[NODATA, 2, 0]]


def test_first_and_last_water_days():
    doy = np.array([280, 292, 304], np.uint16)                 # three passes
    water = np.zeros((3, 1, 4), bool)
    seen = np.ones((3, 1, 4), bool)
    water[1:, 0, 0] = True                                     # floods on the 2nd pass, stays
    water[0, 0, 1] = water[2, 0, 1] = True                     # wet, dry, wet again
    seen[:, 0, 3] = False                                      # never seen
    first, last = water_days(water, seen, doy)
    assert first[0].tolist() == [292, 280, DOY_NEVER, DOY_NODATA]
    assert last[0].tolist() == [304, 304, DOY_NEVER, DOY_NODATA]
    water[1, 0, 2] = True
    seen[1, 0, 2] = False                                      # water on an unseen date does not count
    assert water_days(water, seen, doy)[0][0, 2] == DOY_NEVER


def test_web_cog_keeps_classes_colormap_and_nodata(tmp_path):
    grid = Grid("EPSG:32630", from_origin(725_000, 4_365_000, 20, 20), 300, 300)
    classes = np.zeros((300, 300), "uint8")
    classes[50:150, 50:150] = 1
    classes[200:250, :] = NODATA
    path = write_cog(classes, grid, tmp_path / "w.tif")
    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 3857 and src.nodata == NODATA
        assert src.colormap(1)[1] == COLORMAP[1]
        assert set(np.unique(src.read(1))) <= {0, 1, NODATA}


def test_cv_manifest_entries_are_per_date_and_replace_a_rerun(tmp_path):
    p = tmp_path / "manifest.json"
    base = {"model": "cv", "site": "pego_oliva", "stack": "066_D_069", "layer": "water"}
    upsert_manifest(p, [{**base, "date": "2026-10-16", "v": 1}, {**base, "date": "2026-10-28", "v": 1}], KEY_FIELDS)
    upsert_manifest(p, [{**base, "date": "2026-10-28", "v": 2}], KEY_FIELDS)
    upsert_manifest(p, [{"model": "ml", "site": "pego_oliva", "stack": "066_D_069", "layer": "class",
                         "date": "2026-06-18/2026-10-28"}])          # ML keeps its own default key
    rows = json.loads(p.read_text())
    assert sorted((r["model"], r["date"], r.get("v")) for r in rows) == [
        ("cv", "2026-10-16", 1), ("cv", "2026-10-28", 2), ("ml", "2026-06-18/2026-10-28", None)]
