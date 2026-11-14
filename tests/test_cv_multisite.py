"""Checks for training the CV U-Net on several sites (compact scenes, per-site blocks). Written with SI assistance (Claude Code)."""

import numpy as np
import pytest

from pipeline.config import CV_LABEL_SITES, CV_STACKS, STACKS, site_stacks
from pipeline.cv.dataset import IGNORE, CropDataset, Scene, blocks_mask, channel_stats, target
from pipeline.cv.train import TrainConfig, train


def _scene(site: str, seed: int, shape: tuple[int, int] = (256, 256), shared_ref: np.ndarray | None = None) -> Scene:
    """Synthetic scene with an open water patch and a dead strip; optional shared reference channels."""
    rng = np.random.default_rng(seed)
    h, w = shape
    cls = np.zeros(shape, "uint8")
    cls[40:120, 30:200] = 1
    hh = np.where(cls == 1, -24.0, -8.0) + rng.normal(0, 1.5, shape)
    hv = np.where(cls == 1, -30.0, -16.0) + rng.normal(0, 1.5, shape)
    x = np.stack([hh, hv]).astype("float32")
    x[:, :, :8] = np.nan
    usable = np.isfinite(x).all(axis=0)
    y = target(cls, usable, "water13")
    cls = np.where(usable, cls, IGNORE).astype("uint8")
    return Scene(site, "000_D_000", f"2026-10-{seed + 10}", x.astype("float16"), y, cls, shared_ref)


def test_site_stacks_cover_shared_and_cv_only_sites():
    assert site_stacks("albufera") == STACKS["albufera"]
    assert site_stacks("ebro") == CV_STACKS["ebro"]
    assert set(CV_LABEL_SITES) >= {"albufera", "pego_oliva", "ebro", "camargue", "donana"}
    assert not set(CV_STACKS) & set(STACKS)          # CV-only sites never reach pipeline.run
    with pytest.raises(KeyError):
        site_stacks("lorca")


def test_shared_reference_crops_like_the_old_copied_inputs():
    rng = np.random.default_rng(0)
    ref = rng.normal(-10, 2, (4, 256, 256)).astype("float16")
    s = _scene("a", 0, shared_ref=ref)
    other = _scene("a", 1, shared_ref=ref)
    assert other.ref is s.ref                                          # one array per stack, not a copy
    crop = s.crop(10, 0, 64)
    assert crop.shape == (6, 64, 64) and crop.dtype == np.float32
    # the old layout: reference appended, NaN where the date is not usable
    old_ref = ref.astype("float32").copy()
    old_ref[:, ~np.isfinite(s.x.astype("float32")).all(axis=0)] = np.nan
    old = np.concatenate([s.x.astype("float32"), old_ref])
    np.testing.assert_array_equal(np.isnan(crop), np.isnan(old[:, 10:74, 0:64]))
    np.testing.assert_allclose(crop, old[:, 10:74, 0:64], equal_nan=True)
    assert s.full().shape == (6, 256, 256)
    assert np.isfinite(ref[:, :, :8]).all() and np.isnan(s.full()[2:, :, :8]).all()  # shared array left untouched


def test_streaming_channel_stats_match_a_concatenation():
    scenes = [_scene("a", 0), _scene("b", 1, (320, 256))]
    region = {"a": np.ones((256, 256), bool), "b": np.zeros((320, 256), bool)}
    region["b"][:160] = True
    mean, std = channel_stats(scenes, region)
    for c in range(2):
        values = np.concatenate([np.clip(s.x[c].astype("float32")[region[s.site] & (s.y != IGNORE)], -35, 5)
                                 for s in scenes])
        values = values[np.isfinite(values)]
        assert mean[c] == pytest.approx(values.mean(), abs=1e-4)
        assert std[c] == pytest.approx(values.std(), abs=1e-4)


def test_crops_stay_inside_each_sites_own_region():
    scenes = [_scene("a", 0), _scene("b", 1, (320, 256))]
    allowed = {"a": np.zeros((256, 256), bool), "b": np.zeros((320, 256), bool)}
    allowed["a"][:128, :] = True
    allowed["b"][192:, :] = True
    ds = CropDataset(scenes, allowed, np.zeros(2, "float32"), np.ones(2, "float32"), samples=4, size=64)
    for i, (r, c) in ds.pool:
        assert allowed[scenes[i].site][r:r + 64, c:c + 64].all()
    assert {scenes[i].site for i, _ in ds.pool} == {"a", "b"}


def test_older_labels_add_training_crops_but_never_validation():
    from pipeline.cv.dataset import WATER_CLASSES, choose_validation_blocks

    clean = [_scene("a", s) for s in range(2)]
    old = _scene("a", 5)
    old.gap_h = 13.0
    old.cls[150:, :] = 1                         # water that no same-pass scene has

    def weight(ss):
        return sum(np.isin(s.cls, WATER_CLASSES).astype("float64") for s in ss)

    # if the older scene were used for the stratified blocks, they would move
    assert (choose_validation_blocks((256, 256), 0.25, 0, 64, weight(clean))
            != choose_validation_blocks((256, 256), 0.25, 0, 64, weight(clean + [old])))
    cfg = TrainConfig(sites=("a",), epochs=1, samples_per_epoch=8, batch=4, tile=64, block=64,
                      val_share=0.25, encoder_weights=None)
    permanent = {"a": np.zeros((256, 256), bool)}
    with_old = train(cfg, scenes=clean + [old], permanent=permanent, device="cpu")
    without = train(cfg, scenes=clean, permanent=permanent, device="cpu")
    assert with_old["val_blocks"] == without["val_blocks"]
    assert len(with_old["train_scenes"]) == 3


def test_two_site_training_keeps_blocks_per_site(tmp_path):
    from pipeline.cv.evaluate import train_sites_of, training_region
    from pipeline.cv.predict import load_model

    scenes = [_scene("a", s) for s in range(2)] + [_scene("b", s, (320, 256)) for s in range(2, 4)]
    permanent = {"a": np.zeros((256, 256), bool), "b": np.zeros((320, 256), bool)}
    cfg = TrainConfig(sites=("a", "b"), epochs=1, samples_per_epoch=8, batch=4, tile=64, block=64,
                      val_share=0.25, encoder_weights=None)
    out = tmp_path / "m.pt"
    summary = train(cfg, scenes=scenes, permanent=permanent, out=out, device="cpu")
    assert summary["train_sites"] == ["a", "b"] and set(summary["val_blocks"]) == {"a", "b"}
    assert set(summary["history"][0]["val_open_dynamic_by_site"]) == {"a", "b"}
    _, _, _, ckpt = load_model(out, device="cpu")
    assert train_sites_of(ckpt) == ["a", "b"]
    for site, shape in (("a", (256, 256)), ("b", (320, 256))):
        held = blocks_mask(shape, ckpt["val_blocks"][site], 64)
        assert 0 < held.mean() < 0.5
    with pytest.raises(KeyError):            # synthetic sites have no grid in the config
        training_region(ckpt, "a")
