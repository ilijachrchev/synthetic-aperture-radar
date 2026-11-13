"""Checks for the CMR catalog parsing. Written with SI assistance (Claude Code)."""

from pipeline.catalog import granule_entry, maturity_of, parse_title_dates, site_coverage

GCOV_UR = "NISAR_L2_PR_GCOV_033_066_D_069_2005_DHDH_M_20261016T185318_20261016T185353_P05023_N_F_J_001"
GUNW_UR = (
    "NISAR_L2_PR_GUNW_031_141_D_085_032_2000_SH_20260927T235335_20260927T235348"
    "_20261009T235335_20261009T235349_P05023_N_P_J_001"
)


def _umm(ur: str) -> dict:
    """A trimmed copy of a real CMR UMM-G record (fields the parser reads)."""
    return {
        "GranuleUR": ur,
        "AdditionalAttributes": [
            {"Name": "TRACK_NUMBER", "Values": ["66"]},
            {"Name": "ASCENDING_DESCENDING", "Values": ["DESCENDING"]},
            {"Name": "FRAME_NUMBER", "Values": ["69"]},
            {"Name": "STACK_ID", "Values": ["066_D_069"]},
            {"Name": "FULL_FRAME", "Values": ["TRUE"]},
            {"Name": "RANGE_BANDWIDTH_CONCAT", "Values": ["20+5"]},
            {"Name": "FREQUENCY_A_POLARIZATION", "Values": ["HH", "HV"]},
            {"Name": "PRODUCT_VERSION", "Values": ["1.0.11"]},
        ],
        "RelatedUrls": [
            {"URL": f"https://example.org/{ur}.h5"},
            {"URL": f"https://example.org/{ur}_LATLON.png"},
            {"URL": f"s3://bucket/{ur}.h5"},
        ],
        "TemporalExtent": {
            "RangeDateTime": {
                "BeginningDateTime": "2026-10-16T18:53:18Z",
                "EndingDateTime": "2026-10-16T18:53:53Z",
            }
        },
        "SpatialExtent": {
            "HorizontalSpatialDomain": {
                "Geometry": {
                    "GPolygons": [
                        {
                            "Boundary": {
                                "Points": [
                                    {"Longitude": -0.57, "Latitude": 40.05},
                                    {"Longitude": -1.39, "Latitude": 37.94},
                                    {"Longitude": 1.32, "Latitude": 37.25},
                                    {"Longitude": 2.22, "Latitude": 39.34},
                                    {"Longitude": -0.57, "Latitude": 40.05},
                                ]
                            }
                        }
                    ]
                }
            }
        },
    }


def test_maturity_from_collection_name():
    assert maturity_of("NISAR_L2_GCOV_PROVISIONAL_V1") == "PROVISIONAL"
    assert maturity_of("NISAR_L2_GCOV_BETA_V1") == "BETA"
    assert maturity_of("NISAR_L2_GCOV_V1") == "VALIDATED"


def test_title_dates_in_order():
    assert parse_title_dates(GUNW_UR) == [
        "20260927T235335",
        "20260927T235348",
        "20261009T235335",
        "20261009T235349",
    ]


def test_gcov_entry_fields():
    e = granule_entry(_umm(GCOV_UR), "NISAR_L2_GCOV_PROVISIONAL_V1", "GCOV")
    assert e["stack_id"] == "066_D_069"
    assert e["crid"] == "P05023"
    assert e["maturity"] == "PROVISIONAL"
    assert e["pols_a"] == ["HH", "HV"]
    assert e["full_frame"] is True
    assert e["h5_url"].endswith(".h5") and e["h5_url"].startswith("https")
    assert e["browse_url"].endswith("_LATLON.png")
    assert len(e["footprint"]) == 5
    assert "reference_utc" not in e


def test_site_coverage_full_partial_none():
    frame = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)]
    assert site_coverage(frame, (1.0, 1.0, 2.0, 2.0)) == 1.0
    assert site_coverage(frame, (9.0, 1.0, 11.0, 2.0)) == 0.5
    assert site_coverage(frame, (20.0, 20.0, 21.0, 21.0)) == 0.0


def test_gunw_entry_has_pair_dates():
    e = granule_entry(_umm(GUNW_UR), "NISAR_L2_GUNW_PROVISIONAL_V1", "GUNW")
    assert e["reference_utc"].startswith("2026-09-27T23:53:35")
    assert e["secondary_utc"].startswith("2026-10-09T23:53:35")
