# Presentation plan: 10 slides

How to read this: **On the slide** is the exact text. **Image** says what goes where; you insert it. **Say** is a short speaker line, optional. Every number comes from the paper (`docs/paper/paper.md`, traced in `docs/paper/numbers.md`) or from the source named next to it. No dashes in slide text (team rule).

---

## Slide 1. Title

**On the slide**
- Title: **Where will the water go?**
- Subtitle: Mapping flood extent in Valencia, judged by NASA's newest radar, NISAR
- Team: **[team name]**
- Luka Georgieski · Ilija Chrchev · Zhivko Stoimchev
- NASA Space Apps Challenge 2026, Valencia · Challenge: Dancing with the SARs

**Image:** full-bleed background of the Albufera rice fields or the Pego-Oliva marsh from above, darkened so the text reads. Candidates: `docs/storyboard/01_earth.jpg` or `docs/storyboard/12_rice_summer.jpg`. Team logo small in a corner, if you have one.

**Say:** "We are three Erasmus students in Valencia, and this is about one question: where will the water go?"

---

## Slide 2. The flood of 2024

**On the slide** (big white numbers over the photo)
- **29 October 2024, Valencia**
- **229** lives lost
- **€17.8 billion** in damage
- **75** towns under water
- Small source line at the bottom: *France 24, one year after the DANA (28 Oct 2025)*

**Image:** one full-screen photo of the 2024 flood (streets of Paiporta or the Horta Sud under mud and water), darkened on the left for the numbers. Use a photo you are allowed to use (Wikimedia Commons with its credit line, or a press photo with permission), and put the credit in small text.

**Note on "over 2000 missing":** don't use it. We could not find a source for it. The France 24 tally says 3 people were still missing a year later. "75 towns" is from the same article (564 km² of 75 municipalities). The 229 and €17.8 billion match the app and the paper.

**Say:** "Two hundred and twenty-nine people died. Many of them in places nobody expected the water to reach."

---

## Slide 3. Our phones, one month ago

**On the slide**
- Title: **17 October 2026. Our phones went off.**
- Under the screenshots: **It said how much rain. It said to stay away from flood-prone areas.**
- Then, larger: **It didn't say which ones.**

**Image:** 2 or 3 phone screenshots side by side: the ES-Alert message and the weather warning you got before DANA "Adam" (17 Oct 2026). Crop out personal details (contact names, other notifications). If the warning shows a colour, keep the word the screenshot uses. The official Spanish levels are yellow, orange and red; the paper says "orange", not "amber".

**Say:** "We got this alert. We read it twice. We still didn't know if our street was the one to leave."

---

## Slide 4. The problem

**On the slide**
- Title: **A rain warning tells you how much. Not where the water goes.**
- Three short blocks:
  1. **Warnings are per region.** Yellow, orange, red: 60, 100, 180 mm of rain in 12 hours. Nothing about your street.
  2. **Flood maps don't change.** The official flood zones show the same map whatever the forecast.
  3. **Satellites miss water under crops.** On 18 June 2026 the Sentinel-1 water map found **2 %** of the wet rice in the Albufera.

**Image:** right side, a simple before/after pair: the warning map of the region (one colour per zone) next to a street-level map of the same area. The paper's Fig. 4 (`docs/paper/figures/fig4_june18_map.png`) can stand in for block 3.

**Say:** "So the question a resident has, 'will my road flood?', has no answer today."

---

## Slide 5. Our solution

**On the slide**
- Title: **We turn a rain forecast into a map of likely flooded places.**
- Flow (left to right, three boxes with arrows):
  **Rain forecast** → **Our model** (terrain, land, past water) → **Map: where water is likely**
- Under it: **And NASA's NISAR radar checks every step.**
- Bottom: live demo link and QR code: dancing-with-the-sars-liard.vercel.app

**Image:** a screenshot of the app's flood map (the likelihood layer over Pego-Oliva). Candidate: `docs/storyboard/a4_phone.jpg` (phone view) or a fresh screenshot of `/explore`. QR code to the live demo in the bottom right.

**Say:** "The forecast says when. Our model says where. And NISAR tells us if we're right."

---

## Slide 6. Our models and what they learned from

**On the slide**
- Title: **Four models, four jobs**

| Model | What it does | Learned from |
|---|---|---|
| **Water per NISAR pass** | Finds water on every NISAR pass, through clouds | No training: a fixed radar rule (−15 dB) plus a per-scene threshold |
| **Water network** (Ilija) | Finds water and flood change in NISAR images | NISAR HH and HV images; labels from Sentinel-1 water maps and the Copernicus flood outline |
| **Land map** (Luka) | Labels every field: rice, water, town, forest, orchard… | The NISAR season, both tracks (62 features); labels from ESA WorldCover, JRC, CORINE, EFFIS and hand-drawn fields |
| **Flood model** (Zhivko) | Scores every 20 m pixel: how likely is water after this rain? | **413 Sentinel-1 water maps per site** (Aug 2024 to Oct 2026), ECMWF rain, terrain (height above the nearest river), land cover, past water. The October 2026 storm was **held out** |

- Footer: **Plus a rain trigger:** amber at 50 mm, red at 100 mm in 3 days (ECMWF 9 km forecast).

