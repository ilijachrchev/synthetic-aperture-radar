"""Checks for NISAR granule selection and Harmony output matching. Written with SI assistance (Claude Code)."""

from pipeline.nisar_fetch import (
    acquisition_stamp, assign_outputs, expected_layers, match_layer, select_granules,
)

UR = "NISAR_L2_PR_GCOV_033_066_D_069_{mode}_{pol}_M_{date}T185318_{date}T185353_{crid}_N_{frame}_J_{counter}"


def _g(date, stack="066_D_069", product="GCOV", coverage=1.0, bandwidth="20+5", full=True,
       maturity="PROVISIONAL", crid="P05023", counter="001", pols=("HH", "HV")):
    mode = {"20+5": "2005", "40+5": "4005"}[bandwidth]
    pol = "DHDH" if "HV" in pols else "SHSH"
    return {
        "granule_ur": UR.format(mode=mode, pol=pol, date=date, crid=crid, frame="F" if full else "P", counter=counter),
        "product": product, "stack_id": stack, "site_coverage": coverage, "bandwidth_mhz": bandwidth,
        "full_frame": full, "maturity": maturity, "crid": crid, "pols_a": list(pols),
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


def test_one_granule_per_date_with_the_right_preference():
    cat = {"granules": [
        _g("20260812", bandwidth="40+5"),                        # other mode: dropped by the bandwidth filter
        _g("20260812", full=False, counter="003"),               # partial frame loses to a full frame
        _g("20260812"),
        _g("20260905", counter="001"), _g("20260905", counter="002"),   # reprocessed copy wins
        _g("20261021"), _g("20261021", maturity="VALIDATED", crid="P05036"),  # validated wins
    ]}
    chosen = {acquisition_stamp(g)[:8]: g for g in select_granules(cat, "066_D_069")}
    assert sorted(chosen) == ["20260812", "20260905", "20261021"]
    assert chosen["20260812"]["full_frame"] and "_2005_" in chosen["20260812"]["granule_ur"]
    assert chosen["20260905"]["granule_ur"].endswith("_002")
    assert chosen["20261021"]["maturity"] == "VALIDATED"
    # A stack that only exists in the 40+5 mode is found by asking for that mode.
    assert len(select_granules({"granules": [_g("20260929", bandwidth="40+5")]}, "066_D_069", bandwidth="40+5")) == 1


def test_match_layer_from_harmony_file_names():
    assert match_layer("NISAR_..._20261016T185318_..._HHHH_subsetted.tif") == "HHHH"
    assert match_layer("x_HVHV.tif") == "HVHV"
    assert match_layer("granule__mask_reformatted.tif") == "mask"
    assert match_layer("granule_numberOfLooks.tif") == "numberOfLooks"
    assert match_layer("granule_HHHV.tif") is None  # off-diagonal term, not requested


def test_outputs_are_assigned_by_full_granule_name():
    a, b = _g("20261016"), _g("20261016", counter="002")   # same date and stamp, different granules
    names = [
        f"462923131_{a['granule_ur']}_science_LSAR_GCOV_grids_frequencyA_HHHH_subsetted.tif",
        f"462923132_{a['granule_ur']}_science_LSAR_GCOV_grids_frequencyA_mask_subsetted.tif",
        f"462923133_{b['granule_ur']}_science_LSAR_GCOV_grids_frequencyA_HHHH_subsetted.tif",
        "462923134_some_other_file_HHHH.tif",                                   # no requested granule
        f"462923135_{a['granule_ur']}_science_LSAR_GCOV_grids_frequencyA_HHHV_subsetted.tif",  # unknown layer
    ]
    got = assign_outputs([a, b], names)
    assert set(got[a["granule_ur"]]) == {"HHHH", "mask"}
    assert set(got[b["granule_ur"]]) == {"HHHH"}
    assert got[a["granule_ur"]]["HHHH"].startswith("462923131_")


def test_expected_layers_skip_hv_for_hh_only():
    layers = ("HHHH", "HVHV", "mask")
    assert expected_layers(_g("20260922", pols=("HH",)), layers) == ("HHHH", "mask")
    assert expected_layers(_g("20260910"), layers) == layers
