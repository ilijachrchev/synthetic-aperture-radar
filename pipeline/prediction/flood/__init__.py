"""Rain-threshold flood alerts (option C in discussion #9).

Per site: does rain over the last days predict *new* flood water on the next
Sentinel-1 pass? A threshold on the largest 3-day rain total is fitted on every
pass since Aug 2024 except the held-out Oct 2026 DANA at Pego-Oliva, then
scored on it and turned into a traffic light from the ECMWF ensemble.

Steps (python -m pipeline.prediction.flood <step>):

1. ``history --site S``: every DSWx-S1 pass over the site (as for Albufera).
2. ``water``: flooded hectares per pass in each site's assessment zone.
3. ``rain``: daily rain per site from Open-Meteo (ECMWF IFS 9 km archive).
4. ``fit``: events table, threshold, held-out scores, live alert, DANA replay.

Written with SI assistance (Claude Code), reviewed by the team.
"""

SITES = ("albufera", "pego_oliva")
