"""Checks for DSWx-S1 label selection. Written with SI assistance (Claude Code)."""

from pipeline.dswx import WTR_CLASSES, WTR_INVALID, hours_apart, select_closest_pass, wtr_url


def _g(tile, acq, prod, hours):
    return {
        "granule_ur": f"OPERA_L3_DSWx-S1_{tile}_{acq}Z_{prod}Z_S1A_30_v1.0",
        "begin_utc": f"{acq[:4]}-{acq[4:6]}-{acq[6:8]}T{acq[9:11]}:{acq[11:13]}:00Z",
        "hours_from_nisar": hours,
        "wtr_url": None,
    }


def test_closest_pass_newest_per_tile():
    granules = [
        _g("T30SYJ", "20261028T060900", "20261029T000000", 12.7),  # morning pass, far from NISAR
        _g("T31SBD", "20261028T060900", "20261029T000000", 12.7),
        _g("T30SYJ", "20261028T180200", "20261029T010000", 0.9),   # evening pass, closest
        _g("T31SBD", "20261028T180200", "20261029T010000", 0.9),
        _g("T31SBD", "20261028T180200", "20261105T120000", 0.9),   # reprocessed duplicate, newer
    ]
    sel = select_closest_pass(granules)
    assert [g["granule_ur"].split("_")[3] for g in sel] == ["T30SYJ", "T31SBD"]
    assert all(g["hours_from_nisar"] == 0.9 for g in sel)
    assert sel[1]["granule_ur"].split("_")[5] == "20261105T120000Z"  # the newer reprocessing wins


def test_empty_and_helpers():
    assert select_closest_pass([]) == []
    assert hours_apart("2026-10-28T18:53:18Z", "2026-10-28T18:02:00Z") == (51 * 60 + 18) / 3600
    umm = {"RelatedUrls": [{"URL": "s3://b/x_B01_WTR.tif"}, {"URL": "https://a/x_B02_BWTR.tif"},
                           {"URL": "https://a/x_B01_WTR.tif"}]}
    assert wtr_url(umm) == "https://a/x_B01_WTR.tif"


def test_class_table_matches_rev_a_spec():
    assert WTR_CLASSES[1] == "open_water" and WTR_CLASSES[3] == "inundated_vegetation"
    assert set(WTR_INVALID) == {250, 251, 255}
