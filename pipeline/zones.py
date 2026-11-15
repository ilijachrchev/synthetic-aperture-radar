"""Official flood zones against where the water really went (the app's "before" screen).

Two DANAs, never mixed:

- 29 Oct 2024, L'Horta Sud and Chiva (Paiporta, Massanassa, Sedaví, Catarroja,
  Alfafar, Benetússer, Picanya, Aldaia, Chiva, Torrent). Before NISAR had any
  data: context only. Observed flood: Copernicus EMS EMSR773.
- DANA "Adam", 18 to 19 Oct 2026, Pego and Oliva. NISAR saw it. Observed flood:
  Copernicus EMS EMSR935 (data/labels/, built by pipeline.labels).

Official zones: the Spanish national flood zone map (SNCZI, MITECO), fluvial
T10, T100 and T500 and marine T100 and T500, read from MITECO's WFS. Every
flooded spot gets the most frequent zone it lies in: frequent (T10),
occasional (T100), rare (T500 only) or none (outside every zone).

Municipality boundaries: IGN, INSPIRE administrative units (CC BY 4.0).

Steps:
    python -m pipeline.zones fetch     # downloads into data/interim/flood-zones/ (not in git)
    python -m pipeline.zones compute   # data/zones/zones_vs_floods.json and the web layers
    python -m pipeline.zones report    # the tables of docs/ZONES.md, printed from the JSON
    python -m pipeline.zones           # fetch and compute

Outputs in data/zones/ (small, in git): zones_vs_floods.json (every number with
its source and retrieval date), municipalities.geojson, zones_<area>.geojson
(official zones clipped to the municipalities) and floods_<event>.geojson
(observed flood split by municipality, zone class and observed class). Areas
are measured on exact geometries in UTM 30N; the web layers are simplified
for display only.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
import shapely
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from pipeline.config import DATA_DIR, LABELS_DIR
from pipeline.labels import clean_text, polygonal_part

INTERIM_DIR = DATA_DIR / "interim" / "flood-zones"
ZONES_DIR = DATA_DIR / "zones"
AREA_CRS = "EPSG:32630"     # UTM 30N, as in pipeline.labels: every area we report
SERVICE_CRS = "EPSG:25830"  # ETRS89 / UTM 30N, native CRS of SNCZI and IGN
GRID_M = 0.01               # overlay precision in metres: robust unions, no area change
TIMEOUT_S = 300

IGN_WFS = "https://www.ign.es/wfs-inspire/unidades-administrativas"
MITECO_WFS = "https://gis.miteco.gob.es/geoserver/{workspace}/wfs"
EMS_API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"

SI_LINE = "Written with SI assistance (Claude Code), reviewed by the team."

# Mutually exclusive classes, most frequent first. "none" = outside every zone.
CLASSES = ("frequent", "occasional", "rare", "none")
CLASS_TITLES = {
    "frequent": "frequent: T10 zone (high probability, 1 in 10 each year)",
    "occasional": "occasional: T100 zone, not T10 (medium probability, 1 in 100 each year)",
    "rare": "rare: only the T500 zone (low probability, 1 in 500 each year)",
    "none": "outside every official zone",
}
OBSERVED = ("flooded_area", "flood_trace")
NOTATION = {"Flooded area": "flooded_area", "Flood trace": "flood_trace"}

EN_DASH, EM_DASH = chr(0x2013), chr(0x2014)


@dataclass(frozen=True)
class ZoneLayer:
    key: str
    workspace: str
    layer: str
    origin: str  # fluvial or marine
    return_period: int
    title: str
    metadata: str  # MITECO open data catalogue record


ZONE_LAYERS = (
    ZoneLayer("fluvial_t10", "agua", "Zi_laminas_q10", "fluvial", 10,
              "Z.I. con alta probabilidad (T=10 años) de origen fluvial",
              "https://catalogo.datosabiertos.miteco.gob.es/catalogo#/metadata/813bd9ed-a458-438e-af96-b9cbca568007"),
    ZoneLayer("fluvial_t100", "agua", "Zi_laminas_q100", "fluvial", 100,
              "Z.I. con probabilidad media u ocasional (T=100 años) de origen fluvial",
              "https://catalogo.datosabiertos.miteco.gob.es/catalogo#/metadata/cc381566-d971-4dea-9938-84ad8c0d3ff3"),
    ZoneLayer("fluvial_t500", "agua", "Zi_laminas_q500", "fluvial", 500,
              "Z.I. con probabilidad baja o excepcional (T=500 años) de origen fluvial",
              "https://catalogo.datosabiertos.miteco.gob.es/catalogo#/metadata/b3c330f1-ef8d-4e62-a940-1040083dabff"),
    ZoneLayer("marine_t100", "costas", "zim_laminas_q100", "marine", 100,
              "Z.I. con probabilidad media u ocasional (T=100 años) de origen marino", ""),
    ZoneLayer("marine_t500", "costas", "zim_laminas_q500", "marine", 500,
              "Z.I. con probabilidad baja o excepcional (T=500 años) de origen marino", ""),
)


@dataclass(frozen=True)
class Municipality:
    name: str
    ine: str  # INE municipality code; the first two digits are the province

    @property
    def ign_id(self) -> str:
        """IGN INSPIRE id: country 34, region 10 (Comunitat Valenciana), province, INE code."""
        return f"AU_ADMINISTRATIVEUNIT_3410{self.ine[:2]}{self.ine}"


@dataclass(frozen=True)
class EmsProduct:
    """One Copernicus EMS rapid mapping product (vector package)."""

    activation: str
    aoi: int
    aoi_name: str
    kind: str  # DEL (delineation) or GRA (grading)
    version: int
    imagery: str

    @property
    def stem(self) -> str:
        return f"{self.activation}_AOI{self.aoi:02d}_{self.kind}_PRODUCT"

    @property
    def zip_name(self) -> str:
        return f"{self.stem}_v{self.version}.zip"

    @property
    def credit(self) -> str:
        year = 2024 if self.activation == "EMSR773" else 2026
        kind = {"DEL": "Delineation Map", "GRA": "Grading Map"}[self.kind]
        return (f"Copernicus Emergency Management Service (© {year} European Union), "
                f"[{self.activation}] {self.aoi_name} (AOI{self.aoi:02d}): {kind}")


@dataclass(frozen=True)
class Event:
    key: str
    area: str
    title: str
    nisar: str
    municipalities: tuple[Municipality, ...]


HORTA_SUD = (
    Municipality("Paiporta", "46186"), Municipality("Massanassa", "46165"),
    Municipality("Sedaví", "46223"), Municipality("Catarroja", "46094"),
    Municipality("Alfafar", "46022"), Municipality("Benetússer", "46054"),
    Municipality("Picanya", "46193"), Municipality("Aldaia", "46021"),
    Municipality("Chiva", "46111"), Municipality("Torrent", "46244"),
)
PEGO_OLIVA = (Municipality("Pego", "03102"), Municipality("Oliva", "46181"))

EVENTS = (
    Event("dana_2024_horta_sud", "horta_sud", "DANA of 29 Oct 2024, L'Horta Sud and Chiva",
          "Before NISAR had any data (first public NISAR data 20 Jul 2026): context only, never a NISAR result.",
          HORTA_SUD),
    Event("dana_adam_2026_pego_oliva", "pego_oliva", "DANA Adam, 18 to 19 Oct 2026, Pego and Oliva",
          "NISAR saw this event (see pipeline/cv/evaluate.py, flood_vs_emsr935).", PEGO_OLIVA),
)

# EMSR773 products that map L'Horta Sud and Chiva in the first days. Priority order:
# a spot is decided by the first product that analysed it (sharpest imagery first;
# the grading product v2 corrects the first delineation, which missed flood traces).
# Later products (monitoring from 3 Nov, gradings from 11 Nov aerial and Pleiades
# imagery) are not used: they show receding water, not where the water went.
EMSR773_PRODUCTS = (
    EmsProduct("EMSR773", 3, "Horta Sud", "GRA", 2,
               "GeoEye-1, 31 Oct 2024 10:22 UTC; version 2: correction of the observed event, "
               "not all flood traces were delineated in version 1"),
    EmsProduct("EMSR773", 3, "Horta Sud", "DEL", 1, "WorldView-2 and GeoEye-1, 31 Oct 2024 10:22 UTC"),
    EmsProduct("EMSR773", 1, "Valencia province", "DEL", 1,
               "Landsat-8 30 Oct 2024 10:37 UTC, Sentinel-2 31 Oct 10:51 UTC, Sentinel-1 31 Oct 18:02 UTC"),
)

EMSR935_FLOOD = LABELS_DIR / "pego_oliva_emsr935_flood.geojson"
EMSR935_AOI = LABELS_DIR / "pego_oliva_emsr935_aoi.geojson"
GENERALITAT_FOOTPRINT = LABELS_DIR / "pego_oliva_generalitat_footprint.geojson"

SOURCES_STATIC = {
    "snczi": {
        "name": "Sistema Nacional de Cartografía de Zonas Inundables (SNCZI), zonas inundables asociadas a periodos de retorno",
        "publisher": "Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO)",
        "download_page": "https://www.miteco.gob.es/en/cartografia-y-sig/ide/descargas/agua/zi-lamina.html",
        "data_updated": "2026-06-01 (date listed for every layer on the download page, read 2026-11-15)",
        "service_sheets": "https://gis.miteco.gob.es/descargas/info/ZI_T10.pdf, ZI_T100.pdf, ZI_T500.pdf",
        "licence": "Free use, crediting the ministry as author and owner (MITECO download page)",
        "credit": "© Ministerio para la Transición Ecológica y el Reto Demográfico",
    },
    "ign": {
        "name": "Unidades administrativas (INSPIRE AU), municipios",
        "publisher": "Instituto Geográfico Nacional (IGN), Base de Datos de Delimitaciones Territoriales",
        "service": IGN_WFS,
        "licence": "CC BY 4.0 (WFS capabilities: AccessConstraints 'CC BY 4.0 ign.es')",
        "credit": "© Instituto Geográfico Nacional, CC BY 4.0 ign.es",
    },
    "copernicus_ems": {
        "citation_guidelines": "https://mapping.emergency.copernicus.eu/about/citation-guidelines/",
        "terms": "https://mapping.emergency.copernicus.eu/terms-and-conditions/",
    },
}


# ---------------------------------------------------------------- fetch


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(manifest: dict, key: str, url: str, params: dict | None, data: bytes, path: Path) -> None:
    manifest[key] = {
        "url": url, "params": params or {}, "file": path.relative_to(DATA_DIR.parent).as_posix(),
        "bytes": len(data), "sha256": _sha256(data),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _get(url: str, params: dict | None = None) -> bytes:
    resp = requests.get(url, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return resp.content


def fetch_municipalities(manifest: dict) -> None:
    """IGN municipality polygons by INSPIRE id (small requests; a bbox request also returns
    the province and region polygons and times out)."""
    for event in EVENTS:
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": "au:AdministrativeUnit", "outputFormat": "application/geo+json",
            "resourceId": ",".join(m.ign_id for m in event.municipalities),
        }
        data = _get(IGN_WFS, params)
        found = {f["id"] for f in json.loads(data)["features"]}
        missing = [m.name for m in event.municipalities if m.ign_id not in found]
        if missing:
            raise RuntimeError(f"IGN returned no polygon for {missing}")
        path = INTERIM_DIR / f"ign_{event.area}.geojson"
        path.write_bytes(data)
        _record(manifest, f"ign_{event.area}", IGN_WFS, params, data, path)
        print(f"IGN {event.area}: {len(found)} municipalities")


def study_bbox(event: Event, buffer_m: float = 1000.0) -> tuple[float, float, float, float]:
    """Bounding box of the event's municipalities in EPSG:25830, with a margin."""
    munis = load_municipalities(event).to_crs(SERVICE_CRS)
    w, s, e, n = munis.total_bounds
    return w - buffer_m, s - buffer_m, e + buffer_m, n + buffer_m


