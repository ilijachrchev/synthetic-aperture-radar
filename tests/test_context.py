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


def test_mjd_to_date_matches_ngl_rows():
    # First two LOR1 rows: MJD 55086 is 09SEP12, MJD 55087 is 09SEP13.
    assert mjd_to_date(55086) == date(2009, 9, 12)
    assert mjd_to_date(55087) == date(2009, 9, 13)
