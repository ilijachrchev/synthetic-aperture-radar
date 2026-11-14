<div align="center">

# Map visualization

**How the app shows change on the map: the research, the decisions, the storyboard and a working prototype.**

</div>

Written 14 Nov 2026 on branch `feat/map-viz`. The prototype is the page `/flood` of the web app (`web/`).

Every fact below was checked that day against the source named beside it. Three marks say how:

- **[data]** I ran the query or read the file myself (NASA CMR, Earth Search, the tiles, the files in this repo).
- **[doc]** A research agent of this session opened the page and quoted it; the ones marked **[doc, rechecked]** I opened again myself.
- **[not checked]** Taken from another note and not verified here. Do not put these in a caption.

---

## 1. Decisions

| Question | Decision | Why |
|---|---|---|
| Map library | **MapLibre GL JS 6** (already in the app), with our own WebGL custom layers | Open (BSD-3-Clause), no token, no billing, and a custom layer gets the graphics card directly. Mapbox needs an account and bills map loads, Cesium is a 6 MB globe we do not need, deck.gl would only add a second renderer for one rectangle. |
| How a dated raster reaches the browser | **Pre-baked frames**, one small lossless WebP per pass that holds distance fields, drawn by a shader | The shoreline can travel between passes instead of fading, the picture is crisp at any zoom, and a plain file fetch works on every static host. COGs stay the exchange format of the pipeline: the bake reads them. |
| Tile server | **None** | Eleven to eighteen frames of 1800 px per site. A server adds cost and a point of failure for nothing. |
| Base imagery | **Real Sentinel-2 pictures of the event days** over the site, **EOX cloudless 2017** around it, **NASA GIBS** for the storm from far out | Real, dated, free to use. The 2017 mosaic is CC BY 4.0; the newer ones are non-commercial share-alike. |
| Between passes | **Interpolated, and drawn as an estimate**: hatched fill, dashed shoreline, a chip that says so | NISAR passes every 12 days. The app never lets an estimate look like a measurement. |
| Storm timing | Water **rises with the rain** and only **falls after it** | Without this the interpolation raised water under a dry sky and shrank it while it poured. |
| Two radars | **NISAR and Sentinel-1 are separate series**, switchable, never blended | L band and C band see vegetation differently, and the two water products use different classes. |

## 2. What the data says about the DANA at the Pego-Oliva marsh

All times UTC, October and November 2026.

| When | What | Source |
|---|---|---|
| 8 Oct 11:00 | Sentinel-2 picture, 2.4 % cloud (tile 30SYJ). The clear "before". | [data] Earth Search |
| 16 Oct 05:06 | NISAR pass, track 058 A | [data] CMR |
| 16 Oct 18:53 | NISAR pass, track 066 D: **113 ha** of water (CV model, sea left out) | [data] CMR, `data/cv` |
| 16 to 17 Oct | Four Sentinel-1 passes: 27 ha of open water, 375 ha of flooded vegetation on the last one | [data] CMR, OPERA DSWx-S1 |
| 18 Oct 11:00 | Sentinel-2 picture: **100 % cloud** | [data] Earth Search |
| 18 to 19 Oct | The rain. 193 mm in the weather model at the marsh, up to 27 mm in one hour | [data] Open-Meteo, AROME 1.5 km |
| 20 to 21 Oct | Copernicus EMS maps the flood from other satellites: **1,118 ha** | [data] `data/labels` (EMSR935) |
| 21 Oct 11:00 | Sentinel-2 picture: **0 % cloud**. The marsh under orange water, sediment running into the sea. | [data] Earth Search |
| 22 Oct 06:09 | First Sentinel-1 pass after the storm: **524 ha** of open water (it saw 82 % of the site) | [data] OPERA DSWx-S1 |
| 23 Oct 19:01 | NISAR pass, track 167 D, covers 63 % of the site | [data] CMR, `docs/DATA.md` |
| 28 Oct 05:06 | NISAR pass, track 058 A (new in CMR, being added to the stacks) | [data] CMR |
| 28 Oct 18:53 | NISAR pass, track 066 D: **447 ha** of water, 334 ha more than on 16 Oct | [data] `data/cv` |
| 28 Oct to 10 Nov | Eleven Sentinel-1 passes: open water falls to **250 ha** | [data] OPERA DSWx-S1 |
| after 28 Oct | No NISAR pass over the marsh published yet | [data] CMR, 14 Nov |

