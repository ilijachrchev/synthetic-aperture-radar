"""Bake the model's two steps of the guided flood map (/explore, steps 5 and 6) from the model maps of a git ref.

    python web/scripts/bake_exam.py [--ref REF] [--data DIR] [--result FILE]
        (from the repository root, with the pipeline environment and PYTHONPATH set to the repository root)

    --ref     a git ref (branch, tag or commit) that holds data/prediction/spatial, the frozen model maps; without it,
              the files of the working tree. New frozen maps: run again with --ref <their branch or commit>.
    --data    the folder that holds stack/pego_oliva_066_D_069.nc (NISAR, for the scored pixels of the test); by
              default data/ here, else the data/ of the main checkout
    --result  a result.json of the independent test (data/validation/emsr935/result.json): rewrites test_score.json
              from it. Without it test_score.json stays as it is (it can also be edited by hand).
    --result-source  how the page names that file (default: its path in the repository, e.g. when it comes from
              another branch: "data/validation/emsr935/result.json on branch claude/paper-0808b2")

Step 5, "Did we get it right?": the model's map for 22 Oct 2026 (replay_2026-10-22, issued from the Sentinel-1 pass
of 17 Oct, with the rain that fell), likely water at the frozen threshold of development_metrics.json
(thresholds.rain_and_state.water), against the Copernicus EMSR935 flooded area of AOI01, on the pixels the
independent test scores (pipeline/validation/emsr935_test.py, branch claude/paper-0808b2, set all_pixels): inside
AOI01, land, not permanent water (evidence 1), valid in NISAR's pass of 16 Oct. Two pictures for the swipe, on the zoom
13 Web Mercator lattice: exam_prediction.webp (green predicted and flooded, red predicted but dry) and
exam_happened.webp (green predicted and flooded, yellow flooded but missed). Their hectares, counted on the model's
20 m grid, are checked against the test's predicted and observed hectares when --result is given.

Step 6, "What if it rains": for each rain scenario of the ref (scenario_000mm to scenario_200mm), the model's likely
new water (new_water_likelihood_utm.tif at thresholds.new_water, evidence 0 pixels, as forecast.json counts it) as
one outline: rain_2026.json, one feature per rain, with the hectares of forecast.json and the hectares of the drawn
mask beside them.

Writes exam_prediction.webp, exam_happened.webp, rain_2026.json and exam.json (the index, every number with the file
it comes from) under web/public/layers/guided/. Needs numpy, rasterio, shapely, pyproj, geopandas, xarray and pillow.
Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import shapely
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize, shapes
from rasterio.warp import Resampling, reproject, transform_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bake_prediction import bounds_of  # noqa: E402
from bake_water import pixel_ha, web_grid  # noqa: E402

WEB = Path(__file__).resolve().parents[1]
REPO = WEB.parent
OUT = WEB / "public" / "layers" / "guided"
SPATIAL = "data/prediction/spatial"
SITE = "pego_oliva"
REPLAY = "replay_2026-10-22"
FORECAST = "forecast_2026-10-22"
SCENARIOS = ("scenario_000mm", "scenario_050mm", "scenario_100mm", "scenario_200mm")
STACK = "pego_oliva_066_D_069.nc"
BEFORE = "2026-10-16"
PIXEL_HA = 0.04  # 20 m
HIT, FALSE_ALARM, MISSED = 1, 2, 3
COLOURS = {
    "prediction": {HIT: (47, 210, 122, 235), FALSE_ALARM: (255, 77, 79, 235)},
    "happened": {HIT: (47, 210, 122, 235), MISSED: (255, 210, 63, 235)},
}
OUTLINE_SIMPLIFY_M = 10.0


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ref:
    """The model files of a git ref, or of the working tree."""

    def __init__(self, ref: str | None):
        self.ref = ref
        self.tmp = Path(tempfile.mkdtemp(prefix="bake_exam_"))
        self.commit = None
        if ref:
            self.commit = subprocess.check_output(["git", "rev-parse", ref], cwd=REPO, text=True).strip()

    def path(self, rel: str) -> Path:
        if not self.ref:
            return REPO / rel
        out = self.tmp / rel
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(subprocess.check_output(["git", "show", f"{self.commit}:{rel}"], cwd=REPO))
        return out

    def name(self, rel: str) -> str:
        return f"{rel} at {self.ref} ({self.commit[:7]})" if self.ref else rel


def read(path: Path):
    with rasterio.open(path) as r:
        return r.read(1), r.profile, r.transform, r.crs, r.bounds


def burn(features: list[dict], shape, transform, crs) -> np.ndarray:
    import geopandas as gpd

    if not features:
        return np.zeros(shape, bool)
    g = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326").to_crs(crs)
    return rasterize(((geom, 1) for geom in g.geometry), out_shape=shape, transform=transform, fill=0, dtype="uint8").astype(bool)


def stack_dir(arg: Path | None) -> Path:
    if arg:
        return arg
    here = REPO / "data"
    if (here / "stack" / STACK).exists():
        return here
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=REPO, text=True).strip())
    main = (REPO / common).resolve().parent / "data"
    return main


def picture(path: Path, codes: np.ndarray, colours: dict) -> int:
    rgba = np.zeros(codes.shape + (4,), "uint8")
    for code, c in colours.items():
        rgba[codes == code] = c
    Image.fromarray(rgba, "RGBA").save(path, "WEBP", lossless=True, quality=100, method=6)
    return path.stat().st_size


def exam(src: Ref, data: Path) -> dict:
    """The colour layer of step 5, on the pixels of the independent test."""
    from pipeline.cv.data import open_stack
    from pipeline.prediction.nisar_check import scene_db

    dev = json.loads(src.path(f"{SPATIAL}/development_metrics.json").read_text(encoding="utf-8"))
    thr = float(dev["thresholds"]["rain_and_state"]["water"])
    like, _, t, crs, bnds = read(src.path(f"{SPATIAL}/{SITE}/{REPLAY}/water_likelihood_utm.tif"))
    ev, *_ = read(src.path(f"{SPATIAL}/{SITE}/{REPLAY}/evidence_utm.tif"))
    hand, *_ = read(src.path(f"{SPATIAL}/{SITE}/static/hand_m.tif"))
    jrc, *_ = read(REPO / "data" / "context" / f"{SITE}_jrc_occurrence_20m.tif")
    sea, *_ = read(REPO / "data" / "context" / f"{SITE}_sea_20m.tif")
    meta = json.loads(src.path(f"{SPATIAL}/{SITE}/{REPLAY}/forecast.json").read_text(encoding="utf-8"))
    aoi = json.loads((REPO / "data/labels/pego_oliva_emsr935_aoi.geojson").read_text(encoding="utf-8"))["features"]
    fl = json.loads((REPO / "data/labels/pego_oliva_emsr935_flood.geojson").read_text(encoding="utf-8"))["features"]
    in_aoi = burn([f for f in aoi if f["properties"]["aoi"] == "AOI01"], like.shape, t, crs)
    flooded = burn([f for f in fl if f["properties"]["aoi"] == "AOI01" and f["properties"]["class"] == "flooded_area"], like.shape, t, crs)

    ds = open_stack(data / "stack" / STACK)
    days = [str(x)[:10] for x in ds["time"].values]
    _, ok, _ = scene_db(ds, days.index(BEFORE))
    scored = in_aoi & (sea == 0) & (ev != 255) & (ev != 1) & ok & np.isfinite(like) & np.isfinite(hand) & (jrc != 255)
    predicted = scored & (like >= thr)
    happened = scored & flooded
    codes = np.zeros(like.shape, "uint8")
    codes[predicted & happened] = HIT
    codes[predicted & ~happened] = FALSE_ALARM
    codes[~predicted & happened] = MISSED
    hectares = {
        "hit": round(float((codes == HIT).sum()) * PIXEL_HA, 1),
        "false_alarm": round(float((codes == FALSE_ALARM).sum()) * PIXEL_HA, 1),
        "missed": round(float((codes == MISSED).sum()) * PIXEL_HA, 1),
    }
    hectares["predicted"] = round(hectares["hit"] + hectares["false_alarm"], 1)
    hectares["observed"] = round(hectares["hit"] + hectares["missed"], 1)
    hectares["scored"] = round(float(scored.sum()) * PIXEL_HA, 1)

    # the pictures: the zoom 13 lattice over the scored pixels' box, nearest neighbour from the 20 m grid
    rows, cols = np.nonzero(scored)
    x0, y0 = t * (cols.min(), rows.max() + 1)
    x1, y1 = t * (cols.max() + 1, rows.min())
    west, south, east, north = transform_bounds(crs, "EPSG:4326", x0, y0, x1, y1)
    wt, w, h = web_grid((west, south, east, north))
    web = np.zeros((h, w), "uint8")
    reproject(codes, web, src_transform=t, src_crs=crs, src_nodata=None, dst_transform=wt, dst_crs="EPSG:3857",
              dst_nodata=None, resampling=Resampling.nearest)
    row_ha = pixel_ha(wt, h)[:, None]
    files = {}
    for side in ("prediction", "happened"):
        path = OUT / f"exam_{side}.webp"
        files[side] = {"file": path.name, "bytes": picture(path, web, COLOURS[side])}
    drawn = {k: round(float((row_ha * (web == c)).sum()), 1) for k, c in (("hit", HIT), ("false_alarm", FALSE_ALARM), ("missed", MISSED))}
    print(f"  exam: {hectares} (drawn {drawn}), threshold {thr:.4f}", flush=True)
    return {
        "bounds": bounds_of(wt, w, h), "size": [w, h], "prediction": files["prediction"], "happened": files["happened"],
        "hectares": hectares, "hectares_drawn": drawn, "threshold_water": round(thr, 4),
        "model": {"scenario": REPLAY, "issued_from_pass": meta.get("issued_from_pass"), "target_pass": meta.get("target_pass"),
                  "model_sha256_16": meta.get("model_sha256_16")},
        "rule": ("likely water (water_likelihood >= the frozen threshold) against EMSR935 AOI01 flooded_area, on the pixels of the "
                 "independent test (set all_pixels): inside AOI01, land, not permanent water, valid in NISAR's pass of 16 Oct"),
        "source": {
            "model": src.name(f"{SPATIAL}/{SITE}/{REPLAY}/water_likelihood_utm.tif"),
            "threshold": src.name(f"{SPATIAL}/development_metrics.json") + " thresholds.rain_and_state.water",
            "flood": "Copernicus EMSR935 AOI01 flooded_area, imagery 20 to 21 Oct 2026 (data/labels/pego_oliva_emsr935_flood.geojson, © European Union)",
            "test": "pipeline/validation/emsr935_test.py on branch claude/paper-0808b2 (the scored pixels are rebuilt the same way here)",
        },
    }


def rain(src: Ref) -> dict:
    """The outline of the model's likely new water for each rain scenario (step 6)."""
    feats, stops = [], []
    to_deg = None
    for sid in SCENARIOS:
        doc = json.loads(src.path(f"{SPATIAL}/{SITE}/{sid}/forecast.json").read_text(encoding="utf-8"))
        nl, _, t, crs, _ = read(src.path(f"{SPATIAL}/{SITE}/{sid}/new_water_likelihood_utm.tif"))
        ev, *_ = read(src.path(f"{SPATIAL}/{SITE}/{sid}/evidence_utm.tif"))
        thr = float(doc["thresholds"]["new_water"])
        mask = (ev == 0) & np.isfinite(nl) & (nl >= thr)
        polys = [shapely.geometry.shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask, transform=t, connectivity=4) if v == 1]
        merged = shapely.union_all(polys) if polys else shapely.Polygon()
        merged = shapely.make_valid(shapely.simplify(merged, OUTLINE_SIMPLIFY_M, preserve_topology=True))
        if to_deg is None:
            to_deg = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        geo = shapely.transform(merged, lambda xy: np.column_stack(to_deg.transform(xy[:, 0], xy[:, 1])))
        geo = shapely.set_precision(geo, 1e-5)
        mm = int(round(float(doc["rain"]["rain_between_mm"])))
        ha_file = float(doc["area_ha"]["likely_new_water"])
        ha_mask = round(float(mask.sum()) * PIXEL_HA, 1)
        seen = doc.get("rain_seen_in_training") or {}
        warning = None
        if seen and not seen.get("inside_training_range", True):
            warning = f"Beyond the storms the model learned from: the largest had {round(float(seen['max']))} mm"
        feats.append({"type": "Feature", "properties": {"rain_mm": mm}, "geometry": shapely.geometry.mapping(geo)})
        stops.append({"id": sid, "rain_mm": mm, "lead_days": doc["lead_days"], "ha": ha_file, "ha_mask": ha_mask,
                      "issued_from_pass": doc.get("issued_from_pass"), "target_time_utc": doc.get("target_time_utc"),
                      "warning": warning, "source": src.name(f"{SPATIAL}/{SITE}/{sid}/forecast.json") + " area_ha.likely_new_water"})
        print(f"  rain {mm} mm: {ha_file} ha in forecast.json, {ha_mask} ha in the drawn mask", flush=True)
    data = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")).encode("utf-8")
    path = OUT / "rain_2026.json"
    path.write_bytes(data)
    print(f"  rain_2026.json: {len(data) / 1e3:.0f} kB", flush=True)
    return {
        "file": path.name, "bytes": len(data), "stops": stops,
        "rule": "likely new water: new_water_likelihood_utm.tif at forecast.json thresholds.new_water, on evidence 0 pixels (as forecast.json counts area_ha.likely_new_water), outlined and simplified by 10 m",
        "source": {"model": src.name(f"{SPATIAL}/{SITE}/scenario_*mm") + ", the team spatial model (LightGBM, PR #33)",
                   "rain": "hypothetical rain in the 4 days after the latest Sentinel-1 map, at the wettest point of the site (forecast.json mode_note)"},
        "streets": "no street scenarios in data/streets yet: fields only",
    }


