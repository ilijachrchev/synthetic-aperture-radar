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

## Street by street: which method pointed to the streets that flooded

The same test as above, counted in street length instead of land: of the streets that really flooded on 29 Oct 2024 in the 10 towns, how much did each method point to, and how much of what it pointed to really flooded. Code: `pipeline/street_scores.py`; numbers: `results.json` → `streets`.

### Rules (written before any street score)

Written down on 15 Nov 2026 and committed before any street was scored (see the git history of this file). The downloads (streets, UPV map) were made before; nothing was scored with them. The methods are those of PR #39, unchanged; no threshold below was chosen by looking at a result. Any later change goes under "Changes to the rules" with its reason, and the result under the original rule is kept.

**Streets.**

- **Source**: OpenStreetMap as it was on 28 Oct 2024 at 00:00 UTC, the day before the flood (Overpass API, attic query `[date:"2024-10-28T00:00:00Z"]`): every way tagged `highway` in a box around each of the 10 municipalities (the IGN polygons of PR #36 plus about 200 m), read 15 Nov 2026. © OpenStreetMap contributors, ODbL 1.0. Coordinates to EPSG:25830 with pyproj; a way that appears in two boxes counts once.
- **Kept**: roads (`highway` = `motorway`, `trunk`, `primary`, `secondary`, `tertiary`, the `_link` of each, `unclassified`, `residential`, `living_street`, `service`, `road`, `busway`) and pedestrian ways (`pedestrian`, `footway`, `path`, `steps`, `cycleway`).
- **Left out**: farm and forest tracks (`track`, kept in one sensitivity run below), sidewalks and crossings drawn as their own ways (`footway`, `path` or `cycleway` tagged `sidewalk` or `crossing`: they repeat a street that is already counted), ways in a tunnel (`tunnel` present and not `no`: the maps describe the ground above them), areas (`area=yes`, squares drawn as outlines), and every other `highway` value (construction, proposed, platforms, corridors and the like).
- **Pieces**: each way is cut into n pieces of equal length, n being its length divided by 25 m, rounded, at least 1. Pieces are therefore 12.5 to 37.5 m long, except ways shorter than 12.5 m, which stay whole. Lengths are planar metres in EPSG:25830.
- **Sample points**: each piece of length l gets m = ceil(l / 2.5 m) points, at the centres of m equal parts (at most 2.5 m apart).
- **Scored pieces**: a piece counts when its midpoint lies on a scored pixel of PR #39 (inside one of the 10 municipalities, inside the area an EMSR773 product analysed, not permanent water, with terrain). Its town is the town of that pixel. Everything below is read on the 5 m grid of PR #39 (the cell holding the point), over the piece's sample points that lie on scored pixels (if none does, its midpoint alone).
- **A piece is in a layer** when at least half of those sample points lie on cells of that layer.

**What counts as a flooded street (the answer keys; never used to build or tune a method).**

- **Key A, observed**: a piece is flooded if it is in the EMSR773 observed flood (maximum observed extent, flooded area or flood traces, exactly the raster of PR #39), or if any part of it lies within 10 m (planar distance from the piece's line) of a surveyed water mark above 0 m (the ICV layers `DANA2024.ZonasInundadas.AlturaAgua.UPV`, `.IVE`, `.SGRT`, `.AyuntamientosOtros`, as in PR #39). Otherwise it is dry. Sensitivity only: EMSR773 alone, and the marks alone.
- **Key B, the UPV street depth map** (CGAT, Universitat Politècnica de València; Roch Talens et al. 2025): the maximum water depth, interpolated from flood marks the CGAT measured on walls (6,483 points) on the 2023 LiDAR terrain. WCS coverage `dana2024__H_lamina` of `https://dana2024.gisserver.car.upv.es/geoserver/dana2024/wcs` (depth with buildings not masked; the viewer's default layer is the same surface with the building footprints removed, so on streets the two agree), 0.5 m pixels in EPSG:25830, version "result updated 05/11/2026", read 15 Nov 2026. Each 5 m cell takes the depth of the 0.5 m pixel that holds its centre. A piece is flooded if at least half of its sample points have a depth above 0.1 m. Key B is scored only on the pieces whose midpoint lies inside the map's outlines (the surveyed area and the extra zones, WFS layers `dana2024:Delimitació CGAT` and `dana2024:delimitació zona extra`); outside them the map says nothing, and the street length it covers is reported per town. For a piece inside the outlines, a sample point without a value counts as dry, 0 m (the map holds values above 0 m only; see the check below). Key B is never merged with key A.
- **Licence of the UPV map**: none is named. The viewer says "The data are freely available through the WMS server" and asks to cite the article; the GeoServer capabilities (WMS, WCS, WFS) give Fees NONE and AccessConstraints NONE. It is used here for derived numbers only, with the citation; the raster stays in `data/interim/` and is not redistributed.
- **Not independent**: the UPV map is built from wall marks, and the UPV marks in the ICV service (part of key A) come from the same survey. Key B is a second view of the same kind of evidence, not an independent one.

**Methods** (each flags the pieces that are in its layer; layers exactly as in PR #39).

1. **Official zones** (SNCZI): T10, T100 and T500 apart, and any zone (their union).
2. **Terrain, HAND below 15 m** (PR #39 method 2: bare terrain, drainage above 0.5 km²).
3. **Terrain, equal-area cut** (PR #39 method 3 at the union area: in each town the scored pixels of lowest HAND, as many as the town's pixels in any official zone).
4. **SIMULATED run, its own extent**: maximum simulated depth above 0.3 m (PR #39 method 4, the 25 m cell holding the 5 m cell).
5. **SIMULATED run, equal-area cut** (PR #39: in each town the deepest scored pixels, as many as the town's pixels in any official zone).

**Equal street length.** In each town, any official zone flags some street length L. Each ranking is cut to the same length: its pieces in order, taken until their summed length first reaches L (so it exceeds L by less than one piece). Terrain ranks pieces by the median HAND of their sample points, lowest first; the SIMULATED run by the median of their maximum simulated depth, deepest first; ties by way id and position along the way; pieces without a value come last. Both terrain methods (2, 3) share the one terrain ranking, and both simulated methods (4, 5) the one simulated ranking. The official zones at equal length are any zone itself (T10, then T100, then T500 would rank to the same set).

**Metrics**, for every method, per town and for the 10 towns together, for each key:

- **Street length flagged** (km) and its share of the scored street length.
- **Hit rate**: the share of the flooded street length that the method flagged.
- **Precision**: the share of the method's flagged street length that really flooded.
- **Chance**: a random choice of pieces of the same length has, on average, a hit rate equal to its share of the street length and a precision equal to the flooded share of the street length. Every result is read against it.
- **At equal street length**: hit rate and precision of each ranking (with the same length they move together), and the official zones' for comparison.
- **Key B** is computed on the pieces inside the UPV outlines only: the same metrics, with the flagged length inside the outlines.

**What is fixed and what is only sensitivity.**

- **Headline** (fixed now): at equal street length, per town and in total, the hit rate against key A of the terrain ranking and of the SIMULATED ranking against the official zones (any zone). Second headline: the same against key B. The methods at their own length are reported in full, but a method that flags more street catches more, so they are not the headline.
- **Sensitivity only, never used to pick a version**: tracks included; key A from EMSR773 alone; key A from the marks alone.
- **Checks**: pieces and kilometres per town and per `highway` value; the share of sample points on scored pixels; the equal-area cuts of PR #39 rebuilt with the same cell count per town as `results.json`; for key B, what the UPV map holds at the surveyed marks of 0 m (dry spots) and above 0 m.
- Whatever the numbers show is written here, including where the official zones do better.

### Results

Every number below is in `results.json` → `streets` (`main`, `with_tracks`, `checks`, `inputs`), written by `python -m pipeline.street_scores score`; the tables are printed from it by `python -m pipeline.street_scores report`. Scored streets: 64,174 pieces, **1,591.2 km** in the 10 towns, cut from the 16,092 OSM ways kept in the 10 boxes (of 21,515 read, 3,010 tracks, 2,101 sidewalks and crossings, 124 tunnels, 113 areas and 75 other values were left out; pieces whose midpoint is not on a scored pixel, Valencia city's for instance, are not scored). Key A: **513.7 km flooded** (32.3 % of the streets). Key B: 519.1 km flooded of the 801.5 km that lie inside the UPV outlines (64.8 %).

**Short answer: at the same street length, no method beat the official map; what the official map lacks is reach.** Cut town by town to the 280.0 km of street that the official zones flag, the terrain ranking caught **41.4 %** of the flooded street length (key A), the SIMULATED run **41.3 %** and the zones themselves **41.0 %**, and 75 to 76 % of what each flagged really flooded (a random pick of the same length: 32.3 %). Against the UPV map the zones lead: 50.8 % against 46.4 % for the terrain and 50.4 % for the simulation. But **303 of the 514 km of streets that flooded (59.0 %) lay outside every official zone** (key B: 255 of 519 km, 49.2 %). The SIMULATED run at its own extent (maximum depth above 0.3 m) reaches them: it flags 531.6 km and catches **76.0 %** of the flooded streets with **73.4 %** of its streets really flooded, against 41.0 % and 75.2 % for the zones; it finds 390.4 km of flooded street where the zones find 210.7 km. That run is a hindcast: it was fed the rain measured on the day, with no infiltration (PR #39), so it shows what terrain and rain together point to, not what anyone could have known before the storm.

#### The same street length, town by town (headline)

Key A. Each ranking cut to the street length the official zones (any zone) flag in that town.

| Town | Streets (km) | Flooded (km) | Zones' length (km) | Hit rate: zones / terrain / simulated | Precision: zones / terrain / simulated | Chance precision |
|---|---|---|---|---|---|---|
| Paiporta | 76.0 | 75.3 | 27.5 | 36.5 / 36.5 / 36.5 % | 100.0 / 99.9 / 100.0 % | 99.1 % |
| Massanassa | 35.1 | 24.8 | 32.4 | 89.3 / 97.1 / 94.7 % | 68.4 / 74.3 / 72.4 % | 70.6 % |
| Sedaví | 30.9 | 23.5 | 0.7 | 3.0 / 3.0 / 3.0 % | 100.0 / 100.0 / 100.0 % | 76.1 % |
| Catarroja | 103.6 | 64.2 | 77.7 | 83.4 / 84.6 / 82.3 % | 68.9 / 69.9 / 68.0 % | 62.0 % |
| Alfafar | 86.8 | 67.9 | 60.0 | 77.0 / 84.2 / 77.4 % | 87.1 / 95.2 / 87.5 % | 78.2 % |
| Benetússer | 21.3 | 5.9 | 6.0 | 44.3 / 22.8 / 39.8 % | 43.0 / 22.1 / 38.6 % | 27.6 % |
| Picanya | 94.2 | 83.4 | 3.0 | 3.6 / 2.8 / 3.4 % | 98.4 / 75.5 / 93.4 % | 88.6 % |
| Aldaia | 163.2 | 92.0 | 56.4 | 42.8 / 45.6 / 45.5 % | 69.8 / 74.3 / 74.3 % | 56.4 % |
| Chiva | 429.3 | 11.0 | 6.5 | 15.8 / 6.2 / 2.8 % | 26.5 / 10.4 / 4.7 % | 2.6 % |
| Torrent | 551.0 | 65.7 | 9.6 | 11.8 / 3.8 / 11.3 % | 80.7 / 25.6 / 77.4 % | 11.9 % |
| **Total** | 1,591.2 | 513.7 | 280.0 | 41.0 / 41.4 / 41.3 % | 75.2 / 75.9 / 75.7 % | 32.3 % |

Key B (UPV depth above 0.1 m), on the streets inside the UPV outlines only; the cut is the same, the length counted inside the outlines.

| Town | Streets inside (km) | Flooded (km) | Zones' length inside (km) | Hit rate: zones / terrain / simulated | Precision: zones / terrain / simulated | Chance precision |
|---|---|---|---|---|---|---|
| Paiporta | 75.9 | 72.4 | 27.5 | 37.8 / 37.2 / 37.8 % | 99.5 / 97.8 / 99.6 % | 95.4 % |
| Massanassa | 35.1 | 33.2 | 32.4 | 95.3 / 92.2 / 94.4 % | 97.7 / 94.5 / 96.7 % | 94.5 % |
| Sedaví | 30.9 | 29.7 | 0.7 | 2.3 / 2.4 / 2.2 % | 100.0 / 100.0 / 92.8 % | 96.2 % |
| Catarroja | 84.3 | 77.2 | 76.6 | 94.7 / 86.7 / 93.3 % | 95.5 / 93.6 / 94.6 % | 91.7 % |
| Alfafar | 86.8 | 83.7 | 60.0 | 69.8 / 70.2 / 70.6 % | 97.3 / 97.9 / 98.4 % | 96.5 % |
| Benetússer | 21.3 | 21.2 | 6.0 | 28.4 / 28.4 / 28.4 % | 100.0 / 100.0 / 100.0 % | 99.9 % |
| Picanya | 82.9 | 70.9 | 3.0 | 4.2 / 3.0 / 3.9 % | 98.4 / 90.6 / 91.7 % | 85.5 % |
| Aldaia | 139.2 | 91.7 | 56.4 | 59.5 / 49.9 / 58.1 % | 96.8 / 85.5 / 95.0 % | 65.9 % |
| Chiva | 121.0 | 5.8 | 0.5 | 8.7 / 15.6 / 9.1 % | 100.0 / 81.8 / 100.0 % | 4.8 % |
| Torrent | 124.1 | 33.1 | 9.6 | 24.8 / 6.1 / 25.3 % | 85.6 / 69.7 / 93.7 % | 26.7 % |
| **Total** | 801.5 | 519.1 | 272.7 | 50.8 / 46.4 / 50.4 % | 96.6 / 93.3 / 96.4 % | 64.8 % |

With a budget of 0.7 km (Sedaví), 3.0 km (Picanya) or 0.5 km (Chiva under key B), every ranking catches almost nothing, by design. Inside the UPV outlines 64.8 % of the street length flooded (90.3 % in the surveyed area alone), so key B leaves little room between a good and a random pick.

- **Terrain better**: the low plain by the Albufera again, Massanassa (97.1 against 89.3 %) and Alfafar (84.2 against 77.0 %), and a little in Aldaia (45.6 against 42.8 %).
- **Terrain worse**: Torrent (3.8 against 11.8 %), Chiva (6.2 against 15.8 %) and Benetússer (22.8 against 44.3 %), as on land in PR #39: in the hills the lowest streets are gully floors, not the Poyo's path. Against key B the zones also lead the terrain in Catarroja (94.7 against 86.7 %) and Aldaia (59.5 against 49.9 %).
- **SIMULATED ranking**: level with the zones in Torrent (11.3 against 11.8 %; key B 25.3 against 24.8 %), better in Massanassa and Aldaia, worse in Chiva (2.8 %) and Benetússer.
- **Why the terrain ties here but trailed on land.** PR #39's equal-area terrain map, cut to the zones' land, holds only 230.8 km of street (the zones' land holds 280.0 km): part of its land budget goes to fields and gully floors without streets. Ranking the street pieces themselves removes that handicap, and the terrain then catches as much as the zones (41.4 against 41.0 %). At the pixel cut it is behind (33.6 %, below), like on land.

#### Every method at its own length, the 10 towns together

| Method | Flagged (km) | Share of streets | Key A: hit rate | Key A: precision | Key B: flagged inside (km) | Key B: hit rate | Key B: precision |
|---|---|---|---|---|---|---|---|
| Official T10 | 9.0 | 0.6 % | 1.3 % | 76.7 % | 8.1 | 1.4 % | 91.7 % |
| Official T100 | 37.2 | 2.3 % | 5.1 % | 70.6 % | 34.6 | 6.4 % | 96.5 % |
| Official T500 | 279.9 | 17.6 % | 41.0 % | 75.2 % | 272.7 | 50.8 % | 96.6 % |
| **Official, any zone** | 280.0 | 17.6 % | **41.0 %** | **75.2 %** | 272.7 | **50.8 %** | **96.6 %** |
| Terrain, HAND below 15 m | 1,062.3 | 66.8 % | 98.3 % | 47.5 % | 686.5 | 99.9 % | 75.5 % |
| Terrain, equal-area cut of PR #39 | 230.8 | 14.5 % | 33.6 % | 74.7 % | 203.8 | 36.6 % | 93.2 % |
| **SIMULATED, depth above 0.3 m** | 531.6 | 33.4 % | **76.0 %** | **73.4 %** | 479.5 | **81.9 %** | **88.7 %** |
| SIMULATED, equal-area cut of PR #39 | 255.7 | 16.1 % | 36.3 % | 73.0 % | 239.9 | 44.7 % | 96.6 % |
| Chance (a random pick) | | | = its share | 32.3 % | | = its share | 64.8 % |

- The frequent and occasional zones flag almost no street: T10 9.0 km (1.3 % of the flooded street length), T100 37.2 km (5.1 %). Everything the official map caught, it caught with the rare T500 zone.
- HAND below 15 m flags two thirds of the streets: it misses almost nothing (98.3 %), but half of what it flags stayed dry (precision 47.5 %). It says where water cannot go (the hills), not where it went.
- The SIMULATED extent flags 1.9 times the zones' street length at almost their precision (73.4 against 75.2 %). **Outside every official zone** it flags 291.0 km, of which 70.6 % flooded, where only 23.1 % of all streets outside the zones flooded (key B: 79.2 % against 48.3 %). Descriptive, computed after the headline.

#### Reach: the zones and the SIMULATED extent at their own length, town by town

Key A.

| Town | Zones: km | Zones: hit rate | Zones: precision | SIMULATED: km | SIMULATED: hit rate | SIMULATED: precision |
|---|---|---|---|---|---|---|
| Paiporta | 27.5 | 36.5 % | 100.0 % | 58.6 | 77.5 % | 99.5 % |
| Massanassa | 32.4 | 89.3 % | 68.4 % | 27.4 | 82.3 % | 74.4 % |
| Sedaví | 0.7 | 3.0 % | 100.0 % | 24.1 | 82.8 % | 80.8 % |
| Catarroja | 77.7 | 83.4 % | 68.9 % | 58.1 | 61.5 % | 67.9 % |
| Alfafar | 60.0 | 77.0 % | 87.1 % | 73.9 | 92.6 % | 85.1 % |
| Benetússer | 6.0 | 44.3 % | 43.0 % | 11.9 | 62.5 % | 30.7 % |
| Picanya | 3.0 | 3.6 % | 98.4 % | 78.0 | 90.8 % | 97.1 % |
| Aldaia | 56.4 | 42.8 % | 69.8 % | 82.8 | 66.8 % | 74.3 % |
| Chiva | 6.5 | 15.8 % | 26.5 % | 41.8 | 55.1 % | 14.5 % |
| Torrent | 9.6 | 11.8 % | 80.7 % | 75.0 | 65.2 % | 57.1 % |
| **Total** | 280.0 | 41.0 % | 75.2 % | 531.6 | 76.0 % | 73.4 % |

Where the official map left a town almost bare, the simulated run, fed the day's rain, found most of its flooded streets: Picanya (90.8 against 3.6 %, with 97.1 % of its streets flooded), Sedaví (82.8 against 3.0 %), Torrent (65.2 against 11.8 %, though only 57.1 % of what it flags there flooded), Paiporta (77.5 against 36.5 %). Where the zones were drawn on the fan (Catarroja, Massanassa) they catch more than the simulation (83.4 against 61.5 %, 89.3 against 82.3 %). In Chiva most of what it flags stayed dry (14.5 %), as on land.

#### Sensitivity (never used to pick a version)

At equal street length, hit rate of the zones / terrain / SIMULATED:

- Key A from EMSR773 alone (495.8 km flooded): 40.7 / 41.6 / 41.4 %.
- Key A from the water marks alone (36.4 km of street within 10 m of a mark): 47.5 / 41.2 / 40.6 %: on the streets beside a surveyed mark the zones lead.
- Tracks included (2,254.0 km of street, 664.8 km flooded, zones' length 363.3 km): key A 43.4 / 42.5 / 42.4 %, key B 53.0 / 46.7 / 51.7 %. The SIMULATED extent: 76.5 % at 73.3 % precision.
- **Key B on the surveyed area alone (POST-HOC, see "Changes to the rules", item 4)**: 508.8 km of street, 459.2 km flooded: 53.0 / 47.7 / 51.6 %; the SIMULATED extent 82.3 % at 95.1 % precision, the zones 53.0 % at 97.0 %.

#### Checks

- **The equal-area cuts of PR #39 rebuilt exactly**: for the terrain and the SIMULATED cuts, every town has the same cell count and the same share of land flooded as `results.json` → `methods` (`checks.equal_area_cuts_rebuilt`).
- **Pieces**: median length 25.0 m (5 % to 95 %: 22.8 to 26.7 m); every scored piece has sample points on scored pixels (none fell back to its midpoint). Street length by class: residential 603.4 km, unclassified 278.5, tertiary 137.5, service 122.6, path 114.4, cycleway 73.5, motorway 63.4, secondary 57.5, footway 37.7, motorway links 34.2, the rest 68.5 km.
- **The UPV map at the surveyed marks** (`checks.upv_at_marks`): inside its outlines lie 3,663 wet marks; the map has a value at 87.2 % of them, at 91.6 % of the 3,299 in the surveyed area but only at 47.8 % of the 364 in the extra zones. Where it has a value, its median depth is 1.22 m against 1.30 m on the walls (median absolute difference 0.15 m, correlation 0.81; the map is built from such marks). Only 5 marks of 0 m lie inside the outlines, too few to check dry spots. So in the extra zones "no value" is often not dry, and key B, which counts it as dry as the rule says, misses flooded streets there; hence the post-hoc variant above.
- **The two keys inside the UPV outlines** agree on 76.8 % of the street length; key A has 486.1 km flooded there, key B 519.1 km.
- A map of the keys and flags around Torrent, Picanya, Paiporta and the plain was looked at before writing this: the flooded streets of both keys follow the Poyo's path along the north edge of Torrent and through Picanya and Paiporta, then spread over the plain; Torrent's centre stayed dry.

#### What this means, and what it does not

- Length for length, the official zones choose flooded streets as well as the terrain ranking and the simulation. Their failure in 2024 was size: they flag 17.6 % of the streets and left out 59 % of the flooded street length (49 % by the UPV map), almost all of Picanya and Sedaví and nearly nine tenths of Torrent's.
- Only a method that points beyond the zones can reach those streets, and only one of ours did so with few false alarms (about one flagged street in four stayed dry): the simulated run fed with the rain that was measured. Its value for a warning would depend on a rain forecast as good as that measurement; it was not tested with a forecast here.
- One event, one town network: as above, nothing here is a validation across floods.

## Two more simulations: the forecast of the night before, and buildings

The SIMULATED run above was fed the rain measured on the day, so it shows what terrain and rain together point to, not what anyone could have known before the storm. Two more runs of the same model test that, each scored street by street exactly like it. Code: `pipeline/streets.py` (steps `fetch-forecast`, `sim-prepare`, `sim-collect`) and `pipeline/street_scores.py`; numbers: `results.json` → `simulation_runs` and `streets`.

### Rules (written before any score of these runs)

Written down on 15 Nov 2026 and committed before either run was simulated or scored (see the git history of this file). The forecast was downloaded, and its rain at the grid points looked at, before this was written. Nothing below was chosen by looking at a 2024 score. Any later change goes under "Changes to the rules" with its reason, and the result under the original rule is kept.

**Run A, "the night before": the same model, driven by the rain of the forecast.**

- **Forecast**: ECMWF IFS HRES, the deterministic high resolution forecast at its native 9 km (O1280 grid), from Open-Meteo's Single Runs API (`https://single-runs-api.open-meteo.com/v1/forecast`, `models=ecmwf_ifs`, `run=` the initial time), which returns one model run as it was issued. Open-Meteo's Historical Forecast API is not used: it joins the first hours of successive runs, so for 29 Oct it would take rain from runs started during the storm.
- **Two runs, fixed now, both reported, neither chosen**: initial time 28 Oct 2024 12:00 UTC (available to forecasters in the evening of 28 Oct) and 29 Oct 2024 00:00 UTC (available on the morning of 29 Oct, hours before the flood).
- **Variable**: hourly precipitation (`precipitation`: rain, showers and snow of the preceding hour, mm), `cell_selection=nearest`, `timezone=GMT`, 3 forecast days. The value at a run's initial hour has no preceding hour and counts as 0.
- **Grid points**: Open-Meteo is asked at the points of a 2 km lattice over the Poyo, Pozalet and Saleta catchment (ICV `DANA2024.AVSRE.Cuencas`, code 29) and 6 km around it (339 points); it answers each with the grid point it used. The distinct grid points are the forecast's grid points here; their coordinates and elevations are recorded.
- **Rain on the zones**: the three rain zones of the run above, unchanged. Each 25 m cell of a zone takes the rain of its nearest grid point (great-circle distance); a zone's hourly rain is the mean over its area, spread evenly over the zone, as the gauged rain was. As in the run above, no rain falls outside the three zones: the forecast's rain on the plain is reported, not simulated.
- **Hours**: the same 25 hours, 29 Oct 05:00 to 30 Oct 06:00 local time (CET; 04:00 UTC to 05:00 UTC the next day). Open-Meteo's value at 05:00 UTC is the rain of 04:00 to 05:00 UTC, the run's first hour (PH06 in Pérez Cueva et al.). The gauged rain fell in the first 19 of these hours (PH06 to PH24); the forecast's rain in all 25 is used. Forecast rain before 29 Oct 05:00 local is not simulated, as for the gauged run, whose table starts at PH06; it is reported.
- **Everything else as the run above**: the same 25 m terrain, Manning's n 0.05, no infiltration, the same sinks, time steps and gauge record.
- **Recorded**: the grid points and their share of each zone, the run times, each zone's hourly rain and its total in the 25 hours and since the initial time, against the gauged totals (Poyo up to the gauge 79.0 hm³, 431.7 mm; gauge to fan apex 68.4 hm³, 405.9 mm; Possalet-Saleta 9.9 hm³, 132.7 mm), and the modelled flow at the CHJ gauge (a check, not a calibration).

**Run B, "better physics": the gauged rain, buildings as obstacles.**

- The run above with one change: buildings stand in the water's way. The Catastro INSPIRE footprints of PR #39 (data of 21 Aug 2026, the same files: their checksums match) in the 5 m raster of PR #39 (a 5 m cell is a building when its centre lies inside a footprint) are raised by 10 m, as in PR #39's buildings variant. On the 25 m grid, a cell is raised by 10 m when at least half of its 25 cells of 5 m are building cells; every other cell keeps the bare terrain. Sink cells are never raised. Rain falls on raised cells too and runs off them, as roof water reaches the street.
- Why a majority and not a mean: a 25 m cell holds street and building; raising every cell by its building share would put a step of a few metres in most street cells. The majority rule keeps a cell open unless it is mostly building. At 25 m many narrow streets lie in cells that are mostly building, so this blocks more than reality does; it is a coarse picture of the buildings and is labelled as such.
- Only the buildings of the 10 municipalities are in the data (Catastro was read for them alone); buildings of the other municipalities on the grid are not raised.

**Scoring (both runs).**

- `pipeline/street_scores.py` exactly as in "Street by street" above: the same pieces, the same keys (key A everywhere, key B only inside the UPV outlines), the same majority rule. Each new run is scored as the SIMULATED run is: (1) its own extent, maximum depth above 0.3 m; (2) its ranking (median maximum depth of a piece's sample points, deepest first) cut, town by town, to the street length the official zones flag.
- Reported for each run, in total and per town, against key A and key B: flagged street length (km), hit rate (share of the flooded street length flagged) and precision (share of the flagged length that really flooded), always together, next to the official zones (any zone) and the SIMULATED run above. Descriptive, after these: the street length each run flags outside every official zone, and the share of it that flooded.
- **The two forecasts are reported side by side and neither is chosen.** A "before the storm" number is quoted with its run's initial time, its hit rate and its precision.
- **Ceiling (two records of the same flood)**, added on request before any score of these runs: on the streets both keys cover (pieces inside the UPV outlines), key B (the UPV map) is scored as if it were a method against key A, and key A against key B, with the same hit rate and precision. It shows how well one record of this flood matches the other, so how far any method could get against them; the two records are not independent (the UPV marks are part of key A). So that the ceiling can be read on the same streets, every method's key A numbers are also given inside the UPV outlines. It is reported in the same table, labelled "ceiling (two records of the same flood)".
- **The rebuild is checked.** The terrain and the run above were rebuilt on 15 Nov 2026 from the same sources (the earlier intermediate files were deleted with their working copy). The rebuilt run must reproduce PR #39 (time steps, volumes, gauge flow) and PR #43 (its street scores); any difference is reported.
- No threshold or setting (0.3 m, the majority, 10 m, the hours, the zones, the averaging) changes after a score is seen. If a run does not finish in time, this page says so.

**Amendment: run A3, "the same morning"** (added on 15 Nov 2026 at about 10:00 UTC, at the team's request, *after* run A with the forecast of 29 Oct 00 UTC had been scored; committed before run A3 was simulated or scored; see "Changes to the rules", item 5).

- **The run**: the same model and settings as run A, driven by the ECMWF IFS HRES run with initial time 29 Oct 2024 06:00 UTC, fetched in the same way (the same 339 query points; it answers with the same 24 grid points).
- **Why**: a forecast closer to the storm. ECMWF's dissemination schedule (`https://confluence.ecmwf.int/display/DAC/Dissemination+schedule`, read 15 Nov 2026, page last updated 7 Oct 2026) sends the 06 UTC run's hourly steps 0 to 90 between 11:45 and 12:12 UTC, so about 12:45 to 13:12 local time; the page does not give the schedule of October 2024, which may differ by some minutes. That is about five hours before the streets of Chiva flooded (17:47 local) and about six before the Poyo's last gauge reading (2,282.9 m³/s at 18:55; both in the timeline of `docs/ZONES.md`).
- **Its first hours**: the run starts two hours after the window opens (04:00 UTC). The window's hours up to its initial time (04:00 to 06:00 UTC, 05:00 to 07:00 local) take the rain of the 29 Oct 00 UTC run, the newest forecast for those hours at 06 UTC; every later hour is the 06 UTC run's.
- **Scored and reported exactly like run A**: own extent and the zones' street length, keys A and B, the streets outside every official zone, next to the zones, the gauged run and the other forecast runs. All three forecast runs are reported; none is chosen.

### Results

Every number below is in `results.json`: the runs in `simulation_runs` (rain, volumes, gauge flow), their street scores in `streets_more_runs` (written by `python -m pipeline.street_scores score-runs`; the tables are printed from it by `report-runs`). The PR #39 run and its PR #43 street scores stay in `simulation` and `streets`.

**The rebuild.** The intermediate files of PR #39 had been deleted with the working copy that held them, so on 15 Nov 2026 they were rebuilt from the same sources. The two 1 m terrain sheets downloaded whole (0722, 0721) have PR #39's SHA-256. The other four were averaged to 5 m while being read over HTTP, because disk space was short; they have PR #39's byte sizes and dimensions. Catastro, WorldCover and the rain papers have PR #39's checksums. The ICV, SNCZI and OSM files differ from PR #39's only in their download time stamps (same sizes, or 1 or 2 bytes apart where the time stamp is written with fewer digits). The rebuilt grid matches PR #39 cell for cell in every count: 52,653,524 cells with terrain, 1,621,421 of permanent water, 1,510,811 lake cells, 479,941 building cells, and in the lake routing 4,420,130 flat cells drained in 989 rounds. The three rain zones cover 183.0, 168.7 and 74.6 km², again as in PR #39.

**The forecast rain against the gauged rain** (`results.json` → `simulation_runs` → `rain_forecast`). On the three zones, over the 25 hours of the run (29 Oct 05:00 to 30 Oct 06:00 local):

| Zone | Area | Gauged (Pérez Cueva et al. 2025) | IFS run of 28 Oct 12 UTC | IFS run of 29 Oct 00 UTC |
|---|---|---|---|---|
| Poyo up to the CHJ gauge | 183.0 km² | 431.7 mm (79.0 hm³); heaviest hour 71 mm, 19:00 to 20:00 | 170.0 mm (39 %); heaviest hour 15.8 mm, 15:00 to 16:00 | 149.8 mm (35 %); heaviest hour 14.2 mm, 14:00 to 15:00 |
| Poyo, gauge to fan apex | 168.7 km² | 405.9 mm (68.4 hm³); heaviest hour 98 mm, 17:00 to 18:00 | 165.0 mm (41 %); heaviest hour 17.9 mm, 13:00 to 14:00 | 170.2 mm (42 %); heaviest hour 14.3 mm, 15:00 to 16:00 |
| Possalet-Saleta | 74.6 km² | 132.7 mm (9.9 hm³); heaviest hour 43 mm, 17:00 to 18:00 | 156.9 mm (118 %); heaviest hour 15.4 mm, 12:00 to 13:00 | 135.3 mm (102 %); heaviest hour 11.9 mm, 15:00 to 16:00 |

Local time (CET). Each zone's rain comes from 12 of the 24 grid points found (the nearest grid point of each 25 m cell); Open-Meteo's own choice of grid point was the great-circle nearest at all 339 query points. From each run's initial time to the end of the window the totals are hardly larger (Poyo up to the gauge: 174.3 and 150.6 mm), so cutting the window at 29 Oct 05:00 local loses little.

The forecasts put heavy rain on the right ravines, but a third to two fifths of what fell on the Poyo, with their heaviest hour two to five hours early and about a fifth as intense as the gauged one. On the small Possalet-Saleta catchment they gave as much as fell, or slightly more.

**The rebuilt PR #39 run** (rerun on 15 Nov 2026 from the rebuilt inputs, to check them) reproduces PR #39 exactly: 95,092 time steps, 157.38 hm³ of rain, 110.63 hm³ left at the sinks and 46.74 hm³ on the ground at the end, 3,052.5 m³/s at the CHJ gauge at 18:55 and a peak of 3,291.7 m³/s at 20:40. Street by street it reproduces PR #43 exactly too: the same 64,174 pieces, the same keys (513.7 km flooded under key A, 519.1 km under key B), the same official zones, and for the SIMULATED run the same 531.65 km at its own extent with 76.0 % found and 73.4 % really flooded, and the same ranking at equal length (`streets_more_runs` → `same_as_pr43`). One PR #39 method is left out of the new block: the equal-area pixel cut of the SIMULATED run breaks its ties (the 25 cells of 5 m in each 25 m cell share one depth) by the bare terrain's upstream area, and that routing was not rebuilt.

**Short answer: with the rain the forecast gave before the storm, the model did not point to more of the flooded streets than the official map; the 76 % of the hindcast came from the rain that really fell.** At its own extent (maximum depth above 0.3 m), the run fed the IFS forecast of 29 Oct 00 UTC flags 188.9 km of street and finds **26.1 %** of the flooded street length (key A), with **70.9 %** of what it flags really flooded; the run fed the forecast of 28 Oct 12 UTC flags 194.7 km and finds **26.8 %**, with **70.6 %** really flooded. The official zones find 41.0 % at 75.2 %, the hindcast with the gauged rain 76.0 % at 73.4 %. Cut to the zones' street length, the forecast runs tie the zones (40.6 and 40.6 % against 41.0 %), as the hindcast and the terrain did. The forecasts put a third to two fifths of the Poyo's rain on its catchment, at their heaviest hour about a fifth of the gauged intensity, so the Poyo they make peaks at the CHJ gauge at 549 m³/s (17:25, the 29 Oct 00 UTC run) and 636 m³/s (17:50, the 28 Oct 12 UTC run), against 2,282.9 m³/s measured at 18:55 before the gauge was lost. The water stays in the ravines and the low plain: Picanya, Paiporta and Sedaví, where the hindcast found 78 to 91 % of the flooded streets, get almost nothing. Fed by this deterministic forecast, the model could not have pointed to the streets that flooded.

| Run | Rain on the Poyo up to the gauge | Flagged (km) | Key A: found | Key A: really flooded | Key B: found | Key B: really flooded | Key A, cut to the zones' length: found / really flooded | Flow at the CHJ gauge, 18:55 |
|---|---|---|---|---|---|---|---|---|
| Official zones (any zone) |  | 280.0 | 41.0 % | 75.2 % | 50.8 % | 96.6 % | 41.0 / 75.2 % |  |
| SIMULATED, gauged rain (PR #39; rebuilt, identical) | 431.7 mm | 531.6 | 76.0 % | 73.4 % | 81.9 % | 88.7 % | 41.3 / 75.7 % | 3,052.5 m³/s |
| Run A, forecast of 29 Oct 00 UTC | 149.8 mm | 188.9 | 26.1 % | 70.9 % | 31.0 % | 94.6 % | 40.6 / 74.4 % | 529.7 m³/s |
| Run A, forecast of 28 Oct 12 UTC | 170.0 mm | 194.7 | 26.8 % | 70.6 % | 31.9 % | 94.5 % | 40.6 / 74.5 % | 615.8 m³/s |
| Ceiling (two records of the same flood): the UPV map against key A, inside the UPV outlines | | 519.1 | 84.2 % | 78.9 % | | | | |
| Ceiling (two records of the same flood): key A against the UPV map | | 486.1 | | | 78.9 % | 84.2 % | | |

Own extent except the cut column; key B inside the UPV outlines only (801.5 km of street, the flagged length inside them: zones 272.7 km, hindcast 479.5 km, run A 170.2 km (29 Oct 00 UTC), run A 175.1 km (28 Oct 12 UTC)). A random pick of the same length has a precision of 32.3 % (key A) and 64.8 % (key B). The CHJ gauge measured 2,282.9 m³/s at 18:55. The forecast runs are also scored with tracks and against the keys' parts (`streets_more_runs` → `with_tracks`, `key_sensitivity`), and nothing there changes the picture: at their own extent the zones stay ahead (tracks included: 43.4 % found against 30.3 and 31.0 %), and at the zones' length the forecast runs tie them (key A from EMSR773 alone: 40.7 against 40.8 and 40.8 %) or trail them (key A from the marks alone: 47.5 against 36.1 and 36.6 %).

**The ceiling (two records of the same flood).** On the 801.5 km of street inside the UPV outlines, where both keys exist, the UPV map scored as a method against key A finds 84.2 % of the flooded street length with 78.9 % of what it flags flooded; key A against the UPV map finds 78.9 % at 84.2 %. On the same streets, against key A, the official zones find 42.9 % at 76.4 %, the hindcast 78.6 % at 79.7 %, the forecast runs 26.7 % at 76.3 % (29 Oct 00 UTC) and 27.4 % at 76.2 % (28 Oct 12 UTC). Two records of the same flood, both made after it, agree on about four fifths of each other; the hindcast comes close to that, the forecast runs reach about a third of it.

Own extent, key A, by town: found / really flooded (flagged km).

| Town | Flooded (km) | Zones | Gauged rain | A, 29 Oct 00 UTC | A, 28 Oct 12 UTC |
|---|---|---|---|---|---|
| Paiporta | 75.3 | 36.5 / 100.0 % (27.5) | 77.5 / 99.5 % (58.6) | 9.5 / 100.0 % (7.2) | 9.3 / 100.0 % (7.0) |
| Massanassa | 24.8 | 89.3 / 68.4 % (32.4) | 82.3 / 74.4 % (27.4) | 64.0 / 78.0 % (20.3) | 63.9 / 78.1 % (20.3) |
| Sedaví | 23.5 | 3.0 / 100.0 % (0.7) | 82.8 / 80.8 % (24.1) | 3.3 / 100.0 % (0.8) | 3.3 / 100.0 % (0.8) |
| Catarroja | 64.2 | 83.4 / 68.9 % (77.7) | 61.5 / 67.9 % (58.1) | 21.6 / 58.2 % (23.9) | 21.6 / 58.1 % (23.9) |
| Alfafar | 67.9 | 77.0 / 87.1 % (60.0) | 92.6 / 85.1 % (73.9) | 72.2 / 88.6 % (55.3) | 72.3 / 88.7 % (55.3) |
| Benetússer | 5.9 | 44.3 / 43.0 % (6.0) | 62.5 / 30.7 % (11.9) | 37.9 / 39.7 % (5.6) | 37.9 / 40.4 % (5.5) |
| Picanya | 83.4 | 3.6 / 98.4 % (3.0) | 90.8 / 97.1 % (78.0) | 4.5 / 98.1 % (3.8) | 4.6 / 98.2 % (3.9) |
| Aldaia | 92.0 | 42.8 / 69.8 % (56.4) | 66.8 / 74.3 % (82.8) | 29.2 / 71.7 % (37.5) | 32.8 / 71.8 % (42.0) |
| Chiva | 11.0 | 15.8 / 26.5 % (6.5) | 55.1 / 14.5 % (41.8) | 18.5 / 14.4 % (14.2) | 19.9 / 14.6 % (15.0) |
| Torrent | 65.7 | 11.8 / 80.7 % (9.6) | 65.2 / 57.1 % (75.0) | 18.7 / 60.4 % (20.3) | 19.1 / 59.4 % (21.1) |
| **Total** | 513.7 | 41.0 / 75.2 % (280.0) | 76.0 / 73.4 % (531.6) | 26.1 / 70.9 % (188.9) | 26.8 / 70.6 % (194.7) |

**Run A3 (the forecast of 29 Oct 06 UTC, amendment) and run B (buildings)** were still running when this was written (10:10 UTC); their numbers are added here when they are scored.

**What this means, and what it does not.**

- The hindcast's 76 % needs the rain that fell. The ECMWF forecasts before the storm had heavy rain over the right ravines, but a third to two fifths of what fell there, and that was not enough for this model to reach the streets of Picanya, Paiporta and Sedaví. A "before the storm" version of this model would need a better rain forecast, for example the ensemble's wettest members or a convection-permitting model, and that was not tested here.
- One deterministic forecast per run, one event: nothing here says how often a forecast-driven run would miss or find a flood.
- Rain only on the three upstream zones, as in the hindcast; the forecast's rain on the plain is not simulated.

<!-- street results: filled in as the runs are scored -->

## Limits

- **One event.** The 2024 DANA is one test. A method that ranks well here may rank worse in a flood of another shape; nothing here is a validation across events.
- **HAND does not know how much water comes.** It ranks land by its height above the nearest drainage line, the same for a 10-year and a 500-year flood. In 2024 the water came as a flash flood from the catchment upstream (the CHJ gauge read 2,282.9 m³/s at 18:55 before it was destroyed), so how far it spread on the plain depended on that volume, which no terrain map carries. The equal-area cut uses the official zones' area as the budget; a real warning would have to choose a budget from the forecast.
- **Terrain of 2015.** The LiDAR was flown in October and November 2015, nine years before the flood. Buildings, roads and earthworks built since are not in it. Averaging to 5 m smooths walls, kerbs and narrow channels.
- **The references are satellite outlines.** EMSR773 mapped the flood one to two days after the peak; in dense streets the flood traces are photo-interpreted, and a satellite misses water under trees and roofs. "Own area that flooded" is therefore a lower bound for every method alike. The graded buildings exist only where the AOI03 grading map looked (all of L'Horta Sud, 6 % of Chiva).
- **Small official zones, small budgets.** Where the official zones cover little (Torrent, Chiva, Picanya), the terrain map at equal area covers just as little, by design.
- **The simulation is simple and simulated.** No infiltration (all rain runs off, an upper bound), one Manning's n, 25 m cells that cannot resolve streets, no sewers, culverts or bridges other than what the bare-earth terrain shows, and rain only on the three upstream zones.
- **Streets are OpenStreetMap's.** Its coverage differs from street to street: a dual carriageway counts twice, a cycleway drawn beside a road counts as its own way, and the sidewalks and crossings left out are only those tagged as such. Lengths are those of the centre lines, not the street areas.
- **The street keys are not ground truth either.** Key A takes the satellite outline (lower bound, photo-interpreted in dense streets) or a mark within 10 m; key B is an interpolation of wall marks, partly the same marks as key A, and is empty in half of its extra zones. Both read one 5 m cell per sample point, so a narrow street at the edge of a zone or a flood outline can fall either way.

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
| `pipeline/street_scores.py` | street by street: `fetch` (OSM streets of 28 Oct 2024 by Overpass, the UPV depth map by WCS), `score`, `report` |
| `tests/test_street_scores.py` | the street pieces, sample points, the 10 m rule, the majority rule, the equal-length cut and the UPV cell pick on tiny cases |
| `data/streets/forecast_rain_ifs_2024.json` | the input of run A: hourly precipitation of the two ECMWF IFS HRES runs (28 Oct 2024 12 UTC, 29 Oct 2024 00 UTC) at the 24 grid points around the catchment, FORECAST, from Open-Meteo's Single Runs API (CC BY 4.0: weather data by Open-Meteo.com, ECMWF IFS HRES) |

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

Street by street (after `terrain` and `simulate`; the downloads go to `data/interim/streets/osm/` and `upv/`, about 2.5 GB of UPV tiles streamed, 11 MB kept):

```bash
python -m pipeline.street_scores fetch
```

```bash
python -m pipeline.street_scores score
```

```bash
python -m pipeline.street_scores report
```

The two more simulations (after `terrain`; the forecast comes from Open-Meteo, about 1.4 MB). `terrain --only buildings` burns the building footprints without the buildings routing. `sim-prepare` writes one `inputs.npz` per run into `data/interim/streets/simulation_<run>/`; the kernel then runs once per run (they can run side by side, `NUMBA_NUM_THREADS` sets the threads of each); `sim-collect` writes `results.json` → `simulation_runs`; `score-runs` writes `results.json` → `streets_more_runs` and leaves `streets` (PR #43) as it was.

```bash
python -m pipeline.streets fetch-forecast
```

```bash
python -m pipeline.streets terrain --only buildings
```

```bash
python -m pipeline.streets sim-prepare
```

```bash
python -I pipeline/inertial_kernel.py data/interim/streets/simulation_ifs_20241028T12/inputs.npz data/interim/streets/simulation_ifs_20241028T12/outputs.npz
```

```bash
python -I pipeline/inertial_kernel.py data/interim/streets/simulation_ifs_20241029T00/inputs.npz data/interim/streets/simulation_ifs_20241029T00/outputs.npz
```

```bash
python -I pipeline/inertial_kernel.py data/interim/streets/simulation_buildings/inputs.npz data/interim/streets/simulation_buildings/outputs.npz
```

```bash
python -m pipeline.streets sim-collect
```

```bash
python -m pipeline.street_scores score-runs
```

```bash
python -m pipeline.street_scores report-runs
```

## Changes to the rules

1. **Permanent water also counts as drainage for HAND** (decided while writing the code, before any score). The rules make permanent water an outlet of the depression filling, so water that reaches the Albufera leaves the grid there; without this clarification a cell that drains straight into the lake would have no drainage cell on its path. HAND is then measured from the lake surface, as for a river. The lake itself is not a scored pixel.
2. **In the simulation, only water bodies of at least 1 km² are sinks** (decided before any simulation result existed). "Permanent water" in the rules meant the Albufera and the sea, but ESA WorldCover's class 80 also marks 942 small patches inside the catchment (ponds, a quarry lake; 2.7 km² of its 40.5 km² in the grid). One of them lies on the Poyo near Cheste, and with every patch as a sink the D8 routing ended the Poyo there, with 157.6 km² upstream; in the simulation it would have swallowed the flood. The three bodies of 1 km² or more are the sea, the port and the Albufera (37.8 km²). The rain zones are delineated on this routing: the gauge cell drains 183.0 km² (Pérez Cueva et al.: 183.0), the apex 351.7 km² (351.5), the Saleta 74.6 km² (74.6).
3. **A post-hoc check of HAND with the same lake-only sinks** (added after the first scores, because of item 2). The pre-registered HAND, with every WorldCover patch as a sink, stays the headline; the lake-only HAND is reported beside it, labelled post-hoc, so a reader can see whether the ponds change the answer.
4. **Street by street: a post-hoc variant of key B on the UPV surveyed area alone** (added after the first street scores, because of the check of the UPV map at the water marks). The rules count a point without a value inside the UPV outlines as dry; the check showed that in the extra zones the map has no value at 52 % of the wet marks (in the surveyed area at 8 %), so there "no value" is often not dry. Key B as written stays the second headline; the variant limited to the surveyed area (CGAT outline) is reported beside it, labelled post-hoc. It does not change the order (zones 53.0, terrain 47.7, SIMULATED 51.6 % at equal street length).
5. **Two more simulations: a third forecast run, A3 (29 Oct 2024 06 UTC)**, added on 15 Nov 2026 at the team's request after run A with the forecast of 29 Oct 00 UTC had been scored (it found fewer flooded streets than the official zones), and committed before run A3 was simulated or scored. The two forecast runs fixed in advance stay as they are and are reported whatever run A3 shows; the reason for the third is a forecast available closer to the storm (see the amendment in "Two more simulations"). Being added after a score was seen, run A3 is reported beside the others and is not a replacement for them.

## Sources

- **Terrain**: Institut Cartogràfic Valencià, Modelo Digital del Terreno (MDT) de LIDAR de 1 metro de resolución de la provincia de Valencia 2015, by MTN50 sheet ([catalogue](https://dadesobertes.gva.es/dataset/modelo-digital-del-terreno-mdt-de-lidar-de-1-metro-de-resolucion-de-la-provincia-de-valenc-2015)), "Producto derivado de LIDAR-PNOA 2015 CC-BY 4.0 scne.es", flight 1 Oct to 30 Nov 2015. Here: obra derivada (averaged to 5 m). Read 15 Nov 2026. IGN's own 5 m web service (`https://servicios.idee.es/wcs-inspire/mdt`, coverage `Elevacion25830_5`) was tried first and not used: it returns whole metres, too coarse for a plain where the land drops a few metres over kilometres.
- **Generalitat's footprint, water marks and catchments**: Institut Cartogràfic Valencià, service `https://terramapas.icv.gva.es/2702_DANA2024` (WFS), layers `DANA2024.ZonasInundadas.HuellaInundacion`, `DANA2024.ZonasInundadas.AlturaAgua.*`, `DANA2024.AVSRE.Cuencas`. Read 15 Nov 2026.
- **EMSR773, SNCZI zones, municipalities**: as in `docs/ZONES.md` (PR #36).
- **Permanent water**: ESA WorldCover 2021 v200, © ESA WorldCover project / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium, CC BY 4.0.
- **Buildings**: Dirección General del Catastro, INSPIRE Buildings download service (ATOM), by municipality.
- **Rain and gauge**: Pérez Cueva, A. J., Armengot Serrano, R., Fansa Saleh, G., Núñez Mora, J. Á., and Revert Ferrero, A. (2025), Estudio cronológico de los volúmenes de precipitación en las subcuencas de la rambla de Poyo en el episodio del 29 octubre de 2024, Investigaciones Geográficas 84, 9 to 29, [doi:10.14198/INGEO.30056](https://doi.org/10.14198/INGEO.30056) ([PDF at AEMET's repository](https://repositorio.aemet.es/bitstream/20.500.11765/17270/1/IG_Perez_2025.pdf)); Confederación Hidrográfica del Júcar, [Informe del episodio de lluvias y avenidas del 28 de octubre al 4 de noviembre de 2024](https://saih.chj.es/docs/20241029-1104Informe-Episodio-C-version2.pdf) (15 Jan 2025); AEMET, [informe del episodio DANA 29 oct 2024](https://repositorio.aemet.es/bitstream/20.500.11765/16360/1/informe_episodio_dana_29_oct_2024_.pdf). Read 15 Nov 2026.
- **Depth estimate**: Cohen, S., Brakenridge, G. R., Kettner, A., Bates, B., Nelson, J., McDonald, R., Huang, Y.-F., Munasinghe, D., and Zhang, J. (2018), Estimating floodwater depths from flood inundation maps and topography, Journal of the American Water Resources Association 54(4), 847 to 858, doi:10.1111/1752-1688.12609. Cohen, S., et al. (2019), The Floodwater Depth Estimation Tool (FwDET v2.0) for improved remote sensing analysis of coastal flooding, Natural Hazards and Earth System Sciences 19, 2053 to 2065, doi:10.5194/nhess-19-2053-2019. Water marks of 2026: ICV service `2702_DANAAdam2026`, as in `pipeline.labels`.
- **Streets**: OpenStreetMap, © OpenStreetMap contributors, ODbL 1.0, as mapped on 28 Oct 2024 (Overpass API attic query at `https://overpass-api.de/api/interpreter`), read 15 Nov 2026.
- **UPV street depth map**: Grup de Cartografia GeoAmbiental i Teledetecció (CGAT), Universitat Politècnica de València, Mapa d'inundació carrer a carrer de l'Horta Sud 2024 ([viewer](https://dana2024.upvusig.car.upv.es), [UPV news](https://www.upv.es/noticias-upv/noticia-15013-mapa-de-inunda-en.html)), GeoServer `https://dana2024.gisserver.car.upv.es/geoserver/dana2024/` (WCS coverage `dana2024__H_lamina`, WFS outlines), result updated 05/11/2026, read 15 Nov 2026; no licence named ("The data are freely available through the WMS server"; Fees NONE, AccessConstraints NONE). Roch Talens, A., Pardo-Pascual, J. E., Almonacid-Caballer, J., Fernández-Sarría, A., Palomar-Vázquez, J., and Cabezas-Rabadán, C. (2025), Mapa de calados máximos de las inundaciones del 29 de octubre de 2024 en l'Horta Sud y la Ribera, Cuadernos de Geografía 114-115, 347 to 374, doi:10.7203/CGUV.114-15.32144.
- **Further work**: Chini, M., Pelich, R., Pulvirenti, L., Pierdicca, N., Hostache, R., and Matgen, P. (2019), Sentinel-1 InSAR coherence to detect floodwater in urban areas: Houston and Hurricane Harvey as a test case, Remote Sensing 11(2), 107, doi:10.3390/rs11020107. Rossman, L. A. (2015), Storm Water Management Model User's Manual, Version 5.1, EPA/600/R-14/413b, U.S. Environmental Protection Agency.
- **Methods**: Nobre, A. D., et al. (2011), Height Above the Nearest Drainage, a hydrologically relevant new terrain model, Journal of Hydrology 404, 13 to 29, doi:10.1016/j.jhydrol.2011.03.051. Yamazaki, D., et al. (2019), MERIT Hydro: a high-resolution global hydrography map based on latest topography datasets, Water Resources Research 55, 5053 to 5073, doi:10.1029/2019WR024873 (drainage above 0.5 km²: [MERIT Hydro page](https://global-hydrodynamics.github.io/MERIT_Hydro/), read 15 Nov 2026). Twele, A., Cao, W., Plank, S., and Martinis, S. (2016), Sentinel-1-based flood mapping: a fully automated processing chain, International Journal of Remote Sensing 37(13), 2990 to 3004, doi:10.1080/01431161.2016.1192304. Garbrecht, J., and Martz, L. W. (1997), The assignment of drainage direction over flat surfaces in raster digital elevation models, Journal of Hydrology 193, 204 to 213. Bates, P. D., Horritt, M. S., and Fewtrell, T. J. (2010), A simple inertial formulation of the shallow water equations for efficient two-dimensional flood inundation modelling, Journal of Hydrology 387, 33 to 45, doi:10.1016/j.jhydrol.2010.03.027.

Written with SI assistance (Claude Code), reviewed by the team.
