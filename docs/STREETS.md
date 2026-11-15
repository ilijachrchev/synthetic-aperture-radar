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

Not computed yet.

## Changes to the rules

None yet.

## Sources

- **Terrain**: Institut Cartogràfic Valencià, Modelo Digital del Terreno (MDT) de LIDAR de 1 metro de resolución de la provincia de Valencia 2015, by MTN50 sheet ([catalogue](https://dadesobertes.gva.es/dataset/modelo-digital-del-terreno-mdt-de-lidar-de-1-metro-de-resolucion-de-la-provincia-de-valenc-2015)), "Producto derivado de LIDAR-PNOA 2015 CC-BY 4.0 scne.es", flight 1 Oct to 30 Nov 2015. Here: obra derivada (averaged to 5 m). Read 15 Nov 2026. IGN's own 5 m web service (`https://servicios.idee.es/wcs-inspire/mdt`, coverage `Elevacion25830_5`) was tried first and not used: it returns whole metres, too coarse for a plain where the land drops a few metres over kilometres.
- **Generalitat's footprint, water marks and catchments**: Institut Cartogràfic Valencià, service `https://terramapas.icv.gva.es/2702_DANA2024` (WFS), layers `DANA2024.ZonasInundadas.HuellaInundacion`, `DANA2024.ZonasInundadas.AlturaAgua.*`, `DANA2024.AVSRE.Cuencas`. Read 15 Nov 2026.
- **EMSR773, SNCZI zones, municipalities**: as in `docs/ZONES.md` (PR #36).
- **Permanent water**: ESA WorldCover 2021 v200, © ESA WorldCover project / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium, CC BY 4.0.
- **Buildings**: Dirección General del Catastro, INSPIRE Buildings download service (ATOM), by municipality.
- **Rain and gauge**: Pérez Cueva, A. J., Armengot Serrano, R., Fansa Saleh, G., Núñez Mora, J. Á., and Revert Ferrero, A. (2025), Estudio cronológico de los volúmenes de precipitación en las subcuencas de la rambla de Poyo en el episodio del 29 octubre de 2024, Investigaciones Geográficas 84, 9 to 29, [doi:10.14198/INGEO.30056](https://doi.org/10.14198/INGEO.30056) ([PDF at AEMET's repository](https://repositorio.aemet.es/bitstream/20.500.11765/17270/1/IG_Perez_2025.pdf)); Confederación Hidrográfica del Júcar, [Informe del episodio de lluvias y avenidas del 28 de octubre al 4 de noviembre de 2024](https://saih.chj.es/docs/20241029-1104Informe-Episodio-C-version2.pdf) (15 Jan 2025); AEMET, [informe del episodio DANA 29 oct 2024](https://repositorio.aemet.es/bitstream/20.500.11765/16360/1/informe_episodio_dana_29_oct_2024_.pdf). Read 15 Nov 2026.
- **Methods**: Nobre, A. D., et al. (2011), Height Above the Nearest Drainage, a hydrologically relevant new terrain model, Journal of Hydrology 404, 13 to 29, doi:10.1016/j.jhydrol.2011.03.051. Yamazaki, D., et al. (2019), MERIT Hydro: a high-resolution global hydrography map based on latest topography datasets, Water Resources Research 55, 5053 to 5073, doi:10.1029/2019WR024873 (drainage above 0.5 km²: [MERIT Hydro page](https://global-hydrodynamics.github.io/MERIT_Hydro/), read 15 Nov 2026). Twele, A., Cao, W., Plank, S., and Martinis, S. (2016), Sentinel-1-based flood mapping: a fully automated processing chain, International Journal of Remote Sensing 37(13), 2990 to 3004, doi:10.1080/01431161.2016.1192304. Garbrecht, J., and Martz, L. W. (1997), The assignment of drainage direction over flat surfaces in raster digital elevation models, Journal of Hydrology 193, 204 to 213. Bates, P. D., Horritt, M. S., and Fewtrell, T. J. (2010), A simple inertial formulation of the shallow water equations for efficient two-dimensional flood inundation modelling, Journal of Hydrology 387, 33 to 45, doi:10.1016/j.jhydrol.2010.03.027.

Written with SI assistance (Claude Code), reviewed by the team.
