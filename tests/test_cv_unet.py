"""Smoke tests for the U-Net data split, training loop and prediction (CPU, tiny). Written with SI assistance (Claude Code)."""

import numpy as np
import torch

from pipeline.cv.dataset import IGNORE, Scene, validation_blocks, windows
from pipeline.cv.predict import load_model, predict_scene
from pipeline.cv.train import TrainConfig, masked_loss, train


def _scene(seed: int, size: int = 256) -> Scene:
    rng = np.random.default_rng(seed)
    y = np.zeros((size, size), "uint8")
    y[40:120, 30:200] = 1                                   # a water patch
    hh = np.where(y == 1, -24.0, -8.0) + rng.normal(0, 1.5, y.shape)
    hv = np.where(y == 1, -30.0, -16.0) + rng.normal(0, 1.5, y.shape)
    x = np.stack([hh, hv]).astype("float32")
    x[:, :, :8] = np.nan                                    # an unusable strip
    y[:, :8] = IGNORE
    return Scene("synthetic", "000_D_000", f"2026-10-{seed + 10}", x, y)


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
    weight[:128, :128] = 1.0               # rare water only in 4 of 64 blocks... spread wider below
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


def test_masked_loss_ignores_unlabelled_pixels():
    logits = torch.zeros(1, 4, 4)
    y = torch.full((1, 4, 4), IGNORE, dtype=torch.uint8)
    y[0, 0, 0] = 1
    loss_one = masked_loss(logits, y)
    y2 = y.clone()
    y2[0, 3, 3] = IGNORE  # still ignored: loss must not change
    assert torch.isclose(loss_one, masked_loss(logits, y2))


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
