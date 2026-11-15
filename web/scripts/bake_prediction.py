"""Bake the spatial water prediction (pipeline/prediction/spatial, PR #33) into overlays for the map.

    python web/scripts/bake_prediction.py                     # data/prediction/spatial of this checkout
    python web/scripts/bake_prediction.py --ref pr-33         # the same folder from a git ref, nothing checked out
    python web/scripts/bake_prediction.py --src D:/run/spatial  # any folder that holds index.json

One command after every retrain: it reads index.json, every scenario and replay it lists, and writes under
web/public/layers/<site>/ for every site the app has a grid for (meta.json of bake_water.py):

    prediction/<scenario>.webp  what the map draws, lossless, on the model's own web grid: the zoom 13 lattice of the
                                water frames (so it drapes over the terrain like them), as large as the model's land
                                grid, which reaches a little beyond the box of meta.json:
                                R  255 the model predicts here (evidence 0, 1, 3), 96 extrapolated (2 built-up land,
                                   4 ground Sentinel-1 rarely maps), 0 sea or outside the model's land grid
                                G  relative water likelihood in percent, 0 to 100, the value of water_likelihood_web.tif
                                B  the ground on the map the prediction was issued from: 255 dry (water here would
                                   be new), 0 water already or permanent water, 128 no earlier map (evidence 3)
    prediction/<scenario>.bin   what a click reads, exact: planes of bytes on the same grid, in bands of rows that
                                inflate one at a time (see planes()): the evidence flag (0 to 4, 255), the water
                                likelihood (0 to 100, 255 no data) as the files hold them, and where the issue map
                                was dry (there the new water likelihood of the export is the water likelihood)
    prediction/inspect.bin      the same for what does not depend on the scenario: ESA WorldCover class, NISAR soil
                                moisture before the storm (m3/m3 x 100, 255 no data) and the NISAR water history of
                                every pass of the story's series (0 not seen, 1 dry, 2 water under plants, 3 open water)

A click reads the numbers from these planes in the page's own code, not back from a canvas: browsers that guard
against fingerprinting add noise to pixels read back from a canvas, and a number on the panel must be the file's.
    prediction/game.json        the model's answer in the flood game (src/components/game), where game.json exists:
                                every cell scored with the map GAME_MAP (one setting, or --game-map); the game takes
                                the model's top cells and judges them with its own rule against the NISAR pass
    prediction.json             scenarios and replays with their dates, rain, captions and every number, each with
                                the file it comes from

Run it after bake_water.py (the frames give the NISAR history) and bake_game.py (the game's cells).

The likelihood rasters of the export (water_likelihood_web.tif, new_water_likelihood_web.tif) already sit on the zoom
13 Web Mercator lattice, so they are cut out, not resampled. The evidence flags are on the 20 m UTM grid of the
model and are taken over by nearest neighbour, as the export does for the web rasters.

The hectares shown are the ones of forecast.json ("counted on evidence 0 pixels only", 20 m pixels). The bake also
counts the same thresholds on the drawn grid and writes both, so the outline on the map can be checked against them.

Needs numpy, rasterio, pillow and pyproj (the pipeline environment has them all).
Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bake_water import ORIGIN, RES, SITES, pixel_ha, web_grid  # noqa: E402

WEB = Path(__file__).resolve().parents[1]
REPO = WEB.parent
SPATIAL = "data/prediction/spatial"
# R of the display frames: how far the value is the model's own
TRUST = {0: 255, 1: 255, 3: 255, 2: 96, 4: 96}
# the ground on the map the prediction was issued from, in B of the display frames
DRY_BEFORE, WET_BEFORE, NO_MAP = 255, 0, 128
WORLDCOVER = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare or sparse vegetation",
    70: "Snow and ice", 80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen",
}
# the story the overlays are told in (content/stories.ts): its series gives the NISAR history of a pixel
STORY_SERIES = {"pego_oliva": "nisar_066_D_069", "albufera": "nisar_066_D_069"}
# the rain of DANA Adam began on 18 Oct 2026 (content/stories.ts): soil moisture "before the storm" is the newest
# NISAR SME2 map before that day
STORM_DAY = "2026-10-18"
# The model map that plays the flood game against the player (src/components/game): the replay issued before the
# storm for the NISAR pass of 28 Oct. It was given the rain that fell. Should a replay run on the forecast rain be
# added, put its scenario id here (or pass --game-map): the game's caption follows that map's own forecast.json.
GAME_MAP = "replay_2026-10-28_prestorm"


# ---------------------------------------------------------------- where the results come from

class Source:
    """The folder of results, from the file system or from a git ref. Paths in the output name where a number
    comes from: `data/prediction/spatial/...` in this checkout, or `<ref>:data/prediction/spatial/...`."""

    def __init__(self, src: Path | None, ref: str | None):
        self._tmp = None
        if ref:
            self.commit = git("rev-parse", ref).strip()
            self._tmp = tempfile.TemporaryDirectory(prefix="bake_prediction_")
            data = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", self.commit, SPATIAL],
                                  capture_output=True, check=True).stdout
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                tar.extractall(self._tmp.name, filter="data")
            self.root = Path(self._tmp.name) / SPATIAL
            self.label = f"{ref}:{SPATIAL}"
            self.ref = ref
        else:
            self.root = (src or REPO / SPATIAL).resolve()
            self.ref = None
            try:
                self.label = self.root.relative_to(REPO).as_posix()
                self.commit = git("rev-parse", "HEAD").strip()
                if git("status", "--porcelain", "--", self.label).strip():
                    self.commit += " (with local changes)"
            except ValueError:
                self.label = self.root.as_posix()
                self.commit = None
        if not (self.root / "index.json").exists():
            sys.exit(f"no index.json in {self.label}")

    def name(self, path: Path) -> str:
        """How a result file is cited."""
        rel = path.relative_to(self.root).as_posix()
        return f"{self.label}/{rel}"

    def close(self):
        if self._tmp:
            self._tmp.cleanup()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------- rasters onto the grid of the app

def onto(path: Path, transform, width: int, height: int, nodata: int, dtype: str = "uint8") -> tuple[np.ndarray, str]:
    """Band 1 of a raster on the app grid. A raster on the same Web Mercator lattice is cut out pixel for pixel;
    anything else is taken over by nearest neighbour. Returns the array and how it was made."""
    with rasterio.open(path) as src:
        t = src.transform
        if src.crs and src.crs.to_epsg() == 3857 and abs(t.a - RES) < 1e-6 and abs(t.e + RES) < 1e-6 and not t.b and not t.d:
            c0 = (transform.c - t.c) / RES
            r0 = (t.f - transform.f) / RES
            if abs(c0 - round(c0)) < 1e-6 and abs(r0 - round(r0)) < 1e-6:
                win = Window(round(c0), round(r0), width, height)
                return src.read(1, window=win, boundless=True, fill_value=nodata).astype(dtype), "cut out"
        out = np.full((height, width), nodata, dtype)
        reproject(rasterio.band(src, 1), out, src_nodata=src.nodata if src.nodata is not None else nodata,
                  dst_transform=transform, dst_crs="EPSG:3857", dst_nodata=nodata, resampling=Resampling.nearest)
        return out, "nearest neighbour"


def webp(path: Path, rgb: np.ndarray) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path, "WEBP", lossless=True, quality=100, method=6, exact=True)
    return path.stat().st_size


CHUNK_ROWS = 64  # a click inflates one band of this many rows of each plane, never the whole file


def planes(path: Path, layers: list[np.ndarray]) -> int:
    """Planes of bytes cut into bands of CHUNK_ROWS rows, each band zlib compressed on its own, so a click inflates
    only the bands under it (src/lib/prediction.ts reads this; the page inflates with DecompressionStream).

        'PLN1', then uint32 little endian: width, height, planes, rows per band, bands per plane,
        then bands x planes + 1 offsets into the data that follows, then the bands, plane after plane."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = layers[0].shape
    bands = -(-h // CHUNK_ROWS)
    blobs = [zlib.compress(np.ascontiguousarray(a[i * CHUNK_ROWS:(i + 1) * CHUNK_ROWS].astype("uint8")).tobytes(), 9)
             for a in layers for i in range(bands)]
    offsets = np.concatenate([[0], np.cumsum([len(b) for b in blobs])]).astype("<u4")
    head = b"PLN1" + np.array([w, h, len(layers), CHUNK_ROWS, bands], "<u4").tobytes() + offsets.tobytes()
    path.write_bytes(head + b"".join(blobs))
    return path.stat().st_size


# ---------------------------------------------------------------- one scenario or replay

def day(iso: str) -> str:
    """'2026-10-17T17:53:23.000Z' -> '17 Oct'"""
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{d.day} {d.strftime('%b')}"


def pass_time(pass_id: str) -> str:
    """'20261017T175323_S1C' -> '2026-10-17T17:53:23Z'"""
    s = pass_id.split("_")[0]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}Z"


