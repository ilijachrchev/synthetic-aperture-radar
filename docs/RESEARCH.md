# Dancing with the SARs: research and recommendation

Research date: **13 November 2026**. The brief in [INSTRUCTIONS.md](INSTRUCTIONS.md) is the requirement; [RESOURCES.md](RESOURCES.md) supplied the starting sources. Recommendations below assume a Space Apps weekend and a team comfortable with Python and web development. These are proposed choices, pending team preferences.

## Recommended direction

Build an **Albufera water and landscape change explorer**, provisionally named **WaterRhythm**. Use real NISAR observations to help people explore how the lake, rice fields, and surrounding wetlands change between summer and autumn.

The central question is: **Where did the radar-observed landscape change, how did it change through time, and what evidence helps explain it?**

Start with one small study area, a few acquisition dates, and an explanation of what radar measures. Make the results useful to wetland managers, educators, and local residents through a comparison map, a timeline, and charts for selected areas. Expand to other locations after this example works.

This is a recommendation based on accessible catalog records and a locally relevant story. **No NISAR pixels have been analyzed yet**, so the magnitude and cause of any change remain hypotheses. The first implementation milestone must establish that the selected images contain a clear, credible example.

## What the challenge actually requires

The supplied brief calls for an interactive, open-source application that uses **NISAR** to visualize surface change, explains plausible physical drivers, and makes the observations understandable. It permits supplemental optical imagery and GIS layers. It does not require a global processing service, machine learning, or multiple hazard types. See [the supplied objectives](INSTRUCTIONS.md#objectives).

Our minimum demonstration should therefore contain:

1. An actual NISAR comparison with acquisition dates, product identifiers, and source attribution.
2. A map or animation that makes the change visible.
3. A plain-language explanation supported by ancillary evidence.
4. A clear distinction between measured backscatter, our derived classifications, and interpretation.

## The data availability finding that changes the plan

NISAR launched on **30 July 2025**. ASF reports that validated L0–L2 products were released on **6 November 2026**, covering acquisitions from 21 October 2026 onward. Earlier provisional products cover acquisitions from 17 June through part of 23 October 2026. Beta products also exist, but are less suitable for quantitative work. Validated soil-moisture products are not yet available. These availability statements are time-sensitive. [ASF availability](https://nisar-docs.asf.alaska.edu/availability-overview/)

Collection maturity matters: a change in calibration or processing can look like a change on the ground. Treat each maturity and processing release separately in the initial analysis. [ASF maturity guidance](https://nisar-docs.asf.alaska.edu/products-overview/)

I queried NASA's public Common Metadata Repository (CMR), rather than assuming Valencia coverage:

| Collection | Records intersecting the discovery box | Implication |
| --- | ---: | --- |
| `NISAR_L2_GCOV_PROVISIONAL_V1` | 54 | Several candidate repeat sequences; best starting archive |
| `NISAR_L2_GCOV_V1` | 5 | Newly validated examples, but no repeated track/frame in this returned set |
| `NISAR_L2_GCOV_BETA_V1` | 0 | No matches for this particular query |

The discovery box is **west −0.50°, south 39.10°, east −0.20°, north 39.50°**, around Albufera and nearby land. Counts are records, not unique dates, and footprint intersection does not establish complete or valid pixel coverage. The saved [catalog inventory](research/valencia_nisar_catalog.json) contains the exact queries, timestamps, footprints, and access links.

The most promising sequence is **track 066, descending, frame 069**, provisional release **P05023**:

> 18 Jun → 30 Jun → 12 Jul → 24 Jul → 17 Aug → 29 Aug → 10 Sep → 22 Sep → 4 Oct → 16 Oct 2026

The **10 September and 4 October** records were inspected at the detailed metadata level. Both list HH/HV polarizations, 20 MHz primary bandwidth, and the same stack and processing release. They are candidate endpoints; 22 September supplies an intermediate date. Exact scene identifiers and metadata are in the [implementation plan](IMPLEMENTATION_PLAN.md#1-establish-the-first-real-data-example).

Other sequences need more care: ascending track 058 has HH-only acquisitions on 22 September, while another track contains duplicate records for an acquisition. Select by metadata and quality, rather than taking the first N search results.

## Why Albufera, and how to tell the story honestly

Albufera's water is actively managed for agriculture and ecology. The regional park's explanation of lake levels describes the connection between rice-field inundation, lake management, and the autumn/winter *perellonà*. This gives us a physical reason to investigate seasonal radar changes. [Generalitat Valenciana lake-management explanation](https://parquesnaturales.gva.es/documents/80302883/162014201/Manejo%2Bde%2B%2Blos%2Bniveles%2Bdel%2Blago%2Bde%2Bl%E2%80%99Albufera.pdf/4fa7b7ff-64a0-445c-aa29-be7cec20ec5a?t=1547029164992)

The application should help distinguish **seasonal water management, vegetation changes, and possible storm effects**. A newly dark patch is an observation to investigate, not proof of damage.

There are two useful local event stories, with different constraints:

- **29 October 2024 floods:** these predate NISAR. A historical chapter can use Sentinel-1 and Copernicus EMS activation EMSR773, while the application's main NISAR chapter uses later dates. The historical chapter alone would not meet the brief's NISAR requirement. [Copernicus event account](https://mapping.emergency.copernicus.eu/news/flood-in-valencia-region-spain/)
- **18 October 2026 DANA Adam:** the University of Valencia published a Sentinel-2 comparison, but explicitly notes that some rice fields were already inundated before the storm. Its public page offers JPEG illustrations, not an analysis-ready flood polygon. Our provisional sequence ends before this event; a later validated scene would cross a processing-release boundary. Keep this as contextual research unless a scientifically defensible comparison becomes available. [University of Valencia analysis](https://www.uv.es/777ExEwIyUlIA8=/2026-10-18_DANA.html)

I also verified **21 OPERA Sentinel-1 RTC catalog records** intersecting the discovery box between 20 October and 2 November 2024. Repeated burst identifiers exist on **20 October and 1 November**. These are useful candidates for the historical chapter, subject to pixel coverage and processing-version checks. The [Sentinel-1 inventory](research/valencia_sentinel1_2024_catalog.json) preserves the evidence. November imagery shows conditions at acquisition time, not necessarily the peak flood.

## Other viable project directions

The feasibility judgments in this table are engineering assessments. Product capabilities come from [ASF's product descriptions](https://nisar-docs.asf.alaska.edu/products-overview/).

| Direction | Useful question | Starting product | Weekend assessment |
| --- | --- | --- | --- |
| **Wetlands / water / agriculture** | How do water extent and vegetation structure vary? | **GCOV** | Recommended: accessible intensity measurements and an understandable local story |
| Wildfire or forest disturbance | Where did vegetation structure change? | GCOV, optical evidence, event perimeter | Good alternative if a clean, well-timed pair and reference perimeter are secured |
| Earthquake or subsidence | Where did the ground move along the satellite's viewing direction? | GUNW | More interpretation and quality control; atmosphere, coherence, reference choice, and unwrapping matter |
| Glacier movement | Where and how fast is ice moving? | GOFF | Visually attractive, but requires offset quality control and conversion to meaningful movement |
| Soil moisture / irrigation | How does estimated soil moisture vary? | SME2 | Defer: current maturity and validation limitations complicate strong quantitative claims |

A deforestation or wildfire comparison is a good replacement if Albufera's pixels prove uninformative. Its availability has **not** been verified in this research; select and validate its actual scenes before changing the product story.

## The SAR concepts that affect implementation

SAR actively illuminates Earth with microwaves, making observations possible at night and through cloud. Radar brightness depends on geometry, roughness, structure, and moisture; it is not a photograph or a direct land-cover label. NISAR's L-band can reveal different vegetation/ground interactions from Sentinel-1's shorter-wavelength C-band. [ASF interpretation guidance](https://nisar-docs.asf.alaska.edu/amplitude/)

For our use case:

- **Smooth open water often returns little energy** and appears dark. Wind, rough water, and mixed shoreline pixels complicate this.
- **Flooded vegetation can become brighter**, particularly through interactions between vertical stems/trunks and water. Urban structures also produce strong returns. A dark-pixel rule will miss some inundation.
- **Cross-polarized HV** helps describe vegetation scattering; **co-polarized HH** provides complementary structural information. Neither channel uniquely identifies a process. [NASA polarimetry](https://science.nasa.gov/mission/nisar/polarimetry/), [ASF scattering explanation](https://hyp3-docs.asf.alaska.edu/guides/opera_rtc_product_guide/)

GCOV is the practical starting point: its diagonal covariance layers represent terrain-corrected **gamma-zero power**. `HHHH` contains HH intensity and `HVHV` contains HV intensity; these are not four-letter polarization modes. The chosen primary bandwidth implies an expected **20 m posting**, which must be checked in the downloaded subset. Pixel spacing is not a guarantee that every 20 m feature is resolved. [GCOV specification overview](https://nisar-docs.asf.alaska.edu/gcov/)

**Frequency A and Frequency B inside an LSAR file are both L-band sub-bands. They are not the L- and S-band instruments.** Use Frequency A initially. Global L-band access is through ASF; S-band covers selected areas and is distributed through ISRO's Bhoonidhi. [ASF mission and frequency description](https://nisar-docs.asf.alaska.edu/nisar-intro/)

## Data to use

| Dataset | Why include it | How to use it |
| --- | --- | --- |
| **NISAR provisional L2 GCOV, P05023** | Core challenge data; a candidate Albufera sequence is verified | Frequency A HH/HV layers; compare matched dates; retain validity information and provenance |
| **Sentinel-2 L2A** | Independently inspect water and vegetation where cloud permits | True color, water-index comparison, and cloud/shadow masks; find nearby dates, not just attractive imagery |
| **ESA WorldCover 2021 v200** | Context for cropland, built areas, wetland, and water | Stratify interpretation and exclude open sea from land statistics; historical context, not 2026 truth |
| **JRC Global Surface Water** | Historical water occurrence and seasonality | Compare candidate new water against an older water baseline; record the exact release |
| **OPERA Sentinel-1 RTC** | Optional historical Valencia case and independent sensor comparison | Use matched bursts and VV/VH layers; analyze separately from NISAR |
| **Copernicus EMSR773** | Reference evidence for the 2024 event | Compare with temporally appropriate delineation products; distinguish observed water from flood traces |

Sentinel-2 L2A includes surface reflectance and a scene classification layer. For a water check, use green B03 with NIR B08 or SWIR B11, mask cloud/shadow, and align resolutions. The nearby optical observation remains imperfect evidence, especially under vegetation. [Copernicus L2A documentation](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html)

WorldCover's 2020 and 2021 maps use different algorithms, so differences between them should not be treated as pure land-cover change. Use one version as context. [WorldCover access and version guidance](https://esa-worldcover.org/en/data-access)

JRC's current download page provides an update through 2024, including v1.5 occurrence corrections and caveats about combining Landsat collections. Do not assume all historical assets use one consistent processing chain. For this MVP, one pinned occurrence layer is sufficient. [JRC release notes and downloads](https://global-surface-water.appspot.com/download)

OPERA RTC-S1 supplies gamma-zero power as 30 m COGs with associated masks. It avoids starting with unprocessed Sentinel-1 imagery, although burst mosaicking and version selection are still needed. [JPL RTC product documentation](https://www.jpl.nasa.gov/go/opera/products/rtc-product/)

Rainfall, population, roads, and parcel boundaries are optional extensions. Add a layer only when it answers a specific question. Population intersecting a candidate water mask does not establish casualties, damage, or people needing evacuation.

## Recommended stack

This architecture is our engineering recommendation, not a requirement of NASA's challenge.

| Layer | Recommendation | Reason |
| --- | --- | --- |
| Data access | Earthdata Search + Harmony first; `earthaccess` for reproducible searches | Extract only needed layers and a small spatial subset |
| Analysis | Python, NumPy, SciPy, Rasterio; QGIS for visual inspection | A small, inspectable raster workflow; windowed reads limit memory use |
| Scientific storage | COG rasters + GeoJSON regions + JSON manifest/statistics | Files are portable and easy to inspect and publish |
| Interface | React + TypeScript + Vite | Suitable for an interactive map, synchronized dates, and explanatory panels |
| Map | MapLibre GL JS | Raster imagery, vector overlays, and feature interaction in an open-source renderer |
| Charts | A small React chart library already familiar to the team | Avoid spending the weekend learning a charting framework |
| Serving | Static app, pre-rendered tiles, and cached JSON | A bounded demonstration can work without a live processing service |
| Optional backend | FastAPI + TiTiler | Add only for dynamic raster rendering or queries beyond the cached regions |

Rasterio supports reading windows instead of loading entire rasters. Vite produces a static build, MapLibre documents raster and GeoJSON sources, and TiTiler can serve COG-derived tiles if needed. [Rasterio](https://rasterio.readthedocs.io/en/stable/topics/windowed-rw.html), [Vite](https://vite.dev/guide/), [MapLibre sources](https://maplibre.org/maplibre-style-spec/sources/), [TiTiler](https://developmentseed.org/titiler/)

Use an isolated Python environment and lock versions after one successful extraction. The default workflow does not require a GPU, PostGIS, Kubernetes, or a trained neural network. A Python dashboard is a reasonable scope adjustment if the team has little web experience; the data recipe stays the same.

## Useful resources, in working order

1. **Acquire a small real subset:** [Harmony customization guide](https://nisar-docs.asf.alaska.edu/harmony/), then [Earthdata Search](https://search.earthdata.nasa.gov/search/granules?p=C2854338529-ASF). Harmony can extract GCOV variables, clip an AOI, and export COGs.
2. **Automate discovery:** [Earthaccess examples](https://nisar-docs.asf.alaska.edu/earthaccess/) and [ASF Search examples](https://nisar-docs.asf.alaska.edu/asf-search/). Data download/streaming requires a free Earthdata Login; public catalog discovery does not.
3. **Reuse learning material:** [ASF NISAR Cookbook](https://asfopensarlab.github.io/NISAR_Cookbook/) and its [notebooks](https://github.com/ASFOpenSARlab/NISAR_Cookbook/tree/main/notebooks). Particularly relevant are `NISAR_GCOV_Time_Series_Example.ipynb`, `NISAR_GCOV_SARChangeDetectionMethods.ipynb`, and `NISAR_Pixel_Conversion.ipynb`. They are references to inspect and adapt, not an end-to-end app already tested here.
4. **Check artifacts before interpretation:** [provisional known issues](https://nisar-docs.asf.alaska.edu/provisional-known-issues/). Radio interference, missing raw data, and processing artifacts can affect results. Frequency B has additional calibration caveats.
5. **Learn the science and explain it:** [ARSET](https://appliedsciences.nasa.gov/get-involved/training), [NISAR StoryMaps](https://science.nasa.gov/mission/nisar/arcgis-storymaps/), and [UAVSAR postcards](https://uavsar.jpl.nasa.gov/education/postcards.html). Use them for physical interpretation and visual communication; UAVSAR images are not NISAR observations.

The partner resources in the supplied list remain useful, but do not simplify the proposed core workflow:

- [CSA's Python/QGIS tutorial](https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial) provides beginner examples using British Columbia wildfire imagery. It is useful onboarding material; it does not establish a NISAR time series.
- [RCM access](https://www.asc-csa.gc.ca/eng/satellites/radarsat/access-to-data/about.asp) requires EODMS registration, with different access levels. Do not make the main demonstration depend on gaining additional access.
- [RADARSAT-1](https://www.csa-asc.gc.ca/eng/satellites/radarsat1/data-access.asp) is an openly licensed historical archive, useful for a longer-term extension.
- [SAOCOM's simplified access route](https://www.argentina.gob.ar/noticias/la-informacion-saocom-cada-vez-mas-accesible) concerns archived imagery over Argentina and requires registration and license acceptance. It is an option for an Argentine case study, not a substitute for verified NISAR data in this brief. The older [catalog information](https://catalogos.conae.gov.ar/catalogo/catalogoSatSaocomInfo.html) describes additional agreement requirements, so confirm the applicable route before relying on it.

## What is established, and what remains to establish

**Established:** the supplied challenge requirements; current official NISAR release guidance; candidate Valencia scene availability; compatible metadata for two selected NISAR acquisitions; a historical Sentinel-1 burst sequence; and documented access/subsetting approaches.

**Not established:** successful authenticated subset retrieval, per-pixel coverage/quality, visible change in the chosen scenes, classification accuracy, or any numerical water/vegetation result. The catalog files are evidence of discovery, not a completed scientific analysis.

The next step is [the first real-data milestone](IMPLEMENTATION_PLAN.md#1-establish-the-first-real-data-example): extract two small NISAR subsets, inspect them, and select the story from what the pixels support.