def fetch_zones(manifest: dict) -> None:
    for event in EVENTS:
        w, s, e, n = study_bbox(event)
        for layer in ZONE_LAYERS:
            url = MITECO_WFS.format(workspace=layer.workspace)
            params = {
                "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeNames": f"{layer.workspace}:{layer.layer}", "outputFormat": "application/json",
                "srsName": SERVICE_CRS, "bbox": f"{w:.0f},{s:.0f},{e:.0f},{n:.0f},{SERVICE_CRS}",
            }
            data = _get(url, params)
            doc = json.loads(data)
            matched = doc.get("numberMatched", doc.get("totalFeatures"))
            if matched is not None and int(matched) != len(doc["features"]):
                raise RuntimeError(f"{layer.layer}: {len(doc['features'])} of {matched} features returned")
            path = INTERIM_DIR / f"snczi_{event.area}_{layer.key}.geojson"
            path.write_bytes(data)
            _record(manifest, f"snczi_{event.area}_{layer.key}", url, params, data, path)
            print(f"SNCZI {event.area} {layer.key}: {len(doc['features'])} features")


def fetch_emsr773(manifest: dict) -> None:
    """The EMSR773 activation record and the vector packages of the products we use."""
    params = {"code": "EMSR773"}
    data = _get(EMS_API, params)
    results = [r for r in json.loads(data).get("results", []) if r.get("code") == "EMSR773"]
    if len(results) != 1:
        raise RuntimeError(f"EMSR773 not found exactly once in the rapid mapping API (got {len(results)})")
    path = INTERIM_DIR / "emsr773_activation.json"
    path.write_bytes(data)
    _record(manifest, "emsr773_activation", EMS_API, params, data, path)

    raw = INTERIM_DIR / "raw" / "emsr773"
    raw.mkdir(parents=True, exist_ok=True)
    for prod in EMSR773_PRODUCTS:
        url = product_record(results[0], prod)["downloadPath"]
        data = _get(url)
        path = raw / prod.zip_name
        path.write_bytes(data)
        _record(manifest, f"emsr773_{prod.stem}_v{prod.version}", url, None, data, path)
        print(f"{prod.zip_name}: {len(data) / 1e6:.1f} MB")


def product_record(activation: dict, prod: EmsProduct) -> dict:
    """The API record of one product: first (not monitoring) product of this AOI, kind and version."""
    for aoi in activation["aois"]:
        if int(aoi["number"]) != prod.aoi:
            continue
        for p in aoi["products"]:
            if (p["type"] == prod.kind and not p.get("monitoring")
                    and int(p["version"]["number"]) == prod.version and p["version"]["statusCode"] == "F"):
                return p
    raise RuntimeError(f"{prod.stem} v{prod.version} not found as a finished product")