def sensor(pass_id: str | None) -> str:
    """The radar of the map a prediction was issued from, from its pass id ('20261110T175323_S1C')."""
    tail = (pass_id or "").rsplit("_", 1)[-1]
    return "Sentinel-1" if tail.startswith("S1") else "NISAR" if "NISAR" in (pass_id or "") else "radar"


def caption(doc: dict) -> dict:
    """The words the page shows with this map, made only from forecast.json."""
    rain = doc["rain"]["rain_between_mm"]
    issued = day(doc["issue_time_utc"])
    target = day(doc["target_time_utc"])
    radar = sensor(doc.get("issued_from_pass"))
    if doc["mode"] == "scenario":
        mm = round(rain)
        train = doc.get("rain_seen_in_training") or {}
        warn = None
        if train and not train.get("inside_training_range", True):
            warn = f"Beyond the storms the model learned from: the largest had {round(train['max'])} mm"
        days = round(doc["lead_days"])
        return {"title": f"{mm} mm of rain",
                "line": f"If no rain fell in the {days} days after the {radar} map of {issued}" if mm == 0
                else f"If {mm} mm fell in the {days} days after the {radar} map of {issued}",
                "note": "Relative likelihood from our model, not depth and not a flood probability", "warning": warn, "detail": None}
    return {
        "title": f"Model map for {target}",
        "line": f"Issued from the {radar} map of {issued}, given the {round(rain)} mm that fell after it",
        "note": "A reconstruction with the rain that fell, not a forecast. Relative likelihood, not depth",
        "warning": None,
        "detail": None,
    }


