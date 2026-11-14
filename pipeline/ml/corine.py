"""CORINE Land Cover 2018 polygons for the ML labels (public EEA service, no login).

Saves data/labels/<site>_clc2018.geojson with the classes the ML labels use:

    213            rice fields                    -> rice_paddy (shrunk by labels.RICE_SHRINK_M)
    221 222 223    vineyards, fruit trees, olives -> splits WorldCover tree cover: orchard
    241 to 244     mixed agricultural areas      -> orchard where WorldCover sees trees
    311 312 313    broad-leaved, coniferous, mixed forest -> forest

CORINE is mapped at 1:100,000 (25 ha minimum unit) from 2018 imagery, so it is
coarser than our 20 m grid. Rice is shrunk so field edges and canals drop out.

    python -m pipeline.ml.corine            # every ML site

Attribution: © European Union, Copernicus Land Monitoring Service 2018,
European Environment Agency (EEA).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import box

from pipeline.config import SITES, get_site
from pipeline.stack import site_grid

from . import config

URL = "https://image.discomap.eea.europa.eu/arcgis/rest/services/Corine/CLC2018_WM/MapServer/0/query"
CODES = ("213", "221", "222", "223", "241", "242", "243", "244", "311", "312", "313")
ATTRIBUTION = "© European Union, Copernicus Land Monitoring Service 2018, European Environment Agency (EEA)"
PAGE = 1000
CLIP_MARGIN_M = 200
SIMPLIFY_M = 5.0


def corine_path(site: str) -> Path:
    return config.LABELS_DIR / f"{site}_clc2018.geojson"


def fetch(site_name: str) -> Path:
    site = get_site(site_name)
    where = "Code_18 IN (" + ",".join(f"'{c}'" for c in CODES) + ")"
    features, offset = [], 0
    while True:
        r = requests.get(URL, timeout=120, params={
            "where": where, "geometry": ",".join(str(v) for v in site.bbox),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "Code_18,Area_Ha",
            "outSR": 4326, "f": "geojson", "resultOffset": offset, "resultRecordCount": PAGE,
        })
        r.raise_for_status()
        page = r.json()
        if "error" in page:
            raise RuntimeError(f"EEA service error: {page['error']}")
        features += page.get("features", [])
        if not page.get("exceededTransferLimit") and not page.get("properties", {}).get("exceededTransferLimit"):
            break
        offset += PAGE
    # Polygons reach far past the site box: clip to the stack grid (plus a margin)
    # so the committed file stays small.
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    grid = site_grid(site)
    w, n = grid.transform.c, grid.transform.f
    e, s = w + grid.width * grid.transform.a, n + grid.height * grid.transform.e
    box_utm = box(w - CLIP_MARGIN_M, s - CLIP_MARGIN_M, e + CLIP_MARGIN_M, n + CLIP_MARGIN_M)
    gdf = gpd.clip(gdf.to_crs(grid.crs), box_utm)
    gdf = gdf[~gdf.geometry.is_empty]
    # CORINE is a 100 m scale map; 5 m simplification loses nothing it holds.
    gdf.geometry = gdf.geometry.simplify(SIMPLIFY_M, preserve_topology=True)
    gdf["Code_18"] = gdf["Code_18"].astype(str)
    gdf = gdf.to_crs("EPSG:4326")
    gdf.geometry = gdf.geometry.set_precision(1e-6)  # about 0.1 m
    path = corine_path(site_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(gdf.to_json(drop_id=True))
    doc.update(name=f"{site_name}_clc2018", attribution=ATTRIBUTION, source=URL)
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    counts = gdf["Code_18"].value_counts().sort_index().to_dict()
    print(f"{site_name}: {len(gdf)} CORINE polygons {counts} -> {path} "
          f"({path.stat().st_size / 1e6:.1f} MB)")
    return path


def main() -> None:
    for name, site in SITES.items():
        if "ml" in site.models:
            fetch(name)


if __name__ == "__main__":
    main()
