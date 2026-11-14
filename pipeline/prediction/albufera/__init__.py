"""Albufera rice-field flooded-area forecast from the Sentinel-1 water history.

Steps (each one a subcommand of ``python -m pipeline.prediction.albufera``):

1. ``history``: every OPERA DSWx-S1 pass over the site since Aug 2024 (B01_WTR only).
2. ``mask``: rice-field mask on the shared 20 m site grid (no sea, no lagoon, no towns).
3. ``area``: flooded hectares inside the mask for every pass.
4. ``forecast``: persistence, day-of-year climatology and climatology + damped anomaly,
   each scored on a season it never saw, with historical-error ranges.

This is deliberate, seasonal agricultural flooding, not a disaster flood forecast.

Written with SI assistance (Claude Code), reviewed by the team.
"""

SITE = "albufera"
