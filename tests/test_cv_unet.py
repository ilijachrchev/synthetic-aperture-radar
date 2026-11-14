"""Smoke tests for the U-Net data, losses, training loop and prediction (CPU, tiny). Written with SI assistance (Claude Code)."""

import numpy as np
import pytest
import torch

from pipeline.cv.dataset import IGNORE, Scene, nan_quantile0, target, validation_blocks, windows
from pipeline.cv.model import expand_conv1
from pipeline.cv.predict import load_model, predict_scene, water_probabilities
from pipeline.cv.train import TrainConfig, masked_loss, masked_loss_multi, train


def _scene(seed: int, size: int = 256, reference: bool = False, label_mode: str = "water13") -> Scene:
    """Synthetic scene: an open water patch (dark), a flooded vegetation patch (bright HH), a dead strip."""
    rng = np.random.default_rng(seed)
    cls = np.zeros((size, size), "uint8")
    cls[40:120, 30:200] = 1                                 # open water
    cls[150:210, 40:140] = 3                                # inundated vegetation
    hh = np.select([cls == 1, cls == 3], [-24.0, -3.0], -8.0) + rng.normal(0, 1.5, cls.shape)
    hv = np.select([cls == 1, cls == 3], [-30.0, -14.0], -16.0) + rng.normal(0, 1.5, cls.shape)
    x = np.stack([hh, hv]).astype("float32")
    if reference:  # the usual state of every pixel: dry land
        x = np.concatenate([x, np.stack([v + rng.normal(0, 0.5, cls.shape) for v in (-8.0, -16.0, -6.0, -14.0)])
                            .astype("float32")])
    x[:, :, :8] = np.nan                                    # an unusable strip
    usable = np.isfinite(x[:2]).all(axis=0)
    y = target(cls, usable, label_mode)
    cls = np.where(usable, cls, IGNORE).astype("uint8")
    return Scene("synthetic", "000_D_000", f"2026-10-{seed + 10}", x, y, cls)


def test_validation_blocks_and_windows_never_overlap():
    val = validation_blocks((256, 256), share=0.2, seed=0, block=64)
    assert 0.1 < val.mean() < 0.3
    y = np.zeros((256, 256), "uint8")
    for r, c in windows(~val, y, size=64, step=16):
        assert not val[r:r + 64, c:c + 64].any()
    # Same seed, same blocks.
    assert np.array_equal(val, validation_blocks((256, 256), share=0.2, seed=0, block=64))


def test_stratified_blocks_get_a_fair_share_of_rare_water():
    from pipeline.cv.dataset import block_ids, choose_validation_blocks

    shape = (512, 512)                     # 64 blocks of 64 px
    weight = np.zeros(shape)
    weight[:128, :128] = 1.0               # rare water in 4 of 64 blocks
    weight[256:384, 256:512] = 1.0         # plus 8 more blocks
    ids = choose_validation_blocks(shape, share=0.25, seed=0, block=64, weight=weight)
    held = np.isin(block_ids(shape, 64), ids)
    assert len(ids) == 16
    assert 0.15 <= weight[held].sum() / weight.sum() <= 0.35   # about the requested share, not 0 or all


def test_focus_crops_contain_the_rare_class():
    from pipeline.cv.dataset import CropDataset

    s = _scene(0)
    focus = np.ones(s.y.shape, bool)
    ds = CropDataset([s], np.ones(s.y.shape, bool), np.zeros(2, "float32"), np.ones(2, "float32"),
                     samples=20, size=64, seed=0, focus=focus, focus_share=1.0, min_focus_px=200)
    assert ds.focus_pool and all(int((y == 1).sum()) >= 200 for _, y in (ds[i] for i in range(20)))


def test_label_modes_from_dswx_classes():
    water_map = np.array([[0, 1, 3, 250]], "uint8")
    usable = np.ones(water_map.shape, bool)
    assert target(water_map, usable, "water13").tolist() == [[0, 1, 1, IGNORE]]
    assert target(water_map, usable, "open1").tolist() == [[0, 1, 0, IGNORE]]
    assert target(water_map, usable, "three").tolist() == [[0, 1, 2, IGNORE]]
    with pytest.raises(ValueError):
        target(water_map, usable, "water")


