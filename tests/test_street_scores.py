"""Street pieces, sample points, the 10 m rule, the equal-length cut and the UPV cell pick (pipeline.street_scores).

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from pipeline import street_scores as ss


def ways_from(lines: list[list[tuple[float, float]]]):
    xy = np.array([p for line in lines for p in line], dtype=np.float64)
    nv = np.array([len(line) for line in lines], dtype=np.int64)
    cum, length = ss.way_measures(xy, nv)
    return xy, nv, cum, length


def test_way_reason_follows_the_rules():
    assert ss.way_reason({"highway": "residential"}) == "kept"
    assert ss.way_reason({"highway": "footway"}) == "kept"
    assert ss.way_reason({"highway": "track"}) == "track"
    assert ss.way_reason({"highway": "track"}, tracks=True) == "kept"
    assert ss.way_reason({"highway": "footway", "footway": "sidewalk"}) == "sidewalk or crossing"
    assert ss.way_reason({"highway": "cycleway", "cycleway": "crossing"}) == "sidewalk or crossing"
    assert ss.way_reason({"highway": "footway", "footway": "crossing"}) == "sidewalk or crossing"
    # a road keeps its bike-lane tags: only pedestrian ways can be sidewalk duplicates
    assert ss.way_reason({"highway": "residential", "cycleway": "crossing"}) == "kept"
    assert ss.way_reason({"highway": "primary", "tunnel": "yes"}) == "tunnel"
    assert ss.way_reason({"highway": "primary", "tunnel": "no"}) == "kept"
    assert ss.way_reason({"highway": "pedestrian", "area": "yes"}) == "area"
    assert ss.way_reason({"highway": "construction"}) == "other highway value"
    assert ss.way_reason({"highway": "platform"}) == "other highway value"


def test_ways_are_cut_into_pieces_of_about_25_m():
    length = np.array([10.0, 37.4, 37.5, 100.0, 12.0])
    p = ss.pieces_of(length)
    counts = np.bincount(p["way"], minlength=length.size)
    assert counts.tolist() == [1, 1, 2, 4, 1]
    assert p["length"][p["way"] == 3] == pytest.approx([25.0] * 4)
    assert p["start"][p["way"] == 3] == pytest.approx([0.0, 25.0, 50.0, 75.0])
    # the pieces of each way add up to the way
    assert np.bincount(p["way"], weights=p["length"]) == pytest.approx(length)


def test_sample_points_are_at_most_2p5_m_apart_at_part_centres():
    piece, off = ss.samples_of(np.array([25.0, 2.0, 2.5, 2.51]))
    assert np.bincount(piece).tolist() == [10, 1, 1, 2]
    assert off[piece == 0] == pytest.approx(np.arange(10) * 2.5 + 1.25)
    assert off[piece == 1] == pytest.approx([1.0])
    assert off[piece == 3] == pytest.approx([2.51 / 4, 3 * 2.51 / 4])


def test_interpolate_walks_around_a_corner():
    xy, nv, cum, length = ways_from([[(0, 0), (10, 0), (10, 10)], [(100, 100), (100, 130)]])
    assert length == pytest.approx([20.0, 30.0])
    pts = ss.interpolate(xy, nv, cum, length, np.array([0, 0, 0, 0, 1]), np.array([0.0, 5.0, 15.0, 20.0, 12.0]))
    assert pts == pytest.approx(np.array([[0, 0], [5, 0], [10, 5], [10, 10], [100, 112]]))


def test_piece_lines_keep_the_corner_and_add_up():
    xy, nv, cum, length = ways_from([[(0, 0), (40, 0), (40, 35)]])  # 75 m: three pieces of 25 m
    p = ss.pieces_of(length)
    lines = ss.piece_lines(xy, nv, cum, length, p)
    assert len(lines) == 3
    assert shapely.length(lines) == pytest.approx([25.0, 25.0, 25.0])
    # the middle piece runs from (25, 0) through the corner (40, 0) to (40, 10)
    assert shapely.get_coordinates(lines[1]) == pytest.approx(np.array([[25, 0], [40, 0], [40, 10]]))


def test_near_points_uses_10_m_from_the_line():
    lines = shapely.linestrings([[[0, 0], [25, 0]], [[0, 100], [25, 100]]])
    near = ss.near_points(lines, np.array([12.0, 40.0]), np.array([9.9, 50.0]))
    assert near.tolist() == [True, False]
    near = ss.near_points(lines, np.array([12.0]), np.array([10.1]))
    assert near.tolist() == [False, False]
    # beyond the end: distance to the end point
    near = ss.near_points(lines, np.array([32.0]), np.array([107.0]))
    assert near.tolist() == [False, True]


def test_majority_rule_and_medians():
    piece = np.array([0, 0, 0, 1, 1, 2])
    layer = np.array([True, True, False, True, False, False])
    share = ss.share_in(layer, piece, 3)
    assert share == pytest.approx([2 / 3, 0.5, 0.0])
    assert (share >= ss.MAJORITY).tolist() == [True, True, False]
    med = ss.group_median(np.array([1.0, np.nan, 3.0, np.nan, np.nan, 7.0]), piece, 3)
    assert med[0] == pytest.approx(2.0)
    assert np.isnan(med[1])
    assert med[2] == pytest.approx(7.0)


def test_cut_to_length_takes_lowest_first_until_the_budget():
    score = np.array([3.0, 1.0, np.nan, 2.0, 1.0])
    length = np.array([10.0, 25.0, 25.0, 20.0, 5.0])
    # order: 1 (1.0), 4 (1.0, tie by index), 3 (2.0), 0 (3.0), 2 (NaN last)
    assert ss.cut_to_length(score, length, 25.0).tolist() == [False, True, False, False, False]
    assert ss.cut_to_length(score, length, 26.0).tolist() == [False, True, False, False, True]
    assert ss.cut_to_length(score, length, 31.0).tolist() == [False, True, False, True, True]
    assert ss.cut_to_length(score, length, 0.0).sum() == 0
    assert ss.cut_to_length(score, length, 1e6).all()


def test_street_metrics_hit_rate_and_precision():
    flag = np.array([True, True, False, False])
    flood = np.array([True, False, True, False])
    length = np.array([10.0, 30.0, 20.0, 40.0])
    m = ss.street_metrics(flag, flood, length)
    assert m["hit_rate_pct"] == pytest.approx(100 * 10 / 30, abs=0.05)
    assert m["precision_pct"] == pytest.approx(100 * 10 / 40, abs=0.05)
    assert m["chance_precision_pct"] == pytest.approx(30.0)
    assert m["flagged_pct_of_streets"] == pytest.approx(40.0)
    dom = np.array([True, False, True, False])
    m = ss.street_metrics(flag, flood, length, dom)
    assert m["street_km"] == pytest.approx(0.03)
    assert m["precision_pct"] == pytest.approx(100.0)


def test_pick_cell_centres_takes_the_native_pixel_holding_each_centre():
    from rasterio.io import MemoryFile
    from rasterio.transform import Affine

    bounds = (1000.0, 2000.0, 1020.0, 2010.0)  # a 4 x 2 grid of 5 m cells
    # native 0.5 m pixels, origin off the 5 m lines as on the UPV server; value = 1000 * row + col
    t = Affine(0.5, 0.0, 999.89, 0.0, -0.5, 2010.22)
    rows, cols = 22, 42
    a = (1000.0 * np.arange(rows)[:, None] + np.arange(cols)[None, :]).astype(np.float32)
    a[0:12, 0:12] = np.nan
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", width=cols, height=rows, count=1, dtype="float32", transform=t,
                      crs="EPSG:25830", nodata=np.nan) as dst:
            dst.write(a, 1)
        data = mem.read()
    out = np.full((2, 4), np.nan, dtype=np.float32)
    n = ss.pick_cell_centres(data, out, (1000.0, 2000.0, 1020.0, 2010.0), bounds=bounds)
    # centre of cell (row 0, col 1): x 1007.5, y 2007.5 -> pixel col floor((1007.5 - 999.89) / 0.5) = 15,
    # row floor((2010.22 - 2007.5) / 0.5) = 5
    assert out[0, 1] == pytest.approx(1000 * 5 + 15)
    assert out[1, 3] == pytest.approx(1000 * 15 + 35)
    assert np.isnan(out[0, 0])  # the pixel holding that centre has no value
    assert n == 7