def fetch() -> None:
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = INTERIM_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    fetch_municipalities(manifest)
    fetch_zones(manifest)
    fetch_emsr773(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- geometry

EMPTY = shapely.Polygon()


def polygonal(geom: BaseGeometry | None) -> BaseGeometry:
    part = polygonal_part(geom)
    return part if part is not None else EMPTY


def _overlay(fn, *args):
    """A GEOS overlay; on a topology error the same overlay snapped to the 1 cm grid."""
    try:
        return fn(*args)
    except shapely.errors.GEOSException:
        return fn(*args, grid_size=GRID_M)


def clean(geom: BaseGeometry | None, bounds: tuple[float, float, float, float] | None = None) -> BaseGeometry:
    """Valid polygonal part of a source geometry, cut to a box first when given (fast).

    The SNCZI T500 zones of L'Horta Sud alone have 1.5 million vertices, most far
    outside the municipalities, so everything is cut to the study box before any overlay.
    """
    if geom is None or geom.is_empty:
        return EMPTY
    if not geom.is_valid:
        geom = polygonal(shapely.make_valid(geom))
    if bounds is not None:
        geom = shapely.clip_by_rect(geom, *bounds)
        if not geom.is_valid:
            geom = shapely.make_valid(geom)
    return polygonal(geom)


def union(geoms) -> BaseGeometry:
    """Union of polygons; an empty polygon when there is nothing."""
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return EMPTY
    if len(geoms) == 1:
        return geoms[0]
    return polygonal(_overlay(shapely.union_all, geoms))


def inter(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    if a.is_empty or b.is_empty:
        return EMPTY
    return polygonal(_overlay(shapely.intersection, a, b))


def diff(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    if a.is_empty or b.is_empty:
        return a
    return polygonal(_overlay(shapely.difference, a, b))


def ha(geom: BaseGeometry) -> float:
    """Area in hectares; the geometry must be in AREA_CRS (metres)."""
    return float(geom.area) / 1e4


def zone_classes(t10: BaseGeometry, t100: BaseGeometry, t500: BaseGeometry,
                 clip: BaseGeometry) -> dict[str, BaseGeometry]:
    """Split `clip` into the four exclusive classes: the most frequent zone wins.

    The official zones are not always nested (a T500 study may not cover a T100
    study's area), so each class is taken against the union of the more frequent ones.
    """
    c10 = inter(t10, clip)
    c100 = inter(union([t10, t100]), clip)
    c500 = inter(union([t10, t100, t500]), clip)
    return {"frequent": c10, "occasional": diff(c100, c10), "rare": diff(c500, c100), "none": diff(clip, c500)}


def split_by_class(flood: BaseGeometry, classes: dict[str, BaseGeometry]) -> dict[str, BaseGeometry]:
    """The flood cut into the zone classes (done once for the whole study area)."""
    return {z: inter(flood, classes[z]) for z in CLASSES}


def ha_inside(geom: BaseGeometry, where: BaseGeometry) -> float:
    """Hectares of `geom` inside `where`, without one big overlay.

    Parts wholly inside count as they are; only parts that cross the border are
    intersected. Same result as ha(inter(geom, where)), many times faster on a
    flood of thousands of parts.
    """
    if geom.is_empty or where.is_empty:
        return 0.0
    parts = shapely.get_parts(geom)
    shapely.prepare(where)
    inside = shapely.contains_properly(where, parts)
    crossing = ~inside & shapely.intersects(where, parts)
    area = float(shapely.area(parts[inside]).sum())
    if crossing.any():
        cut = [_overlay(shapely.intersection, p, where) for p in parts[crossing]]
        area += float(sum(polygonal(c).area for c in cut))
    return area / 1e4


def tally(pieces: dict[str, BaseGeometry], where: BaseGeometry | None = None) -> dict[str, float]:
    """Hectares per class, optionally only inside `where` (a municipality)."""
    return {z: ha(g) if where is None else ha_inside(g, where) for z, g in pieces.items()}


def shares(by_class: dict[str, float]) -> dict:
    """Flooded hectares and the shares the app shows, in percent with one decimal."""
    total = sum(by_class.values())
    out = {"flooded_ha": round(total, 1), "ha_by_class": {k: round(v, 1) for k, v in by_class.items()}}
    if total <= 0:
        return {**out, "outside_every_zone_pct": None, "only_rare_t500_pct": None,
                "frequent_or_occasional_pct": None, "frequent_t10_pct": None}
    pct = {k: 100.0 * v / total for k, v in by_class.items()}
    return {
        **out,
        "outside_every_zone_pct": round(pct["none"], 1),
        "only_rare_t500_pct": round(pct["rare"], 1),
        "frequent_or_occasional_pct": round(pct["frequent"] + pct["occasional"], 1),
        "frequent_t10_pct": round(pct["frequent"], 1),
    }


def key_shares(block: dict) -> dict:
    return {k: block[k] for k in ("flooded_ha", "outside_every_zone_pct", "only_rare_t500_pct",
                                  "frequent_or_occasional_pct")}


def union_flood(products: list[tuple[str, BaseGeometry, dict[str, BaseGeometry]]],
                clip: BaseGeometry) -> dict[str, BaseGeometry]:
    """Maximum observed extent: a spot is flooded if any product saw water or a flood trace there.

    Where one product saw water and another only a trace, it counts as water.
    """
    flood = {c: union(inter(o.get(c, EMPTY), clip) for _, _, o in products) for c in OBSERVED}
    flood["flood_trace"] = diff(flood["flood_trace"], flood["flooded_area"])
    return flood


def mosaic(products: list[tuple[str, BaseGeometry, dict[str, BaseGeometry]]],
           clip: BaseGeometry) -> tuple[dict[str, BaseGeometry], dict[str, BaseGeometry]]:
    """Priority mosaic of several mapped products.

    products: (name, analysed area, {observed class: geometry}) in priority order.
    Each spot is decided by the first product that analysed it. Returns the
    observed geometry per class and the region each product decided.
    """
    covered = EMPTY
    pieces = {c: [] for c in OBSERVED}
    regions = {}
    for name, analysed, observed in products:
        region = diff(inter(analysed, clip), covered)
        regions[name] = region
        for c in OBSERVED:
            pieces[c].append(inter(observed.get(c, EMPTY), region))
        covered = union([covered, region])
    flood = {c: union(pieces[c]) for c in OBSERVED}
    # Inside one product the two classes do not overlap; keep it so if a source ever does.
    flood["flood_trace"] = diff(flood["flood_trace"], flood["flooded_area"])
    return flood, regions


# ---------------------------------------------------------------- loading


def load_municipalities(event: Event) -> gpd.GeoDataFrame:
    """The event's municipalities in AREA_CRS, in the order of Event.municipalities.

    The IGN names are checked against ours, so a wrong INE code cannot slip through.
    """
    doc = json.loads((INTERIM_DIR / f"ign_{event.area}.geojson").read_text(encoding="utf-8"))
    feats = {f["id"]: f for f in doc["features"]}
    rows = []
    for m in event.municipalities:
        f = feats[m.ign_id]
        ign_name = f["properties"]["name"]["GeographicalName"]["spelling"]["SpellingOfName"]["text"]
        if m.name.casefold() not in [n.strip().casefold() for n in ign_name.split("/")]:
            raise RuntimeError(f"INE {m.ine}: IGN calls it {ign_name!r}, expected {m.name!r}")
        rows.append({"name": m.name, "ine": m.ine, "ign_name": ign_name, "geometry": shape(f["geometry"])})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4258")  # the service's default CRS
    gdf = gdf.to_crs(AREA_CRS)
    return gdf.assign(geometry=[clean(g) for g in gdf.geometry]).reset_index(drop=True)


def load_zone_layer(event: Event, layer: ZoneLayer, bounds) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(INTERIM_DIR / f"snczi_{event.area}_{layer.key}.geojson")
    if gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs=AREA_CRS)
    if gdf.crs is None:
        gdf = gdf.set_crs(SERVICE_CRS)
    keep = [c for c in ("id_zona", "zona", "tipo_zona", "rio", "estudio", "fecha_apro", "fecha",
                        "organismo", "zi_directiva", "zi_directi", "demarcacio") if c in gdf.columns]
    gdf = gdf[keep + ["geometry"]].to_crs(AREA_CRS)
    gdf = gdf.assign(geometry=[clean(g, bounds) for g in gdf.geometry])
    return gdf[~gdf.geometry.is_empty]


def ems_layer(zip_path: Path, prod: EmsProduct, layer: str, bounds=None) -> gpd.GeoDataFrame:
    shp = f"{prod.stem}_{layer}_v{prod.version}.shp"
    gdf = gpd.read_file(f"/vsizip/{zip_path.as_posix()}/{shp}").to_crs(AREA_CRS)
    return gdf.assign(geometry=[clean(g, bounds) for g in gdf.geometry])


def ems_observed(gdf: gpd.GeoDataFrame) -> dict[str, BaseGeometry]:
    unknown = set(gdf["notation"]) - set(NOTATION)
    if unknown:
        raise RuntimeError(f"unexpected observed-event classes: {sorted(unknown)}")
    cls = gdf["notation"].map(NOTATION)
    return {c: union(gdf.geometry[cls == c]) for c in OBSERVED}


def ems_analysed(zip_path: Path, prod: EmsProduct, bounds=None) -> BaseGeometry:
    """Where a product looked: its AOI inside the image footprints, minus 'Not Analysed' parts."""
    aoi = union(ems_layer(zip_path, prod, "areaOfInterestA", bounds).geometry)
    fp = ems_layer(zip_path, prod, "imageFootprintA", bounds)
    kind = fp["obj_type"].astype(str)
    images = union(fp.geometry[kind == "Image Footprint"])
    not_analysed = union(fp.geometry[kind.str.startswith("Not Analysed")])
    return diff(inter(aoi, images), not_analysed)


def emsr773_products(bounds) -> list[tuple[str, BaseGeometry, dict[str, BaseGeometry]]]:
    raw = INTERIM_DIR / "raw" / "emsr773"
    out = []
    for prod in EMSR773_PRODUCTS:
        path = raw / prod.zip_name
        out.append((f"{prod.stem}_v{prod.version}", ems_analysed(path, prod, bounds),
                    ems_observed(ems_layer(path, prod, "observedEventA", bounds))))
    return out


def emsr935_product(bounds) -> list[tuple[str, BaseGeometry, dict[str, BaseGeometry]]]:
    flood = gpd.read_file(EMSR935_FLOOD).to_crs(AREA_CRS)
    aoi = gpd.read_file(EMSR935_AOI).to_crs(AREA_CRS)
    observed = {c: union(clean(g, bounds) for g in flood.geometry[flood["class"] == c]) for c in OBSERVED}
    return [("EMSR935_AOI01_AOI02 (data/labels)", union(clean(g, bounds) for g in aoi.geometry), observed)]


# ---------------------------------------------------------------- compute


@dataclass
class StudyArea:
    """One event's municipalities and official zones, ready for overlays."""

    event: Event
    munis: gpd.GeoDataFrame
    clip: BaseGeometry
    bounds: tuple[float, float, float, float]
    layers: dict[str, gpd.GeoDataFrame]
    classes: dict[str, BaseGeometry]
    classes_fluvial: dict[str, BaseGeometry]


def classes_from(layers: dict[str, gpd.GeoDataFrame], clip: BaseGeometry,
                 origins: tuple[str, ...] = ("fluvial", "marine")) -> dict[str, BaseGeometry]:
    by_rp: dict[int, list[BaseGeometry]] = {10: [], 100: [], 500: []}
    for layer in ZONE_LAYERS:
        if layer.origin in origins and layer.key in layers:
            by_rp[layer.return_period].extend(layers[layer.key].geometry)
    return zone_classes(union(by_rp[10]), union(by_rp[100]), union(by_rp[500]), clip)


def prepare(event: Event) -> StudyArea:
    munis = load_municipalities(event)
    clip = union(munis.geometry)
    w, s, e, n = clip.bounds
    bounds = (w - 10.0, s - 10.0, e + 10.0, n + 10.0)
    layers = {layer.key: load_zone_layer(event, layer, bounds) for layer in ZONE_LAYERS}
    return StudyArea(event, munis, clip, bounds, layers, classes_from(layers, clip),
                     classes_from(layers, clip, ("fluvial",)))


def zone_studies(area: StudyArea) -> list[dict]:
    """Which official studies the zones inside the study area come from."""
    rows = []
    for key, gdf in area.layers.items():
        for _, r in gdf.iterrows():
            inside = ha(inter(r.geometry, area.clip))
            if inside < 0.05:
                continue
            row = {"layer": key, "ha_in_study_area": round(inside, 1)}
            for col in ("id_zona", "zona", "tipo_zona", "rio", "estudio", "fecha_apro", "fecha",
                        "zi_directiva", "zi_directi"):
                if col in r and pd.notna(r[col]) and str(r[col]).strip():
                    value = r[col]
                    if isinstance(value, pd.Timestamp) or col in ("fecha_apro", "fecha"):
                        # Stored as UTC midnight of the previous day: report the local (Madrid) date.
                        try:
                            ts = pd.Timestamp(value)
                            ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
                            value = ts.tz_convert("Europe/Madrid").date().isoformat()
                        except (ValueError, TypeError):
                            pass
                    row[col] = no_dashes(str(value).strip())
            rows.append(row)
    return sorted(rows, key=lambda r: (r["layer"], -r["ha_in_study_area"]))


def event_numbers(area: StudyArea, flood: dict[str, BaseGeometry],
                  products) -> tuple[dict, dict[str, dict[str, BaseGeometry]]]:
    pieces = {c: split_by_class(flood[c], area.classes) for c in OBSERVED}
    zoned = union([area.classes[k] for k in ("frequent", "occasional", "rare")])
    looked = {name: inter(a, area.clip) for name, a, _ in products}
    seen = {name: inter(union(o.values()), area.clip) for name, _, o in products}
    analysed = union(looked.values())
    rows = []
    for _, m in area.munis.iterrows():
        mg = m.geometry
        by_obs = {c: tally(pieces[c], mg) for c in OBSERVED}
        row = {"name": m["name"], "ine": m["ine"], "municipality_ha": round(ha(mg), 1),
               "zone_cover_pct": round(100.0 * ha_inside(zoned, mg) / ha(mg), 1),
               "analysed_pct": round(100.0 * ha_inside(analysed, mg) / ha(mg), 1)}
        row.update(shares({z: by_obs["flooded_area"][z] + by_obs["flood_trace"][z] for z in CLASSES}))
        row["by_observed_class"] = {c: shares(by_obs[c]) for c in OBSERVED}
        row["analysed_by_product_pct"] = {n: round(100.0 * ha_inside(g, mg) / ha(mg), 1) for n, g in looked.items()}
        row["observed_by_product_ha"] = {n: round(ha_inside(g, mg), 1) for n, g in seen.items()}
        rows.append(row)
    by_obs = {c: tally(pieces[c]) for c in OBSERVED}
    total = shares({z: by_obs["flooded_area"][z] + by_obs["flood_trace"][z] for z in CLASSES})
    total["by_observed_class"] = {c: shares(by_obs[c]) for c in OBSERVED}
    total["sum_of_municipalities_ha"] = round(sum(r["flooded_ha"] for r in rows), 1)
    total["zone_cover_pct"] = round(100.0 * ha(zoned) / ha(area.clip), 1)
    return {"municipalities": rows, "total": total}, pieces


def variant(area: StudyArea, flood: BaseGeometry, what: str, classes: dict[str, BaseGeometry] | None = None) -> dict:
    pieces = split_by_class(inter(flood, area.clip), classes or area.classes)
    return {
        "what": what,
        "total": key_shares(shares(tally(pieces))),
        "municipalities": {m["name"]: key_shares(shares(tally(pieces, m.geometry))) for _, m in area.munis.iterrows()},
    }


def sensitivity_2024(area: StudyArea, products, flood: dict[str, BaseGeometry]) -> dict:
    """The same shares under other reasonable choices, so the verdicts do not hang on one."""
    sharp_first, _ = mosaic(products, area.clip)
    out = {"sharpest_map_first": variant(
        area, union(sharp_first.values()),
        "priority mosaic: each spot from the first product that analysed it (AOI03 grading v2, then AOI03 "
        "delineation v1, then AOI01 delineation v1); the lower bound, as the sharp maps may miss water in fields")}
    for name, _, observed in products:
        out[f"only_{name}"] = variant(area, union(observed.values()),
                                      f"only the product {name}, inside the area it analysed")
    out["flooded_area_only"] = variant(area, flood["flooded_area"],
                                       "headline extent, flooded area only (water still on the image, no traces)")
    out["flood_trace_only"] = variant(area, flood["flood_trace"],
                                      "headline extent, flood traces only (the water had gone; mostly streets)")
    out["fluvial_zones_only"] = variant(area, union(flood.values()),
                                        "headline extent, marine zones left out (SNCZI fluvial only)",
                                        area.classes_fluvial)
    return out


def label_points(points: gpd.GeoSeries, polygons: dict[str, BaseGeometry]) -> list[str | None]:
    """For each point, the key of the first polygon (in dict order) that holds it, else None."""
    label: list[str | None] = [None] * len(points)
    geoms = points.values
    for key, g in polygons.items():
        if g.is_empty:
            continue
        shapely.prepare(g)
        hit = shapely.intersects(g, geoms)
        for i in range(len(label)):
            if label[i] is None and hit[i]:
                label[i] = key
    return label


def zone_of_points(points: gpd.GeoSeries, classes: dict[str, BaseGeometry]) -> list[str | None]:
    """The zone class of each point; on a shared border the more frequent class wins."""
    return label_points(points, {z: classes[z] for z in CLASSES})


def graded_buildings(area: StudyArea) -> tuple[dict, gpd.GeoDataFrame]:
    """Buildings the EMSR773 Horta Sud grading map marked as affected, by zone class.

    Closer to "your street" than land area: the elDiario.es claims were about
    buildings. Only where the grading map looked (L'Horta Sud; 6 % of Chiva).
    """
    prod = EMSR773_PRODUCTS[0]
    path = INTERIM_DIR / "raw" / "emsr773" / prod.zip_name
    pts = gpd.read_file(f"/vsizip/{path.as_posix()}/{prod.stem}_builtUpP_v{prod.version}.shp").to_crs(AREA_CRS)
    muni = label_points(pts.geometry, dict(zip(area.munis["name"], area.munis.geometry)))
    pts = pts.assign(municipality=muni, zone=zone_of_points(pts.geometry, area.classes),
                     damage=pts["damage_gra"].astype(str))
    pts = pts[pts["municipality"].notna()]

    def block(df: pd.DataFrame) -> dict:
        n = len(df)
        by = {z: int((df["zone"] == z).sum()) for z in CLASSES}
        pct = (lambda k: round(100.0 * k / n, 1)) if n else (lambda k: None)
        return {"buildings": n, "by_class": by, "outside_every_zone_pct": pct(by["none"]),
                "only_rare_t500_pct": pct(by["rare"]), "frequent_or_occasional_pct": pct(by["frequent"] + by["occasional"]),
                "by_damage": {d: int(k) for d, k in df["damage"].value_counts().sort_index().items()}}

    out = {
        "source": f"{prod.stem}_v{prod.version} builtUpP: building points graded by photo-interpretation of "
                  "GeoEye-1 imagery of 31 Oct 2024 (Possibly damaged, Damaged, Destroyed)",
        "credit": prod.credit,
        "what": "buildings graded as affected, by the zone class of their point",
        "coverage": "only inside the grading map's area of interest: all of L'Horta Sud here, 6 % of Chiva",
        "total": block(pts),
        "municipalities": {m: block(pts[pts["municipality"] == m]) for m in area.munis["name"]},
    }
    web = gpd.GeoDataFrame({"municipality": pts["municipality"], "zone": pts["zone"], "damage": pts["damage"]},
                           geometry=pts.geometry, crs=AREA_CRS)
    return out, web


WORLDCOVER = DATA_DIR / "context" / "albufera_worldcover_2021_20m.tif"
WORLDCOVER_CLASSES = {10: "tree", 20: "shrub", 30: "grass", 40: "cropland", 50: "built", 60: "bare",
                      80: "water", 90: "wetland"}


def land_cover(area: StudyArea, flood: dict[str, BaseGeometry]) -> dict:
    """What the observed flood lay on (ESA WorldCover 2021), for towns wholly inside the Albufera 20 m grid.

    Separates standing water in the Albufera rice fields from water through the streets.
    """
    with rasterio.open(WORLDCOVER) as src:
        wc, transform = src.read(1), src.transform
        if src.crs.to_epsg() != 32630:
            raise RuntimeError(f"{WORLDCOVER.name} is not on EPSG:32630")
        grid = shapely.box(*src.bounds)
    out = {"source": "ESA WorldCover 2021 v200 (CC BY 4.0) on the Albufera 20 m grid, "
                     f"{WORLDCOVER.relative_to(DATA_DIR.parent).as_posix()} (pipeline.context); share of the "
                     "pixels whose centre lies in the observed flood", "municipalities": {}}
    for _, m in area.munis.iterrows():
        if not grid.contains(m.geometry):
            continue
        row = {}
        for c in OBSERVED:
            geom = inter(flood[c], m.geometry)
            if geom.is_empty:
                continue
            mask = rasterize([(geom, 1)], out_shape=wc.shape, transform=transform, fill=0, dtype="uint8").astype(bool)
            values, counts = np.unique(wc[mask], return_counts=True)
            if counts.sum() == 0:
                continue
            row[c] = {WORLDCOVER_CLASSES.get(int(v), f"class_{int(v)}"): round(100.0 * k / counts.sum(), 1)
                      for v, k in zip(values, counts) if 100.0 * k / counts.sum() >= 0.5}
        out["municipalities"][m["name"]] = row
    return out


def sensitivity_2026(area: StudyArea, flood: dict[str, BaseGeometry]) -> dict:
    fp = gpd.read_file(GENERALITAT_FOOTPRINT).to_crs(AREA_CRS)
    return {
        "generalitat_footprint": variant(
            area, union(clean(g, area.bounds) for g in fp.geometry),
            "official DANA Adam river-flood footprint of the Generalitat Valenciana (surveyed flood marks), "
            f"{GENERALITAT_FOOTPRINT.relative_to(DATA_DIR.parent).as_posix()}, instead of EMSR935"),
        "flooded_area_only": variant(area, flood["flooded_area"],
                                     "EMSR935 flooded area only (water still on the image, no traces)"),
        "flood_trace_only": variant(area, flood["flood_trace"],
                                    "EMSR935 flood traces only (the water had gone)"),
        "fluvial_zones_only": variant(area, union(flood.values()),
                                      "EMSR935, marine zones left out (SNCZI fluvial only)", area.classes_fluvial),
    }


def marine_overlap(area: StudyArea, flood: dict[str, BaseGeometry]) -> dict:
    observed = union(flood.values())
    return {layer.key: round(ha(inter(inter(union(area.layers[layer.key].geometry), area.clip), observed)), 1)
            for layer in ZONE_LAYERS if layer.origin == "marine"}


def other_emsr773_aois(activation: dict, clip: BaseGeometry) -> list[dict]:
    """EMSR773 areas of interest that touch the study area but whose products are not used."""
    used = {p.aoi for p in EMSR773_PRODUCTS}
    rows = []
    for aoi in activation["aois"]:
        n = int(aoi["number"])
        if n in used:
            continue
        geom = gpd.GeoSeries([shapely.from_wkt(aoi["extent"])], crs="EPSG:4326").to_crs(AREA_CRS).iloc[0]
        overlap = ha(inter(clean(geom), clip))
        if overlap > 0:
            rows.append({"aoi": f"AOI{n:02d}", "name": aoi["name"], "overlap_ha": round(overlap, 1),
                         "products": sorted({p["type"] for p in aoi["products"]}),
                         "first_image_utc": min((i["acquisitionTime"] for p in aoi["products"]
                                                 for i in p.get("images") or []), default=None)})
    return rows


def emsr773_sources(activation: dict) -> list[dict]:
    rows = []
    for prod in EMSR773_PRODUCTS:
        rec = product_record(activation, prod)
        rows.append({
            "product": f"{prod.stem}_v{prod.version}", "aoi": f"AOI{prod.aoi:02d} {prod.aoi_name}",
            "imagery": prod.imagery,
            "images_api": [f"{i['sensorName']} {i['acquisitionTime']}" for i in rec.get("images") or []],
            "delivered_utc": rec["version"]["deliveryTime"][:19],
            "download": rec["downloadPath"], "credit": prod.credit,
        })
    return rows


def observed_source(event: Event, activation773: dict, clip: BaseGeometry) -> dict:
    if event.key.startswith("dana_2024"):
        return {
            "activation": "EMSR773, Flood in Valencia Region, Spain (event 29 Oct 2024 14:30 UTC, "
                          "activated 29 Oct 2024 16:40 UTC)",
            "api": f"{EMS_API}?code=EMSR773",
            "products_in_priority_order": emsr773_sources(activation773),
            "other_aois_touching_the_area_not_used": other_emsr773_aois(activation773, clip),
        }
    return {
        "activation": "EMSR935, DANA Adam (imagery 20 to 21 Oct 2026)",
        "files": [EMSR935_FLOOD.relative_to(DATA_DIR.parent).as_posix(),
                  EMSR935_AOI.relative_to(DATA_DIR.parent).as_posix()],
        "built_by": "python -m pipeline.labels (Copernicus EMS EMSR935 as republished by the Institut "
                    "Cartogràfic Valencià, WFS https://terramapas.icv.gva.es/2702_DANAAdam2026; mapped "
                    "areas from the rapid mapping API)",
        "credit": "Copernicus Emergency Management Service (© 2026 European Union), [EMSR935] Moraira (AOI01): "
                  "Delineation Map; Gandia (AOI02): Grading Map",
    }


def compute() -> dict:
    manifest = json.loads((INTERIM_DIR / "manifest.json").read_text(encoding="utf-8"))
    activation773 = json.loads((INTERIM_DIR / "emsr773_activation.json").read_text(encoding="utf-8"))["results"][0]
    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": SI_LINE,
        "what": "Official flood zones (SNCZI) against the observed flood (Copernicus EMS) per municipality.",
        "method": method_text(),
        "classes": CLASS_TITLES,
        "events": {}, "sources": {},
    }
    web: dict[str, gpd.GeoDataFrame] = {}
    muni_frames = []
    for event in EVENTS:
        area = prepare(event)
        is_2024 = event.key.startswith("dana_2024")
        products = emsr773_products(area.bounds) if is_2024 else emsr935_product(area.bounds)
        flood = union_flood(products, area.clip)
        numbers, pieces = event_numbers(area, flood, products)
        result["events"][event.key] = {
            "title": event.title, "nisar": event.nisar,
            "observed_flood": "flooded area (water on the image) plus flood traces (water gone, mud and debris "
                              "left): where the water went. Maximum observed extent: a spot counts if any of the "
                              "products saw water or a trace there",
            "observed_source": observed_source(event, activation773, area.clip),
            "zones_in_study_area_ha": {k: round(ha(g), 1) for k, g in area.classes.items()},
            "marine_zones_overlap_with_observed_flood_ha": marine_overlap(area, flood),
            **numbers,
            "sensitivity": sensitivity_2024(area, products, flood) if is_2024 else sensitivity_2026(area, flood),
            "official_studies": zone_studies(area),
        }
        if is_2024:
            result["events"][event.key]["graded_buildings"], web["buildings_dana_2024_horta_sud"] = \
                graded_buildings(area)
            result["events"][event.key]["land_cover_of_observed_flood"] = land_cover(area, flood)
        result["sources"][f"municipalities_{event.area}"] = manifest[f"ign_{event.area}"]
        for layer in ZONE_LAYERS:
            result["sources"][f"snczi_{event.area}_{layer.key}"] = {
                "layer": f"{layer.workspace}:{layer.layer}", "title": layer.title,
                "metadata": layer.metadata, **manifest[f"snczi_{event.area}_{layer.key}"]}
        web[f"zones_{event.area}"] = web_zones(area.classes)
        web[f"floods_{event.key}"] = web_floods(pieces, area.munis)
        muni_frames.append(web_municipalities(area.munis, numbers, event))
        print(f"{event.key}: {numbers['total']['flooded_ha']} ha observed, "
              f"{numbers['total']['outside_every_zone_pct']} % outside every zone", flush=True)
    for prod in EMSR773_PRODUCTS:
        key = f"emsr773_{prod.stem}_v{prod.version}"
        result["sources"][key] = {**manifest[key], "credit": prod.credit}
    result["sources"]["emsr773_activation"] = manifest["emsr773_activation"]
    result["sources"].update(SOURCES_STATIC)
    result["claims"] = check_claims(result)
    result["timeline_2024"] = TIMELINE_2024
    web["municipalities"] = pd.concat(muni_frames, ignore_index=True)
    write_outputs(result, web)
    return result


# ---------------------------------------------------------------- claims and timeline

# Cited numbers that are not ours. Each one carries its source.
CAMARASA_2025 = {
    "citation": "Camarasa-Belmonte, A., Zornoza-Gallego, C., Sanchis-Ibor, C., Serrano-Lara, J.J. (2025). "
                "¿Cómo de efectiva es la cartografía de peligro de inundación para la gestión de la emergencia? "
                "Evaluación a partir del mapa de las inundaciones de Valencia de octubre de 2024. "
                "Ingeniería del Agua 29(4), 229-244",
    "doi": "https://doi.org/10.4995/ia.2025.24007",
    "pdf": "https://riunet.upv.es/bitstreams/81252377-dfac-44de-b2bf-35d52521b831/download",
    "retrieved": "2026-11-15",
    "numbers": "Table 1: 37,972.1 ha flooded in the Poyo-Poçalet-Saleta, Magro and Albufera ravine basins; "
               "5,353.5 ha (14.1 %) outside the hazard map MIPICOVA (PATRICOVA plus SNCZI, with the "
               "geomorphological level); Poyo-Poçalet-Saleta 20.5 %, Magro 20.8 %, Albufera ravines 5.4 %",
    "outside_pct": 14.1,
}
ELDIARIO_2025 = {
    "citation": "Miguel Giménez, 'El riesgo de inundación en los municipios de la zona cero de la DANA en "
                "Valencia era muy bajo', elDiario.es, 8 Jan 2025",
    "url": "https://www.eldiario.es/comunitat-valenciana/riesgo-inundacion-municipios-zona-cero-dana-valencia_1_11945779.html",
    "retrieved": "2026-11-15",
    "numbers": "Dwellings (Catastro) in SNCZI zones, not flooded area: Massanassa 100 % of buildings in the "
               "500-year zone and 0.1 % in the 100-year zone; Paiporta about 3,500 dwellings in the 500-year "
               "zone and 3 in the 100-year zone; Sedaví with no risk in the 500-year map",
}


def check_claims(result: dict) -> list[dict]:
    """Each claim of discussion #29 against our numbers, with the threshold used and what to say instead."""
    ev = result["events"]["dana_2024_horta_sud"]
    by = {m["name"]: m for m in ev["municipalities"]}
    tot = ev["total"]
    low = ev["sensitivity"]["sharpest_map_first"]
    trace = ev["sensitivity"]["flood_trace_only"]
    bld = ev["graded_buildings"]
    src_total = "data/zones/zones_vs_floods.json events.dana_2024_horta_sud"

    def verdict(ok: bool, partly: bool = False) -> str:
        return "holds" if ok else ("partly holds" if partly else "does not hold")

    out = []
    head, lower = tot["outside_every_zone_pct"], low["total"]["outside_every_zone_pct"]
    out.append({
        "claim": "the 2024 DANA flooded 14 % outside every zone",
        "our_number": f"SNCZI, 10 municipalities: {head} % of the observed flood outside every zone "
                      f"({tot['ha_by_class']['none']} of {tot['flooded_ha']} ha); {lower} % with the sharpest map "
                      f"first ({low['total']['flooded_ha']} ha); {trace['total']['outside_every_zone_pct']} % of the "
                      f"flood traces (streets); {bld['total']['outside_every_zone_pct']} % of the "
                      f"{bld['total']['buildings']} graded buildings",
        "cited_number": f"{CAMARASA_2025['outside_pct']} % outside MIPICOVA (PATRICOVA plus SNCZI) in three whole "
                        "basins (Camarasa-Belmonte et al. 2025)",
        "threshold": "holds if our numbers are within 3 points of 14 %",
        "verdict": verdict(abs(head - 14.1) <= 3 and abs(lower - 14.1) <= 3),
        "say": f"With the national flood map (SNCZI), {lower:.0f} to {head:.0f} % of the land the 2024 DANA flooded in "
               "these 10 towns was outside every official flood zone. The 14 % figure is real but belongs to a "
               "different map and area: 14.1 % of the area flooded in the Poyo, Magro and Albufera ravine basins "
               "was outside the Valencian integrated hazard map MIPICOVA (Camarasa-Belmonte et al. 2025).",
        "sources": [CAMARASA_2025, f"{src_total}.total, .sensitivity, .graded_buildings"],
    })
    lc = ev.get("land_cover_of_observed_flood", {}).get("municipalities", {})
    rows, towns_ok = [], {}
    for n in ("Paiporta", "Massanassa"):
        land, b = by[n], bld["municipalities"][n]
        rows.append(f"{n}: land {land['only_rare_t500_pct']} % only rare, {land['outside_every_zone_pct']} % outside "
                    f"every zone, {land['frequent_or_occasional_pct']} % frequent or occasional; flood traces "
                    f"{land['by_observed_class']['flood_trace']['only_rare_t500_pct']} % only rare; graded buildings "
                    f"{b['only_rare_t500_pct']} % only rare, {b['outside_every_zone_pct']} % outside (of {b['buildings']})")
        towns_ok[n] = (b["only_rare_t500_pct"] or 0) >= 90
    pai, mas, bp, bm = by["Paiporta"], by["Massanassa"], bld["municipalities"]["Paiporta"], bld["municipalities"]["Massanassa"]
    mas_fa = mas["by_observed_class"]["flooded_area"]
    mas_lc = lc.get("Massanassa", {}).get("flooded_area", {})
    out.append({
        "claim": "Paiporta and Massanassa were almost all rare",
        "our_number": "; ".join(rows),
        "threshold": "almost all = at least 90 % of the graded (affected) buildings only in the rare (T500) zone; "
                     "the elDiario.es source of the claim counted buildings",
        "verdict": verdict(all(towns_ok.values()), partly=any(towns_ok.values())),
        "say": f"Massanassa, yes: {bm['only_rare_t500_pct']:.0f} % of its affected buildings were in the rare zone. "
               f"Paiporta, no: {bp['only_rare_t500_pct']:.0f} % of its affected buildings were in the rare zone and "
               f"{bp['outside_every_zone_pct']:.0f} % outside every zone; of its flooded land "
               f"{pai['only_rare_t500_pct']:.0f} % was rare and {pai['outside_every_zone_pct']:.0f} % outside. "
               f"Massanassa's standing water ({mas_fa['flooded_ha']:.0f} ha, "
               f"{mas_fa['frequent_or_occasional_pct']:.0f} % in the frequent or occasional zones) lay on cropland "
               f"and wetland of the Albufera ({mas_lc.get('cropland', 0):.0f} % and {mas_lc.get('wetland', 0):.0f} % "
               "in ESA WorldCover), not in the town.",
        "sources": [ELDIARIO_2025, f"{src_total}.municipalities, .graded_buildings, .land_cover_of_observed_flood"],
    })
    sed, sb = by["Sedaví"], bld["municipalities"]["Sedaví"]
    sed_trace = sed["by_observed_class"]["flood_trace"]["outside_every_zone_pct"]
    out.append({
        "claim": "Sedaví in none (no official zone)",
        "our_number": f"Sedaví: {sed['outside_every_zone_pct']} % of its flooded land outside every zone "
                      f"({sed_trace} % of its flood traces), {sb['outside_every_zone_pct']} % of its {sb['buildings']} "
                      f"graded buildings; official zones cover {sed['zone_cover_pct']} % of the municipality",
        "threshold": "holds if at least 95 % of the affected buildings and of the flood traces were outside every "
                     "zone; partly if at least 80 %",
        "verdict": verdict(min(sb["outside_every_zone_pct"] or 0, sed_trace or 0) >= 95,
                           partly=min(sb["outside_every_zone_pct"] or 0, sed_trace or 0) >= 80),
        "say": f"Sedaví: {sb['outside_every_zone_pct']:.1f} % of its affected buildings and "
               f"{sed['outside_every_zone_pct']:.0f} % of the land that flooded were outside every official flood "
               f"zone (zones cover only {sed['zone_cover_pct']:.0f} % of the town's area, so not literally none).",
        "sources": [ELDIARIO_2025, f"{src_total}.municipalities, .graded_buildings"],
    })
    out += [
        {"claim": "red warning 07:30", "verdict": "holds with other wording",
         "say": "07:36, first AEMET red warning of the day, for the Litoral sur de Valencia zone. The zone of "
                "L'Horta Sud and Chiva (Litoral norte de Valencia) went red at 09:41.",
         "sources": [AEMET_REPORT, AEMET_ZONES]},
        {"claim": "Chiva 11:30", "verdict": "holds with other wording",
         "say": "11:30, first flash flood on the Poyo below Chiva (208 m3/s at 11:30). Chiva's streets flooded "
                "later (17:47); do not say Chiva was destroyed at 11:30.",
         "sources": [MALDITA_POYO, ELDIARIO_TIMELINE]},
        {"claim": "Torrent 18:30", "verdict": "holds", "say": "About 18:30, the Poyo floods Torrent and "
         "l'Horta Sud; its gauge reads 2,282.9 m3/s at 18:55 and is then destroyed.",
         "sources": [ELDIARIO_TIMELINE, MALDITA_POYO, CHJ_REPORT]},
        {"claim": "phone alert 20:11", "verdict": "holds", "say": "20:11, ES-Alert to every phone in Valencia "
         "province.", "sources": [TSJCV_NOTE]},
    ]
    return out


AEMET_REPORT = {
    "title": "Informe sobre el episodio meteorológico de precipitaciones torrenciales y persistentes ocasionadas "
             "por una DANA el día 29 de octubre de 2024 (information up to 8 Nov 2024)",
    "publisher": "AEMET", "url": "https://repositorio.aemet.es/bitstream/20.500.11765/16360/1/"
                                 "informe_episodio_dana_29_oct_2024_.pdf",
    "where": "section 3.4 Secuencia de avisos, pages 8 to 9 (times in official peninsular time, CET that day)",
    "retrieved": "2026-11-15",
}
AEMET_ZONES = {
    "title": "AEMET municipal forecast pages, field 'Zona de avisos' (one page per municipality, id = INE code)",
    "publisher": "AEMET warning zones",
    "url": "https://www.aemet.es/es/eltiempo/prediccion/municipios/paiporta-id46186",
    "numbers": "Litoral norte de Valencia: Paiporta, Massanassa, Sedaví, Catarroja, Alfafar, Benetússer, Picanya, "
               "Aldaia, Chiva, Torrent. Litoral sur de Valencia: Oliva. Litoral norte de Alicante: Pego. "
               "Zone as listed today; assumed unchanged since Oct 2024",
    "retrieved": "2026-11-15",
}
MALDITA_POYO = {
    "title": "Cronología de la crecida del río Magro, la rambla del Poyo y los avisos de la AEMET, de la CHJ y la "
             "alerta de la Comunidad Valenciana",
    "publisher": "Maldita.es", "date": "2024-11-08",
    "url": "https://maldita.es/clima/20241108/cronologia-avisos-rio-magro-rambla-poyo/",
    "where": "entries 11:25, 11:30, 12:07, 12:20, 17:47, 18:25, 18:28, 18:35, 18:55 (gauge values from the CHJ "
             "SAIH, rambla del Poyo at the A-3, Riba-roja)",
    "retrieved": "2026-11-15",
}
ELDIARIO_TIMELINE = {
    "title": "Cronología de una alerta que llegó tarde", "publisher": "elDiario.es (Sergi Pitarch)",
    "date": "2024-10-30, updated 2024-10-31",
    "url": "https://www.eldiario.es/comunitat-valenciana/"
           "cronologia-alerta-llego-tarde-utiel-requena-inundan-pasar-despues-rio-abajo_1_11779079.html",
    "where": "timeline entries 11:30 (the barranco del Poyo overflows in Chiva), 12:20, 18:30 (Torrent), 20:12",
    "retrieved": "2026-11-15",
}
CHJ_REPORT = {
    "title": "Nota informativa. Episodio de lluvias y avenidas del 28 de octubre al 4 de noviembre de 2024, "
             "version 2", "publisher": "Confederación Hidrográfica del Júcar (CHJ)", "date": "2025-01-15",
    "url": "https://saih.chj.es/docs/20241029-1104Informe-Episodio-C-version2.pdf",
    "where": "section 2.1 table, row 'Rambla Del Poyo - NIII' (page 14); section 2.3 (page 16)",
    "retrieved": "2026-11-15",
}
TSJCV_NOTE = {
    "title": "El juzgado vuelve a requerir a la Generalitat para que informe sobre quién decidió enviar el SMS de "
             "alerta por la Dana ...", "publisher": "Tribunal Superior de Justicia de la Comunitat Valenciana, "
                                                   "press office (poderjudicial.es)", "date": "2025-02-06",
    "url": "https://www.poderjudicial.es/cgpj/es/Poder-Judicial/Tribunales-Superiores-de-Justicia/"
           "TSJ-Comunidad-Valenciana/Oficina-de-Comunicacion/Archivo-de-notas-de-prensa/"
           "El-juzgado-vuelve-a-requerir-a-la-Generalitat-para-que-informe-sobre-quien-decidio-enviar-el-SMS-de-"
           "alerta-por-la-Dana-y-pide-a-la-CHJ-datos-del-caudal-del-Poyo-entre-las-16-13-y-las-18-42-horas-del-29-"
           "de-octubre",
    "where": "body: the alert was sent to mobile phones at 20.11",
    "retrieved": "2026-11-15",
}

# 29 Oct 2024, local time (CET, UTC+1). Every line checked against the cited text on 2026-11-15.
TIMELINE_2024: list[dict] = [
    {"time_local": "07:36", "what": "First AEMET red warning of the day in Valencia province, for the Litoral sur "
     "de Valencia zone (observed 90 mm in one hour, forecast 180 mm in 12 hours), valid to 12:00. Not the zone of "
     "L'Horta Sud or Chiva.", "sources": [AEMET_REPORT]},
    {"time_local": "09:41", "what": "AEMET red warning for the Litoral norte de Valencia zone, the warning zone of "
     "every 2024 municipality here (Paiporta, Chiva, Torrent and the rest): 90 mm in one hour and 180 mm in 12 "
     "hours, to 18:00; extended at 17:49 to 20:00.", "sources": [AEMET_REPORT, AEMET_ZONES]},
    {"time_local": "11:30", "what": "First flash flood on the rambla del Poyo below Chiva: the CHJ gauge at the A-3 "
     "(Riba-roja) jumps from 57.6 m3/s at 11:25 to 208.2 m3/s at 11:30 (264 m3/s at 11:40). elDiario.es puts the "
     "Poyo overflowing in Chiva at 11:30; the flooding of Chiva's streets is documented later, at 17:47.",
     "sources": [MALDITA_POYO, ELDIARIO_TIMELINE]},
    {"time_local": "12:20", "what": "Special hydrological alert of the Generalitat's emergency centre for the Poyo "
     "towns (Torrent, Picanya, Paiporta, Benetússer, Sedaví, Alfafar, Massanassa, Catarroja). Not sent to phones.",
     "sources": [MALDITA_POYO, ELDIARIO_TIMELINE]},
    {"time_local": "about 18:30", "what": "The Poyo floods Torrent and l'Horta Sud: a video at 18:28 shows Picanya "
     "starting to flood; the gauge reads 1,686.7 m3/s at 18:25 and 1,756.9 m3/s at 18:35; elDiario.es gives 18:30 "
     "for Torrent.", "sources": [MALDITA_POYO, ELDIARIO_TIMELINE]},
    {"time_local": "18:55", "what": "Last reading of the Poyo gauge before the flood destroyed it: 2,282.90 m3/s "
     "(water level 4.899 m).", "sources": [CHJ_REPORT, MALDITA_POYO]},
    {"time_local": "20:11", "what": "ES-Alert to every mobile phone in Valencia province, asking people to avoid "
     "any travel (elDiario.es's first timeline said 20:12).", "sources": [TSJCV_NOTE, ELDIARIO_TIMELINE]},
]


def method_text() -> list[str]:
    return [
        "Municipalities: IGN INSPIRE administrative units, fetched by id.",
        "Official zones: SNCZI fluvial T10, T100, T500 and marine T100, T500 from the MITECO WFS, clipped to "
        "the municipalities. Each spot gets the most frequent zone it lies in: frequent (T10), occasional (T100), "
        "rare (T500 only), none (outside every zone).",
        "Observed flood: flooded area plus flood traces of Copernicus EMS, as the maximum observed extent (a spot "
        "counts if any product saw water or a trace there). 2024: EMSR773, the three first-response products that "
        "map these towns (AOI03 grading v2, AOI03 delineation v1, AOI01 delineation v1); the priority mosaic "
        "(sharpest map first, where it looked) is given as the lower bound under sensitivity. 2026: EMSR935 as in "
        "data/labels.",
        "Graded buildings (2024): the building points of the AOI03 grading map, each with the zone class of its "
        "point.",
        "Areas: exact geometries in UTM 30N (EPSG:32630), GEOS overlay (snapped to a 1 cm grid only where GEOS "
        "reports a topology error). Shares are of the observed flood inside each municipality. Web layers are "
        "simplified copies for display only; their area_ha comes from the exact geometries.",
        "No estimate without a label: a share is null where nothing was observed.",
    ]


# ---------------------------------------------------------------- web layers


def simplify(geom: BaseGeometry, tol_m: float) -> BaseGeometry:
    return polygonal(shapely.make_valid(shapely.simplify(geom, tol_m, preserve_topology=True)))


def web_zones(classes: dict[str, BaseGeometry], tol_m: float = 6.0) -> gpd.GeoDataFrame:
    """Display copy of the three zone classes: nested envelopes simplified, then split again."""
    s10 = simplify(classes["frequent"], tol_m)
    s100 = simplify(union([classes["frequent"], classes["occasional"]]), tol_m)
    s500 = simplify(union([classes["frequent"], classes["occasional"], classes["rare"]]), tol_m)
    rows = [("frequent", s10), ("occasional", diff(s100, s10)), ("rare", diff(s500, union([s100, s10])))]
    exact = {k: round(ha(classes[k]), 1) for k in ("frequent", "occasional", "rare")}
    return gpd.GeoDataFrame(
        {"zone": [k for k, _ in rows], "title": [CLASS_TITLES[k] for k, _ in rows],
         "area_ha": [exact[k] for k, _ in rows]},
        geometry=[g for _, g in rows], crs=AREA_CRS)


def web_floods(pieces: dict[str, dict[str, BaseGeometry]], munis: gpd.GeoDataFrame,
               tol_m: float = 4.0) -> gpd.GeoDataFrame:
    """Display copy of the observed flood, split by municipality, zone class and observed class."""
    rows = []
    for _, m in munis.iterrows():
        for c in OBSERVED:
            for z in CLASSES:
                piece = inter(pieces[c][z], m.geometry)
                if ha(piece) < 0.01:
                    continue
                rows.append({"municipality": m["name"], "ine": m["ine"], "zone": z, "observed": c,
                             "area_ha": round(ha(piece), 2), "geometry": simplify(piece, tol_m)})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=AREA_CRS)
    return gdf[~gdf.geometry.is_empty]


