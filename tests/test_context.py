"""Checks for helper-data tile selection. Written with SI assistance (Claude Code)."""

from datetime import date

from pipeline.context import jrc_tiles, mjd_to_date, worldcover_tiles


def test_worldcover_tiles_single_and_crossing():
    # Albufera sits inside one 3 x 3 degree tile.
    assert worldcover_tiles((-0.45, 39.15, -0.22, 39.45)) == ["N39W003"]
    # Pego-Oliva crosses 39 N and 0 degrees: four tiles.
    assert sorted(worldcover_tiles((-0.25, 38.78, 0.06, 39.02))) == ["N36E000", "N36W003", "N39E000", "N39W003"]


def test_jrc_tiles_named_by_west_and_north_edges():
    assert jrc_tiles((-0.45, 39.15, -0.22, 39.45)) == ["10W_40N"]
    # Espadà crosses 40 N, Pego-Oliva crosses 0 degrees.
    assert sorted(jrc_tiles((-0.50, 39.78, -0.10, 40.02))) == ["10W_40N", "10W_50N"]
    assert sorted(jrc_tiles((-0.25, 38.78, 0.06, 39.02))) == ["0E_40N", "10W_40N"]


def test_grid_bbox_contains_site_box():
    from pipeline.config import get_site
    from pipeline.context import grid_bbox_wgs84

    for name in ("albufera", "pego_oliva", "espada", "lorca"):
        w, s, e, n = grid_bbox_wgs84(get_site(name))
        sw, ss, se, sn = get_site(name).bbox
        assert w < sw and s < ss and e > se and n > sn


def test_warp_to_grid_covers_the_grid_and_keeps_class_codes(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling

    from pipeline.config import get_site
    from pipeline.context import grid_bbox_wgs84, warp_to_grid

    site = get_site("albufera")
    w, s, e, n = grid_bbox_wgs84(site)
    res = 1 / 12000  # WorldCover's 10 m pixel in degrees
    width, height = int((e - w) / res) + 1, int((n - s) / res) + 1
    codes = np.full((height, width), 40, dtype="uint8")
    codes[:, width // 2:] = 80  # cropland west, water east
    path = tmp_path / "wc.tif"
    with rasterio.open(path, "w", driver="GTiff", height=height, width=width, count=1, dtype="uint8",
                       crs="EPSG:4326", transform=from_origin(w, n, res, res), nodata=0) as dst:
        dst.write(codes, 1)
    out = warp_to_grid(path, site, Resampling.mode, 0)
    assert set(np.unique(out)) == {40, 80}  # no empty edges, no blended codes


def test_sea_mask_keeps_a_canal_linked_lagoon_separate():
    import numpy as np

    from pipeline.context import sea_mask

    water = np.zeros((60, 60), bool)
    water[:, 45:] = True            # open sea along the east edge
    water[20:35, 10:25] = True      # inland lagoon
    water[27:29, 25:45] = True      # a 2 px canal from the lagoon to the sea
    sea = sea_mask(water, ("east",))
    assert sea[:, 50:].all()                    # the sea, including the edge column
    assert not sea[20:35, 10:25].any()          # the lagoon stays separate
    assert not sea_mask(water, ()).any()        # a site without sea edges has no sea


def test_mjd_to_date_matches_ngl_rows():
    # First two LOR1 rows: MJD 55086 is 09SEP12, MJD 55087 is 09SEP13.
    assert mjd_to_date(55086) == date(2009, 9, 12)
    assert mjd_to_date(55087) == date(2009, 9, 13)