# what the model marks with no rain at all is the water of the season, not rain: in the words of the model's author
# (discussion #37), per site
SEASON = {
    "pego_oliva": "water the marsh holds in this season anyway",
    "albufera": "mostly rice fields that farmers flood in this season",
}
# two rain stops whose likely new water differs by less than this share read as "almost the same map"
SAME_MAP = 0.10


def slider_notes(site: str, scenarios: list[dict]) -> None:
    """The plain notes the rain slider needs, from the numbers of the scenarios themselves: what 0 mm already holds,
    stops that give almost the same map and why, (the step beyond the training rain is the caption's warning)."""
    ha = lambda v: f"{int(v + 0.5):,}"  # noqa: E731  (half up, as the page rounds)
    new = lambda r: r["area_ha"]["likely_new_water"]  # noqa: E731
    for r in scenarios:
        if r["rain_mm"] == 0:
            r["caption"]["detail"] = (f"With no rain the model still marks {ha(new(r))} ha of likely new water: "
                                      f"{SEASON.get(site, 'water of the season')}, not new rain.")
    for a, b in zip(scenarios, scenarios[1:]):
        if not a["rain_mm"] or not b["rain_mm"]:
            continue
        if abs(new(a) - new(b)) <= SAME_MAP * max(new(a), new(b)):
            p90 = (b.get("rain_seen_in_training") or {}).get("p90")
            why = f" (nine in ten of its training examples had at most {int(p90 + 0.5)} mm)" if p90 is not None else ""
            text = (f"{a['rain_mm']} and {b['rain_mm']} mm give almost the same map ({ha(new(a))} and {ha(new(b))} ha): "
                    f"the model saw few storms of this size{why}.")
            for r in (a, b):
                r["caption"]["detail"] = text


