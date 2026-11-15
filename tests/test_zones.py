"""Area bookkeeping of pipeline.zones on tiny synthetic polygons (1 ha = a 100 m square).

Written with SI assistance (Claude Code), reviewed by the team.
"""

import geopandas as gpd
import pytest
import shapely
from shapely.geometry import Point, Polygon, box

from pipeline.zones import (
    CLASSES, EM_DASH, EN_DASH, EmsProduct, Municipality, assert_no_dashes, clean, ha_inside, label_points, mosaic,
    no_dashes, shares, split_by_class, tally, union_flood, zone_classes, zone_of_points,
)

EMPTY = shapely.Polygon()


def ha_box(x0, y0, x1, y1):
    """A box in metres; its area in ha is (x1 - x0) * (y1 - y0) / 1e4."""
    return box(x0, y0, x1, y1)


# A 1000 m x 100 m strip (10 ha) as the study area, cut into ten 1 ha cells along x.
CLIP = ha_box(0, 0, 1000, 100)
T10 = ha_box(0, 0, 100, 100)        # cell 0
T100 = ha_box(0, 0, 300, 100)       # cells 0 to 2 (contains T10)
T500 = ha_box(0, 0, 600, 100)       # cells 0 to 5 (contains T100)


def areas(classes):
    return {k: round(g.area / 1e4, 6) for k, g in classes.items()}


def test_nested_zones_split_into_exclusive_classes():
    classes = zone_classes(T10, T100, T500, CLIP)
    assert areas(classes) == {"frequent": 1.0, "occasional": 2.0, "rare": 3.0, "none": 4.0}
    # The four classes tile the study area: no overlap, no gap.
    assert round(shapely.union_all(list(classes.values())).area / 1e4, 6) == 10.0
    assert round(sum(g.area for g in classes.values()) / 1e4, 6) == 10.0


def test_most_frequent_zone_wins_when_zones_are_not_nested():
    # A T100 study (cells 7 to 8) that no T500 study covers is still "occasional", not "none";
    # T500 is only "rare" where no more frequent zone lies.
    t100 = shapely.union_all([T100, ha_box(700, 0, 900, 100)])
    classes = zone_classes(T10, t100, T500, CLIP)
    assert areas(classes) == {"frequent": 1.0, "occasional": 4.0, "rare": 3.0, "none": 2.0}


def test_zones_outside_the_study_area_are_ignored():
    classes = zone_classes(ha_box(-500, 0, 100, 100), T100, ha_box(0, 0, 600, 900), CLIP)
    assert areas(classes) == {"frequent": 1.0, "occasional": 2.0, "rare": 3.0, "none": 4.0}


def test_flood_hectares_and_shares():
    classes = zone_classes(T10, T100, T500, CLIP)
    # Flood over cells 2 to 7: 1 ha occasional, 3 ha rare, 2 ha none = 6 ha.
    flood = ha_box(200, 0, 800, 100)
    by_class = tally(split_by_class(flood, classes))
    assert {k: round(v, 6) for k, v in by_class.items()} == {"frequent": 0.0, "occasional": 1.0, "rare": 3.0, "none": 2.0}
    s = shares(by_class)
    assert s["flooded_ha"] == 6.0
    assert s["outside_every_zone_pct"] == pytest.approx(33.3)
    assert s["only_rare_t500_pct"] == pytest.approx(50.0)
    assert s["frequent_or_occasional_pct"] == pytest.approx(16.7)
    assert s["frequent_t10_pct"] == 0.0
    total = s["outside_every_zone_pct"] + s["only_rare_t500_pct"] + s["frequent_or_occasional_pct"]
    assert total == pytest.approx(100.0, abs=0.11)


def test_flood_outside_the_study_area_is_not_counted():
    classes = zone_classes(T10, T100, T500, CLIP)
    flood = ha_box(900, 0, 1500, 100)  # 1 ha inside, 5 ha beyond the strip
    assert shares(tally(split_by_class(flood, classes)))["flooded_ha"] == 1.0


def test_per_municipality_tallies_add_up_to_the_total():
    classes = zone_classes(T10, T100, T500, CLIP)
    pieces = split_by_class(ha_box(50, 0, 750, 100), classes)
    west, east = ha_box(0, 0, 400, 100), ha_box(400, 0, 1000, 100)
    total = tally(pieces)
    w, e = tally(pieces, west), tally(pieces, east)
    for k in CLASSES:
        assert w[k] + e[k] == pytest.approx(total[k])
    assert w == pytest.approx({"frequent": 0.5, "occasional": 2.0, "rare": 1.0, "none": 0.0})
    assert e == pytest.approx({"frequent": 0.0, "occasional": 0.0, "rare": 2.0, "none": 1.5})


def test_ha_inside_matches_a_plain_intersection():
    # Many small parts: some wholly inside the municipality, some crossing its border, some outside.
    parts = [ha_box(x, y, x + 30, y + 30) for x in range(0, 1000, 50) for y in range(0, 300, 50)]
    flood = shapely.union_all(parts)
    town = Polygon([(120, 10), (640, 40), (700, 260), (90, 220)])
    assert ha_inside(flood, town) == pytest.approx(flood.intersection(town).area / 1e4, rel=1e-9)
    assert ha_inside(flood, ha_box(5000, 0, 6000, 100)) == 0.0
    assert ha_inside(EMPTY, town) == 0.0


def test_no_flood_gives_null_shares_not_zero():
    s = shares({k: 0.0 for k in CLASSES})
    assert s["flooded_ha"] == 0.0
    assert s["outside_every_zone_pct"] is None and s["only_rare_t500_pct"] is None


