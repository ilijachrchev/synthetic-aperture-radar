"""Bake the streets of the guided flood map (/explore, steps 2 and 3): the 2024 streets that really flooded and the
streets each method flags (the official zones, the SIMULATED run, and any run added with --method), as one light
line layer.

    set PYTHONPATH=<repository root>
    python web/scripts/bake_streets.py [--sim-raster PATH] [--method KEY=LABEL=RASTER[=RESULTS_PATH[=NOTE]] ...]
        (from the repository root, with the pipeline environment)

    --sim-raster  the SIMULATED run's maximum depth raster (PR #39's sim_hmax_25m.tif, or its rebuild): its streets
                  are then flagged from the run's own 25 m cells, as PR #43 did. Without it they come from the web copy
                  data/streets/simulated_max_depth.geojson (simplified at 25 m, specks under 4 cells dropped), which
                  flags fewer streets; the index says which, and the check shows the difference.
    --upv-raster  the UPV street depth map of 2024 (upv_depth5.tif of the street scores, 5 m, no value = NaN) and,
    --upv-outlines  beside it, its outlines (outline_cgat.geojson, outline_extra.geojson): the tap card then says what
                  that map holds on each street (a depth, no value inside its outlines, or outside them)
    --method      one more simulated run, repeatable, e.g. the runs driven by the forecasts of the night before and the
                  same morning (the last step's switch draws them through public/layers/guided/coming.json):
                  KEY (a short name), LABEL (the words on the switch), RASTER (its maximum depth raster, flagged above
                  0.3 m like the SIMULATED run), RESULTS_PATH (optional: a dotted path in data/streets/results.json to
                  its totals against key A, with flagged_km, hit_rate_pct and precision_pct; without it the numbers are
                  computed here on the same pieces), NOTE (optional: one line the step shows under the numbers).

The pieces are cut exactly as pipeline/street_scores.py cut them (PR #43): the OpenStreetMap ways of 28 Oct 2024 in
the 10 towns, cut into pieces of about 25 m, judged by the same rules (docs/STREETS.md, "Street by street"):

    flooded (key A)     at least half of the piece in the EMSR773 observed flood (flooded area or flood trace, the 3
                        first-response maps), or a surveyed water mark above 0 m within 10 m
    official zone       at least half of the piece in an SNCZI zone (T10, T100 or T500)
    SIMULATED           at least half of the piece where the SIMULATED run (rain on terrain, 25 m) is deeper than 0.3 m

It needs the downloads of the street scores, refetched into data/interim (they are not in git):

    data/interim/streets/osm/highways_<ine>.json    the Overpass answers recorded in data/streets/results.json
    data/interim/streets/icv/*.gml                  the ICV water marks (pipeline.streets fetch_icv)
    data/interim/flood-zones/                       IGN towns, SNCZI zones and EMSR773 packages (pipeline.zones fetch)

Two layers of the scores are not rebuilt here (the 1 m terrain behind them is several GB): the permanent water mask
and the terrain's no-data cells, which only leave out pieces on the sea, the port or the lagoon. Every total is checked
against data/streets/results.json and the check is written into the index, so a difference shows.

Writes, under web/public/layers/guided/:

    streets_2024.json      GeoJSON lines (WGS84, 5 decimals) of every scored street piece that flooded or that a method
                           flags, consecutive pieces of a way with the same values merged. Properties (left out when
                           0): f 1 flooded (key A), o 1 inside the EMSR773 observed flood, z official zone (1 T500,
                           2 T100, 3 T10), s 1 flagged by the SIMULATED run, sd its median maximum depth there (m,
                           SIMULATED), m_<key> 1 flagged by an added method, u the UPV map's median depth there (m,
                           MEASURED map) and uo 1 inside the UPV map's outlines, b graded buildings of EMSR773 within
                           25 m and bx the worst grade (1 possibly damaged, 2 damaged, 3 destroyed), r reveal order of a
                           flooded street (0 to 15, outward from the ravines), t town, n street name (indexes into
                           streets.json)
    zones_horta_sud.json   the official zones as one outline (the display copy of data/zones, dissolved)
    streets.json           the index: files, names and towns, the methods of step 3 (label, the property that flags a
                           street, their numbers with the field of results.json they come from, the rebuild check),
                           the numbers of step 2, the water marks for the tap card

Needs numpy, shapely, pyproj, rasterio and geopandas. Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer

from pipeline import street_scores as ss
from pipeline import streets as st

WEB = Path(__file__).resolve().parents[1]
REPO = WEB.parent
OUT = WEB / "public" / "layers" / "guided"
ZONES_DIR = REPO / "data" / "interim" / "flood-zones"
RESULTS = REPO / "data" / "streets" / "results.json"
SIM = REPO / "data" / "streets" / "simulated_max_depth.geojson"
FLOW = REPO / "data" / "streets" / "flow_paths.geojson"
MARKS = REPO / "data" / "streets" / "water_marks_2024.geojson"
ZONES_WEB = REPO / "data" / "zones" / "zones_horta_sud.geojson"
BUILDINGS = REPO / "data" / "zones" / "buildings_dana_2024_horta_sud.geojson"
BUILDINGS_M = 25.0  # the graded buildings counted beside a stretch of street
RAVINE_KM2 = 20.0  # a ravine: a terrain flow path draining more than 20 km2 (data/streets/flow_paths.geojson)
REVEAL_BINS = 16
KINDS = {
    "residential": "street", "living_street": "street", "pedestrian": "pedestrian street", "unclassified": "road",
    "tertiary": "road", "tertiary_link": "road", "secondary": "road", "secondary_link": "road", "primary": "road",
    "primary_link": "road", "trunk": "main road", "trunk_link": "main road", "motorway": "motorway",
    "motorway_link": "motorway slip road", "service": "service road", "footway": "footpath", "path": "path",
    "cycleway": "cycle path", "steps": "steps",
}
DASHES = dict.fromkeys([0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0x2E3A, 0x2E3B, 0xFE58, 0xFE31, 0xFE32], "-")  # code points, so this file holds none of them
RESULTS_CITE = "data/streets/results.json"


def plain(text: str) -> str:
    """Text as the page may show it: the dash family becomes a plain hyphen (the build refuses the others)."""
    return text.translate(DASHES)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def way_names() -> dict[int, str]:
    """OSM name of every way of the recorded Overpass answers (the ways kept by load_ways are among them)."""
    names: dict[int, str] = {}
    for path in sorted(ss.OSM_DIR.glob("highways_*.json")):
        for el in json.loads(path.read_text(encoding="utf-8")).get("elements", []):
            if el.get("type") == "way" and el["id"] not in names:
                names[el["id"]] = (el.get("tags") or {}).get("name", "")
    return names


def web_copy_at(cells: np.ndarray, on_grid: np.ndarray) -> np.ndarray:
    """The SIMULATED run deeper than 0.3 m from its web copy: the polygons burnt on the run's 25 m grid by cell centre,
    read at the 5 m cells of the points (the cell of a point holds the 25 m cell of PR #39, as pixel_layers reads it)."""
    import geopandas as gpd

    g = gpd.read_file(SIM).to_crs(st.CRS)
    sim = st.burn(g.geometry, cell=st.SIM_CELL_M)
    f = int(st.SIM_CELL_M // st.CELL_M)
    r, c = np.divmod(cells, st.grid_shape()[1])
    return sim[r // f, c // f] & on_grid


def raster_at(path: Path, xy: np.ndarray, depth_m: float = ss.SIM_EXTENT_M) -> np.ndarray:
    """A maximum depth raster deeper than depth_m at the points (EPSG:25830), cell by cell; no data or NaN is not."""
    vals = raster_values(path, xy)
    return np.isfinite(vals) & (vals > depth_m)


def raster_values(path: Path, xy: np.ndarray) -> np.ndarray:
    """A raster's values at the points (EPSG:25830), cell by cell; NaN where it has no value or no cell."""
    import rasterio

    with rasterio.open(path) as r:
        x, y = xy[:, 0], xy[:, 1]
        if r.crs and r.crs.to_string() not in ("EPSG:25830",):
            x, y = Transformer.from_crs(st.CRS, r.crs, always_xy=True).transform(x, y)
        rows, cols = rasterio.transform.rowcol(r.transform, x, y)
        rows, cols = np.asarray(rows), np.asarray(cols)
        ok = (rows >= 0) & (rows < r.height) & (cols >= 0) & (cols < r.width)
        band = r.read(1, masked=True)
        vals = np.full(xy.shape[0], np.nan, dtype=np.float64)
        got = band[rows[ok], cols[ok]]
        vals[ok] = np.where(np.ma.getmaskarray(got), np.nan, np.ma.getdata(got).astype(np.float64))
        print(f"  {path.name}: {r.width} x {r.height} cells of {r.res[0]:g} m, {r.crs}", flush=True)
    return vals


def dotted(doc: dict, path: str):
    for part in path.split("."):
        doc = doc[part]
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sim-raster", type=Path, default=None, help="maximum depth raster of the SIMULATED run (PR #39 sim_hmax_25m.tif)")
    ap.add_argument("--method", action="append", default=[], help="KEY=LABEL=RASTER[=RESULTS_PATH[=NOTE]]: one more option for step 3")
    ap.add_argument("--upv-raster", type=Path, default=None, help="the UPV street depth map (upv_depth5.tif, 5 m, EPSG:25830)")
    ap.add_argument("--upv-outlines", type=Path, nargs="*", default=[], help="the UPV map's outlines (GeoJSON)")
    a = ap.parse_args()
    extras = []
    for spec in a.method:
        parts = spec.split("=")
        if len(parts) < 3:
            raise SystemExit(f"--method {spec!r}: KEY=LABEL=RASTER[=RESULTS_PATH[=NOTE]]")
        extras.append({"key": parts[0], "label": parts[1], "raster": Path(parts[2]),
                       "results": parts[3] if len(parts) > 3 and parts[3] else None,
                       "note": parts[4] if len(parts) > 4 and parts[4] else None})

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    main_res = res["streets"]["main"]

    # ------------------------------------------------------------ pieces (as pipeline.street_scores.build_pieces)
    b = ss.build_pieces(tracks=False)
    pcs = b["pieces"]
    n_all = pcs["length"].size
    print(f"pieces cut: {n_all}, {time.time() - t0:.0f} s", flush=True)
    s_cells = st.cells_of_points(b["s_xy"][:, 0], b["s_xy"][:, 1])
    m_cells = st.cells_of_points(b["m_xy"][:, 0], b["m_xy"][:, 1])
    cells = np.concatenate([s_cells, m_cells])
    points = np.concatenate([b["s_xy"], b["m_xy"]])
    on_grid = cells >= 0
    safe = np.where(on_grid, cells, 0)
    ns = s_cells.size

    # ------------------------------------------------------------ the layers at the sample and midpoint cells
    lay: dict[str, np.ndarray] = {}
    towns = st.load_towns(ZONES_DIR)
    tid = st.town_grid(towns).ravel()
    products = st.ems_products(ZONES_DIR)
    analysed = np.logical_or.reduce([p["analysed"] for p in products]).ravel()
    observed = np.logical_or.reduce([p["flooded_area"] | p["flood_trace"] for p in products]).ravel()
    del products
    gc.collect()
    scored = (tid > 0) & analysed            # the scores also leave out permanent water and no-data terrain
    lay["scored"] = scored[safe] & on_grid
    lay["town"] = np.where(on_grid, tid[safe], 0)
    lay["observed"] = observed[safe] & on_grid
    del tid, analysed, observed, scored
    gc.collect()
    zones = st.zone_grids(ZONES_DIR)
    for z in st.ZONE_NAMES:
        lay[f"zone_{z}"] = zones[z].ravel()[safe] & on_grid
    del zones
    gc.collect()
    if a.sim_raster:
        lay["sim_depth"] = np.where(on_grid, raster_values(a.sim_raster, points), np.nan)
        lay["sim"] = np.isfinite(lay["sim_depth"]) & (lay["sim_depth"] > ss.SIM_EXTENT_M)
        sim_from = f"the run's own raster ({a.sim_raster.name})"
    else:
        lay["sim"] = web_copy_at(safe, on_grid)
        sim_from = "the web copy data/streets/simulated_max_depth.geojson (simplified at 25 m, specks under 4 cells dropped)"
    for e in extras:
        lay[f"m_{e['key']}"] = raster_at(e["raster"], points) & on_grid
    if a.upv_raster:
        lay["upv"] = np.where(on_grid, raster_values(a.upv_raster, points), np.nan)
    print(f"layers read, {time.time() - t0:.0f} s", flush=True)

    # ------------------------------------------------------------ the rules of evaluate()
    s_scored = lay["scored"][:ns]
    m_scored = lay["scored"][ns:]
    m_town = lay["town"][ns:]
    keep = m_scored & (m_town > 0)
    has = np.bincount(b["s_piece"][s_scored], minlength=n_all) > 0
    fallback = np.flatnonzero(keep & ~has)
    e_rows = np.concatenate([np.flatnonzero(s_scored & keep[b["s_piece"]]), ns + fallback])
    e_piece = np.concatenate([b["s_piece"][s_scored & keep[b["s_piece"]]], fallback])
    remap = np.full(n_all, -1, dtype=np.int64)
    remap[keep] = np.arange(int(keep.sum()))
    e_piece = remap[e_piece]
    n = int(keep.sum())
    length = pcs["length"][keep]
    town = m_town[keep]

    def frac(name: str) -> np.ndarray:
        return ss.share_in(lay[name][e_rows], e_piece, n)

    marks = st.water_marks_all()
    marks = marks[marks["height_m"] > 0]
    lines = b["lines"][keep]
    in_obs = frac("observed") >= ss.MAJORITY
    near = ss.near_points(lines, marks["x"].to_numpy(), marks["y"].to_numpy())
    flooded = in_obs | near
    zone_share = {z: frac(f"zone_{z}") for z in st.ZONE_NAMES}
    in_zone = zone_share["union"] >= ss.MAJORITY
    zone = np.where(zone_share["T10"] >= ss.MAJORITY, 3, np.where(zone_share["T100"] >= ss.MAJORITY, 2, np.where(in_zone, 1, 0)))
    sim_flag = frac("sim") >= ss.MAJORITY
    extra_flags = {e["key"]: frac(f"m_{e['key']}") >= ss.MAJORITY for e in extras}
    # what the tap card reads: medians over each piece's samples (NaN where the layer has no value)
    sim_depth = ss.group_median(lay["sim_depth"][e_rows], e_piece, n) if "sim_depth" in lay else np.full(n, np.nan)
    upv_depth = ss.group_median(lay["upv"][e_rows], e_piece, n) if "upv" in lay else np.full(n, np.nan)
    in_upv = np.zeros(n, dtype=bool)
    if a.upv_outlines:
        import geopandas as gpd

        outline = shapely.union_all([g for f in a.upv_outlines for g in gpd.read_file(f).to_crs(st.CRS).geometry])
        shapely.prepare(outline)
        mid = b["m_xy"][keep]
        in_upv = shapely.contains_xy(outline, mid[:, 0], mid[:, 1])

    # ------------------------------------------------------------ checks against results.json
    def km(sel: np.ndarray) -> float:
        return round(float(length[sel].sum()) / 1000, 2)

    def metrics(flag: np.ndarray) -> dict:
        return {"flagged_km": km(flag), "flagged_and_flooded_km": km(flag & flooded),
                "hit_rate_pct": round(100 * float(length[flag & flooded].sum()) / float(length[flooded].sum()), 1),
                "precision_pct": round(100 * float(length[flag & flooded].sum()) / max(1e-9, float(length[flag].sum())), 1)}

    def same(m: dict, t: dict) -> bool:
        return abs(m["flagged_km"] - t["flagged_km"]) <= 0.5 and m["hit_rate_pct"] == t["hit_rate_pct"] and m["precision_pct"] == t["precision_pct"]

    meth = main_res["methods"]
    mine = {
        "pieces": n, "street_km": km(np.ones(n, bool)), "flooded_km": km(flooded),
        "in_observed_flood_km": km(in_obs), "near_a_mark_km": km(near),
        "flooded_km_outside_every_zone": km(flooded & ~in_zone),
    }
    theirs = {
        "pieces": main_res["summary"]["pieces"], "street_km": main_res["summary"]["street_km"],
        "flooded_km": main_res["summary"]["key_a"]["flooded_km"],
        "in_observed_flood_km": main_res["summary"]["key_a"]["in_observed_flood_km"],
        "near_a_mark_km": main_res["summary"]["key_a"]["near_a_mark_km"],
        "flooded_km_outside_every_zone": main_res["descriptive"]["key_a_flooded_km_outside_every_zone"],
    }
    print(json.dumps({"rebuilt": mine, "results_json": theirs}, indent=1), flush=True)

    # the methods of step 3: the words on the switch, the property that flags a street, the numbers shown (from
    # results.json when it has them) and the same numbers counted on the pieces drawn here
    def entry(key, label, prop, flag, path, note, drawn_from):
        rebuilt = metrics(flag)
        out = {"key": key, "label": label, "prop": prop, "note": note, "drawn_from": drawn_from, "rebuilt": rebuilt}
        if path:
            tot = dotted(res, path)
            out.update({f: {"value": tot[f], "source": f"{RESULTS_CITE} {path}.{f}"} for f in ("hit_rate_pct", "precision_pct", "flagged_km")})
            out["results_json"] = {f: tot[f] for f in ("flagged_km", "hit_rate_pct", "precision_pct")}
            out["exact"] = same(rebuilt, out["results_json"])
        else:
            out.update({f: {"value": rebuilt[f], "source": f"counted by web/scripts/bake_streets.py on the PR #43 pieces ({drawn_from})"} for f in ("hit_rate_pct", "precision_pct", "flagged_km")})
            out["exact"] = None
        print(f"  method {key}: rebuilt {rebuilt}" + (f", results.json {out['results_json']}, same: {out['exact']}" if path else ""), flush=True)
        return out

    methods = [
        entry("zones", "Official map", "z", in_zone, "streets.main.methods.official_union.A.total", None,
              "the SNCZI zones refetched by pipeline.zones (T10, T100, T500)"),
        entry("sim", "Our simulation", "s", sim_flag, "streets.main.methods.simulated_depth_above_0p3m.A.total",
              "Run with the rain that fell on 29 Oct 2024.", sim_from),
    ]
    for e in extras:
        methods.append(entry(e["key"], e["label"], f"m_{e['key']}", extra_flags[e["key"]], e["results"], e["note"], f"its raster ({e['raster'].name})"))

    # ------------------------------------------------------------ reveal order: outward from the ravines
    import geopandas as gpd

    flow = gpd.read_file(FLOW).to_crs(st.CRS)
    flow = flow[flow["upstream_km2_from"] >= RAVINE_KM2]
    ravines = shapely.union_all(list(flow.geometry))
    mxy = b["m_xy"][keep]
    dist = shapely.distance(shapely.points(mxy[:, 0], mxy[:, 1]), ravines)
    order = np.full(n, -1, dtype=np.int64)
    fi = np.flatnonzero(flooded)
    rank = np.argsort(np.argsort(dist[fi], kind="stable"), kind="stable")
    order[fi] = np.minimum(REVEAL_BINS - 1, (rank * REVEAL_BINS) // max(1, fi.size))

    # ------------------------------------------------------------ merge runs and write the lines
    names = way_names()
    way_ids = b["ways"]["ids"]
    hw = b["ways"]["highway"]
    piece_way = pcs["way"][keep]
    piece_k = pcs["k"][keep]
    shown = flooded | in_zone | sim_flag
    for fl in extra_flags.values():
        shown |= fl
    name_list: list[str] = []
    name_ix: dict[str, int] = {}

    def name_of(w: int) -> int:
        text = plain(names.get(int(way_ids[w]), "")) or f"Unnamed {KINDS.get(str(hw[w]), 'street')}"
        if text not in name_ix:
            name_ix[text] = len(name_list)
            name_list.append(text)
        return name_ix[text]

    # the graded buildings of EMSR773 (data/zones), for the count within 25 m of a stretch of street
    import geopandas as gpd

    grades = {"Possibly damaged": 1, "Damaged": 2, "Destroyed": 3}
    bld = gpd.read_file(BUILDINGS).to_crs(st.CRS)
    bld_grade = np.array([grades.get(str(d), 0) for d in bld["damage"]])
    bld_tree = shapely.STRtree(np.asarray(bld.geometry))

    def median_of(values: np.ndarray, run: list[int]) -> float:
        v = values[run]
        v = v[np.isfinite(v)]
        return float(np.median(v)) if v.size else float("nan")

    def props_of(i: int, run: list[int], line) -> dict:
        p = {}
        if flooded[i]:
            p["f"] = 1
            p["r"] = int(order[i])
        if in_obs[i]:
            p["o"] = 1
        if zone[i]:
            p["z"] = int(zone[i])
        if sim_flag[i]:
            p["s"] = 1
        sd = median_of(sim_depth, run)
        if np.isfinite(sd) and sd >= 0.05:
            p["sd"] = round(sd, 1)
        ud = median_of(upv_depth, run)
        if np.isfinite(ud):
            p["u"] = round(max(0.0, ud), 1)
        if in_upv[run].any():
            p["uo"] = 1
        near_b = bld_tree.query(line, predicate="dwithin", distance=BUILDINGS_M)
        if near_b.size:
            p["b"] = int(near_b.size)
            p["bx"] = int(bld_grade[near_b].max())
        for k, fl in extra_flags.items():
            if fl[i]:
                p[f"m_{k}"] = 1
        p["t"] = int(town[i] - 1)
        p["n"] = name_of(int(piece_way[i]))
        return p

    to_wgs = Transformer.from_crs(st.CRS, "EPSG:4326", always_xy=True)
    idx = np.flatnonzero(shown)
    idx = idx[np.lexsort((piece_k[idx], piece_way[idx]))]
    feats = []
    run: list[int] = []

    def flush() -> None:
        if not run:
            return
        geoms = shapely.get_coordinates(lines[run])
        # pieces of one way follow each other: drop the repeated joints, then the needless vertices (0.5 m)
        line = shapely.simplify(shapely.linestrings(geoms), 0.5)
        xy = shapely.get_coordinates(line)
        lon, lat = to_wgs.transform(xy[:, 0], xy[:, 1])
        coords = [[round(float(a), 5), round(float(o), 5)] for a, o in zip(lon, lat)]
        dedup = [coords[0]] + [p for i, p in enumerate(coords[1:], 1) if p != coords[i - 1]]
        if len(dedup) < 2:
            dedup = [coords[0], coords[-1]]
        feats.append({"type": "Feature", "properties": props_of(run[0], run, line), "geometry": {"type": "LineString", "coordinates": dedup}})

    prev = None
    for i in idx:
        key = (int(piece_way[i]), int(flooded[i]), int(in_obs[i]), int(zone[i]), int(order[i]), int(sim_flag[i]), *(int(fl[i]) for fl in extra_flags.values()))
        if prev is not None and key == prev[0] and piece_k[i] == prev[1] + 1:
            run.append(int(i))
        else:
            flush()
            run = [int(i)]
        prev = (key, int(piece_k[i]))
    flush()
    doc = {"type": "FeatureCollection", "features": feats}
    data = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    (OUT / "streets_2024.json").write_bytes(data)
    gz = len(gzip.compress(data, 9))
    print(f"streets_2024.json: {len(feats)} lines, {len(data) / 1e6:.2f} MB, gzip {gz / 1e6:.2f} MB", flush=True)

    # ------------------------------------------------------------ the official zones as one outline
    zg = gpd.read_file(ZONES_WEB)
    zu = shapely.union_all(list(zg.to_crs(st.CRS).geometry))
    zu = shapely.simplify(zu, 2.0, preserve_topology=True)
    zw = gpd.GeoSeries([zu], crs=st.CRS).to_crs("EPSG:4326").iloc[0]
    zw = shapely.set_precision(zw, 1e-5)
    zdoc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"zone": "any"}, "geometry": shapely.geometry.mapping(zw)}]}
    zdata = json.dumps(zdoc, separators=(",", ":")).encode("utf-8")
    (OUT / "zones_horta_sud.json").write_bytes(zdata)
    print(f"zones_horta_sud.json: {len(zdata) / 1e6:.2f} MB, gzip {len(gzip.compress(zdata, 9)) / 1e6:.2f} MB", flush=True)
    old = OUT / "simulated_2024.json"
    if old.exists():
        old.unlink()  # step 3 draws the flagged streets now, not the run's area

    # ------------------------------------------------------------ the water marks for the tap card
    mk = json.loads(MARKS.read_text(encoding="utf-8"))
    marks_out = [[round(ft["geometry"]["coordinates"][0], 5), round(ft["geometry"]["coordinates"][1], 5), ft["properties"]["depth_m"]]
                 for ft in mk["features"]]

    d = main_res["descriptive"]
    index = {
        "made_by": "web/scripts/bake_streets.py",
        "baked_utc": now(),
        "files": {
            "streets": {"file": "streets_2024.json", "bytes": len(data), "gzip_bytes": gz, "lines": len(feats),
                        "sha256_16": hashlib.sha256(data).hexdigest()[:16]},
            "zones": {"file": "zones_horta_sud.json", "bytes": len(zdata), "source": "data/zones/zones_horta_sud.geojson (PR #36), the three classes dissolved"},
        },
        "towns": list(st.TOWNS),
        "names": name_list,
        "zones": {"0": "no flood zone", "1": "rare flood zone (T500, 1 in 500 years)", "2": "occasional flood zone (T100, 1 in 100 years)", "3": "frequent flood zone (T10, 1 in 10 years)"},
        "reveal": {"bins": REVEAL_BINS, "rule": f"flooded streets ranked by the distance of their midpoint from the nearest terrain flow path draining more than {RAVINE_KM2:g} km2 (data/streets/flow_paths.geojson); an order in space, not in time"},
        "methods": methods,
        "numbers": {
            "outside_pct": {"value": d["key_a_flooded_outside_every_zone_pct"], "source": f"{RESULTS_CITE} streets.main.descriptive.key_a_flooded_outside_every_zone_pct"},
            "outside_km": {"value": d["key_a_flooded_km_outside_every_zone"], "source": f"{RESULTS_CITE} streets.main.descriptive.key_a_flooded_km_outside_every_zone"},
            "flooded_km": {"value": main_res["summary"]["key_a"]["flooded_km"], "source": f"{RESULTS_CITE} streets.main.summary.key_a.flooded_km"},
            "street_km": {"value": main_res["summary"]["street_km"], "source": f"{RESULTS_CITE} streets.main.summary.street_km"},
        },
        "rules": {
            "flooded": "key A of docs/STREETS.md: at least half of the piece in the EMSR773 observed flood (flooded area or flood trace) or a surveyed water mark above 0 m within 10 m",
            "zone": "at least half of the piece in an SNCZI zone (any of T10, T100, T500); the class named is the most frequent one that holds half the piece",
            "simulated": "at least half of the piece where the SIMULATED run (rain on terrain, 25 m, measured rain of 29 Oct 2024, no infiltration) is deeper than 0.3 m",
            "pieces": "OpenStreetMap ways of 28 Oct 2024 (Overpass, the queries of results.json streets.inputs.osm) cut into pieces of about 25 m, scored when the midpoint lies in one of the 10 towns and in the area EMSR773 analysed",
        },
        "check": {"rebuilt": mine, "results_json": theirs,
                  "not_rebuilt": "the permanent water mask and the terrain's no-data cells of the scores (they only leave out pieces on water)",
                  "methods": {m["key"]: {"rebuilt": m["rebuilt"], "results_json": m.get("results_json"), "same": m["exact"]} for m in methods}},
        "marks": {"what": "water heights surveyed after the flood (MEASURED), above 0 m, in the 10 towns: lon, lat, depth in m",
                  "source": "data/streets/water_marks_2024.geojson (ICV DANA 2024 service, CC BY 4.0)", "radius_m": 25, "points": marks_out},
        "sources": {
            "streets": "OpenStreetMap contributors, ODbL 1.0 (ways of 28 Oct 2024)",
            "flood": "Copernicus EMS EMSR773, observed flood of 3 first-response maps (© European Union)",
            "marks": "Institut Cartogràfic Valencià, Generalitat Valenciana, DANA 2024 service, CC BY 4.0",
            "zones": "SNCZI, MITECO (T10, T100, T500)",
            "simulated": f"the team's rain-on-terrain run (PR #39), streets flagged from {sim_from}",
            "upv": "UPV street depth map of the 2024 flood (Roch Talens et al. 2025, doi 10.7203/CGUV.114-15.32144), median depth over the stretch",
            "buildings": "Copernicus EMS EMSR773 grading of damaged buildings (© European Union), within 25 m of the stretch",
            "scores": "data/streets/results.json (PR #43), docs/STREETS.md",
        },
    }
    (OUT / "streets.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"streets.json written, {time.time() - t0:.0f} s", flush=True)
    print(Counter(int(z) for z in zone[flooded]))


if __name__ == "__main__":
    main()
