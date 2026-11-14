"""Checks for the coherence input and the optical label cleanup of the CV U-Net. Written with SI assistance (Claude Code)."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from pipeline.cv import coherence as coh_mod
from pipeline.cv.dataset import (
    COH_CHANNEL, IGNORE, INPUTS, CropDataset, Scene, TileDataset, optical_disagreement, scene_arrays, target,
    uses_coherence, uses_reference,
)


def test_coherence_inputs_put_coherence_right_after_hh_and_hv():
    for name in ("current+coh", "current+ref+coh"):
        assert INPUTS[name][:3] == ("hh", "hv", "coh") and INPUTS[name].index("coh") == COH_CHANNEL
        assert uses_coherence(name)
    assert uses_reference("current+ref+coh") and not uses_reference("current+coh")
    assert not uses_coherence("current+ref") and not uses_coherence("current")


def test_uint8_coherence_round_trip_and_nodata():
    coh = np.array([[0.0, 0.004, 0.5], [1.0, np.nan, -0.2]], "float32")
    q = coh_mod.to_uint8(coh)
    assert q[0, 0] == coh_mod.NODATA and q[1, 1] == coh_mod.NODATA and q[1, 2] == coh_mod.NODATA  # not positive or NaN
    back = coh_mod.from_uint8(q)
    assert back[0, 2] == pytest.approx(0.5) and back[1, 0] == pytest.approx(1.0) and back[0, 1] == pytest.approx(0.004)
    assert np.isnan(back[0, 0]) and np.isnan(back[1, 1])


def test_coherence_of_a_date_prefers_the_pair_that_ends_on_it(tmp_path, monkeypatch):
    monkeypatch.setattr(coh_mod, "COHERENCE_DIR", tmp_path)
    folder = tmp_path / "s_000_A_000"
    folder.mkdir()
    for name in ("2026-06-06_2026-06-30", "2026-06-18_2026-06-30", "2026-06-30_2026-07-12", "2026-06-18_2026-07-24"):
        (folder / f"{name}.tif").write_bytes(b"")
    # ending on the date wins, and of those the shortest pair (latest reference date)
    assert coh_mod.coherence_path("s", "000_A_000", "2026-06-30").stem == "2026-06-18_2026-06-30"
    # no pair ends on the first date: the pair that starts on it, with the earliest secondary date
    assert coh_mod.coherence_path("s", "000_A_000", "2026-06-18").stem == "2026-06-18_2026-06-30"
    assert coh_mod.coherence_path("s", "000_A_000", "2026-08-01") is None
    out = coh_mod.coherence_for("s", "000_A_000", "2026-08-01", (3, 4))
    assert out.shape == (3, 4) and np.isnan(out).all()


def _stack(h: int = 6, w: int = 5) -> xr.Dataset:
    hh = np.full((1, h, w), 0.01, "float32")
    hv = np.full((1, h, w), 0.001, "float32")
    hh[0, 0, 0] = np.nan                       # not usable
    valid = np.ones((1, h, w), "uint8")
    valid[0, 1, 1] = 0                         # not usable
    return xr.Dataset({"HH": (("time", "y", "x"), hh), "HV": (("time", "y", "x"), hv),
                       "valid": (("time", "y", "x"), valid)},
                      coords={"time": pd.to_datetime(["2026-06-18"])})


def test_scene_arrays_adds_coherence_without_changing_usable_pixels():
    ds = _stack()
    coh = np.full((6, 5), 0.7, "float32")
    coh[2, 2] = np.nan                         # no pair covers this pixel
    x0, y0 = scene_arrays(ds, 0, np.zeros((6, 5), "uint8"), label_mode="water13")
    x, y = scene_arrays(ds, 0, np.zeros((6, 5), "uint8"), label_mode="water13", coherence=coh)
    assert x.shape == (3, 6, 5)
    np.testing.assert_array_equal(x[:2], x0[:2])
    np.testing.assert_array_equal(y, y0)          # a missing coherence drops no label
    assert y[2, 2] != IGNORE and np.isnan(x[COH_CHANNEL, 2, 2])
    assert np.isnan(x[COH_CHANNEL, 0, 0]) and np.isnan(x[COH_CHANNEL, 1, 1])  # unusable stays unusable
    assert x[COH_CHANNEL, 3, 3] == pytest.approx(0.7)
    ref = np.full((4, 6, 5), -12.0, "float32")
    x_ref, _ = scene_arrays(ds, 0, reference=ref, coherence=coh)
    assert x_ref.shape == (7, 6, 5) and x_ref[3, 2, 2] == pytest.approx(-12.0)  # ref kept where coherence is missing


def _coh_scene(seed: int = 0, shape: tuple[int, int] = (128, 128)) -> Scene:
    rng = np.random.default_rng(seed)
    cls = np.zeros(shape, "uint8")
    cls[20:60, 10:100] = 1
    hh = np.where(cls == 1, -24.0, -8.0) + rng.normal(0, 1.0, shape)
    hv = np.where(cls == 1, -30.0, -16.0) + rng.normal(0, 1.0, shape)
    coh = np.where(cls == 1, 0.2, 0.8) + rng.uniform(-0.05, 0.05, shape)
    coh[:5, :5] = np.nan
    x = np.stack([hh, hv, coh]).astype("float32")
    usable = np.isfinite(x[:2]).all(axis=0)
    y = target(cls, usable, "water13")
    return Scene("a", "000_D_000", "2026-06-18", x.astype("float16"), y, cls.copy(), None, 0.5, COH_CHANNEL)


def test_crop_keeps_the_reference_where_only_coherence_is_missing():
    s = _coh_scene()
    s.ref = np.full((4, 128, 128), -10.0, "float16")
    crop = s.crop(0, 0, 16)
    assert crop.shape == (7, 16, 16)
    assert np.isnan(crop[COH_CHANNEL, 0, 0]) and np.isfinite(crop[3:, 0, 0]).all()


def test_jitter_moves_db_channels_but_never_coherence():
    s = _coh_scene()
    # one window (the whole scene), so every item is the same pixels, only turned or flipped
    ds = CropDataset([s], np.ones(s.shape, bool), np.zeros(3, "float32"), np.ones(3, "float32"),
                     samples=12, size=128, jitter_db=3.0)
    assert len(ds.pool) == 1
    means = np.array([[x.numpy()[c].mean() for c in range(3)] for x, _ in (ds[0] for _ in range(12))])
    assert means[:, 0].std() > 0.3 and means[:, 1].std() > 0.3      # HH and HV get the random offset
    assert means[:, COH_CHANNEL].std() < 1e-5                        # coherence never does
    assert np.allclose(means[:, 0] - means[:, 1], means[0, 0] - means[0, 1], atol=0.01)  # one offset for both


def test_coherence_dropout_blanks_the_channel_like_a_date_without_a_pair():
    s = _coh_scene()
    always = CropDataset([s], np.ones(s.shape, bool), np.zeros(3, "float32"), np.ones(3, "float32"),
                         samples=4, size=128, coh_dropout=1.0)
    never = CropDataset([s], np.ones(s.shape, bool), np.zeros(3, "float32"), np.ones(3, "float32"),
                        samples=4, size=128, coh_dropout=0.0)
    x_always, x_never = always[0][0].numpy(), never[0][0].numpy()
    assert (x_always[COH_CHANNEL] == 0).all()          # blanked: the channel mean after standardizing
    assert x_never[COH_CHANNEL].std() > 0.1
    assert np.isfinite(x_always).all()


def test_optical_disagreement_rules():
    s1 = np.array([[1, 1, 0, 0, 3, 3, 250, 1]], "uint8")
    opt = np.array([[0, 1, 1, 0, 0, 1, 1, 253]], "uint8")
    drop = optical_disagreement(s1, opt)
    # S1 open + optical dry: drop; agree: keep; S1 dry + optical open: drop; both dry: keep;
    # inundated vegetation: always keep; masked label: keep; cloudy optical: keep
    assert drop.tolist() == [[True, False, True, False, False, False, False, False]]
    assert not optical_disagreement(s1, np.full_like(opt, 2)).any()   # partial water never decides


def test_dropped_labels_are_neither_trained_nor_scored():
    s = _coh_scene()
    dropped = np.zeros(s.shape, bool)
    dropped[20:60, 10:100] = True              # pretend optical contradicts the whole water patch
    s.dropped, s.cleaned_px = dropped, int(dropped.sum())
    crops = CropDataset([s], np.ones(s.shape, bool), np.zeros(3, "float32"), np.ones(3, "float32"),
                        samples=4, size=128)
    _, y = crops[0]
    assert (y.numpy() == 1).sum() == 0 and (y.numpy() == IGNORE).sum() >= dropped.sum()
    tiles = TileDataset([s], np.ones(s.shape, bool), np.zeros(3, "float32"), np.ones(3, "float32"), size=128)
    assert len(tiles) == 1                     # tiles come from the uncleaned labels
    _, cls = tiles[0]
    assert (cls.numpy()[dropped] == IGNORE).all() and (cls.numpy()[~dropped & (s.cls == 0)] == 0).all()