def score_from(result: Path, label: str | None = None) -> None:
    """test_score.json from a result.json of the independent test (set all_pixels, reference flooded_area)."""
    res = json.loads(result.read_text(encoding="utf-8"))
    sc = res["sets"]["all_pixels"]["references"]["flooded_area"]["scores"]
    rules = {k: sc[k]["f1"] for k in ("low_hand_same_area", "jrc_past_water", "nisar_16oct_persistence")}
    path = OUT / "test_score.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    old.update({
        "model_rain_fell": sc["model"]["f1"], "model_forecast": sc["model_forecast_rain"]["f1"],
        "simple_rules": [min(rules.values()), max(rules.values())],
        "simple_rules_are": f"low terrain (HAND, same area as the model) {rules['low_hand_same_area']}, past water (JRC above 0) {rules['jrc_past_water']}, NISAR water of 16 Oct kept as it was {rules['nisar_16oct_persistence']}",
        "passed": bool(res["sets"]["all_pixels"]["references"]["flooded_area"].get("model_beats_all_three")),
        "source": f"{label or result.resolve().relative_to(REPO).as_posix()}, sets.all_pixels.references.flooded_area.scores",
    })
    path.write_text(json.dumps(old, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  test_score.json from {result}: model {sc['model']['f1']}, forecast {sc['model_forecast_rain']['f1']}, rules {rules}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ref", default=None, help="git ref holding data/prediction/spatial (default: the working tree)")
    ap.add_argument("--data", type=Path, default=None, help="folder holding stack/pego_oliva_066_D_069.nc")
    ap.add_argument("--result", type=Path, default=None, help="result.json of the independent test")
    ap.add_argument("--result-source", default=None, help="how the page names the result file")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    src = Ref(a.ref)
    print(f"model maps: {a.ref or 'working tree'}{f' ({src.commit[:7]})' if src.commit else ''}", flush=True)
    doc = {"made_by": "web/scripts/bake_exam.py", "baked_utc": now(), "ref": a.ref, "commit": src.commit}
    doc.update(exam(src, stack_dir(a.data)))
    doc["rain"] = rain(src)
    if a.result:
        score_from(a.result, a.result_source)
        res = json.loads(a.result.read_text(encoding="utf-8"))["sets"]["all_pixels"]["references"]["flooded_area"]["scores"]["model"]
        doc["check"] = {"test_predicted_ha": res["predicted_ha"], "test_observed_ha": res["observed_ha"],
                        "here_predicted_ha": doc["hectares"]["predicted"], "here_observed_ha": doc["hectares"]["observed"],
                        "same": res["predicted_ha"] == doc["hectares"]["predicted"] and res["observed_ha"] == doc["hectares"]["observed"]}
        print(f"  check against the test: {doc['check']}", flush=True)
    (OUT / "exam.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("exam.json written", flush=True)


if __name__ == "__main__":
    main()