def bake_one(src: Source, site: str, entry: dict, grid: dict, out: Path) -> dict | None:
    folder = src.root / site / entry["scenario_id"]
    f_doc, f_wl, f_nl, f_ev = (folder / n for n in ("forecast.json", "water_likelihood_web.tif", "new_water_likelihood_web.tif", "evidence_utm.tif"))
    missing = [p.name for p in (f_doc, f_wl, f_nl, f_ev) if not p.exists()]
    if missing:
        print(f"  {site} {entry['scenario_id']}: skipped, missing {', '.join(missing)}")
        return None
    doc = json.loads(f_doc.read_text(encoding="utf-8"))
    t, w, h = grid["transform"], grid["width"], grid["height"]
    wl, how_wl = onto(f_wl, t, w, h, 255)
    nl, how_nl = onto(f_nl, t, w, h, 255)
    ev, how_ev = onto(f_ev, t, w, h, 255)
    valid = wl != 255
    r = np.zeros((h, w), "uint8")
    for code, value in TRUST.items():
        r[valid & (ev == code)] = value
    # the evidence grid (UTM) and the likelihood grid (Mercator) meet at their edges a pixel apart in a few places:
    # a value without a flag is drawn as extrapolated; the click data keeps both files as they are
    r[valid & (ev == 255)] = TRUST[4]
    g = np.where(valid, wl, 0).astype("uint8")
    b = np.full((h, w), WET_BEFORE, "uint8")
    b[nl != 255] = DRY_BEFORE
    b[valid & (ev == 3)] = NO_MAP
    sid = entry["scenario_id"]
    display = out / "prediction" / f"{sid}.webp"
    data = out / "prediction" / f"{sid}.bin"
    size = webp(display, np.dstack([r, g, b]))
    # The export writes the new water likelihood as the water likelihood where the issue map was dry (export.py),
    # so the click data keeps that as one flag. Should a retrain ever make them differ, both are kept whole.
    known = nl != 255
    if np.array_equal(nl[known], wl[known]):
        names, layers = ["evidence", "water_likelihood_pct", "dry_before"], [ev, wl, known.astype("uint8")]
    else:
        names, layers = ["evidence", "water_likelihood_pct", "new_water_likelihood_pct"], [ev, wl, nl]
    data_size = planes(data, layers)

    # the thresholds of forecast.json counted again on the drawn grid, with the true size of every Mercator pixel
    row_ha = grid["row_ha"][:, None]
    thr = doc["thresholds"]
    trusted = valid & (ev == 0)
    drawn = {
        "likely_water": round(float((row_ha * (trusted & (wl >= thr["water"] * 100))).sum()), 1),
        "likely_new_water": round(float((row_ha * (trusted & (nl != 255) & (nl >= thr["new_water"] * 100))).sum()), 1),
    }
    cite = src.name(f_doc)
    rec = {
        "id": sid,
        "mode": doc["mode"],
        "rain_mm": entry.get("rain_mm"),
        "file": f"prediction/{sid}.webp",
        "bytes": size,
        "data": f"prediction/{sid}.bin",
        "data_bytes": data_size,
        "data_planes": names,
        "issued_from_pass": doc.get("issued_from_pass"),
        "issued_from_sensor": sensor(doc.get("issued_from_pass")),
        "issue_time_utc": doc.get("issue_time_utc"),
        "target_time_utc": doc.get("target_time_utc"),
        "target_nisar_granule": doc.get("target_nisar_granule"),
        "lead_days": doc.get("lead_days"),
        "rain": doc.get("rain"),
        "rain_source": doc.get("rain_source"),
        "rain_seen_in_training": doc.get("rain_seen_in_training"),
        "thresholds": thr,
        "area_ha": doc["area_ha"],
        "area_ha_drawn": drawn,
        "mode_note": doc.get("mode_note"),
        "validation_status": doc.get("validation_status"),
        "caption": caption(doc),
        "sources": {
            "forecast": cite,
            "water_likelihood": src.name(f_wl),
            "new_water_likelihood": src.name(f_nl),
            "evidence": src.name(f_ev),
            "how": {"water_likelihood": how_wl, "new_water_likelihood": how_nl, "evidence": how_ev},
            "area_ha_drawn": "bake_prediction.py: the thresholds of forecast.json on the drawn grid, evidence 0 pixels",
        },
    }
    a, d = doc["area_ha"], drawn
    print(f"  {site} {sid}: likely water {a['likely_water']} ha (drawn {d['likely_water']}), new {a['likely_new_water']} ha "
          f"(drawn {d['likely_new_water']}); {size / 1e3:.0f} kB to draw, {data_size / 1e3:.0f} kB to click", flush=True)
    return rec


# ---------------------------------------------------------------- what a click reads that is not the model's

