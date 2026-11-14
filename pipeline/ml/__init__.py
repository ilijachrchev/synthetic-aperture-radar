"""ML model: per-pixel land classes from the NISAR GCOV time series.

Reads one shared stack (data/stack/<site>_<stack>.nc, built by pipeline.stack),
builds one feature row per pixel, trains LightGBM on spatially separated blocks
and exports class + confidence COGs. Run: python -m pipeline.ml --help

Written with SI assistance (Claude Code), reviewed by the team.
See the README section "Use of Super Intelligence (SI)".
"""

__version__ = "0.2.0"
