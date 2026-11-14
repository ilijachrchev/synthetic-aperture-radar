"""Equipment-change steps in the Lorca trend models, and the committed station CSV loader (issue #16)."""

from datetime import date, timedelta

import numpy as np
import pytest

from pipeline.prediction.data import load_context_csv
from pipeline.prediction.models import MIN_AFTER_STEP, fit_model


def test_step_term_absorbs_a_level_jump_instead_of_bending_the_trend():
    days = np.arange(0, 800, dtype=float)
    values = -0.1 * days + np.where(days >= 400, -30.0, 0.0)
    with_step = fit_model("linear", days, values, steps=(400.0,))
    without = fit_model("linear", days, values)
    assert with_step.steps == (400.0,)
    assert with_step.coefficients[1] == pytest.approx(-0.1 * 365.25, rel=1e-6)   # trend in mm per year
    assert abs(without.coefficients[1] - (-0.1 * 365.25)) > 1
    assert with_step.predict(np.array([900.0]))[0] == pytest.approx(-120.0, abs=1e-6)


def test_step_needs_enough_data_after_it_and_must_be_inside_the_window():
    days = np.arange(0, 400, dtype=float)
    values = -0.1 * days
    assert fit_model("linear", days, values, steps=(400.0 - MIN_AFTER_STEP + 5,)).steps == ()
    assert fit_model("linear", days, values, steps=(0.0,)).steps == ()
    assert fit_model("persistence", days, values, steps=(200.0,)).coefficients[0] == values[-1]


def test_context_csv_loader_records_antenna_changes_and_filters_sigma(tmp_path):
    path = tmp_path / "lorca_gnss_LOR1_up.csv"
    start = date(2023, 1, 1)
    lines = ["date,decimal_year,up_m,sigma_up_m,antenna_height_m"]
    for i in range(5):
        lines.append(f"{start + timedelta(days=i)},2023.0,{365.0 - i / 1000},0.003,{0.0 if i < 3 else 0.0771}")
    lines.append(f"{start + timedelta(days=5)},2023.0,364.0,0.5,0.0771")   # sigma 500 mm: rejected
    path.write_text("\n".join(lines) + "\n")
    s = load_context_csv(path, "LOR1")
    assert len(s.dates) == 5 and s.source["quality_filter"]["rejected_rows_in_source"] == 1
    assert s.source["equipment_changes"] == ["2023-01-04"]
    assert s.steps == (float(date(2023, 1, 4).toordinal()),)
    np.testing.assert_allclose(s.values - s.values[0], [0, -1, -2, -3, -4], atol=1e-6)
