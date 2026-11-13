"""Checks for NISAR granule selection and Harmony output matching. Written with SI assistance (Claude Code)."""

from pipeline.nisar_fetch import acquisition_stamp, match_layer, select_granules

UR = "NISAR_L2_PR_GCOV_033_066_D_069_2005_DHDH_M_{date}T185318_{date}T185353_P05023_N_F_J_001"


def _g(date, stack="066_D_069", product="GCOV", coverage=1.0):
    return {
        "granule_ur": UR.format(date=date),
        "product": product,
        "stack_id": stack,
        "site_coverage": coverage,
        "begin_utc": f"{date[:4]}-{date[4:6]}-{date[6:]}T18:53:18Z",
    }


def test_select_keeps_one_stack_full_coverage_gcov_sorted():
    cat = {"granules": [
        _g("20261016"), _g("20260618"),
        _g("20261011", stack="167_D_069"),       # other stack
        _g("20260630", coverage=0.52),           # edge hit
        _g("20260712", product="GUNW"),          # not GCOV
    ]}
    chosen = select_granules(cat, "066_D_069")
    assert [acquisition_stamp(g)[:8] for g in chosen] == ["20260618", "20261016"]


def test_match_layer_from_harmony_file_names():
    assert match_layer("NISAR_..._20261016T185318_..._HHHH_subsetted.tif") == "HHHH"
    assert match_layer("x_HVHV.tif") == "HVHV"
    assert match_layer("granule__mask_reformatted.tif") == "mask"
    assert match_layer("granule_numberOfLooks.tif") == "numberOfLooks"
    assert match_layer("granule_HHHV.tif") is None  # off-diagonal term, not requested
