"""The shared manifest: one list keyed by (model, site, stack, layer), as in pipeline.ml.export."""

import json

import pytest

from pipeline.prediction import manifest

ML = {"model": "ml", "site": "albufera", "stack": "066_D_069", "layer": "class", "file": "class.tif"}
CV = {"model": "cv", "site": "albufera", "stack": "066_D_069", "layer": "water", "file": "water.tif"}


def forecast(date, file="forecast.json"):
    return {"model": "prediction", "site": "albufera", "stack": "dswx-s1", "layer": "flooded_area",
            "date": date, "file": file}


def test_keeps_entries_written_by_other_models(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([ML, CV]))
    manifest.upsert(path, [forecast("2026-11-14")])
    assert json.loads(path.read_text()) == [ML, CV, forecast("2026-11-14")]


def test_rerun_with_a_later_origin_replaces_its_entry(tmp_path):
    """One output directory holds one forecast; a stale entry would point at the overwritten file."""
    path = tmp_path / "manifest.json"
    manifest.upsert(path, [forecast("2026-11-14")])
    manifest.upsert(path, [forecast("2026-11-26")])
    assert [e["date"] for e in json.loads(path.read_text())] == ["2026-11-26"]


def test_another_stack_of_the_same_site_is_kept(tmp_path):
    path = tmp_path / "manifest.json"
    other = {**forecast("2026-11-14"), "stack": "nisar-cv"}
    manifest.upsert(path, [forecast("2026-11-14"), other])
    manifest.upsert(path, [forecast("2026-11-26")])
    assert sorted(e["stack"] for e in json.loads(path.read_text())) == ["dswx-s1", "nisar-cv"]


def test_output_is_readable_by_the_ml_writer_logic(tmp_path):
    """Mirror of pipeline.ml.export.upsert_manifest: it needs a list of dicts with .get()."""
    path = tmp_path / "manifest.json"
    manifest.upsert(path, [forecast("2026-11-14")])
    existing = json.loads(path.read_text())
    key = lambda e: (e.get("model"), e.get("site"), e.get("stack"), e.get("layer"))  # noqa: E731
    assert [key(e) for e in existing] == [("prediction", "albufera", "dswx-s1", "flooded_area")]


def test_old_object_format_is_converted(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "layers": [CV], "forecasts": [{"id": "old"}]}))
    manifest.upsert(path, [forecast("2026-11-14")])
    assert json.loads(path.read_text()) == [CV, {"id": "old"}, forecast("2026-11-14")]


def test_rejects_entries_without_the_key(tmp_path):
    with pytest.raises(ValueError, match="layer"):
        manifest.upsert(tmp_path / "m.json", [{"model": "prediction", "site": "x", "stack": "s"}])