What this means for the story:

- **Neither radar passed during the storm.** No Sentinel-1 pass from 18 to 21 Oct, no NISAR pass between 16 and 28 Oct except the partial one. The honest line is not "radar saw the flood through the cloud" but "the optical satellite passed and saw cloud; radar does not need a clear sky, it only needs its next pass". The picture of 21 Oct then confirms the radar maps.
- **The peak was not seen by our radars.** The Copernicus outline (1,118 ha) is drawn as an independent line, never animated as if it were ours.
- **Sentinel-1 fills the days NISAR misses**, 18 passes in 26 days. It is the second series of the page.
- The rain is modelled, not gauged. Three models disagree (ERA5 73 mm, IFS 62 mm, AROME 206 mm for 15 to 24 Oct) [data]. A gauge total of 634 mm at Pego is quoted in the prediction notes [not checked].

## 3. The stack

### Libraries [doc]

| | MapLibre GL JS | deck.gl | Mapbox GL JS v3 | CesiumJS |
|---|---|---|---|---|
| Version | 6.18.0 | 9.4.1 | 3.35.0 | 1.147.0 |
| Licence | BSD-3-Clause | MIT | Proprietary since v2 [doc, rechecked] | Apache-2.0 |
| Token or account | None | None | Token, billed per map load after 50,000 a month | Only for Cesium ion (the default base layer is ion) |
| One raster, updated per frame | Image, canvas or video source; or a custom layer | BitmapLayer makes a new texture when the image changes | Same sources; `raster-color` recolours a raster | Single image assumed geographic, not Web Mercator |
| Time series built in | Example swaps an image source every 200 ms | TileLayer | `raster-array` needs Mapbox Tiling Service | Time-dynamic WMTS |
| Size, minified | 1.1 MB + 0.5 MB worker | 2.1 MB | 1.9 MB | 6.1 MB |

- MapLibre 6 is ESM only and needs WebGL2. A custom layer's `render(gl, options)` gets the Mercator matrix as `options.defaultProjectionData.mainMatrix` [data, read in `node_modules/maplibre-gl/dist/maplibre-gl.d.ts`]. Globe needs MapLibre's shader prelude, so the layers here are Mercator only.
- deck.gl can sit inside MapLibre (`MapLibreOverlay`, interleaved). We do not need it: our layer is one rectangle and one shader.

### COGs in the browser, a tile server, or frames [doc]

| Way | What it gives | Why not as the playback path |
|---|---|---|
| `@geomatico/maplibre-cog-protocol` 0.10 (MIT) | Reads EPSG:3857 COGs as tiles, palette or colour ramp | Its own time series demo removes and re-adds the layer on every tick. No interpolation, and restyling needs the layer re-added. |
| geotiff.js 3.0.5 (MIT) | Range requests, overviews, worker pool | Needs HTTP range support, and we would still have to build the distance fields in the browser. |
| TiTiler (MIT) | Dynamic tiles from COGs | Needs a running Python server. Its own docs say static tiling always loads faster. |
| **Frames baked once** | One lossless WebP per pass, 0.1 to 0.5 MB | Chosen. |

### Hosting [doc]

| Host | Limits that matter |
|---|---|
| Vercel Hobby | 100 GB transfer a month, non-commercial use only |
| GitHub Pages | 1 GB site, 100 GB a month, files under 100 MiB |
| Cloudflare Pages | 25 MiB per file, and it answers range requests with a full 200 [doc, rechecked], so COG readers fail there |
| Hugging Face datasets | Range and CORS worked in a test; one report of failures in January 2026 |

Baked frames are fetched whole, so the page works on any of them. The site layers of the marsh weigh 12 MB in the repo.

## 4. Real imagery and how to credit it