**Image:** small icon per row (radar, neural net, map tiles, rain cloud). Or one diagram: the paper's Figure 1 (pipeline) as a background graphic.

**Say:** "The flood model learns from two years of Sentinel-1 maps, because NISAR has only been delivering for five months. And that's where NISAR's real job starts."

---

## Slide 7. How we used NISAR: the judge

**On the slide**
- Title: **Sentinel-1 teaches. NISAR judges.**
- Subtitle: *NISAR's L-band sees through clouds and under young crops, where other radars go blind.*
- Four numbered cards, each with one big number:
  1. **It checks the labels.** 18 June 2026, Albufera rice: NISAR found **53 %** of the wet rice. Sentinel-1 found **2 %**. Checked on 513 random points, with a rule written before we looked.
  2. **It checks the flood.** Storm "Adam", October 2026: **87 %** of the new water NISAR saw is inside the official Copernicus flood outline.
  3. **It sets the bar.** NISAR's last map before the storm scores **0.27**. Our model must beat it, and it does: **0.42**.
  4. **It starts teaching.** A version that also learns from NISAR passes the same test: **0.44**.
- Bottom strip, small: **Also from NISAR:** the land map of every field, and NISAR soil moisture tested as an input.
- Honest footnote, small: *Why not train on NISAR alone? Five months is about a dozen passes per track. Sentinel-1 gave us 413 passes per site.*

**Image:** the left half shows **the same evening, two radars**: Sentinel-1's water map next to NISAR's over the Albufera rice. Use the swipe view from the app (`/views`, a fresh screenshot) or the paper's `docs/paper/figures/fig2b_map_water_wet.png`. NISAR shows the large wet area and Sentinel-1 almost none, which is the 53 % vs 2 % story in one picture. Optional small inset: `fig6_dana_map.png` (new NISAR water inside the EMSR935 outline) next to card 2.

**Say:** "NISAR is the newest radar in orbit. We didn't just use it as more data. We used it as the referee. It caught the Sentinel-1 labels missing almost all the water under the rice, it confirmed the flood was where the official map says, and it gave our model a bar to beat."

---

## Slide 8. The result

**On the slide**
- Title: **Tested on a storm it never saw**
- A bar chart, F1 score against the official Copernicus flood map (higher is better):
  - **Our model: 0.42**
  - Last NISAR map before the storm: 0.27
  - Past water (JRC): 0.29
  - Low ground only: 0.24
- Three lines under the chart:
  - **Tested by a different team member, with a rule written before the model existed.**
  - **3 later versions also pass:** 0.425 to 0.465.
  - **Honest:** one storm, so not proof yet. Two of the wins are within the uncertainty.

**Image:** the bar chart itself. Make it in Datawrapper from `docs/paper/figure-data/table6_emsr935_test.csv` (Grouped Bars, model highlighted in your accent colour, baselines grey). Next to it, small: a map of the model's likely-flooded pixels over the official outline (a crop of the app's Pego-Oliva view).

**Say:** "On a storm the model had never seen, it beat every simple rule we tested it against. It's one storm, so we say it plainly: promising, not proven."

---

## Slide 9. Who will use it, and what comes next

**On the slide**
- Title: **Who it's for**
  - **Civil protection and town halls:** where to send help and close roads first.
  - **Rice farmers and irrigation communities** of the Albufera: which fields will flood.
  - **Residents:** one map on the phone that answers "my street or not?"
- Second title: **What happens as NISAR keeps flying**
  - **A new NISAR pass every 12 days.** Every storm becomes a new lesson and a new test.
  - **NISAR moves from judge to teacher.** With more passes, the model can learn from L-band directly, including water under crops.
  - **Calibrated data since 21 October 2026,** and NASA's own NISAR water map (DSWx-NI) on the way.
  - **The same recipe fits other rice deltas and wetlands,** like the Ebro Delta and Doñana.

**Image:** a timeline strip across the bottom: Jun 2026 (first calibrated NISAR data), Oct 2026 (storm "Adam", our test), Nov 2026 (today), then "every 12 days" ticks running to the right, to "2027 and on". Optional: small map of Spain with Valencia, Ebro Delta and Doñana marked.

**Say:** "Today NISAR is our judge. A year from now, with thirty more passes, it becomes our teacher."

---

## Slide 10. Thank you

**On the slide**
- **Thank you!**
- **Where will the water go?** Try it: dancing-with-the-sars-liard.vercel.app
- Luka Georgieski · Ilija Chrchev · Zhivko Stoimchev
- Small: Data: NASA-ISRO NISAR (ASF), OPERA DSWx-S1, Copernicus EMS, ECMWF via Open-Meteo, ESA WorldCover, JRC

**Image:** the same background as slide 1 (bookend), with a large QR code to the live demo in the middle. The repo is private, so no repo link until Ilija makes it public.

**Say:** "Thank you. Scan the code and check your own street."

---

## Checklist before presenting
- [ ] Slide 2: no "2000 missing"; credit line for the photo.
- [ ] Slide 3: personal info cropped out of the screenshots.
- [ ] Slide 8: chart numbers match the table above (0.42, 0.27, 0.29, 0.24).
- [ ] Every slide: no en or em dashes.
- [ ] Team name filled in on slide 1.
