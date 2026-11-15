# Official flood zones against where the water really went

Data for the app's "before" screen: for each town, how much of the area a DANA really flooded lay in the official flood zones, and in which one. Every number below comes from [`data/zones/zones_vs_floods.json`](../data/zones/zones_vs_floods.json), written by `python -m pipeline.zones`, or from a cited source; the tables are printed from that file by `python -m pipeline.zones report`.

Two DANAs, never mixed:

- **29 Oct 2024, L'Horta Sud and Chiva** (Paiporta, Massanassa, Sedaví, Catarroja, Alfafar, Benetússer, Picanya, Aldaia, Chiva, Torrent). This was before NISAR had any data: context only, never a NISAR result. Observed flood: Copernicus EMS **EMSR773** (confirmed in the rapid mapping API: "Flood in Valencia Region, Spain", event 29 Oct 2024 14:30 UTC, activated 16:40 UTC).
- **DANA Adam, 18 to 19 Oct 2026, Pego and Oliva.** NISAR saw it. Observed flood: Copernicus EMS **EMSR935** (`data/labels/`, imagery 20 to 21 Oct 2026).

## Results

How to read the tables: "observed flood" is the land the Copernicus maps saw under water or covered in flood traces. The three shares split it by the most frequent official zone it lay in, and add up to 100 %. "Zones cover" is the share of the whole municipality inside any official zone.

**2024, L'Horta Sud and Chiva (context, before NISAR).** Of the 5,253.9 ha the Copernicus maps saw flooded in the 10 towns, 46.0 % lay outside every official flood zone (31.8 % with the sharpest map first), 23.9 % only in the rare (T500) zone and 30.1 % in the frequent or occasional zones. In the streets the gap is wider: 60.8 % of the flood traces and 58.0 % of the 2,238 buildings Copernicus graded as affected (possibly damaged, damaged or destroyed) were outside every zone, and 40.5 % of those buildings were only in the rare zone; 1.5 % were in a frequent or occasional zone. Most of the frequent and occasional share is standing water on the Albufera's cropland and wetland in Massanassa, Catarroja and Alfafar. Official zones cover 11.2 % of the 10 municipalities.