def inspect_layers(site: str, grid: dict, meta: dict, out: Path) -> dict:
    t, w, h = grid["transform"], grid["width"], grid["height"]
    ctx = REPO / "data" / "context"
    layers, info = [], {}

    f_lc = ctx / f"{site}_worldcover_2021_20m.tif"
    if f_lc.exists():
        lc, _ = onto(f_lc, t, w, h, 0)
        layers.append(lc)
        info["landcover"] = {"plane": len(layers) - 1, "source": f_lc.relative_to(REPO).as_posix(), "product": "ESA WorldCover 2021, 10 m, on the 20 m site grid",
                             "classes": {str(k): v for k, v in WORLDCOVER.items()}, "nodata": 0}
    else:
        layers.append(np.zeros((h, w), "uint8"))

    f_idx = ctx / f"{site}_sme2_index.json"
    soil = np.full((h, w), 255, "uint8")
    if f_idx.exists():
        idx = json.loads(f_idx.read_text(encoding="utf-8"))
        days = [d for d in idx["dates"] if d["date"] < STORM_DAY]
        if days:
            d = max(days, key=lambda x: x["date"])
            f_sm = ctx / f"{site}_sme2_{d['date']}_200m.tif"
            q, _ = onto(f_sm, t, w, h, 65535, "uint16")
            ok = q != 65535
            # m3/m3 to two decimals, half up: what the panel shows is the file's value rounded, not changed
            soil[ok] = np.minimum(254, (q[ok].astype("int32") + 50) // 100).astype("uint8")
            info["soil"] = {"plane": 1, "date": d["date"], "source": f_sm.relative_to(REPO).as_posix(), "index": f_idx.relative_to(REPO).as_posix(),
                            "product": idx.get("product"), "maturity": idx.get("maturity"), "unit": "m3/m3", "scale": 100, "nodata": 255,
                            "median_m3m3": d.get("median_m3m3"), "share_recommended": d.get("share_recommended"), "granules": d.get("granules"),
                            "resolution_m": 200}
    layers.append(soil)

    series = next((s for s in meta["series"] if s["id"] == STORY_SERIES.get(site)), None)
    if series:
        # the frames lie on the grid of meta.json, a window of the same lattice inside the model's grid
        mt, _, _ = web_grid(SITES[site]["bbox"])
        c0, r0 = round((mt.c - t.c) / RES), round((t.f - mt.f) / RES)
        passes = []
        for f in series["frames"]:
            a = np.asarray(Image.open(out / f["file"]).convert("RGB"))
            seen, anyw, openw = a[..., 0] == 255, a[..., 1] < 128, a[..., 2] < 128
            frame = np.where(~seen, 0, np.where(openw, 3, np.where(anyw, 2, 1))).astype("uint8")
            state = np.zeros((h, w), "uint8")
            fh, fw = frame.shape
            ys, xs = slice(max(0, r0), min(h, r0 + fh)), slice(max(0, c0), min(w, c0 + fw))
            state[ys, xs] = frame[ys.start - r0:ys.stop - r0, xs.start - c0:xs.stop - c0]
            layers.append(state)
            passes.append({"plane": len(layers) - 1, "time_utc": f.get("time_utc"), "date": f.get("date"), "granule": (f.get("granules") or [None])[0],
                           "open_ha": f.get("open_ha"), "veg_ha": f.get("veg_ha")})
        info["history"] = {"series": series["id"], "sensor": series["sensor"], "product": series["product"],
                           "source": f"web/public/layers/{site}/{series['id']}/*.webp (bake_water.py), the frames the map draws",
                           "bounds": meta["bounds"], "outside": "the frames cover the box of meta.json only: outside it every pass reads 0",
                           "states": {"0": "not seen by this pass", "1": "dry", "2": "water under plants", "3": "open water"},
                           "passes": passes}
    path = out / "prediction" / "inspect.bin"
    info["file"] = "prediction/inspect.bin"
    info["bytes"] = planes(path, layers)
    info["planes"] = len(layers)
    print(f"  {site} inspect: {len(layers)} planes, {info['bytes'] / 1e3:.0f} kB", flush=True)
    return info


# ---------------------------------------------------------------- still flooded after the DANA (PR #35's labels)

LABELS = REPO / "data" / "labels_nisar"
LABELS_SUMMARY = REPO / "data" / "metrics" / "nisar_labels_summary.json"
EMSR935 = REPO / "data" / "labels" / "pego_oliva_emsr935_flood.geojson"
OPEN_WATER, PERMANENT = 1, 4  # the class of open water in <date>_class.tif, the code of permanent water in dana_*.tif


def still_flooded(site: str, out: Path) -> dict | None:
    """The ground the Copernicus EMS map EMSR935 marked flooded (imagery 20 to 21 Oct) that NISAR still saw as open
    water on 28 Oct, for the last step of the DANA replay: the same rule as nisar_labels_summary.json
    (pipeline/cv/labels.py, emsr935_flooded_area_still_water), drawn as one frame in the encoding of bake_water.py
    on the box of meta.json, so the water layer draws it. The numbers on the page are the summary's own."""
    stack = STORY_SERIES.get(site, "").replace("nisar_", "")
    if not (LABELS_SUMMARY.exists() and EMSR935.exists() and stack):
        return None
    entry = json.loads(LABELS_SUMMARY.read_text(encoding="utf-8"))["sites"].get(site, {}).get("dana", {}).get("emsr935_flooded_area_still_water")
    key = next((k for k in (entry or {}).get("per_pass", {}) if k.startswith(stack)), None)
    if not key:
        return None
    after = key.split()[-1]
    numbers = entry["per_pass"][key]
    f_cls = LABELS / f"{site}_{stack}" / f"{after}_class.tif"
    f_dana = next((LABELS / f"{site}_{stack}").glob(f"dana_*_{after}.tif"), None)
    if not f_cls.exists() or f_dana is None:
        return None
    from bake_water import encode, signed_distance
    from rasterio.features import rasterize
    from rasterio.warp import transform_geom

    with rasterio.open(f_cls) as s:
        cls, t, crs = s.read(1), s.transform, s.crs
    with rasterio.open(f_dana) as s:
        dana = s.read(1)
    feats = [f for f in json.loads(EMSR935.read_text(encoding="utf-8"))["features"] if f["properties"].get("class") == "flooded_area"]
    shapes = [(transform_geom("EPSG:4326", crs, f["geometry"]), 1) for f in feats]
    flooded = rasterize(shapes, out_shape=cls.shape, transform=t, fill=0, dtype="uint8").astype(bool) & (dana != PERMANENT)
    still = flooded & (cls == OPEN_WATER)
    utm_ha = round(float(still.sum()) * abs(t.a * t.e) / 1e4, 2)

    mt, w, h = web_grid(SITES[site]["bbox"])
    web = np.zeros((h, w), "uint8")
    reproject(still.astype("uint8"), web, src_transform=t, src_crs=crs, dst_transform=mt, dst_crs="EPSG:3857",
              src_nodata=None, dst_nodata=None, resampling=Resampling.nearest)
    mask = web == 1
    g = encode(signed_distance(mask))
    path = out / "prediction" / "still_flooded.webp"
    size = webp(path, np.dstack([np.full((h, w), 255, "uint8"), g, g]))
    drawn = round(float((pixel_ha(mt, h)[:, None] * mask).sum()), 1)
    print(f"  {site} still flooded on {after}: {numbers['open_water_ha']} ha in the summary, {utm_ha} ha recounted on its grid, "
          f"{drawn} ha drawn; {size / 1e3:.0f} kB", flush=True)
    return {
        "file": "prediction/still_flooded.webp", "bytes": size, "stack": stack, "after": after,
        "outline": entry.get("outline"), "outline_ha": entry.get("outline_ha"),
        "seen_ha": numbers.get("seen_ha"), "open_water_ha": numbers.get("open_water_ha"), "open_water_share": numbers.get("open_water_share"),
        "recounted_ha": utm_ha, "drawn_ha": drawn,
        "sources": {"numbers": f"{LABELS_SUMMARY.relative_to(REPO).as_posix()} sites.{site}.dana.emsr935_flooded_area_still_water.per_pass['{key}']",
                    "class": f_cls.relative_to(REPO).as_posix(), "dana": f_dana.relative_to(REPO).as_posix(), "outline": EMSR935.relative_to(REPO).as_posix()},
    }


# ---------------------------------------------------------------- the model's answer in the flood game

def game_answer(src: Source, site: str, map_id: str, grid: dict, out: Path) -> dict | None:
    """Score every cell of the flood game (game.json of bake_game.py) with the model map `map_id`: the mean new water
    likelihood over the cell's land, ground already under water on the model's starting map counting as 0, so a cell
    scores high only where the model expects much of it to turn to new water (the game's own question). The game
    takes its top cells as the model's picks and judges them with its own rule against the NISAR pass."""
    path_game = out / "game.json"
    folder = src.root / site / map_id
    if not path_game.exists():
        return None
    if not (folder / "forecast.json").exists():
        print(f"  {site} game: no map {map_id} in the results; the game shows no model")
        return None
    game = json.loads(path_game.read_text(encoding="utf-8"))
    doc = json.loads((folder / "forecast.json").read_text(encoding="utf-8"))
    t, w, h = grid["transform"], grid["width"], grid["height"]
    wl, _ = onto(folder / "water_likelihood_web.tif", t, w, h, 255)
    nl, _ = onto(folder / "new_water_likelihood_web.tif", t, w, h, 255)
    land = wl != 255
    new = np.where(nl != 255, nl, 0).astype("float64")

    def col(lon):
        return (6378137.0 * np.radians(lon) - t.c) / RES

    def row(lat):
        return (t.f - 6378137.0 * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))) / RES

    scores = []
    for c in game["cells"]:
        west, south, east, north = c["box"]
        c0, c1, r0, r1 = round(col(west)), round(col(east)), round(row(north)), round(row(south))
        L = land[max(0, r0):r1, max(0, c0):c1]
        scores.append(round(float(new[max(0, r0):r1, max(0, c0):c1][L].mean()), 1) if L.any() else None)
    note = doc.get("mode_note") or ""
    fell = "rain that fell" in note
    rain = round(doc["rain"]["rain_between_mm"])
    out_doc = {
        "site": site,
        "made_by": "web/scripts/bake_prediction.py",
        "baked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "game": f"web/public/layers/{site}/game.json",
        "game_made_utc": game.get("made_utc"),
        "map": map_id,
        "issued_from_pass": doc.get("issued_from_pass"),
        "issued_from_sensor": sensor(doc.get("issued_from_pass")),
        "issue_time_utc": doc.get("issue_time_utc"),
        "target_time_utc": doc.get("target_time_utc"),
        "rain_mm": rain,
        "rain": "fell" if fell else "forecast",
        "mode_note": note,
        "rule": "mean new water likelihood (0 to 100) over the cell's land; ground already under water on the model's starting map counts as 0",
        "scores": scores,
        "sources": {"forecast": src.name(folder / "forecast.json"), "new_water_likelihood": src.name(folder / "new_water_likelihood_web.tif"),
                    "water_likelihood": src.name(folder / "water_likelihood_web.tif")},
    }
    path = out / "prediction" / "game.json"
    path.write_text(json.dumps(out_doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    top = sorted((s, i) for i, s in enumerate(scores) if s is not None)[::-1][:10]
    print(f"  {site} game: {map_id}, {len(scores)} cells, top ten {[i for _, i in top]} ({top[0][0]} to {top[-1][0]})", flush=True)
    return {"file": "prediction/game.json", "map": map_id}


# ---------------------------------------------------------------- one site

def model_grid(src: Source, site: str, entries: list[dict]):
    """The grid of the export's web rasters: a window of the zoom 13 lattice that holds the whole land grid of the
    model. The pipeline box of the site (meta.json) is a little smaller and would cut off part of the prediction."""
    for e in entries:
        path = src.root / site / e["scenario_id"] / "water_likelihood_web.tif"
        if not path.exists():
            continue
        with rasterio.open(path) as s:
            t = s.transform
            col, row = (t.c + ORIGIN) / RES, (ORIGIN - t.f) / RES
            if s.crs.to_epsg() == 3857 and abs(t.a - RES) < 1e-6 and abs(col - round(col)) < 1e-6 and abs(row - round(row)) < 1e-6:
                return t, s.width, s.height
    print(f"{site}: the web rasters are not on the zoom 13 lattice; using the box of meta.json")
    return web_grid(SITES[site]["bbox"])


def bounds_of(transform, width: int, height: int) -> list[float]:
    """west, south, east, north in degrees"""
    from pyproj import Transformer

    to_deg = Transformer.from_crs(3857, 4326, always_xy=True)
    west, north = to_deg.transform(transform.c, transform.f)
    east, south = to_deg.transform(transform.c + width * RES, transform.f - height * RES)
    return [round(west, 7), round(south, 7), round(east, 7), round(north, 7)]


def bake_site(src: Source, site: str, entries: list[dict], index: dict, game_map: str = GAME_MAP) -> Path | None:
    out = WEB / "public" / "layers" / site
    meta_path = out / "meta.json"
    if not meta_path.exists():
        print(f"{site}: no meta.json, run bake_water.py first; skipped")
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    transform, width, height = model_grid(src, site, entries)
    grid = {"transform": transform, "width": width, "height": height, "row_ha": pixel_ha(transform, height)}
    print(f"{site}: {len(entries)} maps onto {width} x {height} px", flush=True)
    folder = out / "prediction"
    for old in list(folder.glob("*.webp")) + list(folder.glob("*.bin")) + list(folder.glob("game.json")):
        old.unlink()

    recs = [r for e in entries if (r := bake_one(src, site, e, grid, out))]
    first = json.loads((src.root / site / recs[0]["id"] / "forecast.json").read_text(encoding="utf-8")) if recs else {}
    scenarios = sorted((r for r in recs if r["mode"] == "scenario"), key=lambda r: r["rain_mm"] if r["rain_mm"] is not None else 0)
    replays = sorted((r for r in recs if r["mode"] != "scenario"), key=lambda r: (r["target_time_utc"] or "", r["issue_time_utc"] or ""))
    slider_notes(site, scenarios)
    doc = {
        "site": site,
        "baked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "made_by": "web/scripts/bake_prediction.py",
        "source": {"folder": src.label, "ref": src.ref, "commit": src.commit, "index": f"{src.label}/index.json",
                   "index_sha256_16": sha16(src.root / "index.json"), "model_sha256_16": index.get("model_sha256_16")},
        "grid": {"width": width, "height": height, "bounds": bounds_of(transform, width, height), "zoom": meta["zoom"],
                 "pixel_m": round(float(np.sqrt(grid["row_ha"].mean() * 1e4)), 2),
                 "note": "the model's own web grid (the zoom 13 lattice of meta.json, a little larger than its box): "
                         "every likely pixel of the model is drawn, so the outline matches the hectares"},
        "display": {
            "R": "255 the model predicts here (evidence 0, 1, 3), 96 extrapolated (evidence 2 built-up, 4 rarely mapped), 0 none",
            "G": "relative water likelihood, percent 0 to 100",
            "B": "ground on the issue map: 255 dry (water would be new), 0 water already or permanent, 128 no earlier map",
        },
        "data_planes": {"evidence": "evidence flag of evidence_utm.tif, 255 sea or outside",
                        "water_likelihood_pct": "water_likelihood_web.tif as it is: 0 to 100, 255 no data",
                        "dry_before": "1 where new_water_likelihood_web.tif has a value (it is then the water likelihood)",
                        "new_water_likelihood_pct": "new_water_likelihood_web.tif as it is, when it is not the water likelihood"},
        "data_format": "PLN1: planes in bands of rows, each band zlib compressed (planes() in bake_prediction.py)",
        "model": first.get("model"),
        "score": first.get("score"),
        "evidence": first.get("evidence"),
        "holdout": first.get("holdout"),
        "attribution": first.get("attribution"),
        "native_resolution": first.get("native_resolution"),
        "scenarios": scenarios,
        "replays": replays,
        "inspect": inspect_layers(site, grid, meta, out),
        "game": game_answer(src, site, game_map, grid, out),
        "still_flooded": still_flooded(site, out),
    }
    path = out / "prediction.json"
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(r["bytes"] for r in recs)
    print(f"{site}: {path.relative_to(REPO).as_posix()}, {len(scenarios)} scenarios, {len(replays)} replays, "
          f"{total / 1e3:.0f} kB of maps to draw, {(sum(r['data_bytes'] for r in recs) + doc['inspect']['bytes']) / 1e3:.0f} kB to click", flush=True)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, help=f"a folder that holds index.json (default: {SPATIAL} of this checkout)")
    ap.add_argument("--ref", help="read the results from this git ref instead (a branch, tag or commit, e.g. pr-33)")
    ap.add_argument("--sites", nargs="*", default=["pego_oliva", "albufera"])
    ap.add_argument("--game-map", default=GAME_MAP, help=f"the model map that plays the flood game (default {GAME_MAP})")
    args = ap.parse_args()
    src = Source(args.src, args.ref)
    try:
        index = json.loads((src.root / "index.json").read_text(encoding="utf-8"))
        print(f"results: {src.label} (commit {src.commit}), model {index.get('model_sha256_16')}")
        for site in args.sites:
            entries = [e for e in index["scenarios"] if e["site"] == site]
            if entries:
                bake_site(src, site, entries, index, args.game_map)
            else:
                print(f"{site}: not in index.json; skipped")
    finally:
        src.close()


if __name__ == "__main__":
    main()
