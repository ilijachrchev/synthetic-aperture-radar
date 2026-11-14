"""Bake what sits around the DANA flood on the map: the official outlines, the depth marks and the hourly rain.

    python scripts/bake_context.py --data-root ../data

Writes into public/layers/pego_oliva/:
    outlines.json   the Copernicus EMS EMSR935 flood outline, the Generalitat river-flood footprint and the measured
                    water depth points, simplified for the browser (the originals stay in data/labels/)
    rain.json       hourly rain at the marsh, 14 Oct to 12 Nov 2026

The rain is modelled, not gauged: Meteo-France AROME (1.5 km grid) short-range runs stitched by Open-Meteo. It gives
the timing of the storm. Gauges nearby recorded far more than any grid cell shows, so the app never calls it a
measurement.

Needs geopandas, shapely and requests (the pipeline environment has them all).
Written with SI assistance (Claude Code), reviewed by the team.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import mapping
from shapely.ops import unary_union

WEB = Path(__file__).resolve().parents[1]
MARSH = (38.87, -0.06)  # latitude, longitude of the Pego-Oliva marsh
RAIN_API = "https://historical-forecast-api.open-meteo.com/v1/forecast"
RAIN_MODEL = "meteofrance_arome_france_hd"


def rounded(geom, digits=5):
    def walk(x):
        if isinstance(x, (list, tuple)):
            if x and isinstance(x[0], (int, float)):
                return [round(x[0], digits), round(x[1], digits)]
            return [walk(v) for v in x]
        return x

    m = mapping(geom)
    return {"type": m["type"], "coordinates": walk(m["coordinates"])}


def outline(path, tolerance_m, close_m=0.0, min_ha=0.0):
    """Dissolve an outline file into one shape for drawing, back in degrees.

    The area in the properties is the area of the source shapes, untouched. The drawn shape is generalised so a
    thousand slivers read as one outline: gaps narrower than 2 * close_m are bridged, parts smaller than min_ha are
    left out, and the edge is simplified to tolerance_m. The drawn area is reported next to the true one.
    """
    g = gpd.read_file(path).to_crs(32630)
    shape = unary_union([geom.buffer(0) for geom in g.geometry if geom is not None and not geom.is_empty])
    area = shape.area / 1e4
    drawn = shape.buffer(close_m).buffer(-close_m) if close_m else shape
    parts = [p for p in getattr(drawn, "geoms", [drawn]) if p.area / 1e4 >= min_ha]
    drawn = unary_union(parts).simplify(tolerance_m, preserve_topology=True)
    back = gpd.GeoSeries([drawn], crs=32630).to_crs(4326).iloc[0]
    return [{"type": "Feature", "properties": {"area_ha": round(area, 1), "drawn_ha": round(drawn.area / 1e4, 1), "parts": len(parts)},
             "geometry": rounded(back)}]


def rain(start, end):
    r = requests.get(RAIN_API, params={"latitude": MARSH[0], "longitude": MARSH[1], "start_date": start, "end_date": end,
                                       "hourly": "precipitation", "timezone": "UTC", "models": RAIN_MODEL}, timeout=120)
    r.raise_for_status()
    j = r.json()
    hours = [{"t": t + ":00Z", "mm": v} for t, v in zip(j["hourly"]["time"], j["hourly"]["precipitation"]) if v is not None]
    return {
        "source": "Open-Meteo Historical Forecast API, model Meteo-France AROME France HD (1.5 km), modelled rain, not a gauge",
        "url": "https://open-meteo.com/en/docs/historical-forecast-api",
        "licence": "CC BY 4.0",
        "point": {"lat": j["latitude"], "lon": j["longitude"]},
        "unit": "mm per hour",
        "total_mm": round(sum(h["mm"] for h in hours), 1),
        "hours": hours,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", type=Path, default=WEB.parent / "data")
    ap.add_argument("--out", type=Path, default=WEB / "public" / "layers" / "pego_oliva")
    ap.add_argument("--no-rain", action="store_true", help="only rebuild the outlines")
    args = ap.parse_args()
    labels = args.data_root / "labels"
    args.out.mkdir(parents=True, exist_ok=True)

    ems = outline(labels / "pego_oliva_emsr935_flood.geojson", 8.0, close_m=6.5, min_ha=0.5)
    gva = outline(labels / "pego_oliva_generalitat_footprint.geojson", 8.0)
    pts = gpd.read_file(labels / "pego_oliva_water_depth_points.geojson").to_crs(4326)
    depth = [{"type": "Feature", "properties": {"depth_m": float(r["AlturaAguam"]), "basin": r["Cuenca"]},
              "geometry": {"type": "Point", "coordinates": [round(r.geometry.x, 5), round(r.geometry.y, 5)]}} for _, r in pts.iterrows()]
    out = {
        "ems": {"title": "Copernicus EMS flood outline", "when": "imagery of 20 to 21 Oct 2026",
                "credit": "Copernicus Emergency Management Service, EMSR935", "features": ems},
        "generalitat": {"title": "Official river-flood footprint", "when": "DANA of 18 Oct 2026",
                        "credit": "Generalitat Valenciana", "features": gva},
        "depth": {"title": "Measured water depth", "credit": "Generalitat Valenciana, Servicio de Gestion de Riesgos en el Territorio",
                  "features": depth},
    }
    (args.out / "outlines.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"outlines: EMS {ems[0]['properties']['area_ha']} ha (drawn {ems[0]['properties']['drawn_ha']} ha in "
          f"{ems[0]['properties']['parts']} parts), Generalitat {gva[0]['properties']['area_ha']} ha, "
          f"{len(depth)} depth points, {(args.out / 'outlines.json').stat().st_size / 1e3:.0f} kB")
    if args.no_rain:
        return

    r = rain("2026-10-14", "2026-11-12")
    (args.out / "rain.json").write_text(json.dumps(r, separators=(",", ":")), encoding="utf-8")
    by_day = {}
    for h in r["hours"]:
        by_day[h["t"][:10]] = by_day.get(h["t"][:10], 0) + h["mm"]
    print(f"rain: {r['total_mm']} mm in {len(r['hours'])} hours; wet days:", {k: round(v, 1) for k, v in by_day.items() if v >= 2})


if __name__ == "__main__":
    sys.exit(main())