def test_nan_quantile_matches_numpy():
    rng = np.random.default_rng(0)
    a = rng.normal(-10, 3, (13, 500)).astype("float32")
    a[rng.random(a.shape) < 0.2] = np.nan
    a[:, 0] = np.nan                                      # a pixel never seen
    for q in (0.5, 0.9):
        expected = np.nanpercentile(a[:, 1:], 100 * q, axis=0)
        got = nan_quantile0(a, q)
        assert np.isnan(got[0])
        np.testing.assert_allclose(got[1:], expected, rtol=1e-5, atol=1e-5)


def test_expand_conv1_keeps_polarisation_order_and_scale():
    w = torch.randn(64, 2, 7, 7)
    assert torch.equal(expand_conv1(w, 2), w)
    w6 = expand_conv1(w, 6)
    assert w6.shape == (64, 6, 7, 7)
    assert torch.allclose(w6[:, 0], w[:, 0] / 3) and torch.allclose(w6[:, 3], w[:, 1] / 3)  # hh, hv_median
    assert torch.allclose(w6.sum(dim=1), w.sum(dim=1), atol=1e-6)   # same response when all channels agree


def test_masked_losses_ignore_unlabelled_pixels():
    y = torch.full((1, 4, 4), IGNORE, dtype=torch.uint8)
    y[0, 0, 0] = 1
    y2 = y.clone()
    y2[0, 3, 3] = IGNORE  # still ignored: losses must not change
    assert torch.isclose(masked_loss(torch.zeros(1, 4, 4), y), masked_loss(torch.zeros(1, 4, 4), y2))
    logits = torch.randn(1, 3, 4, 4)
    assert torch.isclose(masked_loss_multi(logits, y), masked_loss_multi(logits, y2))


def test_tiny_training_run_and_prediction(tmp_path):
    scenes = [_scene(s) for s in range(3)]
    cfg = TrainConfig(epochs=2, samples_per_epoch=8, batch=4, tile=64, block=64, val_share=0.2, encoder_weights=None)
    out = tmp_path / "m.pt"
    summary = train(cfg, scenes=scenes, permanent=np.zeros((256, 256), bool), out=out, device="cpu")
    assert len(summary["history"]) == 2 and out.exists()
    model, mean, std, ckpt = load_model(out, device="cpu")
    assert ckpt["config"]["tile"] == 64 and len(mean) == 2
    prob = predict_scene(model, scenes[0].x, mean, std, tile=64, overlap=16)
    assert prob.shape == (256, 256)
    assert np.isnan(prob[:, :8]).all() and np.isfinite(prob[:, 8:]).all()
    assert ((prob[:, 8:] >= 0) & (prob[:, 8:] <= 1)).all()


def test_three_classes_with_reference_inputs(tmp_path):
    scenes = [_scene(s, reference=True, label_mode="three") for s in range(3)]
    cfg = TrainConfig(epochs=2, samples_per_epoch=8, batch=4, tile=64, block=64, val_share=0.2,
                      encoder_weights=None, inputs="current+ref", label_mode="three", jitter_db=1.0)
    out = tmp_path / "m3.pt"
    summary = train(cfg, scenes=scenes, permanent=np.zeros((256, 256), bool), out=out, device="cpu")
    assert {"val_open_dynamic", "val_any_dynamic"} <= set(summary["history"][0])
    model, mean, std, ckpt = load_model(out, device="cpu")
    assert len(mean) == 6 and ckpt["input_channels"][2] == "hh_median"
    prob = predict_scene(model, scenes[0].x, mean, std, tile=64, overlap=16)
    assert prob.shape == (3, 256, 256)
    np.testing.assert_allclose(prob[:, :, 8:].sum(axis=0), 1.0, atol=1e-4)
    p_open, p_any = water_probabilities(prob)
    assert np.isnan(p_open[:, :8]).all() and (p_any[:, 8:] >= p_open[:, 8:] - 1e-6).all()
