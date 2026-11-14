"""Lorca GUNW check: pair selection, chaining, valid pixels, phase to millimetres, GNSS series."""

import numpy as np

from pipeline.prediction import lorca_gunw as lg


def g(ref, sec, crid="P05023", stack="167_D_069", bw="20", ur="a"):
    return {"product": "GUNW", "stack_id": stack, "bandwidth_mhz": bw, "crid": crid, "granule_ur": ur,
            "reference_utc": f"{ref}T19:01:00Z", "secondary_utc": f"{sec}T19:01:00Z"}


def test_select_pairs_keeps_one_newest_per_pair_and_filters_stack_and_bandwidth():
    cat = {"granules": [g("2026-06-25", "2026-07-07", ur="a"), g("2026-06-25", "2026-07-07", crid="P05024", ur="b"),
                        g("2026-07-07", "2026-07-19", bw="40"), g("2026-07-07", "2026-07-19", stack="066_D_070"),
                        g("2026-07-07", "2026-07-19", ur="c")]}
    got = lg.select_pairs(cat, "167_D_069", "20")
    assert [p["granule_ur"] for p in got] == ["b", "c"]


def test_chain_takes_the_longest_consecutive_run():
    pairs = [g("2026-06-25", "2026-07-07"), g("2026-07-07", "2026-07-19"), g("2026-08-12", "2026-09-17"),
             g("2026-07-19", "2026-08-24")]
    pairs.sort(key=lambda p: p["reference_utc"])
    run = lg.chain(pairs)
    assert [p["reference_utc"][:10] for p in run] == ["2026-06-25", "2026-07-07", "2026-07-19"]


def test_valid_pixels_needs_both_subswaths_no_water_coherence_and_main_component():
    mask = np.array([[11, 11, 10, 111], [11, 11, 11, 11]])         # 10: secondary invalid, 111: water
    d = {"mask": mask, "unwrappedPhase": np.zeros((2, 4)),
         "coherenceMagnitude": np.array([[0.9, 0.9, 0.9, 0.9], [0.9, 0.1, 0.9, 0.9]]),
         "connectedComponents": np.array([[1, 1, 1, 1], [1, 1, 2, 1]])}
    assert lg.valid_pixels(d).tolist() == [[True, True, False, False], [True, False, False, True]]


def test_phase_to_vertical_sign_and_scale():
    f = lg.C / 0.24                       # 24 cm wavelength
    # +2 pi phase = range increase of half a wavelength (12 cm) = away from the satellite; looking straight down: 120 mm down
    assert np.isclose(lg.to_vertical_mm(np.array(2 * np.pi), np.array(1.0), f), -120.0)
    # at 60 deg from vertical the same LOS change is twice the vertical
    assert np.isclose(lg.to_vertical_mm(np.array(2 * np.pi), np.array(0.5), f), -240.0)


def test_gnss_series_averages_around_each_date_and_starts_at_zero(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("date,decimal_year,up_m,sigma_up_m,antenna_height_m\n"
                 "2026-06-24,0,1.000,0,0\n2026-06-26,0,1.002,0,0\n2026-07-07,0,0.995,0,0\n")
    assert lg.gnss_series(["2026-06-25", "2026-07-07", "2026-08-01"], p) == [0.0, -6.0, None]


def test_rate_needs_three_points():
    assert lg.rate_mm_yr(["2026-01-01", "2027-01-01"], [0, -10]) is None
    assert abs(lg.rate_mm_yr(["2026-01-01", "2026-07-02", "2027-01-01"], [0, -5, -10]) + 10) < 0.1


def test_detectable_after_days_grows_with_noise():
    d = ["2026-06-25", "2026-07-07", "2026-07-19"]
    quiet = lg.detectable_after_days(d, 2.0, -48.0)
    noisy = lg.detectable_after_days(d, 10.0, -48.0)
    assert quiet is not None and noisy is not None and quiet < noisy
    assert lg.detectable_after_days(d, 10.0, 0.0, horizon_days=100) is None