| Source | Access | Login | Licence | Line to show |
|---|---|---|---|---|
| Sentinel-2 L2A, Earth Search STAC | `earth-search.aws.element84.com/v1`, asset `visual` | No [data] | Free, full and open | Contains modified Copernicus Sentinel data 2026 |
| NASA GIBS daily true colour | `gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{day}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg` | No, no key [data] | Open | Imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS) [doc, rechecked] |
| EOX cloudless | `tiles.maps.eox.at/wmts/1.0.0/{layer}/default/g/{z}/{y}/{x}.jpg` | No [data] | 2016 and 2017: CC BY 4.0. 2018 to 2025: CC BY-NC-SA 4.0 [data, read in the WMTS capabilities] | EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2017) |
| EOX overlay (names from far out) | layer `overlay_bright_3857` | No [data] | | Data © OpenStreetMap contributors, rendering © EOX and MapServer |
| OPERA DSWx-S1 | PO.DAAC | Earthdata | Open | OPERA Dynamic Surface Water Extent from Sentinel-1, version 1 (NASA JPL, PO.DAAC), plus the Copernicus line |
| NISAR GCOV | ASF DAAC | Earthdata | Open, citation urged | NASA-ISRO NISAR, NASA ASF DAAC |
| Copernicus EMS EMSR935 | `mapping.emergency.copernicus.eu` | No | Free, full and open | Copernicus Emergency Management Service, EMSR935 |
| EFFIS burnt areas | WMS | No | CC BY 4.0 | Burnt areas: EFFIS, © European Union |
| Open-Meteo | API | No key | CC BY 4.0, free tier non-commercial | Weather data by Open-Meteo.com |
| GNSS LOR1 | geodesy.unr.edu | No | | Blewitt, Hammond and Kreemer (2018), Eos, 99 |

Not used, and why: Copernicus Data Space (viewing needs an account), HLS (Earthdata login, 30 m, Sentinel-2 at 10 m is better here), CARTO, Stadia and MapTiler (key or account).

Rules kept: no NASA logo, insignia or mission mark anywhere (NASA allows factual use and a text credit, not the marks) [doc]. The README already says the project is not endorsed by NASA.

The app shows the short credit line all the time and the full list behind the "Sources" button.

## 5. How the layers stack

From the ground up, all on one Web Mercator grid:

1. **Base**: EOX cloudless 2017, a little dimmed.
2. **Storm from space**: NASA GIBS, VIIRS on NOAA-20, 18 Oct. Shown only from far out, with coast lines and names over it and one ring that marks the marsh.
3. **Picture of the day**: the newest real Sentinel-2 picture at the playhead. It fades to the next one, each with its own dimming, and its edge melts into the base. A chip names its day and its cloud share. Nothing is retouched.
4. **Radar water**: the custom layer of section 6.
5. **Reference lines**: Copernicus EMS in pink, the Generalitat footprint in yellow, measured depths as dots. They appear on the day they describe.
6. **Names**: a few place names.

Colour. Data colours are fixed in every palette of the app, because they carry meaning:

| Meaning | Look |
|---|---|
| Water (NISAR), open water (Sentinel-1) | Blue wash, white shoreline |
| Flooded vegetation (Sentinel-1) | Mint wash under fine dots |
| New since the storm | Brighter, with a soft halo on the land side of a shoreline that moved |
| Water that was already there | The same hue, quieter |
| Between passes | Hatched fill, dashed shoreline |
| Not seen by this pass | Thin grey hatching |
| Forecast (section 7) | Stripes only, dashed outline, never a solid fill |

Counters read from the same numbers the picture is drawn from. Hectares are counted on the original pixels with their true ground area, the sea left out.

Compare. A swipe line cuts the map: the picture before the storm on the left, radar water over the newest picture on the right. Both are drawn by our own layers, so the cut is exact.

## 6. Animating the change

### The method

For every pass the bake (`web/scripts/bake_water.py`) writes one frame with, for each pixel, the **signed distance to the nearest shoreline** (negative in water), one field for all water and one for open water, plus a mask of what the pass saw. Distances are packed into one byte each: steps of 1/8 pixel near a shoreline, coarser far from it.

The shader (`web/src/lib/water-layer.ts`) mixes the fields of the pass before and the pass after the playhead and draws water where the mix is below zero. So:

- **At a pass the picture is that pass.** The mix is one field alone. "Exact pixels" shows the radar pixels with no rounding of their corners.
- **Between passes a shoreline travels** across the ground. It is an interpolation, drawn hatched and dashed, and the readout says "Between passes, an estimate".
- **Two clocks.** A pixel on its way into the water follows the gain clock, a pixel on its way out the loss clock. In an ordinary gap both run evenly. In a gap with at least 15 mm of rain the gain clock follows the cumulative rain and the loss clock starts when 97 % of the rain has fallen. For NISAR between 16 and 28 Oct this gives 113 ha, then 456 ha when the rain stops (everything wet on either pass), then 447 ha at the pass.
- **Specks stay quiet.** The shoreline is drawn strong on a body of water that moved and faint on single pixels, so radar speckle does not sparkle.
- **Ripples** run outward where water gains ground and inward where it gives it back, only while the series plays.
- **A pass pulses.** When the playhead reaches a real pass the shoreline flashes once.
- Where a pass did not see a pixel, the last state that was seen is kept, so a shoreline never moves only because a pass missed it.

