"""Reference outlines for checking the CV model (public sources, no login).

Writes small GeoJSON files (WGS84) to data/labels/:

- pego_oliva_emsr935_flood.geojson
    Copernicus EMS rapid mapping EMSR935 (imagery 20 to 21 Oct 2026),
    republished by the Valencian cartographic institute (ICV). Classes
    flooded_area and flood_trace. Our NISAR "after" pass is 28 Oct, so this
    is a maximum-extent reference, not same-day truth.
- pego_oliva_emsr935_aoi.geojson
    The two EMSR935 areas of interest (AOI01 Moraira, delineation; AOI02
    Gandia, grading), from the Copernicus rapid mapping dashboard API. Inside
    them every flooded pixel was outlined, so they bound where a flood map can
    be scored.
- pego_oliva_generalitat_footprint.geojson
    Official river-flood footprint of DANA "Adam" (Generalitat Valenciana),
    one polygon of 1,022.8 ha, from surveyed flood marks.
- pego_oliva_water_depth_points.geojson
    Surveyed water-depth marks in metres (same service).
- espada_effis_burnt_area.geojson
    EFFIS burnt area of the Serra d'Espadà fire (ignition 25 Jul 2026).

Usage:
    python -m pipeline.labels

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import io
import re

import geopandas as gpd
import pandas as pd
import requests
import shapely
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from pipeline.config import LABELS_DIR

RAPID_MAPPING_API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"
ICV_WFS = "https://terramapas.icv.gva.es/2702_DANAAdam2026"
ICV_CRS = "EPSG:25830"  # ETRS89 / UTM 30N, the service's native CRS
EFFIS_API = "https://api.effis.emergency.copernicus.eu/rest/2/burntareas/current/"
ESPADA_EFFIS_ID = "570518"  # Castellón, listed under the municipality Nules
AREA_CRS = "EPSG:32630"  # UTM 30N, used for every area we report
TIMEOUT_S = 180

COORD_GRID_DEG = 1e-6  # about 0.1 m; matches the 6 decimals written to GeoJSON

# En dash (U+2013) and em dash (U+2014) become plain hyphens.
_DASHES = str.maketrans({0x2013: "-", 0x2014: "-"})


def clean_text(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize en and em dashes in text columns to plain hyphens."""
    out = df.copy()
    for col in out.columns:
        if col == "geometry":
            continue
        if out[col].dtype == object or pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].map(lambda v: v.translate(_DASHES) if isinstance(v, str) else v)
    return out