def web_municipalities(munis: gpd.GeoDataFrame, numbers: dict, event: Event, tol_m: float = 10.0):
    by = {r["ine"]: r for r in numbers["municipalities"]}
    rows = []
    for _, m in munis.iterrows():
        r = by[m["ine"]]
        rows.append({"name": m["name"], "ine": m["ine"], "event": event.key,
                     "flooded_ha": r["flooded_ha"], "outside_every_zone_pct": r["outside_every_zone_pct"],
                     "only_rare_t500_pct": r["only_rare_t500_pct"],
                     "frequent_or_occasional_pct": r["frequent_or_occasional_pct"],
                     "geometry": simplify(m.geometry, tol_m)})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=AREA_CRS)


def no_dashes(text: str) -> str:
    """En and em dashes in source text become plain hyphens (house rule)."""
    return text.replace(EN_DASH, "-").replace(EM_DASH, "-")


def assert_no_dashes(text: str, where: str) -> None:
    for ch in (EN_DASH, EM_DASH):
        if ch in text:
            raise ValueError(f"{where} contains U+{ord(ch):04X}")


WEB_GRID_DEG = 1e-5  # about 1 m, well below the 4 to 10 m simplification of the web layers


def _web_snap(geom: BaseGeometry) -> BaseGeometry:
    """Repair and snap one display geometry to the 1e-5 degree grid; points stay points."""
    valid = shapely.make_valid(geom)
    try:
        valid = shapely.set_precision(valid, WEB_GRID_DEG)
    except shapely.errors.GEOSException:
        pass
    return valid if geom.geom_type == "Point" else polygonal(valid)


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    final = clean_text(gdf).to_crs("EPSG:4326")
    final = final.assign(geometry=[_web_snap(g) for g in final.geometry])
    final = final[~final.geometry.is_empty]
    path.unlink(missing_ok=True)
    final.to_file(path, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": "5", "RFC7946": "YES"})
    assert_no_dashes(path.read_text(encoding="utf-8"), path.name)
    print(f"{path.relative_to(DATA_DIR.parent).as_posix()}: {len(final)} features, {path.stat().st_size / 1e6:.2f} MB")


def write_outputs(result: dict, web: dict[str, gpd.GeoDataFrame]) -> None:
    ZONES_DIR.mkdir(parents=True, exist_ok=True)
    for name, gdf in web.items():
        write_geojson(gdf, ZONES_DIR / f"{name}.geojson")
    text = json.dumps(result, indent=1, ensure_ascii=False)
    assert_no_dashes(text, "zones_vs_floods.json")
    (ZONES_DIR / "zones_vs_floods.json").write_text(text + "\n", encoding="utf-8")
    print("data/zones/zones_vs_floods.json written")


def report(path: Path = ZONES_DIR / "zones_vs_floods.json") -> str:
    """Markdown tables of the results file, for docs/ZONES.md (so no number is typed by hand)."""
    result = json.loads(path.read_text(encoding="utf-8"))

    def fmt(v):
        return "n/a" if v is None else f"{v:,.1f}"

    lines = []
    for key, ev in result["events"].items():
        lines += [f"### {ev['title']}", "",
                  "| Municipality | Observed flood (ha) | Outside every zone | Only rare (T500) "
                  "| Frequent or occasional | Zones cover of the municipality |",
                  "|---|---|---|---|---|---|"]
        for m in ev["municipalities"] + [{**ev["total"], "name": "**Total**"}]:
            lines.append(f"| {m['name']} | {fmt(m['flooded_ha'])} | {fmt(m['outside_every_zone_pct'])} % "
                         f"| {fmt(m['only_rare_t500_pct'])} % | {fmt(m['frequent_or_occasional_pct'])} % "
                         f"| {fmt(m['zone_cover_pct'])} % |")
        lines.append("")
        lines += ["Split by what the satellite saw (share outside every zone / only rare / frequent or occasional):", "",
                  "| Municipality | Flooded area (water on the image), ha | shares | Flood traces (water gone), ha | shares |",
                  "|---|---|---|---|---|"]
        for m in ev["municipalities"] + [{**ev["total"], "name": "**Total**"}]:
            fa, ft = m["by_observed_class"]["flooded_area"], m["by_observed_class"]["flood_trace"]
            lines.append(f"| {m['name']} | {fmt(fa['flooded_ha'])} | {fmt(fa['outside_every_zone_pct'])} / "
                         f"{fmt(fa['only_rare_t500_pct'])} / {fmt(fa['frequent_or_occasional_pct'])} % "
                         f"| {fmt(ft['flooded_ha'])} | {fmt(ft['outside_every_zone_pct'])} / "
                         f"{fmt(ft['only_rare_t500_pct'])} / {fmt(ft['frequent_or_occasional_pct'])} % |")
        lines.append("")
        if "graded_buildings" in ev:
            b = ev["graded_buildings"]
            lines += ["Buildings the Copernicus grading map marked as affected (possibly damaged, damaged or "
                      "destroyed), by the zone of their point:", "",
                      "| Municipality | Graded buildings | Outside every zone | Only rare (T500) | Frequent or occasional |",
                      "|---|---|---|---|---|"]
            for name, v in list(b["municipalities"].items()) + [("**Total**", b["total"])]:
                lines.append(f"| {name} | {v['buildings']:,} | {fmt(v['outside_every_zone_pct'])} % "
                             f"| {fmt(v['only_rare_t500_pct'])} % | {fmt(v['frequent_or_occasional_pct'])} % |")
            lines.append("")
        lines += [f"Sensitivity ({key}): share outside every zone, only rare, frequent or occasional.", "",
                  "| Variant | Observed flood (ha) | Outside | Only rare | Frequent or occasional |",
                  "|---|---|---|---|---|"]
        for name, v in ev["sensitivity"].items():
            t = v["total"]
            lines.append(f"| {name} | {fmt(t['flooded_ha'])} | {fmt(t['outside_every_zone_pct'])} % "
                         f"| {fmt(t['only_rare_t500_pct'])} % | {fmt(t['frequent_or_occasional_pct'])} % |")
        lines.append("")
    lines += ["### The claims of discussion #29", "", "| Claim | Verdict | Our numbers | Say instead |", "|---|---|---|---|"]
    for c in result["claims"]:
        lines.append(f"| {c['claim']} | {c['verdict']} | {c.get('our_number', '')} | {c.get('say', '')} |")
    lines += ["", "### 29 Oct 2024, local time", "", "| Time | What | Sources |", "|---|---|---|"]
    for t in result["timeline_2024"]:
        refs = "; ".join(f"[{s['publisher']}]({s['url']})" if "url" in s else s["publisher"] for s in t["sources"])
        lines.append(f"| {t['time_local']} | {t['what']} | {refs} |")
    lines.append("")
    text = "\n".join(lines).replace(" n/a %", " n/a")
    assert_no_dashes(text, "report")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", nargs="?", choices=("fetch", "compute", "report", "all"), default="all",
                        help="fetch the sources, compute the numbers, or print the tables of docs/ZONES.md")
    args = parser.parse_args()
    if args.step in ("fetch", "all"):
        fetch()
    if args.step in ("compute", "all"):
        compute()
    if args.step == "report":
        print(report())


if __name__ == "__main__":
    main()
