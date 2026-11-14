"""Checks for the CV benchmark tables (pooled IoU, bootstrap intervals, paired differences). Written with SI assistance (Claude Code)."""

import numpy as np
import pytest

from pipeline.cv.benchmark import TEST_SPLIT, bootstrap_weights, pooled_iou, summarize


def _row(model: str, stack: str, date: str, tp: int, fp: int, fn: int, split: str = TEST_SPLIT) -> dict:
    iou = tp / (tp + fp + fn)
    return {"site": "s", "stack": stack, "date": date, "model": model, "split": split, "iou": iou, "any_iou": iou,
            "tp": tp, "fp": fp, "fn": fn, "any_tp": tp, "any_fp": fp, "any_fn": fn}


def test_pooled_iou_weighs_dates_by_their_pixels():
    c = np.array([[90, 100], [1, 10]], dtype=float)       # a big good date, a small bad one
    assert pooled_iou(c) == pytest.approx(91 / 110)         # not the mean of 0.9 and 0.1
    w = np.array([[2, 0], [0, 2]], dtype=float)             # two draws: only date 0, only date 1
    np.testing.assert_allclose(pooled_iou(c, w), [0.9, 0.1])


def test_bootstrap_resamples_within_each_stack():
    w = bootstrap_weights(["a", "a", "a", "b"], n_boot=200)
    np.testing.assert_array_equal(w[:, :3].sum(axis=1), 3)   # stack a keeps its 3 dates per draw
    np.testing.assert_array_equal(w[:, 3], 1)                # stack b has one date, always drawn once


def test_paired_difference_of_a_clearly_better_model():
    rows = []
    for i in range(12):
        d = f"2026-10-{i + 10}"
        rows += [_row("baseline", "001_A_001", d, 10, 40, 50), _row("unet", "001_A_001", d, 60, 20, 20)]
    report = {"water_vs_dswx": rows}
    summary = summarize({"m": report}, n_boot=300)
    site = next(e for e in summary if e["site"] == "s")
    assert site["dates"] == 12
    assert site["models"]["baseline"]["open"]["pooled_iou"] == pytest.approx(0.1)
    assert site["models"]["m"]["open"]["pooled_iou"] == pytest.approx(0.6)
    diff = site["differences"]["m - baseline"]["open"]
    assert diff["pooled_iou"] == pytest.approx(0.5) and diff["share_of_draws_better"] == 1.0
    assert any(e["site"] == "all test sites" for e in summary)


def test_dates_one_model_did_not_score_are_left_out_of_both():
    rows = [_row("baseline", "001_A_001", "2026-10-10", 10, 10, 10), _row("unet", "001_A_001", "2026-10-10", 20, 5, 5),
            _row("baseline", "001_A_001", "2026-10-22", 1, 99, 0)]          # no U-Net row on 22 Oct
    summary = summarize({"m": {"water_vs_dswx": rows}}, n_boot=50)
    site = next(e for e in summary if e["site"] == "s")
    assert site["dates"] == 1 and site["models"]["baseline"]["open"]["pooled_iou"] == pytest.approx(1 / 3, abs=1e-4)
