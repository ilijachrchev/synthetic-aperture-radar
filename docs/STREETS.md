# Where did the water run in the towns? Terrain flow against the official flood zones

The product question (discussion #29): the alert says rain, not where the water goes, and the official flood map (SNCZI) says only where land can flood someday. Radar at 20 m cannot see water between buildings, so in the towns the "where will the water go" answer must come from the terrain. This page tests, honestly and on the same pixels, whether a terrain flow map that needs no training points to where the water of the DANA of 29 Oct 2024 ran in the 10 towns of L'Horta Sud and Chiva better than the official zones.

The 2024 flood is a test only. Nothing here is fitted to it.

## Rules

Written down on 15 Nov 2026 before any score was computed, and committed before the scoring code existed (see the git history of this file). Thresholds come from the cited literature or are fixed to the area of the official zones; none was chosen by looking at a 2024 result. If a rule had to change later, the change is listed under "Changes to the rules" with its reason, and the result under the original rule is kept.

### Area and pixels

- **Grid.** 5 m cells in ETRS89 / UTM 30N (EPSG:25830), edges on multiples of 5 m, box x 678,000 to 732,000 m, y 4,357,000 to 4,381,500 m. The box holds the 10 municipalities and the whole catchment of the Poyo, Pozalet and Saleta ravines (ICV layer `DANA2024.AVSRE.Cuencas`, code 29), so the flow from Chiva to the Albufera is inside it.
- **Scored pixels**, the same for every method and every reference: a cell whose centre lies
  1. inside one of the 10 municipalities (Paiporta, Massanassa, Sedaví, Catarroja, Alfafar, Benetússer, Picanya, Aldaia, Chiva, Torrent; IGN polygons, as in `pipeline.zones`),
  2. inside the area that at least one of the three EMSR773 products of `pipeline.zones` looked at (area of interest inside the image footprints, minus "Not Analysed"), and
  3. not on permanent water (ESA WorldCover 2021, class 80; the Albufera lake is never a flood).
- **Cover.** A polygon covers a cell when it contains the cell centre (rasterio `rasterize`, `all_touched=False`), for every layer alike. A point (a building, a water mark) is covered when the cell holding it is covered. Areas are cell counts times 25 m².

### What counts as flooded (references; never used to build or tune a method)

1. **Observed flood, EMSR773**: the maximum observed extent of the three products, exactly as `pipeline.zones` builds it (flooded area plus flood traces; where one product saw water and another a trace, it counts as water). Also its two parts apart: the **flood traces** (water gone, mud left; this is where the streets are) and the flooded area. The lower bound of `pipeline.zones` (sharpest map first) is reported as a sensitivity.
2. **Graded buildings, EMSR773 AOI03**: the 2,238 building points in the 10 towns graded possibly damaged, damaged or destroyed (`data/zones/buildings_dana_2024_horta_sud.geojson` of PR #36).
3. **Second reference, the Generalitat's flood footprint**: ICV layer `DANA2024.ZonasInundadas.HuellaInundacion` of `https://terramapas.icv.gva.es/2702_DANA2024` ("Zona inundada por desbordamiento del Rio Magro y barrancos del Poyo, Saleta y Picassent y afluentes, debido a la DANA del 29-10-24").
4. **Street check, surveyed water marks**: the water heights measured after the flood in the same ICV service (`DANA2024.ZonasInundadas.AlturaAgua.UPV`, `.IVE`, `.SGRT`, `.AyuntamientosOtros`). A point with a height above 0 m is a spot where water stood. Scored like the buildings (share covered).

### Methods

1. **Official zones (SNCZI)**, the fluvial and marine layers that `pipeline.zones` reads from MITECO's WFS: T10, T100 and T500 as mapped (each return period its own layer, fluvial and marine together), and their union ("any zone").
2. **Terrain flow, no training, its own threshold.**
   - Terrain: ICV, MDT 1 m of Valencia province 2015 (ground class of the PNOA-LiDAR 2015 flight, edited by hand, with breaklines), averaged to 5 m (mean of the 25 cells).
   - Depressions filled (morphological reconstruction from the grid edges and the cells next to missing data or permanent water); flat areas drained towards their outlet along the shortest path inside the flat (a geodesic distance, in the spirit of Garbrecht and Martz 1997); D8 flow directions (steepest descent); D8 flow accumulation.
   - Drainage: cells with an upstream area above 0.5 km², the definition used for MERIT Hydro's HAND layer (Yamazaki et al. 2019).
   - HAND (height above the nearest drainage, Nobre et al. 2011): filled elevation of the cell minus filled elevation of the first drainage cell on its flow path.
   - Flood-prone: HAND below 15 m. Twele et al. (2016) take HAND of 15 m or more as "non-flood prone" in an automatic flood mapping chain.
3. **The same terrain map at equal area.** In each town, the scored cells with the lowest HAND are taken (ties: larger upstream area first, then grid order) until their count equals the number of that town's scored cells in the official zone. Done for the T10, T100, T500 and union areas. Also done pooled: one ranking over the 10 towns, total count equal to the union's.
   - **Variant, buildings as obstacles** (declared now, reported whatever it shows): Catastro INSPIRE building footprints raised by 10 m for the flow routing only (fill, directions, accumulation); the HAND heights stay those of the terrain without buildings.
4. **Rain on terrain, simulated** (if it fits in time; labelled simulated everywhere).
   - 25 m cells (the 5 m terrain averaged), the local inertial shallow water scheme of Bates, Horritt and Fewtrell (2010), Manning's n of 0.05 everywhere, no infiltration (all rain runs off, an upper bound on runoff), water leaves at the grid edges, the sea and permanent water.
   - Rain: the hourly rain volumes of Pérez Cueva et al. (2025, Tables 5 and 6), reconstructed from the gauges of AEMET, AVAMET, SAIH-CHJ and others, turned into depths over three zones delineated on our flow directions: upstream of the CHJ Poyo gauge at the A-3 ("Poyo hasta aforo", 183.0 km²), the rest of the Poyo upstream of its fan apex between Torrent and Picanya ("Poyo post aforo", 168.5 km²), and the Possalet-Saleta ravines (74.6 km²). No rain elsewhere: the plain got far less (36.0 mm at the SAIH València gauge for the whole episode, CHJ report).
   - Run from 29 Oct 2024 05:00 to 30 Oct 06:00 local time; the result is the maximum depth. Scored only at equal area (deepest cells first, the same counts as method 3), so it needs no depth threshold.
   - Check, not calibration: the modelled flow at the CHJ gauge against the gauge record (2,282.9 m³/s at 18:55, its last reading). The model is never adjusted to match it.
   - If the 25 m run cannot finish before the code freeze, this page says so; any coarser run is labelled with its cell size.

### Metrics

For every method, per town and for the 10 towns together:

- **Buildings**: share of the graded buildings it covers.
- **Flood traces**: share of the flood-trace area it covers.
- **Observed flood**: share of the observed flood (both parts) it covers.
- **Own area that flooded**: share of its own area that the reference saw flooded (observed flood; also against the Generalitat's footprint).
- Its area in hectares and as a share of the scored pixels.
- **Chance**: a map of the same area placed at random covers, on average, its area share of anything, and its own-area share equals the flooded share of the scored pixels. Every result is read against this.
- For the second reference: share of the Generalitat's footprint covered and own area inside it. For the water marks: share of the marks covered.

### What is fixed and what is only sensitivity

- **Headline** (fixed now): method 3 at the area of the union of the official zones, per town, against method 1's union, on buildings, flood traces and own area that flooded.
- **Sensitivity only, never used to pick a version**: drainage thresholds of 0.05 and 5 km² (ten times smaller and larger), the pooled equal-area ranking, the buildings variant, the lower-bound observed flood, the Generalitat's footprint.
- Whatever the numbers show is written here, including where the terrain does worse.

## Results

Every number below is in [`data/streets/results.json`](../data/streets/results.json) (`methods`, `diagnostics`, `checks`, `simulation`), written by `python -m pipeline.streets score`; the tables are printed from it by `python -m pipeline.streets report`. Scored pixels: 12,232,704 cells of 5 m (30,581.8 ha) in the 10 towns.

**Short answer: no.** On the same amount of land, the terrain flow map (HAND, no training) pointed to where the 2024 water ran worse than the official zones, in total and in most towns. Given the land the official zones cover (3,394.9 ha, 11.1 % of the scored pixels, per town), the terrain map caught **35.0 %** of the 2,237 graded buildings against **42.1 %** for the zones, **32.8 %** of the flood traces against **39.1 %**, and **76.4 %** of its own land really flooded against **83.3 %** (a random map of that size: 17.2 %). The second reference and the water marks say the same (below). The terrain map is far better than chance, it does better than the zones on the low plain by the Albufera (Massanassa, Alfafar), and it would need only 14 % more land to match them, but it is not a better answer to "where will the water go" than the official map, and the official map itself caught under half of the affected buildings. The simulated rain on terrain lands in between (34.2 % of buildings, 34.4 % of traces) and catches far more of Torrent's affected buildings than either map (18.9 % against 7.0 and 1.3 %).

### The same land, town by town (headline)

The official union of T10, T100 and T500 against the terrain map cut to exactly the same number of cells in each town.

| Town | Land in the zones | Buildings: zones | Buildings: terrain | Flood traces: zones | Flood traces: terrain | Own land flooded: zones | Own land flooded: terrain | Own land flooded: chance |
|---|---|---|---|---|---|---|---|---|
| Paiporta | 44.2 % | 45.3 % | 42.5 % | 44.3 % | 44.5 % | 100.0 % | 100.0 % | 99.2 % |
| Massanassa | 94.6 % | 96.0 % | 99.5 % | 89.6 % | **98.1 %** | 91.2 % | 95.7 % | 91.4 % |
| Sedaví | 7.2 % | 0.5 % | 1.0 % | 4.0 % | 7.4 % | 100.0 % | 95.5 % | 83.3 % |
| Catarroja | 66.0 % | **99.2 %** | 64.2 % | **69.6 %** | 60.3 % | **88.5 %** | 82.9 % | 69.8 % |
| Alfafar | 80.1 % | 58.4 % | **71.4 %** | 59.5 % | 57.7 % | 97.5 % | 99.8 % | 93.6 % |
| Benetússer | 28.0 % | **35.7 %** | 0.0 % | **52.1 %** | 18.1 % | **41.1 %** | 14.0 % | 21.9 % |
| Picanya | 2.7 % | 0.0 % | 2.5 % | 3.0 % | 2.6 % | **97.6 %** | 76.4 % | 78.0 % |
| Aldaia | 23.7 % | 39.4 % | **45.5 %** | **36.6 %** | 31.2 % | **82.3 %** | 69.2 % | 52.2 % |
| Chiva | 2.5 % | **66.7 %** | 0.0 % | **58.8 %** | 18.5 % | **37.2 %** | 13.0 % | 1.6 % |
| Torrent | 2.1 % | **7.0 %** | 1.3 % | **16.9 %** | 7.6 % | **74.0 %** | 33.3 % | 9.2 % |
| **Total** | 11.1 % | **42.1 %** | 35.0 % | **39.1 %** | 32.8 % | **83.3 %** | 76.4 % | 17.2 % |

Buildings per town: Paiporta 327, Massanassa 200, Sedaví 196, Catarroja 391, Alfafar 231, Benetússer 28, Picanya 80, Aldaia 33, Chiva 3, Torrent 748 (by the town of the building's cell; one Torrent point falls on a cell outside every municipality). Bold: the better of the two where they differ by 5 points or more. With 3 buildings (Chiva), 28 (Benetússer) or 33 (Aldaia), one building moves the share by 33, 4 or 3 points.

### Every method, the 10 towns together

| Method | Land (% of scored) | Buildings | Flood traces | Observed flood | Own land flooded | Generalitat footprint covered | Own land in the footprint | Water marks |
|---|---|---|---|---|---|---|---|---|
| Official T10 | 3.4 % | 0.4 % | 4.2 % | 17.7 % | 90.1 % | 15.8 % | 99.4 % | 0.7 % |
| Official T100 | 6.0 % | 1.7 % | 10.6 % | 30.0 % | 85.5 % | 28.2 % | 99.5 % | 2.6 % |
| Official T500 | 11.1 % | 42.1 % | 39.1 % | 53.9 % | 83.4 % | 51.3 % | 98.1 % | 43.8 % |
| **Official union** | 11.1 % | **42.1 %** | **39.1 %** | 53.9 % | **83.3 %** | 51.3 % | 98.1 % | 43.9 % |
| Terrain, HAND below 15 m (method 2) | 47.9 % | 94.5 % | 99.1 % | 99.3 % | 35.5 % | 99.1 % | 43.9 % | 98.3 % |
| Terrain at the T10 area | 3.4 % | 1.7 % | 4.0 % | 16.3 % | 83.1 % | 13.6 % | 85.9 % | 1.8 % |
| Terrain at the T100 area | 6.0 % | 3.3 % | 9.1 % | 27.0 % | 76.7 % | 23.7 % | 83.4 % | 4.4 % |
| Terrain at the T500 area | 11.1 % | 35.0 % | 32.8 % | 49.4 % | 76.4 % | 43.0 % | 82.4 % | 32.6 % |
| **Terrain at the union area (headline)** | 11.1 % | **35.0 %** | **32.8 %** | 49.4 % | **76.4 %** | 43.0 % | 82.3 % | 32.6 % |
| Terrain at the union area, pooled over the towns | 11.1 % | 24.7 % | 26.7 % | 45.2 % | 69.9 % | 39.8 % | 76.2 % | 21.6 % |
| Terrain with buildings as obstacles, union area | 11.1 % | 32.9 % | 32.8 % | 49.5 % | 76.5 % | 43.1 % | 82.4 % | 32.1 % |
| Terrain, drainage from 0.05 km², union area | 11.1 % | 29.6 % | 29.4 % | 46.8 % | 72.4 % | 40.7 % | 77.8 % | 31.2 % |
| Terrain, drainage from 5 km², union area | 11.1 % | 35.0 % | 34.5 % | 51.0 % | 78.7 % | 46.0 % | 87.9 % | 30.4 % |
| Terrain, lake-only sinks (post-hoc), union area | 11.1 % | 34.8 % | 32.4 % | 49.2 % | 76.0 % | 42.9 % | 82.0 % | 32.5 % |
| Simulated rain on terrain, union area (SIMULATED) | 11.1 % | 34.2 % | 34.4 % | 51.2 % | 79.2 % | 46.6 % | 89.2 % | 42.5 % |

Against the lower-bound observed flood (sharpest map first; 3,232.5 ha in the municipalities) the order is the same: the official union covers 68.2 % of it and 64.8 % of its land is inside it, the terrain map 61.3 % and 58.2 %, the simulation 65.3 % and 62.0 %.

No version of the terrain map beats the official union on buildings, flood traces or own land flooded in total: not with buildings as obstacles, not with drainage starting at 0.05 or 5 km², not with the lake-only sinks, not pooled. At the T10 and T100 areas the terrain map catches slightly more buildings (1.7 against 0.4 %, 3.3 against 1.7 %), but both are close to nothing: the affected buildings were almost all outside the frequent and occasional zones (PR #36).

**Its own threshold (method 2).** HAND below 15 m covers 47.9 % of the scored land and holds 94.5 % of the buildings and 99.1 % of the flood traces, with 35.5 % of its land flooded (twice chance). In the plain it says "everything can flood" (100 % of Paiporta, Massanassa, Sedaví, Catarroja, Alfafar and Benetússer); what it does say is where water cannot go: the hills of Chiva and Torrent.

**How far behind.** Descriptive only, not a method: with every town's budget scaled by the same factor, the terrain ranking needs **1.14 times** the zones' land (12.5 % of the scored pixels instead of 11.1 %) to catch as many buildings (42.1 %) and as many flood traces (39.1 %) as the zones. Worse, but not by much land.

### Where the terrain does better, where worse, and why

- **Better: the low plain by the Albufera.** Massanassa (buildings 99.5 against 96.0 %, flood traces 98.1 against 89.6 %) and Alfafar (buildings 71.4 against 58.4 %). Here the flooded buildings stood low above the nearest drainage (median HAND 1.7 m in Massanassa, 0.7 m in Alfafar), and that is exactly what HAND ranks first.
- **No difference: where everything or almost nothing is covered.** Paiporta flooded almost entirely (99.2 % of its land), so any map of 44 % of it catches about 44 %. In Sedaví and Picanya the official zones cover 7.2 % and 2.7 % of the town, so the terrain map gets the same small budget and both catch almost none of the affected buildings (0.5 against 1.0 % in Sedaví, 0.0 against 2.5 % in Picanya).
- **Worse: Torrent, Catarroja, Benetússer, Chiva, Aldaia.** Torrent has a third of all graded buildings (748); the zones caught 7.0 % of them, the terrain map 1.3 %, and 16.9 against 7.6 % of the flood traces. In Benetússer the terrain map is below chance (14.0 % of its land flooded, chance 21.9 %).
- **Why, first: HAND treats every drainage line alike.** A gully of 0.5 km² in the hills of Torrent or Chiva ranks the same as the Poyo, so in a town whose budget is small (2.1 % of Torrent, 2.5 % of Chiva) the budget goes to dry gully floors: the equal-area cut stops at HAND 0.12 m in Torrent and 0.45 m in Chiva. Starting drainage at 5 km² instead removes the gullies and helps exactly there (Torrent: 7.2 % of buildings, 14.5 % of traces), but loses elsewhere and stays behind the zones in total.
- **Why, second: the water came from upstream.** The flood was a flash flood from the Poyo catchment: its gauge at the A-3 read 2,282.9 m³/s at 18:55 before it was destroyed (CHJ). The water left the ravine at the fan apex between Torrent and Picanya and ran across the fan; the flooded buildings of Torrent and Picanya stood a median **8.6 m** and **9.7 m** above the nearest drainage line, far above what any small budget of HAND reaches. How far the water spreads depends on how much comes down the ravine, and HAND carries no discharge. The official zones come from hydraulic studies of the Poyo with design floods, which is exactly what HAND lacks; where they cover the fan (Massanassa, Catarroja, the rare T500 zone of Paiporta) they catch the buildings.
- **Why, third: low land floods, but not all low land is alike.** Over the 10 towns the flood traces had a median HAND of 2.3 m and the graded buildings 2.5 m. Of the 6,277 ha less than 3 m above the nearest drainage, 57.5 % flooded (chance 17.2 %): in Paiporta, Massanassa and Alfafar almost all of it (96 to 100 %), in Torrent 27.6 % and in Chiva 10.2 %, where that low land is mostly gully floors in the hills. HAND separates the plain from the hills well; it cannot tell a gully floor from the Poyo's path.

### Simulated rain on terrain (SIMULATED)

The measured hourly rain of 29 Oct (Pérez Cueva et al. 2025) on the three upstream zones, routed by the 25 m local inertial model with no infiltration (`results.json` → `simulation`). Rain: 157.4 hm³; by 30 Oct 06:00, 110.6 hm³ had left the grid (the Albufera, the sea, the grid edges) and 46.7 hm³ were still on the ground. 95,092 time steps, 31 minutes with numba.

**Check at the CHJ gauge (not a calibration).** The model gives 3,052.5 m³/s at 18:55, where the gauge read 2,282.9 m³/s before the flood destroyed it. It rises from 1,098 m³/s at 17:30 to 2,696 m³/s at 18:30 (the gauge: 1,686.7 at 18:25, 1,756.9 at 18:35) and peaks at 3,291.7 m³/s at 20:40, when the gauge no longer worked. The morning pulse is far too big and too early (1,034 m³/s at 10:45; the gauge read 264 m³/s at 11:40): without infiltration, the morning rain on dry soil all runs off. So: the right order of magnitude and shape, about a third too high at 18:55 and a little early, as an upper bound should be. (Gauge readings: 18:55 from the CHJ report; 11:40, 18:25 and 18:35 as quoted by [Maldita.es](https://maldita.es/clima/20241108/cronologia-avisos-rio-magro-rambla-poyo/), see the timeline in `docs/ZONES.md`.)

**At the official zones' area** (the deepest simulated cells of each town first), the simulation catches 34.2 % of the buildings, 34.4 % of the flood traces and 79.2 % of its land flooded: between the terrain map (35.0, 32.8, 76.4 %) and the zones (42.1, 39.1, 83.3 %). It covers 42.5 % of the water marks (zones 43.9 %, terrain 32.6 %) and 46.6 % of the Generalitat's footprint (zones 51.3 %, terrain 43.0 %).

| Town | Buildings: zones / terrain / simulated | Flood traces: zones / terrain / simulated | Own land flooded: zones / terrain / simulated |
|---|---|---|---|
| Paiporta | 45.3 / 42.5 / 32.7 % | 44.3 / 44.5 / 44.1 % | 100.0 / 100.0 / 100.0 % |
| Massanassa | 96.0 / 99.5 / 100.0 % | 89.6 / 98.1 / 91.9 % | 91.2 / 95.7 / 92.5 % |
| Sedaví | 0.5 / 1.0 / 0.0 % | 4.0 / 7.4 / 0.1 % | 100.0 / 95.5 / 100.0 % |
| Catarroja | 99.2 / 64.2 / 52.7 % | 69.6 / 60.3 / 62.6 % | 88.5 / 82.9 / 83.5 % |
| Alfafar | 58.4 / 71.4 / 37.2 % | 59.5 / 57.7 / 52.7 % | 97.5 / 99.8 / 98.2 % |
| Benetússer | 35.7 / 0.0 / 17.9 % | 52.1 / 18.1 / 43.3 % | 41.1 / 14.0 / 34.3 % |
| Picanya | 0.0 / 2.5 / 5.0 % | 3.0 / 2.6 / 2.9 % | 97.6 / 76.4 / 94.3 % |
| Aldaia | 39.4 / 45.5 / 51.5 % | 36.6 / 31.2 / 37.5 % | 82.3 / 69.2 / 84.7 % |
| Chiva | 66.7 / 0.0 / 0.0 % | 58.8 / 18.5 / 21.0 % | 37.2 / 13.0 / 14.8 % |
| Torrent | 7.0 / 1.3 / **18.9 %** | 16.9 / 7.6 / 12.2 % | 74.0 / 33.3 / 62.0 % |
| **Total** | 42.1 / 35.0 / 34.2 % | 39.1 / 32.8 / 34.4 % | 83.3 / 76.4 / 79.2 % |

Sending the measured rain down the ravines does what HAND cannot: in **Torrent**, the town with a third of the affected buildings, the simulation catches 18.9 % of the 748 graded buildings (zones 7.0 %, terrain 1.3 %) and 30.8 % of its water marks (zones 5.6 %), though fewer flood traces (12.2 against 16.9 %) and less of its land flooded (62.0 against 74.0 %). It is the best of the three in Aldaia and well ahead of the terrain map in Benetússer. At 25 m and with one roughness it misplaces water in the dense plain (Alfafar 37.2 % of buildings, Sedaví almost none of the traces). Where the water comes from matters as much as how low the land is; a real warning would need both, and a better model than this one.

### The second reference and the water marks

The Generalitat's flood footprint holds 6,493.2 ha of the scored pixels, more than EMSR773's 5,246.5 ha. Against it the order is the same: the official union covers 51.3 % of it and 98.1 % of the union's land is inside it; the terrain map at the same area covers 43.0 % and 82.3 %. We do not know whether the footprint was drawn independently of the official zones; that it contains 98 % of their land in these towns suggests it may have used them, so this reference may favour the zones. Of the 2,699 surveyed water marks above 0 m on the scored pixels (UPV 362, IVE 1,939, SGRT 385, town halls 13), the official union covers 43.9 %, the terrain map 32.6 %.

### Checks

- The 5 m rasters reproduce PR #36's exact geometry (`checks.rasters_on_every_cell_of_the_municipalities` against `checks.pr36_exact_geometry`): observed flood 5,254.0 ha in the 10 municipalities (PR #36: 5,253.9), flood traces 3,829.0 ha (3,829.0), flooded area 1,425.0 ha (1,424.9), lower bound 3,232.5 ha (3,232.6), every town within 0.2 ha, official zones over 11.2 % of the municipalities (11.2 % in `docs/ZONES.md`), 2,238 graded buildings (2,238). Leaving permanent water out of the scored pixels removes 7.5 ha of observed flood (5,246.5 ha on the scored pixels).
- Every scored pixel has a HAND value in the headline map; no flat area was left undrained (4,121,463 flat cells drained in 459 rounds) and the accumulation found no loop.
- Grid: 4,900 × 10,800 cells, 52,653,524 with terrain (the rest is sea). Drainage cells (upstream area above 0.5 km², plus permanent water): 1,896,665, of them 1,621,421 permanent water. Buildings as obstacles: 479,941 cells of Catastro footprints (data of 21 Aug 2026).

## Flood depth, estimated from the flood outline and terrain

Added after the test above, on request: how deep the water of the two floods may have been, estimated from the satellite outline and the terrain, never measured. Nothing here predicts depth for future storms.

### Method (written before any comparison with the water marks)

- **The FwDET rule** (Floodwater Depth Estimation Tool, Cohen et al. 2018): the water surface of each flooded cell is the ground elevation of its nearest flood-edge cell, and the depth is that surface minus the ground, never below 0. As in FwDET 2.0 (Cohen et al. 2019), edges that are not a real shore of the flood do not count: a flood cell is an edge only where it touches (sharing a side) a dry cell with terrain that a satellite map looked at and that is not permanent water (ESA WorldCover class 80, the sea and missing terrain included). No smoothing.
- **Terrain**: the same 5 m terrain as above (ICV MDT 1 m 2015 averaged to 5 m, not filled).
- **2024 DANA**: the outline is EMSR773's maximum observed extent (flooded area plus flood traces, the same three products), on the whole analysis grid, so the flood's real edges outside the 10 towns count; numbers are given for the 10 towns.
- **2026 DANA Adam, Pego-Oliva**: the outline is EMSR935 (`data/labels/pego_oliva_emsr935_flood.geojson`, flooded area plus flood traces) on the ICV MDT 1 m 2015 sheet 0796, averaged to 5 m in the same way; that sheet holds 99.8 % of the outline (the rest is left out).
- **Classes**, as in the official viewers: below 0.2 m, 0.2 to 1 m, 1 to 2 m, above 2 m.
- **Check against surveyed water marks** (the ICV water heights used above, heights above 0 m): for the marks inside the outline, the estimated depth of the mark's cell against the measured height: mean error (bias), mean absolute error, root mean square error, median absolute error, the share within 0.5 m, by survey. Marks outside the outline get no estimate (the method gives depth only inside it); how many there are is reported. For 2026, none of the 71 surveyed marks (`data/labels/pego_oliva_water_depth_points.geojson`) lies inside the EMSR935 outline, so there is no check there.

### Result: an estimate that does not hold street by street

All numbers are in `results.json` → `flood_depth`; the layers are `data/streets/estimated_depth_dana_2024.geojson` (the 10 towns) and `data/streets/estimated_depth_dana_adam_2026.geojson`, every feature labelled "ESTIMATED from the flood outline and terrain" and carrying the check below.

**2024 DANA, the 10 towns.** Over the 5,246.5 ha of the outline, the estimate gives 47.4 % below 0.2 m, 27.3 % from 0.2 to 1 m, 11.9 % from 1 to 2 m and 13.3 % above 2 m (median 0.25 m, 90th percentile 2.58 m; the deepest values, up to 7 m, are ravine beds).

| Town | Outline (ha) | Below 0.2 m | 0.2 to 1 m | 1 to 2 m | Above 2 m | Median |
|---|---|---|---|---|---|---|
| Paiporta | 398.0 | 72.3 % | 10.5 % | 9.8 % | 7.4 % | 0.00 m |
| Massanassa | 499.0 | 34.6 % | 36.8 % | 12.6 % | 16.0 % | 0.48 m |
| Sedaví | 152.0 | 48.3 % | 22.8 % | 17.6 % | 11.2 % | 0.25 m |
| Catarroja | 910.7 | 51.9 % | 36.2 % | 6.4 % | 5.4 % | 0.17 m |
| Alfafar | 944.5 | 36.2 % | 40.1 % | 15.8 % | 7.8 % | 0.54 m |
| Benetússer | 17.1 | 68.3 % | 28.4 % | 2.9 % | 0.4 % | 0.04 m |
| Picanya | 563.2 | 45.1 % | 17.4 % | 11.0 % | 26.6 % | 0.42 m |
| Aldaia | 841.6 | 49.4 % | 22.7 % | 15.1 % | 12.8 % | 0.22 m |
| Chiva | 281.1 | 47.0 % | 18.3 % | 10.9 % | 23.8 % | 0.29 m |
| Torrent | 639.3 | 51.1 % | 18.4 % | 10.9 % | 19.6 % | 0.17 m |

**The check fails.** Of the 4,064 surveyed water marks above 0 m on the grid, 2,005 lie inside the outline and **2,059 outside it** (measured median 1.2 m), where the method gives no depth at all. At the 2,005 inside, the estimate's median is **0.22 m where the walls say 1.30 m**: mean error −0.49 m, mean absolute error **1.22 m**, root mean square error 1.53 m, median absolute error 1.02 m, only 23.7 % within 0.5 m, and a correlation of **0.08**, close to none. In the 10 towns alone (1,230 marks) the mean absolute error is 1.42 m and the correlation 0.0. By survey: IVE 1,112 marks (mean absolute error 1.29 m, 18.3 % within 0.5 m), SGRT 477 (1.14 m, 29.1 %), UPV 407 (1.15 m, 31.9 %), town halls 9 (0.47 m, 44.4 %). In Paiporta, which flooded almost entirely, the estimate's median is 0.0 m.

**Why.** Half the wet marks lie outside the satellite outline, so the outline's edges sit inside the real flood, below the real waterline, and the method puts the water surface too low. The edge each cell takes its level from is a median 312 m away (90th percentile 829 m) on a fan that slopes towards the Albufera, so one flat surface over that distance is off by metres either way. Edges along building walls are not the cause (6.5 % of the edge cells in the towns touch only buildings; checked after seeing the errors). The FwDET rule needs an outline whose edge is the waterline; EMSR773, drawn one to two days later, is not that in these streets.

**2026 DANA Adam, Pego-Oliva.** The EMSR935 outline holds 1,118.0 ha (99.8 % on the terrain sheet); over the 1,098.5 ha with terrain and not on permanent water, the estimate gives 80.9 % below 0.2 m, 18.7 % from 0.2 to 1 m, 0.4 % from 1 to 2 m and 0.1 % above 2 m (median 0.0 m, 90th percentile 0.37 m; Pego 460.9 ha, Oliva 500.7 ha). **No check**: none of the 71 surveyed marks lies inside the outline (18 lie within 50 m of it); they were measured along the ravines and in the towns around the marsh. In a marsh the 2015 LiDAR saw the water surface of that day over flooded fields and channels, not their bottom, so depths there come out low by construction.

**Use.** The surveyed marks are measurements; this estimate is not, and the check shows it does not tell one street from another. If the app shows depth for 2024, the marks themselves are the honest layer (`data/streets/water_marks_2024.geojson`); this estimate can at most say "shallow on the plain's edges, deep in the ravine beds".

## Limits

- **One event.** The 2024 DANA is one test. A method that ranks well here may rank worse in a flood of another shape; nothing here is a validation across events.
- **HAND does not know how much water comes.** It ranks land by its height above the nearest drainage line, the same for a 10-year and a 500-year flood. In 2024 the water came as a flash flood from the catchment upstream (the CHJ gauge read 2,282.9 m³/s at 18:55 before it was destroyed), so how far it spread on the plain depended on that volume, which no terrain map carries. The equal-area cut uses the official zones' area as the budget; a real warning would have to choose a budget from the forecast.
- **Terrain of 2015.** The LiDAR was flown in October and November 2015, nine years before the flood. Buildings, roads and earthworks built since are not in it. Averaging to 5 m smooths walls, kerbs and narrow channels.
- **The references are satellite outlines.** EMSR773 mapped the flood one to two days after the peak; in dense streets the flood traces are photo-interpreted, and a satellite misses water under trees and roofs. "Own area that flooded" is therefore a lower bound for every method alike. The graded buildings exist only where the AOI03 grading map looked (all of L'Horta Sud, 6 % of Chiva).
- **Small official zones, small budgets.** Where the official zones cover little (Torrent, Chiva, Picanya), the terrain map at equal area covers just as little, by design.
- **The simulation is simple and simulated.** No infiltration (all rain runs off, an upper bound), one Manning's n, 25 m cells that cannot resolve streets, no sewers, culverts or bridges other than what the bare-earth terrain shows, and rain only on the three upstream zones.

## What more time and data would add

**More flood events with traces** would turn one test into a check: the pipeline runs on any flood that has an EMSR delineation and surveyed water marks, and the ICV already publishes such marks for DANA Adam 2026 (service `2702_DANAAdam2026`, read by `pipeline.labels`), though that flood was in a marsh, not in towns. **Sewer networks** matter for the frequent rains this test says nothing about: a coupled sewer and street model (for example EPA's SWMM, Rossman 2015) needs the municipal networks, which are not open data. **Detailed rain radar** would replace our three uniform rain zones, but only once corrected: from 15:00 to 21:00 on 29 Oct 2024 the Valencia radar estimated 42.0 mm at Turís and 15.7 mm at Chiva where the gauges measured 615.2 and 421.0 mm, because rain that heavy attenuates the radar signal (Pérez Cueva et al. 2025, Table 2). **A NISAR pass close to a flood, with coherence,** would add what no terrain map can know: where the water actually stood. Interferometric coherence drops where water covers the ground between buildings; Chini et al. (2019) used this with Sentinel-1 to map flooded urban areas of Houston after Hurricane Harvey, and in our own benchmark NISAR's 12-day coherence separated water (0.25) from dry land (0.81, `docs/CV_BENCHMARK.md`). NISAR repeats each track every 12 days, so on one track the first pass after a flood can come up to 12 days later (sooner where tracks overlap, as the three over the Albufera do), and standing water drains within days; the team's NISAR data start in June 2026 (`docs/DATA.md`), so none could see the 2024 DANA. The terrain map says where water can run before the rain; a pass after it says where it ran.

## Files and how to rebuild

| File | What |
|---|---|
| `pipeline/streets.py` | the pipeline: `fetch`, `terrain`, `simulate`, `score`, `layers`, `report` |
| `pipeline/terrain_flow.py` | depressions, flats, D8 flow, accumulation, HAND (numpy, scipy, scikit-image) |
| `pipeline/inertial.py`, `pipeline/inertial_kernel.py` | the rain-on-terrain scheme (numpy reference; the same with numba) |
| `data/streets/results.json` | every number on this page, with the input files, URLs, checksums and retrieval times |
| `data/streets/flow_paths.geojson` | terrain flow paths with an upstream area above 5 km² (WGS84) |
| `data/streets/terrain_equal_area.geojson` | the terrain map at the official zones' area, per town (WGS84) |
| `data/streets/simulated_max_depth.geojson` | SIMULATED maximum water depth classes (WGS84) |
| `data/streets/water_marks_2024.geojson` | the 2,699 water heights MEASURED after the 2024 flood in the 10 towns (every surveyed mark above 0 m): `depth_m`, `class` (below 0.2, 0.2 to 1, 1 to 2, above 2 m), `surveyed_by` (UPV, IVE, SGRT, town hall), `town`; from the ICV service `https://terramapas.icv.gva.es/2702_DANA2024` (layers `DANA2024.ZonasInundadas.AlturaAgua.*`), read 15 Nov 2026, CC BY 4.0 Generalitat (WGS84) |
| `data/streets/estimated_depth_dana_2024.geojson`, `estimated_depth_dana_adam_2026.geojson` | depth ESTIMATED from the flood outline and terrain, classes below 0.2, 0.2 to 1, 1 to 2, above 2 m, with the check against water marks (WGS84) |
| `tests/test_streets.py`, `tests/test_streets_inertial.py` | the terrain flow, the equal-area cut and the scheme on tiny synthetic grids |

Needs the downloads of `pipeline.zones` (PR #36) in `data/interim/flood-zones/` (`python -m pipeline.zones fetch`), or `--zones-interim` pointing at them. Downloads go to `data/interim/streets/` (not in git). The terrain sheets are about 2 GB each and are deleted once averaged to 5 m; the terrain step needs about 4 GB of RAM.

```bash
python -m pipeline.streets fetch
```

```bash
python -m pipeline.streets terrain
```

The simulation is fast only with numba, which is not in the shared stack; it gets its own venv inside `data/interim/streets/` (the shared venv and `pyproject.toml` stay as they are). Without it, `simulate` runs the numpy version of the same scheme, hours instead of minutes.

```bash
python -m venv data/interim/streets/venv-numba
```

```bash
data/interim/streets/venv-numba/Scripts/python -m pip install numba
```

```bash
python -m pipeline.streets simulate
```

```bash
python -m pipeline.streets score
```

```bash
python -m pipeline.streets layers
```

```bash
python -m pipeline.streets depth
```

```bash
python -m pipeline.streets report
```

## Changes to the rules

1. **Permanent water also counts as drainage for HAND** (decided while writing the code, before any score). The rules make permanent water an outlet of the depression filling, so water that reaches the Albufera leaves the grid there; without this clarification a cell that drains straight into the lake would have no drainage cell on its path. HAND is then measured from the lake surface, as for a river. The lake itself is not a scored pixel.
2. **In the simulation, only water bodies of at least 1 km² are sinks** (decided before any simulation result existed). "Permanent water" in the rules meant the Albufera and the sea, but ESA WorldCover's class 80 also marks 942 small patches inside the catchment (ponds, a quarry lake; 2.7 km² of its 40.5 km² in the grid). One of them lies on the Poyo near Cheste, and with every patch as a sink the D8 routing ended the Poyo there, with 157.6 km² upstream; in the simulation it would have swallowed the flood. The three bodies of 1 km² or more are the sea, the port and the Albufera (37.8 km²). The rain zones are delineated on this routing: the gauge cell drains 183.0 km² (Pérez Cueva et al.: 183.0), the apex 351.7 km² (351.5), the Saleta 74.6 km² (74.6).
3. **A post-hoc check of HAND with the same lake-only sinks** (added after the first scores, because of item 2). The pre-registered HAND, with every WorldCover patch as a sink, stays the headline; the lake-only HAND is reported beside it, labelled post-hoc, so a reader can see whether the ponds change the answer.

## Sources

- **Terrain**: Institut Cartogràfic Valencià, Modelo Digital del Terreno (MDT) de LIDAR de 1 metro de resolución de la provincia de Valencia 2015, by MTN50 sheet ([catalogue](https://dadesobertes.gva.es/dataset/modelo-digital-del-terreno-mdt-de-lidar-de-1-metro-de-resolucion-de-la-provincia-de-valenc-2015)), "Producto derivado de LIDAR-PNOA 2015 CC-BY 4.0 scne.es", flight 1 Oct to 30 Nov 2015. Here: obra derivada (averaged to 5 m). Read 15 Nov 2026. IGN's own 5 m web service (`https://servicios.idee.es/wcs-inspire/mdt`, coverage `Elevacion25830_5`) was tried first and not used: it returns whole metres, too coarse for a plain where the land drops a few metres over kilometres.
- **Generalitat's footprint, water marks and catchments**: Institut Cartogràfic Valencià, service `https://terramapas.icv.gva.es/2702_DANA2024` (WFS), layers `DANA2024.ZonasInundadas.HuellaInundacion`, `DANA2024.ZonasInundadas.AlturaAgua.*`, `DANA2024.AVSRE.Cuencas`. Read 15 Nov 2026.
- **EMSR773, SNCZI zones, municipalities**: as in `docs/ZONES.md` (PR #36).
- **Permanent water**: ESA WorldCover 2021 v200, © ESA WorldCover project / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium, CC BY 4.0.
- **Buildings**: Dirección General del Catastro, INSPIRE Buildings download service (ATOM), by municipality.
- **Rain and gauge**: Pérez Cueva, A. J., Armengot Serrano, R., Fansa Saleh, G., Núñez Mora, J. Á., and Revert Ferrero, A. (2025), Estudio cronológico de los volúmenes de precipitación en las subcuencas de la rambla de Poyo en el episodio del 29 octubre de 2024, Investigaciones Geográficas 84, 9 to 29, [doi:10.14198/INGEO.30056](https://doi.org/10.14198/INGEO.30056) ([PDF at AEMET's repository](https://repositorio.aemet.es/bitstream/20.500.11765/17270/1/IG_Perez_2025.pdf)); Confederación Hidrográfica del Júcar, [Informe del episodio de lluvias y avenidas del 28 de octubre al 4 de noviembre de 2024](https://saih.chj.es/docs/20241029-1104Informe-Episodio-C-version2.pdf) (15 Jan 2025); AEMET, [informe del episodio DANA 29 oct 2024](https://repositorio.aemet.es/bitstream/20.500.11765/16360/1/informe_episodio_dana_29_oct_2024_.pdf). Read 15 Nov 2026.
- **Depth estimate**: Cohen, S., Brakenridge, G. R., Kettner, A., Bates, B., Nelson, J., McDonald, R., Huang, Y.-F., Munasinghe, D., and Zhang, J. (2018), Estimating floodwater depths from flood inundation maps and topography, Journal of the American Water Resources Association 54(4), 847 to 858, doi:10.1111/1752-1688.12609. Cohen, S., et al. (2019), The Floodwater Depth Estimation Tool (FwDET v2.0) for improved remote sensing analysis of coastal flooding, Natural Hazards and Earth System Sciences 19, 2053 to 2065, doi:10.5194/nhess-19-2053-2019. Water marks of 2026: ICV service `2702_DANAAdam2026`, as in `pipeline.labels`.
- **Further work**: Chini, M., Pelich, R., Pulvirenti, L., Pierdicca, N., Hostache, R., and Matgen, P. (2019), Sentinel-1 InSAR coherence to detect floodwater in urban areas: Houston and Hurricane Harvey as a test case, Remote Sensing 11(2), 107, doi:10.3390/rs11020107. Rossman, L. A. (2015), Storm Water Management Model User's Manual, Version 5.1, EPA/600/R-14/413b, U.S. Environmental Protection Agency.
- **Methods**: Nobre, A. D., et al. (2011), Height Above the Nearest Drainage, a hydrologically relevant new terrain model, Journal of Hydrology 404, 13 to 29, doi:10.1016/j.jhydrol.2011.03.051. Yamazaki, D., et al. (2019), MERIT Hydro: a high-resolution global hydrography map based on latest topography datasets, Water Resources Research 55, 5053 to 5073, doi:10.1029/2019WR024873 (drainage above 0.5 km²: [MERIT Hydro page](https://global-hydrodynamics.github.io/MERIT_Hydro/), read 15 Nov 2026). Twele, A., Cao, W., Plank, S., and Martinis, S. (2016), Sentinel-1-based flood mapping: a fully automated processing chain, International Journal of Remote Sensing 37(13), 2990 to 3004, doi:10.1080/01431161.2016.1192304. Garbrecht, J., and Martz, L. W. (1997), The assignment of drainage direction over flat surfaces in raster digital elevation models, Journal of Hydrology 193, 204 to 213. Bates, P. D., Horritt, M. S., and Fewtrell, T. J. (2010), A simple inertial formulation of the shallow water equations for efficient two-dimensional flood inundation modelling, Journal of Hydrology 387, 33 to 45, doi:10.1016/j.jhydrol.2010.03.027.

Written with SI assistance (Claude Code), reviewed by the team.
