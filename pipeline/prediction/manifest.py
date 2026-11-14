"""Shared ``data/manifest.json`` writer for the prediction outputs.

The manifest is one JSON list with one entry per output, keyed by
``(model, site, stack, layer)``, the same format and default key as
``pipeline.ml.export.upsert_manifest``. Every model can then read and write the
same file.

For a forecast, ``stack`` names the input series (``gnss_LOR1``, ``egms_ortho_vertical_<pid>``,
``dswx-s1``) and ``date`` is the forecast origin, kept as a field but not in the
key: each output directory holds one forecast that a re-run overwrites, so a
re-run must replace its entry, never leave one pointing at the overwritten file.
The record of what was forecast when is the git history of forecast.json.
"""

from __future__ import annotations

import json
from pathlib import Path

KEY_FIELDS = ("model", "site", "stack", "layer")


def _key(entry: dict) -> tuple:
    return tuple(entry.get(k) for k in KEY_FIELDS)


def read(path: Path) -> list[dict]:
    """Entries of a manifest; an old prediction-only object is converted to the list format."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):  # format used before the shared list format was agreed (PR #8)
        return [e for e in data.get("layers", []) + data.get("forecasts", []) if isinstance(e, dict)]
    raise ValueError(f"{path} must hold a JSON list of entries")


def upsert(path: Path, entries: list[dict]) -> None:
    """Replace entries with the same (model, site, stack, layer); keep every other entry."""
    for entry in entries:
        missing = [k for k in KEY_FIELDS if not entry.get(k)]
        if missing:
            raise ValueError(f"Manifest entry is missing {missing}")
    new_keys = {_key(e) for e in entries}
    merged = [e for e in read(path) if _key(e) not in new_keys] + entries
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, allow_nan=False) + "\n", encoding="utf-8")
