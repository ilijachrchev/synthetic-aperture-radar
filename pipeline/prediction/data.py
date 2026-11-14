"""Read provider observations without interpolation or retrospective cleaning.

NGL column definitions: https://geodesy.unr.edu/gps_timeseries/readmes/README_tenv3.txt
EGMS dates and units: https://eea.github.io/CLMS_documents/develop/products/European_Ground_Motion_Service_Product_Description_v3.html
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

import numpy as np

NGL_ROOT = "https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20"
NGL_FORMAT_URL = "https://geodesy.unr.edu/gps_timeseries/readmes/README_tenv3.txt"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class Series:
    point_id: str
    dates: tuple[date, ...]
    values: np.ndarray
    source: dict

    def __post_init__(self):
        if not self.dates or self.values.shape != (len(self.dates),):
            raise ValueError("A series needs equally sized, nonempty date and value arrays")
        if not np.all(np.isfinite(self.values)):
            raise ValueError("Series values must be finite")
        if any(a >= b for a, b in zip(self.dates, self.dates[1:])):
            raise ValueError("Observation dates must be unique and increasing")

    @property
    def steps(self) -> tuple[float, ...]:
        """Ordinal days of known equipment changes (from source["equipment_changes"])."""
        return tuple(float(date.fromisoformat(d).toordinal()) for d in self.source.get("equipment_changes", []))

    @property
    def days(self) -> np.ndarray:
        return np.array([d.toordinal() for d in self.dates], dtype=float)

    def between(self, start: date, end: date) -> Series:
        keep = [i for i, d in enumerate(self.dates) if start <= d <= end]
        if not keep:
            raise ValueError(f"No valid observations between {start} and {end}")
        values = self.values[keep]
        source = dict(self.source)
        source.update(reference_date=self.dates[keep[0]].isoformat(),
                      reference_value_before_rebasing_mm=float(values[0]))
        return replace(self, dates=tuple(self.dates[i] for i in keep),
                       values=values - values[0], source=source)


def _series(point_id: str, rows: list[tuple[date, float]], source: dict) -> Series:
    rows.sort(key=lambda row: row[0])
    return Series(point_id, tuple(row[0] for row in rows),
                  np.array([row[1] for row in rows], dtype=float), source)


def fetch_ngl(station: str, directory: Path) -> Path:
    """Download one bounded public station file; no authentication or credentials."""
    if not re.fullmatch(r"[A-Z0-9]{4}", station):
        raise ValueError("Station must contain exactly four uppercase letters/digits")
    url = f"{NGL_ROOT}/{station}.tenv3"
    request = Request(url, headers={"User-Agent": "SpaceApps-Lorca-forecast/0.1"})
    with urlopen(request, timeout=45) as response:
        raw = response.read(3_000_001)
    if len(raw) > 3_000_000:
        raise ValueError("Station file exceeds the 3 MB download limit")
    lines = raw.decode("utf-8-sig").splitlines()
    header = lines[0].split() if lines else []
    if len(lines) < 2 or not {"site", "__MJD", "u0(m)", "____up(m)"} <= set(header):
        raise ValueError("Response is not an NGL tenv3 observation file")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{station}.tenv3"
    temporary = path.with_suffix(".tenv3.tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)
    metadata = {"provider": "Nevada Geodetic Laboratory", "url": url,
                "retrieved_at_utc": utc_now(), "sha256": file_sha256(path),
                "station": station, "reference_frame": "IGS20", "format_url": NGL_FORMAT_URL}
    path.with_suffix(".source.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return path


def load_ngl(path: Path, station: str, max_sigma_mm: float = 20.0) -> Series:
    """Combine integer/fractional vertical coordinates, convert meters to mm.

    Antenna height is metadata, not a correction to subtract again. We retain raw
    observations and apply only a fixed provider-uncertainty quality threshold.
    """
    if not np.isfinite(max_sigma_mm) or max_sigma_mm <= 0:
        raise ValueError("max_sigma_mm must be positive and finite")
    rows = []
    rejected = 0
    latitude = longitude = None
    with path.open(encoding="utf-8-sig") as handle:
        header = handle.readline().split()
        required = {"site", "__MJD", "u0(m)", "____up(m)", "sig_u(m)",
                    "_latitude(deg)", "_longitude(deg)"}
        if not required <= set(header):
            raise ValueError(f"Not an NGL tenv3 file: missing {sorted(required - set(header))}")
        for number, line in enumerate(handle, 2):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != len(header):
                raise ValueError(f"Malformed NGL row {number}")
            row = dict(zip(header, fields))
            if row["site"] != station:
                raise ValueError(f"Unexpected station {row['site']} at row {number}")
            day = date(1858, 11, 17) + timedelta(days=int(row["__MJD"]))
            value = (float(row["u0(m)"]) + float(row["____up(m)"])) * 1000
            sigma = float(row["sig_u(m)"]) * 1000
            if not np.isfinite(value) or not np.isfinite(sigma) or not 0 < sigma <= max_sigma_mm:
                rejected += 1
                continue
            rows.append((day, value))
            if latitude is None:
                latitude = float(row["_latitude(deg)"])
                longitude = float(row["_longitude(deg)"])
    source = {"type": "gnss", "provider": "Nevada Geodetic Laboratory",
              "url": f"{NGL_ROOT}/{station}.tenv3", "format_url": NGL_FORMAT_URL,
              "station": station, "reference_frame": "IGS20", "component": "vertical",
              "units": "mm", "positive_direction": "up", "latitude": latitude,
              "longitude": longitude, "sha256": file_sha256(path),
              "quality_filter": {"max_vertical_sigma_mm": max_sigma_mm,
                                 "rejected_rows_in_source": rejected},
              "corrections": "No equipment-step, earthquake, or loading corrections applied"}
    sidecar = path.with_suffix(".source.json")
    if sidecar.exists():
        provenance = json.loads(sidecar.read_text())
        if provenance.get("sha256") != source["sha256"]:
            raise ValueError("Download metadata checksum does not match the station file")
        source["retrieved_at_utc"] = provenance["retrieved_at_utc"]
    return _series(station, rows, source)


def load_context_csv(path: Path, station: str, max_sigma_mm: float = 20.0) -> Series:
    """The station series committed by pipeline.context (data/context/lorca_gnss_LOR1_up.csv).

    Columns: date, decimal_year, up_m, sigma_up_m, antenna_height_m (from NGL tenv3).
    Antenna height changes are recorded as equipment changes, for step terms in the
    trend models. NGL heights already refer to the ground marker; LOR1 does not jump
    up by the 7.7 cm antenna change of 2023-08-03 (issue #16).
    """
    if not np.isfinite(max_sigma_mm) or max_sigma_mm <= 0:
        raise ValueError("max_sigma_mm must be positive and finite")
    rows, rejected, changes, last_ant = [], 0, [], None
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "up_m", "sigma_up_m", "antenna_height_m"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"Not a pipeline.context GNSS file: missing {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            day = date.fromisoformat(row["date"])
            ant = float(row["antenna_height_m"])
            if last_ant is not None and ant != last_ant:
                changes.append(day.isoformat())
            last_ant = ant
            value, sigma = float(row["up_m"]) * 1000, float(row["sigma_up_m"]) * 1000
            if not np.isfinite(value) or not np.isfinite(sigma) or not 0 < sigma <= max_sigma_mm:
                rejected += 1
                continue
            rows.append((day, value))
    source = {"type": "gnss", "provider": "Nevada Geodetic Laboratory", "url": f"{NGL_ROOT}/{station}.tenv3",
              "format_url": NGL_FORMAT_URL, "station": station, "reference_frame": "IGS20",
              "component": "vertical", "units": "mm", "positive_direction": "up",
              "input_file": path.as_posix(), "sha256": file_sha256(path),
              "quality_filter": {"max_vertical_sigma_mm": max_sigma_mm, "rejected_rows_in_source": rejected},
              "equipment_changes": changes,
              "corrections": "Step term at each equipment change in the trend models; no earthquake or loading corrections"}
    return _series(station, rows, source)


def load_egms(path: Path, point_id: str, nodata: float | None = None) -> Series:
    """Read exactly one point from an EGMS Ortho *Vertical* CSV in native mm.

    Input must be the vertical product, not the E/W product or a velocity TIFF.
    Date headers are YYYYMMDD. Blank/nonfinite values remain unobserved.
    """
    with path.open(encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        if not sample.strip():
            raise ValueError("Empty EGMS input file")
        delimiter = ";" if sample.splitlines()[0].count(";") > sample.splitlines()[0].count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        headers = reader.fieldnames or []
        if "pid" not in headers:
            raise ValueError("EGMS Ortho CSV must have a pid column")
        epochs = {field: datetime.strptime(field, "%Y%m%d").date()
                  for field in headers if re.fullmatch(r"\d{8}", field)}
        if not epochs:
            raise ValueError("No YYYYMMDD displacement columns; a velocity-only file is insufficient")
        selected = None
        for row in reader:
            if row["pid"] == point_id:
                if selected is not None:
                    raise ValueError(f"Duplicate EGMS point {point_id}")
                selected = row
        if selected is None:
            raise ValueError(f"EGMS point {point_id} not found")
    rows = []
    for field, day in epochs.items():
        cell = selected[field].strip()
        if not cell:
            continue
        value = float(cell)
        if np.isfinite(value) and value != nodata:
            rows.append((day, value))
    source = {"type": "egms_ortho_vertical", "provider": "Copernicus EGMS",
              "url": "https://egms.land.copernicus.eu/", "sha256": file_sha256(path),
              "component": "vertical", "units": "mm", "positive_direction": "up",
              "point_id": point_id, "input_filename": path.name,
              "grid_crs": "EPSG:3035", "nodata_value": nodata}
    for field in ("easting", "northing"):
        if selected.get(field):
            source[field] = float(selected[field])
    return _series(point_id, rows, source)