def fetch_wfs_layer(type_name: str) -> gpd.GeoDataFrame:
    """One ICV WFS layer as a GeoDataFrame in EPSG:25830 (GML, the format every layer offers)."""
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "srsName": "urn:ogc:def:crs:EPSG::25830",
        "outputFormat": "text/xml; subtype=gml/3.1.1",
    }
    resp = requests.get(ICV_WFS, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    gdf = gpd.read_file(io.BytesIO(resp.content))
    return gdf.set_crs(ICV_CRS, allow_override=True)


def emsr935_classes(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep the meaningful EMSR935 fields: AOI, class and detection method."""
    aoi = gdf["layer"].astype(str).str.extract(r"(AOI\d+)", expand=False)
    out = gpd.GeoDataFrame(
        {
            "aoi": aoi,
            "class": gdf["notation"].astype(str).str.strip().str.lower().str.replace(" ", "_"),
            "det_method": gdf["det_method"],
            "source": "Copernicus EMS EMSR935, imagery 20 to 21 Oct 2026",
        },
        geometry=gdf.geometry,
        crs=gdf.crs,
    )
    return out


def emsr_aois(activation: dict) -> gpd.GeoDataFrame:
    """AOI polygons of one Copernicus EMS activation record (rapid mapping dashboard API)."""
    rows = []
    for a in activation.get("aois") or []:
        products = a.get("products")
        types = sorted({p.get("type") for p in products}) if isinstance(products, list) else []
        rows.append({
            "aoi": f"AOI{int(a['number']):02d}",
            "name": a["name"],
            "products": "+".join(t for t in types if t),
            "source": f"Copernicus EMS {activation.get('code')} areas of interest",
            "geometry": shapely.from_wkt(a["extent"]),
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def fetch_emsr935_aois() -> gpd.GeoDataFrame:
    """Where EMSR935 was mapped. Inside these areas every flooded pixel was outlined,
    so a pixel without an outline counts as not flooded when scoring a flood map."""
    resp = requests.get(RAPID_MAPPING_API, params={"code": "EMSR935"}, timeout=TIMEOUT_S)
    resp.raise_for_status()
    results = [r for r in resp.json().get("results", []) if r.get("code") == "EMSR935"]
    if len(results) != 1:
        raise RuntimeError(f"EMSR935 not found exactly once in the rapid mapping API (got {len(results)})")
    return emsr_aois(results[0])


def fetch_espada_burn() -> gpd.GeoDataFrame:
    """The EFFIS burnt-area polygon of the Serra d'Espadà fire."""
    params = {
        "country": "ES",
        "province": "Castellón/Castelló",
        "firedate__gte": "2026-07-24",
        "firedate__lte": "2026-07-27",
        "ordering": "-area_ha",
    }
    resp = requests.get(EFFIS_API, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    records = [r for r in resp.json().get("results", []) if str(r.get("id")) == ESPADA_EFFIS_ID]
    if len(records) != 1:
        raise RuntimeError(f"EFFIS record {ESPADA_EFFIS_ID} not found exactly once (got {len(records)})")
    rec = records[0]
    return gpd.GeoDataFrame(
        [{
            "effis_id": rec["id"],
            "firedate": rec["firedate"],
            "effis_area_ha": float(rec["area_ha"]),
            "province": rec["province"],
            "commune": rec["commune"],
            "lastupdate": rec["lastupdate"],
            "source": "EFFIS burnt areas (MODIS/Sentinel-2 based)",
        }],
        geometry=[shape(rec["shape"])],
        crs="EPSG:4326",
    )


def add_area_ha(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Area of each polygon in hectares, measured on the UTM 30N grid."""
    out = gdf.copy()
    if out.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        out["area_ha"] = (out.to_crs(AREA_CRS).area / 1e4).round(2)
    return out


def polygonal_part(geom: BaseGeometry) -> BaseGeometry | None:
    """Polygon or MultiPolygon part of a geometry (drops lines and points)."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [p for p in shapely.get_parts(geom) if p.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else None


def make_polygonal(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repair invalid polygons and keep only polygonal parts.

    The EMSR935 source has one self-intersecting polygon; make_valid turns it
    into a mixed collection, so we keep the polygon pieces only.
    """
    out = gdf.copy()
    out["geometry"] = [polygonal_part(g) for g in shapely.make_valid(out.geometry.values)]
    return out[out.geometry.notna()]


def simplify_m(gdf: gpd.GeoDataFrame, tolerance_m: float) -> gpd.GeoDataFrame:
    """Simplify outlines on the UTM grid, keeping topology.

    Our pixels are 20 m, so a tolerance of a few metres changes nothing the
    models can see but makes the files small enough for git.
    """
    out = gdf.to_crs(AREA_CRS)
    out["geometry"] = out.geometry.simplify(tolerance_m, preserve_topology=True)
    return out.to_crs(gdf.crs)


def to_wgs84_grid(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reproject to WGS84 and snap to the 1e-6 degree grid without breaking polygons.

    Writing with 6 decimals alone can collapse slivers into lines; snapping
    first with GEOS's validity-preserving precision reducer avoids that.
    """
    out = clean_text(gdf).to_crs("EPSG:4326")
    out["geometry"] = [_snap(g) for g in out.geometry.values]
    if out.geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"]).all():
        out = make_polygonal(out)
    return out


def _snap(geom: BaseGeometry | None) -> BaseGeometry | None:
    """Repair, then snap one geometry to the grid; keep it repaired if snapping fails."""
    if geom is None:
        return None
    valid = shapely.make_valid(geom)
    try:
        return shapely.set_precision(valid, COORD_GRID_DEG)
    except shapely.errors.GEOSException:
        return valid


def save(gdf: gpd.GeoDataFrame, name: str) -> None:
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    path = LABELS_DIR / f"{name}.geojson"
    final = to_wgs84_grid(gdf)
    final.to_file(path, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": "6", "RFC7946": "YES"})
    total = f", {final['area_ha'].sum():,.1f} ha" if "area_ha" in final else ""
    print(f"{name}: {len(final)} features{total} -> data/labels/{path.name}")


def main() -> None:
    # 2 m simplification (a tenth of a pixel): the raw file is 11 MB of vertices.
    flood = emsr935_classes(fetch_wfs_layer("ms:CEMS.AreaInundada"))
    flood = add_area_ha(make_polygonal(simplify_m(flood, 2.0)))
    save(flood, "pego_oliva_emsr935_flood")
    save(add_area_ha(make_polygonal(fetch_emsr935_aois())), "pego_oliva_emsr935_aoi")

    footprint = fetch_wfs_layer("ms:ZonasInundadas.HuellaInundacion")
    footprint = footprint.rename(columns={"Descripcion": "description", "Area_ha": "official_area_ha"})
    footprint = add_area_ha(make_polygonal(footprint))
    save(footprint[["description", "official_area_ha", "area_ha", "geometry"]], "pego_oliva_generalitat_footprint")

    depth = fetch_wfs_layer("ms:ZonasInundadas.AlturaAgua.SGRT")
    keep = [c for c in ("Cuenca", "AlturaAguam", "AltRangocm", "FuenteDatos") if c in depth.columns]
    save(depth[keep + ["geometry"]], "pego_oliva_water_depth_points")

    save(add_area_ha(make_polygonal(fetch_espada_burn())), "espada_effis_burnt_area")


if __name__ == "__main__":
    main()
