"""Checks for DSWx-S1 label selection per NISAR acquisition. Written with SI assistance (Claude Code)."""

from pipeline.dswx import WTR_CLASSES, WTR_INVALID, group_passes, hours_apart, pick_pass, wtr_url


def _g(tile, acq, prod, platform):
    """A DSWx-S1 granule record; acq and prod are YYYYMMDDTHHMMSS."""
    return {
        "granule_ur": f"OPERA_L3_DSWx-S1_{tile}_{acq}Z_{prod}Z_{platform}_30_v1.0",
        "begin_utc": f"{acq[:4]}-{acq[4:6]}-{acq[6:8]}T{acq[9:11]}:{acq[11:13]}:{acq[13:15]}Z",
        "wtr_url": None,
    }


# One real day pattern at Pego-Oliva: a morning S1C pass and an evening S1D pass.
MORNING = [_g("T30SYJ", "20261016T060900", "20261017T000000", "S1C"),
           _g("T31SBD", "20261016T060910", "20261017T000000", "S1C")]
EVENING = [_g("T30SYJ", "20261016T180100", "20261018T000000", "S1D"),
           _g("T31SBD", "20261016T180110", "20261018T000000", "S1D")]
NISAR_ASC, NISAR_DESC = "2026-10-16T05:06:52Z", "2026-10-16T18:53:18Z"


def test_each_acquisition_gets_its_own_pass():
    day = MORNING + EVENING
    asc, gap_a = pick_pass(day, NISAR_ASC)
    desc, gap_d = pick_pass(day, NISAR_DESC)
    assert {g["granule_ur"].split("_")[6] for g in asc} == {"S1C"} and gap_a < 1.1
    assert {g["granule_ur"].split("_")[6] for g in desc} == {"S1D"} and gap_d < 0.9


def test_only_a_far_pass_reports_the_real_gap():
    desc, gap = pick_pass(MORNING, NISAR_DESC)
    assert len(desc) == 2 and 12.5 < gap < 13.0  # honest gap, not the best gap of another acquisition


def test_reprocessing_in_another_pass_never_mixes_passes():
    reprocessed_morning_tile = _g("T31SBD", "20261016T060910", "20261120T000000", "S1C")  # newest stamp of all
    desc, _ = pick_pass(MORNING + EVENING + [reprocessed_morning_tile], NISAR_DESC)
    assert {g["granule_ur"].split("_")[6] for g in desc} == {"S1D"}


def test_newest_reprocessing_wins_within_the_pass():
    newer = _g("T31SBD", "20261016T180110", "20261105T120000", "S1D")
    desc, _ = pick_pass(EVENING + [newer], NISAR_DESC)
    assert [g["granule_ur"].split("_")[5] for g in desc] == ["20261018T000000Z", "20261105T120000Z"]


def test_pass_grouping_and_helpers():
    assert len(group_passes(MORNING + EVENING)) == 2
    assert pick_pass([], NISAR_DESC) == ([], None)
    assert hours_apart("2026-10-28T18:53:18Z", "2026-10-28T18:02:00Z") == (51 * 60 + 18) / 3600
    umm = {"RelatedUrls": [{"URL": "s3://b/x_B01_WTR.tif"}, {"URL": "https://a/x_B02_BWTR.tif"},
                           {"URL": "https://a/x_B01_WTR.tif"}]}
    assert wtr_url(umm) == "https://a/x_B01_WTR.tif"


def test_class_table_matches_rev_a_spec():
    assert WTR_CLASSES[1] == "open_water" and WTR_CLASSES[3] == "inundated_vegetation"
    assert set(WTR_INVALID) == {250, 251, 255}