def test_mosaic_first_product_decides_where_it_looked():
    # Product A (sharp) looked at cells 0 to 4 and saw water only in cell 0.
    # Product B (coarse) looked everywhere and saw water in cells 0 to 9.
    a = ("A", ha_box(0, 0, 500, 100), {"flooded_area": ha_box(0, 0, 100, 100), "flood_trace": EMPTY})
    b = ("B", CLIP, {"flooded_area": CLIP, "flood_trace": EMPTY})
    flood, regions = mosaic([a, b], CLIP)
    # A's "no water" in cells 1 to 4 wins over B; B only fills cells 5 to 9.
    assert flood["flooded_area"].area / 1e4 == pytest.approx(1.0 + 5.0)
    assert regions["A"].area / 1e4 == pytest.approx(5.0)
    assert regions["B"].area / 1e4 == pytest.approx(5.0)
    assert regions["A"].intersection(regions["B"]).area == pytest.approx(0.0)


def test_mosaic_order_matters_and_union_is_the_upper_bound():
    a = ("A", ha_box(0, 0, 500, 100), {"flooded_area": ha_box(0, 0, 100, 100), "flood_trace": EMPTY})
    b = ("B", CLIP, {"flooded_area": CLIP, "flood_trace": EMPTY})
    flood_ba, _ = mosaic([b, a], CLIP)
    assert flood_ba["flooded_area"].area / 1e4 == pytest.approx(10.0)


def test_mosaic_keeps_flooded_area_and_trace_apart():
    obs = {"flooded_area": ha_box(0, 0, 300, 100), "flood_trace": ha_box(200, 0, 500, 100)}
    flood, _ = mosaic([("A", CLIP, obs)], CLIP)
    assert flood["flooded_area"].area / 1e4 == pytest.approx(3.0)
    assert flood["flood_trace"].area / 1e4 == pytest.approx(2.0)  # the 1 ha overlap counts once, as water
    assert flood["flooded_area"].intersection(flood["flood_trace"]).area == pytest.approx(0.0)


def test_mosaic_skips_unanalysed_holes():
    # The product looked at the strip except a 1 ha cloud in cell 3: water there stays unknown, not flooded.
    analysed = ha_box(0, 0, 1000, 100).difference(ha_box(300, 0, 400, 100))
    flood, regions = mosaic([("A", analysed, {"flooded_area": CLIP, "flood_trace": EMPTY})], CLIP)
    assert flood["flooded_area"].area / 1e4 == pytest.approx(9.0)
    assert regions["A"].area / 1e4 == pytest.approx(9.0)


def test_union_flood_is_the_maximum_observed_extent():
    # A saw water in cells 0 to 1; B saw only traces in cells 1 to 3. Water wins where both saw something.
    a = ("A", CLIP, {"flooded_area": ha_box(0, 0, 200, 100), "flood_trace": EMPTY})
    b = ("B", CLIP, {"flooded_area": EMPTY, "flood_trace": ha_box(100, 0, 400, 100)})
    flood = union_flood([a, b], CLIP)
    assert flood["flooded_area"].area / 1e4 == pytest.approx(2.0)
    assert flood["flood_trace"].area / 1e4 == pytest.approx(2.0)
    assert flood["flooded_area"].intersection(flood["flood_trace"]).area == pytest.approx(0.0)
    # Never smaller than the sharpest-map-first mosaic of the same products.
    low, _ = mosaic([b, a], CLIP)
    assert shapely.union_all(list(low.values())).area <= shapely.union_all(list(flood.values())).area + 1e-6


def test_points_take_the_most_frequent_class_on_a_shared_border():
    classes = zone_classes(T10, T100, T500, CLIP)
    pts = gpd.GeoSeries([Point(50, 50), Point(100, 50), Point(450, 50), Point(950, 50), Point(5000, 50)])
    assert zone_of_points(pts, classes) == ["frequent", "frequent", "rare", "none", None]
    towns = {"west": ha_box(0, 0, 500, 100), "east": ha_box(500, 0, 1000, 100)}
    assert label_points(pts, towns) == ["west", "west", "west", "east", None]


def test_clean_cuts_to_the_box_and_repairs():
    bowtie = Polygon([(0, 0), (200, 200), (200, 0), (0, 200)])  # self-intersecting, 2 ha once repaired
    out = clean(bowtie, (0, 0, 100, 200))
    assert out.is_valid and out.geom_type in ("Polygon", "MultiPolygon")
    assert out.area / 1e4 == pytest.approx(1.0)  # the left triangle only
    assert clean(None).is_empty and clean(ha_box(0, 0, 10, 10), (50, 50, 60, 60)).is_empty


def test_ids_and_credits():
    assert Municipality("Paiporta", "46186").ign_id == "AU_ADMINISTRATIVEUNIT_34104646186"
    assert Municipality("Pego", "03102").ign_id == "AU_ADMINISTRATIVEUNIT_34100303102"
    prod = EmsProduct("EMSR773", 3, "Horta Sud", "GRA", 2, "")
    assert prod.zip_name == "EMSR773_AOI03_GRA_PRODUCT_v2.zip"
    assert prod.credit == ("Copernicus Emergency Management Service (© 2024 European Union), "
                           "[EMSR773] Horta Sud (AOI03): Grading Map")


def test_dashes_are_caught_and_cleaned():
    assert EN_DASH == chr(0x2013) and EM_DASH == chr(0x2014)
    assert no_dashes(f"Poyo {EN_DASH} Saleta {EM_DASH} T500") == "Poyo - Saleta - T500"
    assert_no_dashes("plain text - fine", "test")
    with pytest.raises(ValueError):
        assert_no_dashes(f"bad {EM_DASH}", "test")