The first and last day rasters of the CV export are not used: this method needs only the per-date layers and also handles ground that floods, drains and floods again.

### Each story

| Story | Data | What moves | State |
|---|---|---|---|
| **DANA flood, Pego-Oliva** | NISAR water 066 D, Sentinel-1 water, four Sentinel-2 pictures, EMS, footprint, depths, rain | Water rises with the rain, the outline of the peak appears, the pass confirms, Sentinel-1 shows the fall | **Built**: `/flood` |
| **Rice season, Albufera** | NISAR water 066 D, 11 passes from 18 Jun to 28 Oct | Paddies fill and drain. New water is measured against the water that is always there (the lagoon). | Same engine, needs its page. Mockup below. |
| **Burn scar, Serra d'Espadà** | Burn layer per pass (asked from the CV session), EFFIS outline | The scar burns in between 24 Jul and 17 Aug with an ember edge, then stays dark. NASA FIRMS hot spots could time the spread [not checked]. | Mockup below |
| **Sinking ground, Lorca** | `data/prediction/lorca`: LOR1 since 2020, forecast for 12, 24 and 36 days with 80 % and 95 % ranges | A ring at the station, the line falling on a chart, then the forecast as a band that widens | Mockup below |
| **Rain to flood, after today** | A probability raster per forecast day (planned) | Stripes for the likely extent, a second outline for the range, a "today" line on the axis | Shader mode exists (`forecast: 1`), needs data. Mockup below. |

## 7. Storyboard

### The film, 30 seconds

Frames marked **real** are screenshots of the running app on real data (`web/scripts/shoot_flood.py`). Frames marked **mockup** were made with an SI image model for scenes that are not built yet; they carry a visible watermark and every number in them is a placeholder.

| # | Time | Shot | Camera | On screen | Frame |
|---|---|---|---|---|---|
| 1 | 0.0 to 3.0 s | The storm from space | 39.3 N 0.6 W, zoom 6.4, slow push to 6.95 | NASA VIIRS picture of 18 Oct, coast lines, a ring on the marsh. Caption: the rain total, "The optical satellite sees only cloud." | real, [01](storyboard/01_space.jpg) |
| 2 | 3.0 to 6.5 s | Down to the marsh | Fly to 38.87 N 0.066 W, zoom 12.45, 3.4 s | The clear picture of 8 Oct, NISAR water of 16 Oct: 113 ha. Chip "NISAR radar pass". | real, [02](storyboard/02_before.jpg) |
| 3 | 6.5 to 9.0 s | The rain | Still | Playhead runs into 18 Oct. Rain bars fall on the axis, the picture turns to cloud, water rises hatched. Chip "Between passes, an estimate". | real, [03](storyboard/03_rain.jpg) |
| 4 | 9.0 to 11.0 s | The peak, seen by others | Still | 21 Oct: the clear picture shows the flood in true colour, the Copernicus outline draws in pink: 1,118 ha. | real, [04](storyboard/04_peak.jpg) |
| 5 | 11.0 to 13.5 s | The pass | Still | 28 Oct: the shoreline pulses, hatching goes, 447 ha, "+334 ha since 16 Oct". | real, [05](storyboard/05_after.jpg) |
| 6 | 13.5 to 17.0 s | The check | Still | Swipe from right to left: before on the left, radar water over the 21 Oct picture on the right. | real, [06](storyboard/06_compare.jpg) |
| 7 | 17.0 to 19.5 s | Sentinel-1 fills the gap | Still | Switch to Sentinel-1: 22 Oct, 524 ha, then the fall to 250 ha by 10 Nov. | real, [07](storyboard/07_sentinel1.jpg) |
| 8 | 19.5 to 22.5 s | Farm water | Cut to the Albufera, zoom 11.6 | Paddies fill and drain through the season. "Rice fields are flooded on purpose." | mockup, [08](storyboard/08_rice_mock.jpg) |
| 9 | 22.5 to 25.0 s | Fire | Cut to Serra d'Espadà, zoom 11.2 | The scar burns in with an ember edge inside the EFFIS line. | mockup, [09](storyboard/09_fire_mock.jpg) |
| 10 | 25.0 to 27.5 s | Sinking | Cut to Lorca, zoom 11.5 | Ring on LOR1, the chart falls, the forecast band opens. | mockup, [10](storyboard/10_sink_mock.jpg) |
| 11 | 27.5 to 30.0 s | What comes next | Back to the marsh | "Today" line, the forecast in stripes with its range. End card: name, link, team, credits. | mockup, [11](storyboard/11_forecast_mock.jpg) |

