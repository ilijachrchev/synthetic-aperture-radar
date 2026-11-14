"""The shared manifest: one list keyed by (model, site, layer, date), as in pipeline.ml.export."""

import json

import pytest

from pipeline.prediction import manifest

ML = {"model": "ml", "site": "albufera", "layer": "class", "date": "2026-10-28", "file": "class.tif"}
CV = {"model": "cv", "site": "albufera", "layer": "water", "date": "2026-10-28", "file": "water.tif"}


def forecast(date, file="forecast.json"):
    return {"model": "prediction", "site": "albufera", "layer": "flooded_area", "date": date, "file": file}


def test_keeps_entries_written_by_other_models(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([ML, CV]))
    manifest.upsert(path, [forecast("2026-11-14")])
    assert json.loads(path.read_text()) == [ML, CV, forecast("2026-11-14")]


def test_same_key_replaces_and_new_date_is_added(tmp_path):
    path = tmp_path / "manifest.json"
    manifest.upsert(path, [forecast("2026-11-14", "old.json")])
    manifest.upsert(path, [forecast("2026-11-14", "new.json")])
    manifest.upsert(path, [forecast("2026-11-26")])
    data = json.loads(path.read_text())
    assert [(e["date"], e["file"]) for e in data] == [("2026-11-14", "new.json"), ("2026-11-26", "forecast.json")]


def test_output_is_readable_by_the_ml_writer_logic(tmp_path):
    """Mirror of pipeline.ml.export.upsert_manifest: it needs a list of dicts with .get()."""
    path = tmp_path / "manifest.json"
    manifest.upsert(path, [forecast("2026-11-14")])
    existing = json.loads(path.read_text())
    key = lambda e: (e.get("model"), e.get("site"), e.get("layer"), e.get("date"))  # noqa: E731
    assert [key(e) for e in existing] == [("prediction", "albufera", "flooded_area", "2026-11-14")]


def test_old_object_format_is_converted(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "layers": [CV], "forecasts": [{"id": "old"}]}))
    manifest.upsert(path, [forecast("2026-11-14")])
    assert json.loads(path.read_text()) == [CV, {"id": "old"}, forecast("2026-11-14")]


def test_rejects_entries_without_the_key(tmp_path):
    with pytest.raises(ValueError, match="layer"):
        manifest.upsert(tmp_path / "m.json", [{"model": "prediction", "site": "x", "date": "2026-11-14"}])
