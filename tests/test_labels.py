"""Checks for label cleaning and geometry repair. Written with SI assistance (Claude Code)."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import GeometryCollection, LineString, Polygon

from pipeline.labels import clean_text, make_polygonal, polygonal_part, simplify_m, to_wgs84_grid


EN, EM = chr(0x2013), chr(0x2014)


def test_clean_text_replaces_en_and_em_dashes():
    df = pd.DataFrame({"a": [f"AOI01 {EM} v1", f"50{EN}100 cm", None], "n": [1, 2, 3]})
    out = clean_text(df)
    assert out["a"].tolist()[:2] == ["AOI01 - v1", "50-100 cm"]
    assert out["a"].isna().tolist()[2]
    assert out["n"].tolist() == [1, 2, 3]


def test_polygonal_part_drops_lines():
    square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    mixed = GeometryCollection([square, LineString([(2, 2), (3, 3)])])
    assert polygonal_part(mixed).equals(square)
    assert polygonal_part(LineString([(0, 0), (1, 1)])) is None


def test_make_polygonal_repairs_bowtie():
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])  # self-intersecting
    gdf = gpd.GeoDataFrame({"k": [1]}, geometry=[bowtie], crs="EPSG:32630")
    out = make_polygonal(gdf)
    assert out.is_valid.all()
    assert out.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    assert abs(out.area.sum() - 2.0) < 1e-9  # two triangles of area 1


def test_wgs84_grid_never_leaves_lines_or_collections():
    # A valid square with a spike only 0.01 m wide: snapping to about 0.1 m must
    # drop the spike, not leave a line or a mixed collection behind.
    x, y = 500000.0, 4300000.0
    spiked = Polygon([(x, y), (x + 100, y), (x + 100, y + 100), (x + 50.01, y + 100),
                      (x + 50.01, y + 200), (x + 50, y + 200), (x + 50, y + 100), (x, y + 100)])
    assert spiked.is_valid
    gdf = gpd.GeoDataFrame({"k": [1]}, geometry=[spiked], crs="EPSG:32630")
    out = to_wgs84_grid(gdf)
    assert out.is_valid.all()
    assert out.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    # Snapping moves corners by up to about 5 cm, so allow 0.5% on a 100 m square.
    assert abs(out.to_crs("EPSG:32630").area.sum() - 100 * 100) / (100 * 100) < 0.005


def test_simplify_keeps_area_within_a_tenth_of_a_pixel():
    # A 1 km square with 1 m jitter vertices: 2 m simplification barely moves its area.
    pts = [(x, 0.5 * (x % 2)) for x in range(0, 1001)] + [(1000, 1000), (0, 1000)]
    gdf = gpd.GeoDataFrame(geometry=[Polygon(pts)], crs="EPSG:32630")
    simple = simplify_m(gdf, 2.0)
    assert len(simple.geometry[0].exterior.coords) < len(pts)
    assert abs(simple.area.sum() - gdf.area.sum()) / gdf.area.sum() < 0.001