Shots 1 to 6 already play by themselves: open `/flood?story`. `web/scripts/record_flood.py` records them as a film file and as frames.

### The live app

1. The page opens on the last NISAR pass before the storm, paused, the caption says what is on screen. [a1](storyboard/a1_app.jpg)
2. Play, or drag the time axis. The axis is the control: rain on top, the water the picture shows as an area, every pass as a mark, NISAR passes as diamonds, picture days as squares, the Copernicus days as a pink bar.
3. The readout always says what the picture is: a pass (with the satellite) or an estimate.
4. One switch changes the radar: NISAR, L band, or Sentinel-1, C band. [a3](storyboard/a3_sentinel1_three_weeks.jpg)
5. "Exact pixels" shows the radar pixels as delivered. [a2](storyboard/a2_exact_pixels.jpg)
6. "Compare" swipes, "From space" flies out to the storm, "Sources" lists every credit.
7. Space plays and pauses, the arrow keys step from pass to pass.

### References looked at

Zoom Earth (`zoom.earth`, the storm of 18 Oct 2026): the map fills the screen and the time control is one small strip. NASA Worldview compare mode: a swipe with the two dates on the handle and ticks for data days. What we refuse from the category: grey panels with layer trees, rainbow ramps, capital-letter labels, a legend larger than the map. Only these two were opened in this session; a wider reference page was not built [not done].

## 8. What each model should deliver for the map

| Model | Layer | Format |
|---|---|---|
| CV, water | Per pass, as now | `data/cv/<site>_<stack>/<date>_water.tif`, EPSG:3857, uint8: 0 not water, 1 water, 2 flooded vegetation, 255 no data or sea, plus the manifest entry |
| CV, probability | Per pass (coming) | `<date>_water_p.tif`, uint8 = round(P x 200), 255 no data. Lets the map draw the uncertain band at a pass. |
| CV, burn | Per pass, Espadà (asked) | `<date>_burn.tif`, uint8: 0, 1 burned, 255 |
| Prediction, flood | Per forecast day | A probability raster on the site grid plus median and range in hectares. The map draws stripes above 50 % and the range as outlines. |
| Prediction, Lorca | As now | `forecast.json` and `observations.csv` |
| ML, classes | As now | A class COG; the map can tint the water by class (rice, permanent water) |

The bake picks up every CV water layer listed in `data/manifest.json` by itself.

## 9. Not verified, or open

- The gauge total of 634 mm at Pego (AEMET) [not checked].
- The NISAR layer in GIBS: listed with data on 16 and 28 Oct [doc], but an earlier note found broken tiles at zoom 12 and 13. Not used.
- FIRMS hot spots for the fire: access and dates [not checked].
- Phones: the layout adapts, the layers were only tested on a desktop graphics card.
- The film recording runs in a headless browser; a final cut should be recorded on a real screen.
- Open for Ilija: which of the three palettes; whether the dock is the right weight; one page per story or one page with a story switch.

## 10. Run it

```bash
cd web
pnpm install
pnpm dev
```

Then open `http://localhost:3000/flood` (or `/flood?story` for the film).

Rebuild the layers (Python with rasterio, scipy, geopandas, earthaccess; the pipeline environment has them):

```bash
python scripts/bake_water.py --site pego_oliva --start 2026-10-16 --end 2026-11-10 --stacks 066_D_069 --data-root ../data
python scripts/fetch_optical.py --site pego_oliva --days 2026-10-08 2026-10-18 2026-10-21 2026-10-28
python scripts/bake_context.py --data-root ../data
python scripts/shoot_flood.py out --cinema --size 1920x1080
```

<sub>Drafted with an SI assistant (Claude Code). Frames marked mockup are SI-generated and watermarked. Decisions on the idea and the look stay with the team.</sub>
