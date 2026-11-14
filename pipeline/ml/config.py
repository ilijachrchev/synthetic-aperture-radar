"""ML model settings: classes, colours, label rules and training defaults.

Paths and the grid come from the shared pipeline.config, so they never drift
from the stacks the CV model uses.

Written with SI assistance (Claude Code), reviewed by the team.
"""

from __future__ import annotations

from pipeline.config import DATA_DIR, LABELS_DIR, PIXEL_SIZE_M, STACK_DIR  # noqa: F401  (re-exported)

CONTEXT_DIR = DATA_DIR / "context"   # WorldCover and JRC already on each site grid (committed)
ML_OUT_DIR = DATA_DIR / "ml"         # our outputs: data/ml/<site>_<stack>/
MANIFEST = DATA_DIR / "manifest.json"

# Order matters: the index is the value written to the class COG.
CLASSES: list[str] = [
    "rice_paddy",
    "permanent_water",
    "urban",
    "forest",
    "burned",
    "other_crops_shrub",
]
CLASS_INDEX: dict[str, int] = {name: i for i, name in enumerate(CLASSES)}

# RGB colours for the embedded COG colormap (the web app may restyle them).
CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "rice_paddy": (230, 200, 60),
    "permanent_water": (40, 90, 200),
    "urban": (200, 60, 60),
    "forest": (30, 120, 50),
    "burned": (60, 40, 30),
    "other_crops_shrub": (170, 200, 120),
}

UNLABELED = -1   # label array value for "no training label"
NODATA_U8 = 255  # nodata in the 8-bit output COGs
PIXEL_HA = PIXEL_SIZE_M * PIXEL_SIZE_M / 10_000  # 0.04 ha

# Training defaults.
BLOCK_PX = 50          # 50 px * 20 m = 1 km blocks for the spatial split
GAP_PX = 2             # drop training pixels this close to a test block
TEST_FRACTION = 0.25
MIN_VALID_DATES = 3    # pixels with fewer valid HH or HV dates are not classified
MAX_TRAIN_PER_CLASS = 20_000
SEED = 42

# Label rules.
JRC_PERMANENT_MIN = 90  # JRC occurrence (%) at or above which water is permanent
JRC_NODATA = 255        # data/context/<site>_jrc_occurrence_20m.tif
WORLDCOVER_NODATA = 0   # data/context/<site>_worldcover_2021_20m.tif
WORLDCOVER_WATER = 80

# ESA WorldCover 2021 codes -> our classes. Codes not listed stay unlabeled:
# 70 snow, 80 water (handled through JRC), 90 herbaceous wetland, 95 mangrove,
# 100 moss. WorldCover has no rice class: rice comes from the drawn polygons.
WORLDCOVER_TO_CLASS: dict[int, str] = {
    10: "forest",             # tree cover
    20: "other_crops_shrub",  # shrubland
    30: "other_crops_shrub",  # grassland
    40: "other_crops_shrub",  # cropland
    50: "urban",              # built-up
    60: "other_crops_shrub",  # bare / sparse vegetation
}
