"""Where will the water go: per-pixel water likelihood from rain, terrain and past water.

Labels are the OPERA DSWx-S1 passes already downloaded for the flood alert
(``data/raw/dswx_history``), on the shared 20 m site grid. The October 2026 DANA
window is held out of every fit. See README.md in this folder.
"""

SITES = ("albufera", "pego_oliva")
HOLDOUT_START = "2026-10-15"   # same window as pipeline.prediction.flood
HOLDOUT_END = "2026-11-15"
