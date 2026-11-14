"""Study sites, paths and analysis grid settings shared by every model.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"          # downloads, not committed
STACK_DIR = DATA_DIR / "stack"      # one NetCDF stack per site, not committed
CATALOG_DIR = DATA_DIR / "catalog"  # NISAR file lists per site, committed (small JSON)
LABELS_DIR = DATA_DIR / "labels"    # reference outlines, committed (small GeoJSON)

PIXEL_SIZE_M = 20.0  # GCOV frequency A posting for the 20 MHz modes used here


@dataclass(frozen=True)
class Site:
    """One study area. bbox is (west, south, east, north) in WGS84 degrees."""

    name: str
    title: str
    bbox: tuple[float, float, float, float]
    crs: str  # analysis grid (UTM zone that contains the site)
    models: tuple[str, ...]


SITES: dict[str, Site] = {
    site.name: site
    for site in (
        Site(
            name="albufera",
            title="Albufera lagoon and rice fields",
            bbox=(-0.45, 39.15, -0.22, 39.45),
            crs="EPSG:32630",
            models=("cv", "ml", "prediction"),
        ),
        Site(
            name="pego_oliva",
            title="Pego-Oliva marsh and Girona plain (DANA Adam flood)",
            # Covers every flood label: EMSR935 reaches 38.992 N, the
            # Generalitat footprint 0.028 E (checked against the WFS data).
            bbox=(-0.25, 38.78, 0.06, 39.02),
            crs="EPSG:32630",
            models=("cv",),
        ),
        Site(
            name="espada",
            title="Serra d'Espadà burn scar",
            bbox=(-0.50, 39.78, -0.10, 40.02),
            crs="EPSG:32630",
            models=("cv", "ml"),
        ),
        Site(
            name="lorca",
            title="Lorca, Alto Guadalentín ground sinking",
            bbox=(-1.80, 37.55, -1.45, 37.85),
            crs="EPSG:32630",
            models=("prediction",),
        ),
        Site(
            name="panama",
            title="Panama M7.7 earthquake of 9 Oct 2026",
            bbox=(-81.30, 7.20, -80.20, 8.00),
            crs="EPSG:32617",
            models=("display",),
        ),
    )
}


# NISAR stacks shared by the CV and ML models: frames that cover the whole site
# box (checked in the catalog). Tracks have different viewing geometry, so each
# track is its own stack and tracks are never mixed.
STACKS: dict[str, tuple[str, ...]] = {
    "albufera": ("066_D_069", "058_A_021"),
    "pego_oliva": ("066_D_069", "058_A_021"),
    "espada": ("058_A_022", "167_D_068"),
}

# Sites whose CV labels are same-day Sentinel-1 water maps (Espadà uses EFFIS).
DSWX_LABEL_SITES: tuple[str, ...] = ("albufera", "pego_oliva")


def get_site(name: str) -> Site:
    """Return a site by name, with a clear error listing the valid names."""
    try:
        return SITES[name]
    except KeyError:
        raise KeyError(f"Unknown site {name!r}. Valid sites: {', '.join(SITES)}") from None
