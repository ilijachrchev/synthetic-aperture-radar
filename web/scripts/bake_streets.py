"""Bake the streets of the guided flood map (/explore, steps 2 and 3): the 2024 streets that really flooded, as one
light line layer, with the official zones and the SIMULATED run's extent as two plain outlines.

    set PYTHONPATH=<repository root>
    python web/scripts/bake_streets.py          (from the repository root, with the pipeline environment)

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
against data/streets/results.json and the check is written into the index, so a difference shows. The SIMULATED run's
own raster is not on this machine either: its web copy (data/streets/simulated_max_depth.geojson, simplified at 25 m,
specks under 4 cells dropped) flags 486 km of street where the scores say 532 km, so the page draws that copy as an
outline (the run's extent, as published) and never as street flags; the street numbers come from results.json.

Writes, under web/public/layers/guided/:

    streets_2024.json      GeoJSON lines (WGS84, 5 decimals) of the streets that flooded (key A), consecutive pieces of a
                           way with the same values merged: z official zone (0 none, 1 T500, 2 T100, 3 T10), r reveal
                           order (0 to 15, outward from the ravines), t town, n street name (both indexes into the
                           lists of streets.json)
    zones_horta_sud.json   the official zones as one outline (the display copy of data/zones, dissolved)
    simulated_2024.json    the SIMULATED run deeper than 0.3 m as one outline (data/streets, its three classes dissolved)
    streets.json           the index: files and bytes, names and towns, the numbers the steps show (each with the
                           field of results.json it comes from), the rebuild check, the water marks for the tap card

Needs numpy, shapely, pyproj, rasterio and geopandas. Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import gc
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
RAVINE_KM2 = 20.0  # a ravine: a terrain flow path draining more than 20 km2 (data/streets/flow_paths.geojson)
REVEAL_BINS = 16
ZONE_CODE = {"none": 0, "T500": 1, "T100": 2, "T10": 3}
KINDS = {
    "residential": "street", "living_street": "street", "pedestrian": "pedestrian street", "unclassified": "road",
    "tertiary": "road", "tertiary_link": "road", "secondary": "road", "secondary_link": "road", "primary": "road",
    "primary_link": "road", "trunk": "main road", "trunk_link": "main road", "motorway": "motorway",
    "motorway_link": "motorway slip road", "service": "service road", "footway": "footpath", "path": "path",
    "cycleway": "cycle path", "steps": "steps",
}


DASHES = dict.fromkeys([0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0x2E3A, 0x2E3B, 0xFE58, 0xFE31, 0xFE32], "-")  # code points, so this file holds none of them


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


def sim_mask_25m() -> np.ndarray:
    """The SIMULATED run deeper than 0.3 m on its own 25 m grid: its polygons burnt by cell centre (they are the cells'
    own outlines, so every centre falls clearly inside or outside)."""
    import geopandas as gpd

    g = gpd.read_file(SIM).to_crs(st.CRS)
    return st.burn(g.geometry, cell=st.SIM_CELL_M)


def main() -> None:
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
    sim = sim_mask_25m()
    f = int(st.SIM_CELL_M // st.CELL_M)
    cols = st.grid_shape()[1]
    r, c = np.divmod(safe, cols)
    lay["sim"] = sim[r // f, c // f] & on_grid
    del sim
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

    # ------------------------------------------------------------ checks against results.json
    def km(sel: np.ndarray) -> float:
        return round(float(length[sel].sum()) / 1000, 2)

    def metrics(flag: np.ndarray) -> dict:
        return {"flagged_km": km(flag), "flagged_and_flooded_km": km(flag & flooded),
                "hit_rate_pct": round(100 * float(length[flag & flooded].sum()) / float(length[flooded].sum()), 1),
                "precision_pct": round(100 * float(length[flag & flooded].sum()) / float(length[flag].sum()), 1)}

    mine = {
        "pieces": n, "street_km": km(np.ones(n, bool)), "flooded_km": km(flooded),
        "in_observed_flood_km": km(in_obs), "near_a_mark_km": km(near),
        "flooded_km_outside_every_zone": km(flooded & ~in_zone),
        "official_union": metrics(in_zone), "simulated_depth_above_0p3m": metrics(sim_flag),
    }
    meth = main_res["methods"]
    theirs = {
        "pieces": main_res["summary"]["pieces"], "street_km": main_res["summary"]["street_km"],
        "flooded_km": main_res["summary"]["key_a"]["flooded_km"],
        "in_observed_flood_km": main_res["summary"]["key_a"]["in_observed_flood_km"],
        "near_a_mark_km": main_res["summary"]["key_a"]["near_a_mark_km"],
        "flooded_km_outside_every_zone": main_res["descriptive"]["key_a_flooded_km_outside_every_zone"],
        "official_union": {k: meth["official_union"]["A"]["total"][k] for k in mine["official_union"]},
        "simulated_depth_above_0p3m": {k: meth["simulated_depth_above_0p3m"]["A"]["total"][k] for k in mine["simulated_depth_above_0p3m"]},
    }
    print(json.dumps({"rebuilt": mine, "results_json": theirs}, indent=1), flush=True)

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
    shown = flooded
    name_list: list[str] = []
    name_ix: dict[str, int] = {}

    def name_of(w: int) -> int:
        text = plain(names.get(int(way_ids[w]), "")) or f"Unnamed {KINDS.get(str(hw[w]), 'street')}"
        if text not in name_ix:
            name_ix[text] = len(name_list)
            name_list.append(text)
        return name_ix[text]

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
        i0 = run[0]
        props = {"z": int(zone[i0]), "r": int(order[i0]), "t": int(town[i0] - 1), "n": name_of(int(piece_way[i0]))}
        feats.append({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": dedup}})

    prev = None
    for i in idx:
        key = (int(piece_way[i]), int(zone[i]), int(order[i]))
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
    import gzip

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

    # ------------------------------------------------------------ the SIMULATED extent as one outline
    sg = gpd.read_file(SIM)
    su = shapely.union_all(list(sg.to_crs(st.CRS).geometry))
    sw = gpd.GeoSeries([su], crs=st.CRS).to_crs("EPSG:4326").iloc[0]
    sw = shapely.set_precision(sw, 1e-5)
    sdoc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"max_depth": "above 0.3 m"}, "geometry": shapely.geometry.mapping(sw)}]}
    sdata = json.dumps(sdoc, separators=(",", ":")).encode("utf-8")
    (OUT / "simulated_2024.json").write_bytes(sdata)
    print(f"simulated_2024.json: {len(sdata) / 1e6:.2f} MB, gzip {len(gzip.compress(sdata, 9)) / 1e6:.2f} MB", flush=True)

    # ------------------------------------------------------------ the water marks for the tap card
    mk = json.loads(MARKS.read_text(encoding="utf-8"))
    marks_out = [[round(ft["geometry"]["coordinates"][0], 5), round(ft["geometry"]["coordinates"][1], 5), ft["properties"]["depth_m"]]
                 for ft in mk["features"]]

    d = main_res["descriptive"]
    o = meth["official_union"]["A"]["total"]
    s = meth["simulated_depth_above_0p3m"]["A"]["total"]
    index = {
        "made_by": "web/scripts/bake_streets.py",
        "baked_utc": now(),
        "files": {
            "streets": {"file": "streets_2024.json", "bytes": len(data), "gzip_bytes": gz, "lines": len(feats),
                        "sha256_16": hashlib.sha256(data).hexdigest()[:16]},
            "zones": {"file": "zones_horta_sud.json", "bytes": len(zdata), "source": "data/zones/zones_horta_sud.geojson (PR #36), the three classes dissolved"},
            "simulated": {"file": "simulated_2024.json", "bytes": len(sdata), "source": "data/streets/simulated_max_depth.geojson (PR #39), the three classes dissolved: deeper than 0.3 m"},
        },
        "towns": list(st.TOWNS),
        "names": name_list,
        "zones": {"0": "no flood zone", "1": "rare flood zone (T500, 1 in 500 years)", "2": "occasional flood zone (T100, 1 in 100 years)", "3": "frequent flood zone (T10, 1 in 10 years)"},
        "reveal": {"bins": REVEAL_BINS, "rule": f"flooded streets ranked by the distance of their midpoint from the nearest terrain flow path draining more than {RAVINE_KM2:g} km2 (data/streets/flow_paths.geojson); an order in space, not in time"},
        "numbers": {
            "outside_pct": {"value": d["key_a_flooded_outside_every_zone_pct"], "source": "data/streets/results.json streets.main.descriptive.key_a_flooded_outside_every_zone_pct"},
            "outside_km": {"value": d["key_a_flooded_km_outside_every_zone"], "source": "data/streets/results.json streets.main.descriptive.key_a_flooded_km_outside_every_zone"},
            "flooded_km": {"value": main_res["summary"]["key_a"]["flooded_km"], "source": "data/streets/results.json streets.main.summary.key_a.flooded_km"},
            "street_km": {"value": main_res["summary"]["street_km"], "source": "data/streets/results.json streets.main.summary.street_km"},
            "sim_hit_pct": {"value": s["hit_rate_pct"], "source": "data/streets/results.json streets.main.methods.simulated_depth_above_0p3m.A.total.hit_rate_pct"},
            "sim_precision_pct": {"value": s["precision_pct"], "source": "data/streets/results.json streets.main.methods.simulated_depth_above_0p3m.A.total.precision_pct"},
            "sim_flagged_km": {"value": s["flagged_km"], "source": "data/streets/results.json streets.main.methods.simulated_depth_above_0p3m.A.total.flagged_km"},
            "zones_hit_pct": {"value": o["hit_rate_pct"], "source": "data/streets/results.json streets.main.methods.official_union.A.total.hit_rate_pct"},
            "zones_precision_pct": {"value": o["precision_pct"], "source": "data/streets/results.json streets.main.methods.official_union.A.total.precision_pct"},
            "zones_flagged_km": {"value": o["flagged_km"], "source": "data/streets/results.json streets.main.methods.official_union.A.total.flagged_km"},
        },
        "rules": {
            "flooded": "key A of docs/STREETS.md: at least half of the piece in the EMSR773 observed flood (flooded area or flood trace) or a surveyed water mark above 0 m within 10 m",
            "zone": "at least half of the piece in an SNCZI zone (any of T10, T100, T500); the class named is the most frequent one that holds half the piece",
            "simulated": "at least half of the piece where the SIMULATED run (rain on terrain, 25 m, measured rain of 29 Oct 2024, no infiltration) is deeper than 0.3 m",
            "pieces": "OpenStreetMap ways of 28 Oct 2024 (Overpass, the queries of results.json streets.inputs.osm) cut into pieces of about 25 m, scored when the midpoint lies in one of the 10 towns and in the area EMSR773 analysed",
        },
        "check": {"rebuilt": mine, "results_json": theirs,
                  "not_rebuilt": "the permanent water mask and the terrain's no-data cells of the scores (they only leave out pieces on water)",
                  "simulated": "rebuilt from the web copy of the SIMULATED depth (simplified at 25 m, specks under 4 cells dropped), not the run's raster: so the page draws that copy as an outline and shows the street numbers of results.json"},
        "marks": {"what": "water heights surveyed after the flood (MEASURED), above 0 m, in the 10 towns: lon, lat, depth in m",
                  "source": "data/streets/water_marks_2024.geojson (ICV DANA 2024 service, CC BY 4.0)", "radius_m": 25, "points": marks_out},
        "sources": {
            "streets": "OpenStreetMap contributors, ODbL 1.0 (ways of 28 Oct 2024)",
            "flood": "Copernicus EMS EMSR773, observed flood of 3 first-response maps (© European Union)",
            "marks": "Institut Cartogràfic Valencià, Generalitat Valenciana, DANA 2024 service, CC BY 4.0",
            "zones": "SNCZI, MITECO (T10, T100, T500)",
            "simulated": "the team's rain-on-terrain run (data/streets/simulated_max_depth.geojson, PR #39)",
            "scores": "data/streets/results.json (PR #43), docs/STREETS.md",
        },
    }
    (OUT / "streets.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"streets.json written, {time.time() - t0:.0f} s", flush=True)
    print(Counter(int(z) for z in zone[flooded]))


if __name__ == "__main__":
    main()