**2026, Pego and Oliva (NISAR saw it).** Here the official map was right: 95.3 % of the 963.2 ha EMSR935 saw flooded lay in the frequent or occasional zones and 0.2 % outside every zone (6.0 % with the Generalitat's surveyed footprint instead of EMSR935).

So the "before" screen has two honest stories: in 2024 the water went where the map said "rare" or nothing; in 2026, at Pego-Oliva, it went where the map said it would.

### DANA of 29 Oct 2024, L'Horta Sud and Chiva

| Municipality | Observed flood (ha) | Outside every zone | Only rare (T500) | Frequent or occasional | Zones cover of the municipality |
|---|---|---|---|---|---|
| Paiporta | 398.2 | 55.5 % | 40.7 % | 3.8 % | 44.2 % |
| Massanassa | 502.6 | 5.5 % | 49.7 % | 44.8 % | 94.8 % |
| Sedaví | 152.1 | 91.4 % | 7.7 % | 0.9 % | 7.2 % |
| Catarroja | 912.3 | 16.3 % | 36.8 % | 46.9 % | 66.1 % |
| Alfafar | 944.9 | 16.6 % | 25.5 % | 57.9 % | 80.0 % |
| Benetússer | 17.1 | 47.9 % | 52.1 % | 0.0 % | 27.9 % |
| Picanya | 563.3 | 96.6 % | 0.9 % | 2.5 % | 2.8 % |
| Aldaia | 842.8 | 62.5 % | 18.1 % | 19.4 % | 23.8 % |
| Chiva | 281.4 | 40.8 % | 16.5 % | 42.7 % | 2.5 % |
| Torrent | 639.2 | 82.9 % | 6.4 % | 10.7 % | 2.1 % |
| **Total** | 5,253.9 | 46.0 % | 23.9 % | 30.1 % | 11.2 % |

Split by what the satellite saw (share outside every zone / only rare / frequent or occasional):

| Municipality | Flooded area (water on the image), ha | shares | Flood traces (water gone), ha | shares |
|---|---|---|---|---|
| Paiporta | 9.0 | 44.6 / 32.2 / 23.2 % | 389.2 | 55.7 / 40.9 / 3.4 % |
| Massanassa | 263.2 | 1.2 / 22.4 / 76.4 % | 239.3 | 10.3 / 79.7 / 10.0 % |
| Sedaví | 25.2 | 68.2 / 26.3 / 5.5 % | 126.9 | 96.0 / 4.0 / 0.0 % |
| Catarroja | 425.0 | 0.2 / 5.0 / 94.8 % | 487.3 | 30.4 / 64.6 / 5.1 % |
| Alfafar | 645.5 | 5.5 / 10.2 / 84.2 % | 299.5 | 40.6 / 58.3 / 1.2 % |
| Benetússer | 0.1 | 2.6 / 97.4 / 0.0 % | 17.0 | 48.2 / 51.8 / 0.0 % |
| Picanya | 4.0 | 33.3 / 5.4 / 61.3 % | 559.3 | 97.0 / 0.9 / 2.1 % |
| Aldaia | 16.7 | 20.4 / 31.7 / 47.9 % | 826.1 | 63.4 / 17.8 / 18.8 % |
| Chiva | 12.2 | 32.4 / 6.4 / 61.2 % | 269.2 | 41.2 / 16.9 / 41.9 % |
| Torrent | 24.0 | 78.1 / 1.5 / 20.4 % | 615.2 | 83.1 / 6.6 / 10.3 % |
| **Total** | 1,424.9 | 6.2 / 11.4 / 82.4 % | 3,829.0 | 60.8 / 28.5 / 10.7 % |

Buildings the Copernicus grading map marked as affected (possibly damaged, damaged or destroyed), by the zone of their point:

| Municipality | Graded buildings | Outside every zone | Only rare (T500) | Frequent or occasional |
|---|---|---|---|---|
| Paiporta | 327 | 54.7 % | 45.3 % | 0.0 % |
| Massanassa | 199 | 4.0 % | 96.0 % | 0.0 % |
| Sedaví | 196 | 99.5 % | 0.5 % | 0.0 % |
| Catarroja | 391 | 0.8 % | 98.7 % | 0.5 % |
| Alfafar | 232 | 41.8 % | 58.2 % | 0.0 % |
| Benetússer | 28 | 64.3 % | 35.7 % | 0.0 % |
| Picanya | 80 | 100.0 % | 0.0 % | 0.0 % |
| Aldaia | 33 | 60.6 % | 18.2 % | 21.2 % |
| Chiva | 3 | 33.3 % | 66.7 % | 0.0 % |
| Torrent | 749 | 93.1 % | 3.6 % | 3.3 % |
| **Total** | 2,238 | 58.0 % | 40.5 % | 1.5 % |

Sensitivity (dana_2024_horta_sud): share outside every zone, only rare, frequent or occasional.

| Variant | Observed flood (ha) | Outside | Only rare | Frequent or occasional |
|---|---|---|---|---|
| sharpest_map_first | 3,232.6 | 31.8 % | 24.7 % | 43.5 % |
| only_EMSR773_AOI03_GRA_PRODUCT_v2 | 2,097.2 | 44.8 % | 36.5 % | 18.7 % |
| only_EMSR773_AOI03_DEL_PRODUCT_v1 | 1,084.4 | 52.7 % | 28.1 % | 19.3 % |
| only_EMSR773_AOI01_DEL_PRODUCT_v1 | 4,517.5 | 43.7 % | 24.4 % | 31.9 % |
| flooded_area_only | 1,424.9 | 6.2 % | 11.4 % | 82.4 % |
| flood_trace_only | 3,829.0 | 60.8 % | 28.5 % | 10.7 % |
| fluvial_zones_only | 5,253.9 | 46.0 % | 23.9 % | 30.1 % |

### DANA Adam, 18 to 19 Oct 2026, Pego and Oliva

| Municipality | Observed flood (ha) | Outside every zone | Only rare (T500) | Frequent or occasional | Zones cover of the municipality |
|---|---|---|---|---|---|
| Pego | 461.1 | 0.3 % | 0.5 % | 99.2 % | 15.3 % |
| Oliva | 502.1 | 0.1 % | 8.1 % | 91.8 % | 44.4 % |
| **Total** | 963.2 | 0.2 % | 4.4 % | 95.3 % | 30.8 % |

Split by what the satellite saw (share outside every zone / only rare / frequent or occasional):

| Municipality | Flooded area (water on the image), ha | shares | Flood traces (water gone), ha | shares |
|---|---|---|---|---|
| Pego | 381.9 | 0.0 / 0.1 / 99.9 % | 79.2 | 1.9 / 2.3 / 95.8 % |
| Oliva | 367.9 | 0.1 / 10.9 / 89.1 % | 134.2 | 0.3 / 0.4 / 99.3 % |
| **Total** | 749.8 | 0.0 / 5.4 / 94.6 % | 213.4 | 0.9 / 1.1 / 98.0 % |

Sensitivity (dana_adam_2026_pego_oliva): share outside every zone, only rare, frequent or occasional.

| Variant | Observed flood (ha) | Outside | Only rare | Frequent or occasional |
|---|---|---|---|---|
| generalitat_footprint | 847.1 | 6.0 % | 3.3 % | 90.6 % |
| flooded_area_only | 749.8 | 0.0 % | 5.4 % | 94.6 % |
| flood_trace_only | 213.4 | 0.9 % | 1.1 % | 98.0 % |
| fluvial_zones_only | 963.2 | 0.2 % | 4.4 % | 95.3 % |

### The claims of discussion #29

| Claim | Verdict | Our numbers | Say instead |
|---|---|---|---|
| the 2024 DANA flooded 14 % outside every zone | does not hold | SNCZI, 10 municipalities: 46.0 % of the observed flood outside every zone (2418.0 of 5253.9 ha); 31.8 % with the sharpest map first (3232.6 ha); 60.8 % of the flood traces (streets); 58.0 % of the 2238 graded buildings | With the national flood map (SNCZI), 32 to 46 % of the land the 2024 DANA flooded in these 10 towns was outside every official flood zone. The 14 % figure is real but belongs to a different map and area: 14.1 % of the area flooded in the Poyo, Magro and Albufera ravine basins was outside the Valencian integrated hazard map MIPICOVA (Camarasa-Belmonte et al. 2025). |
| Paiporta and Massanassa were almost all rare | partly holds | Paiporta: land 40.7 % only rare, 55.5 % outside every zone, 3.8 % frequent or occasional; flood traces 40.9 % only rare; graded buildings 45.3 % only rare, 54.7 % outside (of 327); Massanassa: land 49.7 % only rare, 5.5 % outside every zone, 44.8 % frequent or occasional; flood traces 79.7 % only rare; graded buildings 96.0 % only rare, 4.0 % outside (of 199) | Massanassa, yes: 96 % of its affected buildings were in the rare zone. Paiporta, no: 45 % of its affected buildings were in the rare zone and 55 % outside every zone; of its flooded land 41 % was rare and 56 % outside. Massanassa's standing water (263 ha, 76 % in the frequent or occasional zones) lay on cropland and wetland of the Albufera (74 % and 22 % in ESA WorldCover), not in the town. |
| Sedaví in none (no official zone) | holds | Sedaví: 91.4 % of its flooded land outside every zone (96.0 % of its flood traces), 99.5 % of its 196 graded buildings; official zones cover 7.2 % of the municipality | Sedaví: 99.5 % of its affected buildings and 91 % of the land that flooded were outside every official flood zone (zones cover only 7 % of the town's area, so not literally none). |
| red warning 07:30 | holds with other wording |  | 07:36, first AEMET red warning of the day, for the Litoral sur de Valencia zone. The zone of L'Horta Sud and Chiva (Litoral norte de Valencia) went red at 09:41. |
| Chiva 11:30 | holds with other wording |  | 11:30, first flash flood on the Poyo below Chiva (208 m3/s at 11:30). Chiva's streets flooded later (17:47); do not say Chiva was destroyed at 11:30. |
| Torrent 18:30 | holds |  | About 18:30, the Poyo floods Torrent and l'Horta Sud; its gauge reads 2,282.9 m3/s at 18:55 and is then destroyed. |
| phone alert 20:11 | holds |  | 20:11, ES-Alert to every phone in Valencia province. |

### 29 Oct 2024, local time

| Time | What | Sources |
|---|---|---|
| 07:36 | First AEMET red warning of the day in Valencia province, for the Litoral sur de Valencia zone (observed 90 mm in one hour, forecast 180 mm in 12 hours), valid to 12:00. Not the zone of L'Horta Sud or Chiva. | [AEMET](https://repositorio.aemet.es/bitstream/20.500.11765/16360/1/informe_episodio_dana_29_oct_2024_.pdf) |
| 09:41 | AEMET red warning for the Litoral norte de Valencia zone, the warning zone of every 2024 municipality here (Paiporta, Chiva, Torrent and the rest): 90 mm in one hour and 180 mm in 12 hours, to 18:00; extended at 17:49 to 20:00. | [AEMET](https://repositorio.aemet.es/bitstream/20.500.11765/16360/1/informe_episodio_dana_29_oct_2024_.pdf); [AEMET warning zones](https://www.aemet.es/es/eltiempo/prediccion/municipios/paiporta-id46186) |
| 11:30 | First flash flood on the rambla del Poyo below Chiva: the CHJ gauge at the A-3 (Riba-roja) jumps from 57.6 m3/s at 11:25 to 208.2 m3/s at 11:30 (264 m3/s at 11:40). elDiario.es puts the Poyo overflowing in Chiva at 11:30; the flooding of Chiva's streets is documented later, at 17:47. | [Maldita.es](https://maldita.es/clima/20241108/cronologia-avisos-rio-magro-rambla-poyo/); [elDiario.es (Sergi Pitarch)](https://www.eldiario.es/comunitat-valenciana/cronologia-alerta-llego-tarde-utiel-requena-inundan-pasar-despues-rio-abajo_1_11779079.html) |
| 12:20 | Special hydrological alert of the Generalitat's emergency centre for the Poyo towns (Torrent, Picanya, Paiporta, Benetússer, Sedaví, Alfafar, Massanassa, Catarroja). Not sent to phones. | [Maldita.es](https://maldita.es/clima/20241108/cronologia-avisos-rio-magro-rambla-poyo/); [elDiario.es (Sergi Pitarch)](https://www.eldiario.es/comunitat-valenciana/cronologia-alerta-llego-tarde-utiel-requena-inundan-pasar-despues-rio-abajo_1_11779079.html) |
| about 18:30 | The Poyo floods Torrent and l'Horta Sud: a video at 18:28 shows Picanya starting to flood; the gauge reads 1,686.7 m3/s at 18:25 and 1,756.9 m3/s at 18:35; elDiario.es gives 18:30 for Torrent. | [Maldita.es](https://maldita.es/clima/20241108/cronologia-avisos-rio-magro-rambla-poyo/); [elDiario.es (Sergi Pitarch)](https://www.eldiario.es/comunitat-valenciana/cronologia-alerta-llego-tarde-utiel-requena-inundan-pasar-despues-rio-abajo_1_11779079.html) |
| 18:55 | Last reading of the Poyo gauge before the flood destroyed it: 2,282.90 m3/s (water level 4.899 m). | [Confederación Hidrográfica del Júcar (CHJ)](https://saih.chj.es/docs/20241029-1104Informe-Episodio-C-version2.pdf); [Maldita.es](https://maldita.es/clima/20241108/cronologia-avisos-rio-magro-rambla-poyo/) |
| 20:11 | ES-Alert to every mobile phone in Valencia province, asking people to avoid any travel (elDiario.es's first timeline said 20:12). | [Tribunal Superior de Justicia de la Comunitat Valenciana, press office (poderjudicial.es)](https://www.poderjudicial.es/cgpj/es/Poder-Judicial/Tribunales-Superiores-de-Justicia/TSJ-Comunidad-Valenciana/Oficina-de-Comunicacion/Archivo-de-notas-de-prensa/El-juzgado-vuelve-a-requerir-a-la-Generalitat-para-que-informe-sobre-quien-decidio-enviar-el-SMS-de-alerta-por-la-Dana-y-pide-a-la-CHJ-datos-del-caudal-del-Poyo-entre-las-16-13-y-las-18-42-horas-del-29-de-octubre); [elDiario.es (Sergi Pitarch)](https://www.eldiario.es/comunitat-valenciana/cronologia-alerta-llego-tarde-utiel-requena-inundan-pasar-despues-rio-abajo_1_11779079.html) |

## Method

**Official zones.** The national flood zone map SNCZI of MITECO, read from MITECO's WFS (`https://gis.miteco.gob.es/geoserver/agua/wfs` and `.../costas/wfs`): fluvial T10, T100 and T500 (`agua:Zi_laminas_q10`, `q100`, `q500`) and marine T100 and T500 (`costas:zim_laminas_q100`, `q500`; there is no marine T10). MITECO lists every layer as updated 1 Jun 2026. Each flooded spot gets the most frequent zone it lies in:

| Class | Meaning |
|---|---|
| frequent | in a T10 zone (high probability, about 1 in 10 each year) |
| occasional | in a T100 zone, not T10 (medium probability, about 1 in 100 each year) |
| rare | only in a T500 zone (low probability, about 1 in 500 each year) |
| none | outside every official zone |

Each return period is its own layer and nothing guarantees they nest, so each class is taken against the union of the more frequent ones. The four classes tile each municipality with no gap and no overlap (tested in `tests/test_zones.py`).

**Observed flood.** Flooded area (water still on the image) plus flood traces (the water had gone, mud and debris were left): together, where the water went. The JSON also gives the two parts apart.

- 2024, EMSR773: three first-response products map L'Horta Sud and Chiva:
  1. AOI03 Horta Sud, grading map version 2 (GeoEye-1, 31 Oct 2024 10:22 UTC). Version 2 corrected the observed event of version 1: "not all flood traces were delineated".
  2. AOI03 Horta Sud, delineation map version 1 (WorldView-2 and GeoEye-1, 31 Oct 2024 10:22 UTC).
  3. AOI01 Valencia province, delineation map version 1 (Landsat-8 30 Oct, Sentinel-2 31 Oct, Sentinel-1 31 Oct; 10 to 30 m), the only one that covers Chiva town and the west of the area.

  The headline is the **maximum observed extent**: a spot counts as flooded if any of the three saw water or a flood trace there (where one saw water and another only a trace, it counts as water). The three disagree a lot outside the town centres: in Picanya the sharp grading map outlines 61 ha, the province map 562 ha. So the JSON also gives the **lower bound**, a priority mosaic where each spot is decided by the sharpest product that looked at it (grading map, then delineation AOI03, then AOI01; "looked" = area of interest inside the image footprints, minus "Not Analysed" parts), and each product alone. Later products are not used: monitoring maps from 3 Nov show receding water, and the gradings of other areas of interest use imagery from 10 to 17 Nov; the ones that touch the towns are listed in the JSON (`observed_source.other_aois_touching_the_area_not_used`).
- 2024, graded buildings: the grading map (product 1) also has 3,906 building points graded possibly damaged, damaged or destroyed. Each gets the zone class of its point. This is the closest measure to "your street", and the one the elDiario.es claims were about (buildings, not land).
- 2026, EMSR935: the outline and mapped areas in `data/labels/`, as used by `pipeline/cv/evaluate.py` (`flood_vs_emsr935`), with both classes kept here.

**Municipalities.** IGN INSPIRE administrative units, fetched by id (`AU_ADMINISTRATIVEUNIT_3410` + province + INE code); the IGN name is checked against ours for every town.

**Areas.** Exact geometries in UTM 30N (EPSG:32630, as everywhere in this repo), GEOS overlay, snapped to a 1 cm grid only where GEOS reports a topology error. Shares are of the observed flood inside each municipality. A share is null where nothing was observed. The web layers are simplified copies for display only; their `area_ha` comes from the exact geometries.

**Sensitivity.** The JSON repeats the shares under other reasonable choices, so no verdict hangs on one: the sharpest-map-first mosaic (lower bound), each EMSR773 product alone, the flooded area only, the flood traces only, the fluvial zones only (no marine zones), and for 2026 the Generalitat's surveyed footprint of DANA Adam instead of EMSR935.

## Limits

- **"Outside every zone" also means "never studied".** SNCZI maps only the river stretches that were studied (mostly the areas of significant potential flood risk, ARPSI). A spot outside every zone may be outside because a study found it safe or because no study reached it; the map does not say which.
- **Rain falling on a town is not in SNCZI.** The zones are river and sea floods. Water that ran down streets from local rain counts as "outside every zone" if it lay outside the river zones.
- **SNCZI is not the only official map.** The Generalitat's PATRICOVA and the integrated map MIPICOVA (PATRICOVA plus SNCZI, with a geomorphological level) are wider in places. They are not used here; the 14.1 % in the claims section is against MIPICOVA.
- **Satellite outlines miss and add.** EMSR773 imagery is from 30 and 31 Oct, one to two days after the peak: standing water had partly drained, which is why flood traces matter. In dense streets, photo-interpreted traces are the best evidence available but not a survey. The 10 to 30 m province map draws coarse outlines (in Paiporta it marks 99 % of the municipality); the sharp grading map may miss water in fields. The truth lies between the lower bound and the headline.
- **Chiva town is barely mapped.** The two sharp maps cover only the east tip of Chiva (6.0 % and 7.8 % of the municipality, `analysed_by_product_pct`) and hold 213.6 of Chiva's 281.4 ha; the rest, with the town, is only in the 10 to 30 m province map, which outlines 82.3 ha in the whole municipality. Chiva's numbers describe the east tip, not the town.
- **Rice fields and towns mix.** Massanassa, Catarroja and Alfafar reach into the Albufera rice fields, where most of the standing water lay in the frequent (T10) or occasional (T100) zones. The split by observed class (flooded area against flood traces) and the graded buildings separate the fields from the streets.
- **2026 at Pego-Oliva**: the observed flood includes parts of the Pego-Oliva marsh, a wetland, as EMSR935 outlined them.

## Files

| File | What |
|---|---|
| `pipeline/zones.py` | the pipeline: `fetch`, `compute`, `report` |
| `data/zones/zones_vs_floods.json` | every number, the claims checked, the 2024 timeline, every source with its retrieval date and checksum |
| `data/zones/municipalities.geojson` | the 12 municipalities with their headline numbers (simplified 10 m) |
| `data/zones/zones_horta_sud.geojson`, `zones_pego_oliva.geojson` | official zone classes frequent, occasional, rare, clipped to the municipalities (simplified 6 m) |
| `data/zones/floods_dana_2024_horta_sud.geojson`, `floods_dana_adam_2026_pego_oliva.geojson` | observed flood (maximum extent) split by municipality, zone class and observed class (simplified 4 m) |
| `data/zones/buildings_dana_2024_horta_sud.geojson` | the graded buildings of EMSR773 AOI03 as points, with municipality, zone class and damage grade |
| `tests/test_zones.py` | the area bookkeeping on tiny synthetic polygons |

The web layers are WGS84 GeoJSON with 5 decimals (about 1 m), one to two MB each. Property names: `zone` (frequent, occasional, rare, none), `observed` (flooded_area, flood_trace), `municipality`, `ine`, `area_ha` (from the exact geometry), `damage` (buildings).

Rebuild (downloads go to `data/interim/flood-zones/`, not in git):

```bash
python -m pipeline.zones fetch
python -m pipeline.zones compute
python -m pipeline.zones report
```

## Sources and licences

- **SNCZI flood zones**: © Ministerio para la Transición Ecológica y el Reto Demográfico. Free use crediting the ministry as author and owner ([download page](https://www.miteco.gob.es/en/cartografia-y-sig/ide/descargas/agua/zi-lamina.html); service sheets [ZI_T10.pdf](https://gis.miteco.gob.es/descargas/info/ZI_T10.pdf), [ZI_T100.pdf](https://gis.miteco.gob.es/descargas/info/ZI_T100.pdf), [ZI_T500.pdf](https://gis.miteco.gob.es/descargas/info/ZI_T500.pdf)). WFS read 15 Nov 2026.
- **EMSR773**: Copernicus Emergency Management Service (© 2024 European Union), [EMSR773] Horta Sud (AOI03): Grading Map; Horta Sud (AOI03): Delineation Map; Valencia province (AOI01): Delineation Map. Citation form from the [EMS citation guidelines](https://mapping.emergency.copernicus.eu/about/citation-guidelines/); [terms](https://mapping.emergency.copernicus.eu/terms-and-conditions/). Products downloaded 15 Nov 2026 from the rapid mapping API.
- **EMSR935**: Copernicus Emergency Management Service (© 2026 European Union), [EMSR935] Moraira (AOI01): Delineation Map; Gandia (AOI02): Grading Map; as republished by the Institut Cartogràfic Valencià (see `pipeline/labels.py`).
- **Municipalities**: © Instituto Geográfico Nacional, CC BY 4.0 ign.es ([WFS](https://www.ign.es/wfs-inspire/unidades-administrativas)), read 15 Nov 2026.
- **Land cover check**: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium (CC BY 4.0), already in `data/context/` (`pipeline.context`).
- **AEMET warning zones** of each town: the AEMET municipal forecast pages, field "Zona de avisos" (for example [Paiporta](https://www.aemet.es/es/eltiempo/prediccion/municipios/paiporta-id46186)), read 15 Nov 2026.
- Other sources (the claims and the timeline) are cited where they are used, with links, and in the JSON.

No NASA logo is used. Written with SI assistance (Claude Code), reviewed by the team.
