# Seat: Peer Reviewer 2 — Domain

Written in two phases. Phase 1 below was written from the contract JSON and the paper metadata only (title, field, about 6,500 words), before the manuscript was opened.

---

# PHASE 1 — Paper-content-blind pre-commitment

## Contract Paraphrase

D1 (methodology_rigor, mandatory, owned by the methodology seat). From a domain angle, this asks whether the way the study was built and run (data choice, processing, thresholds, validation design, statistics, and what others need to repeat it) would satisfy a SAR remote-sensing referee. I do not score it; I only note where a domain fact (for example how a SAR product was processed) changes what a methods reader should check.

D2 (domain_accuracy, mandatory, owned by me). This asks whether what the paper says about radar and water is right: that statements about L-band versus C-band behaviour, backscatter of open water, double-bounce in flooded vegetation, rice paddies, speckle, incidence angle, and polarisation match what the published literature shows; that prior SAR flood products and studies are described fairly and not mis-cited; and that technical terms are used the way the field uses them. It also asks whether the paper's interpretation of its own results is one the physics allows, and whether competing physical explanations are acknowledged.

D3 (argumentative_coherence, mandatory, owned by the devil's advocate with methodology). This asks whether the main claim holds together from start to end and whether the evidence shown actually carries it, without leaps or circular steps. I do not score it; domain errors that break the argument are reported under D2.

D4 (cross_disciplinary_relevance, high, owned by the perspective seat). This asks whether readers from neighbouring fields (hydrology, emergency management, machine learning) can follow the framing and whether claims about usefulness to them are backed. I do not score it.

D5 (writing_and_structure, normal, owned by the journal-fit seat). This asks whether the paper is well organised and clearly written, with good figures and tables and the conventions of its venue. I do not score it.

D6 (venue_fit_and_contribution, mandatory, owned by the journal-fit seat). This asks whether the paper suits its venue and adds something original and significant. No venue is confirmed here. I do not score it, though my D2 review will say where the contribution sits against prior SAR flood work.

## Scoring Plan

### D2: domain_accuracy
dimension_id: D2
what_to_look_for: Correct statements of L-band and C-band scattering for open water, flooded vegetation and wet soil; thresholds and polarisation rules justified against published SAR flood literature; prior flood products and L-band studies cited and described accurately; alternative physical explanations for any sensor disagreement acknowledged; terminology consistent with SAR hydrology usage.
what_triggers_block: A core interpretive claim about what the radar signal means rests on one physical explanation while other well-known explanations (wet soil, incidence angle, speckle, threshold bias, timing) are not addressed, or a key scattering fact is stated wrongly in a way that changes a main conclusion.
what_triggers_warn: Literature coverage misses important L-band or SAR flood-mapping work, a threshold or rule is used without citing where it comes from or why it fits this land cover, or terms are used loosely enough to confuse a domain reader, while the main conclusions still stand.
what_triggers_fatal: The central claim depends on a radar physics statement that is plainly false or contradicted by established literature, so that no revision of wording can rescue the main result.

criteria_binding_unavailable

[CONTRACT-ACKNOWLEDGED]

---

# PHASE 2 — Paper-visible review

Manuscript read: `docs/paper/review/manuscript-557e3fd.md` (read-only), plus `docs/paper/review/phase0-field-analysis.md`. Supporting result files read for domain checks: `data/prediction/nisar_check.json`, `data/validation/june18/result.json`, headers of `points.csv` and `reference.csv`. The skill's Python checkers (phase conformance, suggested-reference check) did not run in this install. Suggested references were checked by web search; the ones I could not confirm are marked.

contract_role: domain

## Dimension Scores

### D1: methodology_rigor
score: not_assessed

### D2: domain_accuracy
score: block
trigger: "A core interpretive claim about what the radar signal means rests on one physical explanation"
block_class: repairable

### D3: argumentative_coherence
score: not_assessed

### D4: cross_disciplinary_relevance
score: not_assessed

### D5: writing_and_structure
score: not_assessed

### D6: venue_fit_and_contribution
score: not_assessed

## Review Body

### Reviewer Identity
SAR hydrology researcher working on L- and C-band detection of open water and flooded vegetation in agricultural wetlands (Reviewer Configuration Card #3).

### Overall Recommendation
Major Revision

### Confidence Score
4 — core expertise in SAR water and flooded-vegetation physics; sampling statistics are outside my remit.

Confidence is an uncertainty/scope disclosure only; it never changes consensus counts, severity, decision bearing, or arbitration.

### Calibration Status
`NOT_CALIBRATED`

### Criterion-Bound Judgements
| Dimension / criterion | Criterion source | Judgement | Evidence anchors | Rationale | Uncertainty or scope limit | Decision bearing? |
|---|---|---|---|---|---|---|
| D2 domain_accuracy: radar physics of the June result | Contract D2; Card #3 focus 1–2 | DOES_NOT_MEET | W1, W2, W3 anchors | The step from "NISAR's −15 dB dark class overlaps optically wet rice" to "L-band sees water C-band misses" is not separated from threshold position and DSWx-S1 product rules; the dark class is described as if it captured flooded vegetation | Repairable with the existing 513 points and pixel values; no new field data needed | yes — it is what makes NISAR "better labels" |
| D2: consistency of the water definition | Contract D2 | PARTLY_MEETS | W4 anchor | The DANA check uses a per-scene Otsu threshold near −12 dB, not the −15 dB rule stated in §4.2 | Read from `nisar_check.json`; the authors may have a reason not stated | yes — Contribution 2 validates a different rule |
| D2: flooded-vegetation label rule | Contract D2; Card #3 focus 1 | DOES_NOT_MEET | W5 anchor | Not specified enough to reproduce; the stated change rule would also fire on normal rice growth | The rule is marked as still being finalised | yes for the planned model; no for present results |
| Literature integration | `references/quality_rubrics.md` Dimension 6; Card #3 focus 3 | PARTLY_MEETS | W6 anchor | Operational products and accuracy practice are well covered; L-band rice and flooded-vegetation literature is nearly absent | Existence of suggested works checked by web search, not by the skill's checker | yes — positions the core finding |
| Originality / positioning | Rubric Dimension 1 | MEETS | S5 anchor | First sample-based check of NISAR water over Spain is a real, if narrow, contribution; Table 1 is fair | Novelty depends on literature the paper does not yet cite | no |

Do not total, weight, average, or mechanically map these judgements to the recommendation.

### Summary Assessment
The paper tests whether early NISAR L-band water maps are good enough to train a flood-extent model, using a pre-registered optical check on 18 June 2026 in the Albufera rice and an event check against Copernicus EMSR935 at Pego-Oliva. The validation part is careful and unusually honest: it reports the strict open-water result that goes against the authors, and it correctly says that DSWx-S1's low score is partly the product's land-cover rule. From the SAR hydrology side, though, the main interpretation needs tightening before NISAR water can be called a better label. On 18 June the rice's median HH is −14.4 dB (track 066 D) and −14.8 dB (058 A), so the −15 dB cut runs through the middle of one wet-rice population: moving it by 1 dB changes the NISAR water area by about a quarter. The headline producer's accuracy of 0.52 is therefore a property of the threshold as much as of the sensor. A dark HH pixel at L-band means the radar sees the water surface between sparse plants; it is not the double-bounce flooded-vegetation signal the paper describes in §2. That is why the dark class fades from late June while the paddies stay flooded. The DANA check uses a different threshold from the one stated, and the L-band rice and flooded-vegetation literature is barely cited. All of this can be fixed with data the authors already hold. I recommend Major Revision.

### S1: The result that goes against the hypothesis is reported up front
The strict MNDWI-only referee is reported in the main results, in the abstract and in the conclusion, and it is used to narrow what the NISAR class means. Few validation papers do this, and it is the right reading of an optical open-water index over young rice.
**Evidence Anchor**: text: §5.1 "The result that goes against us: not open water."

### S2: DSWx-S1's inundated-vegetation rule is described correctly
The paper states that DSWx-S1 issues inundated vegetation only where its land cover says wetland, and draws the right conclusion: the 0.02 reflects product rules as much as C-band physics. This matches the product description (the inundated-vegetation class needs both a high dual-polarisation ratio and a wetland land-cover class). Rice paddies are normally cropland in such land-cover layers.
**Evidence Anchor**: text: §6.2 "reflects the product's rules as much as the physics of C-band"

### S3: Sensible physical controls
The non-rice cropland control stratum (2.9 % wet) and the canopy-free autumn comparison, where the two radars rise together on both tracks, are the right controls. They rule out a gross radiometric offset in NISAR.
**Evidence Anchor**: text: §5.2 "On 28 October the morning and evening NISAR tracks agree within 0.2 points."

### S4: SAR limits in towns are stated correctly
Double bounce from walls, layover and shadow are named as reasons why water labels fail in built-up areas, with an appropriate source.
**Evidence Anchor**: text: §6.2 "Radar is weak in streets because of double bounce from walls, layover and shadow."

### S5: Fair positioning against operational products
Table 1 and §6.1 "What others do better" place the work fairly against SNCZI/PATRICOVA, EFAS/GloFAS, Flood Hub, GFM and EMS, without overclaiming.
**Evidence Anchor**: table: Table 1 — row "This work" against the five existing-system rows

### W1: "NISAR sees water Sentinel-1 misses" is not separated from "the −15 dB cut sits inside the June rice distribution"
**Problem**: The paper reads the June gap between NISAR (6,387 ha) and DSWx-S1 (250 ha) as a sensor difference and says it is "specific to water beneath vegetation". The repository's own result files show that the gap's size is driven largely by where the threshold sits:
- On 18 June the median rice HH is −14.41 dB (066 D) and −14.82 dB (058 A), right at the −15 dB cut, while the cropland control median is −8.7 dB.
- The dark share of the rice is 54.5 / 43.7 / 32.2 % at −14 / −15 / −16 dB (066 D) and 62.3 / 46.9 / 27.8 % on 058 A. One dB either way moves the NISAR "water" area by about ±1,600 ha (±26 %). A per-scene Otsu threshold (−9.8 dB) would call about 90 % of the rice water.
- In stratum D (neither map says water), 46 of 68 decided points are optically wet (0.68), against 0.94 in stratum B. So the −15 dB line separates darker wet rice from brighter wet rice. It does not separate wet rice from dry rice.
- The "confirmation" on track 058 A (r = 0.978) uses 10 paired dates that do not include 18 June, because there is no DSWx-S1 pair on 058 A that day. Most of those dates are near zero (August–September) or canopy-free (October). The threshold was picked there for the best mean gap to DSWx-S1 (`threshold_choice` in `nisar_check.json`), so the evidence speaks to canopy-free open water, not to June.

The autumn agreement therefore rules out a radiometric offset (S3). It does not rule out that the June number reflects the threshold's position within a continuum of wet-rice backscatter, plus DSWx-S1's land-cover rule.
**Evidence Anchor**: text: §5.2 "The June disagreement is therefore specific to water beneath vegetation, not a calibration problem."
**Why it matters**: The paper's case for NISAR labels rests on this reading. "About half of the wet rice" is a threshold-dependent number, not a property of the sensor.
**Suggestion**: (1) Using the fixed 513 points, report user's and producer's accuracy against the same referee for HH thresholds from −18 to −12 dB. This needs no new referee labels. (2) Show the 18 June HH (and HV) histograms per stratum, so readers can see whether B and D are separated by a gap or by a cut through one mode. (3) To separate sensor from product, threshold raw Sentinel-1 VV/VH σ⁰ from the same pass on the same points, or use DSWx-S1's dual-pol-ratio layer before the wetland mask. (4) Report the same-day two-track agreement on 18 June (43.7 % evening vs 46.9 % morning). It is good evidence against a look-direction or incidence-angle artefact, and the paper does not use it. (5) Change the §5.2 sentence to what the evidence supports.
**Severity**: Major
**Confidence**: 4 — core expertise in SAR thresholding for water; numbers read from the authors' result files

### W2: The dark-HH class is not the flooded-vegetation signal, so it will miss most flooded rice after June
**Problem**: §2 explains, correctly, that flooded vegetation appears brighter in HH through double bounce. The −15 dB rule maps the opposite: pixels where L-band HH stays dark. At 24 cm wavelength, young, thin rice plants scatter little, so the radar mostly sees the specular water surface between them. That is how L-band "reaches" the water in June. C-band, by contrast, already interacts with small rice leaves and stems. As the rice grows, L-band double bounce between water and stems raises HH, and the dark class shrinks: on 066 D it falls from 43.7 % (18 June) to 13.4 % (30 June), 5.4 % (12 July) and 0.3 % (24 July). Yet §3.1 says the paddies stay flooded until August. Stratum D (0.68 optically wet) probably holds many of these brighter, still-flooded fields. The same applies at Pego-Oliva, where flooded reeds and orchards would brighten rather than darken.
**Evidence Anchor**: text: §6.1 "so labels built from NISAR are less biased towards open water"
**Why it matters**: As described, the present NISAR labels are "water with little canopy", not "water including flooded vegetation". That claim holds only once the double-bounce class (W5) is defined and validated. A model trained on dark-HH labels would learn that flooded rice dries up in July.
**Suggestion**: In §2 and §4.2, state the two mechanisms separately: dark HH means open water or water among sparse, thin vegetation; bright HH with a high HH/HV ratio means double bounce in flooded vegetation. Describe the June result as the first mechanism. Do not claim reduced open-water bias until the double-bounce class is defined and validated. The seasonal fall of the dark share in rice that is still flooded is a ready test for that class. Prior multi-frequency rice studies document this growth-stage behaviour (Inoue et al. 2002; Rosenqvist 1999).
**Severity**: Major
**Confidence**: 4 — core expertise; consistent with published multi-frequency rice backscatter studies

### W3: The strict-referee result is read as "two explanations fit", but the data say more than that
**Problem**: Under the strict MNDWI-only referee, NISAR-only points (stratum B) are open water in 3 of 29 decided cases (0.10). Points that both radars call dry (stratum D) are open water in 10 of 85 (0.12). Points that both radars call water (A) are open water in 7 of 10. So in June the NISAR-only class carries no more open-water signal than the rice background. Its difference from D lies in the broad "wet" index, which responds to wet soil, transplant-stage flooding and leaf water. The paper offers two explanations (water under young plants, or soaked mud) and stops at "optical data cannot separate them". Other readings that also fit are not discussed:
- (a) The threshold cuts through a continuum (W1).
- (b) The optical index loses shallow water under the canopy, whose NDVI rose from 0.34 to 0.59 across the bracket.
- (c) A short drainage. The result file names the local practice (eixugó), but the main text only says farmers drain paddies "briefly".
- (d) Very smooth, puddled paddy soil, which is close to specular at L-band.
**Evidence Anchor**: text: §5.1 "Two explanations fit: water beneath young rice plants (which L-band can reach and the optical open-water index cannot), or soaked mud, which darkens radar"
**Why it matters**: What the labels mean (open water, shallow water among plants, or saturated soil) decides what a model trained on them predicts. "A useful but broader class" is not yet shown to be broader in a useful direction: on the strict test, B and D cannot be told apart.
**Suggestion**: Report strict-referee shares for all strata side by side, with the small numbers stated. List the candidate explanations and say which evidence could separate them: the threshold sweep (W1); HV and HH/HV ratio per stratum (soil and water differ in HV); 058 A morning vs 066 D evening on the same day; and, if obtainable, the 2026 water-management calendar for the Albufera paddies. Rephrase the practical reading to "pixels in wet rice where L-band HH is low".
**Severity**: Major
**Confidence**: 3 — counts read from `result.json`; the interpretation of an optical wetness index over rice is adjacent to my core work

### W4: The DANA event check uses a different water threshold from the one the paper defines
**Problem**: §4.2 defines water as 5 × 5-filtered HH below −15.0 dB. According to `nisar_check.json` (`method`: "Otsu per scene"; `thresholds_db` before −11.85, after −12.03), the Pego-Oliva result (212 ha new water, 87 % inside EMSR935) uses per-scene Otsu thresholds about 3 dB brighter. The manuscript reports a ±1 dB range around an unstated base value.
**Evidence Anchor**: text: §5.3 "when the threshold is moved by ±1 dB"
**Why it matters**: Contribution 2 is offered as support for NISAR water as labels, but it validates a different rule. At about −12 dB, the June rice would be mostly "water". The two checks therefore cannot both support one label definition.
**Suggestion**: Either re-run the DANA check at −15 dB, or state the Otsu rule and explain why the labels and the event check differ. Report both. Also give the outline recall (about 184 of 877 ha) next to the 87 % precision-style share.
**Severity**: Major
**Confidence**: 4 — read directly from the result file; I may be missing an unstated reason

### W5: The flooded-vegetation rule cannot be reproduced and is physically ambiguous in rice
**Problem**: "HH rises by about 3 dB between passes while HV stays flat" leaves open:
- which pass is the reference (previous 12-day pass, same track, or a dry-season baseline);
- dB or linear;
- what "flat" means for HV, a tolerance in dB;
- whether a persistently flooded canopy, with no change between passes, is ever labelled.

In rice, HH rises by several dB through normal growth while the field stays flooded. L-band rice backscatter also depends on planting pattern and row direction (Rosenqvist 1999). Tillage and harvest change HH as well. So the rule mixes flooding onset with crop growth.
**Evidence Anchor**: text: §4.2 "where HH rises by about 3 dB between passes while HV stays flat (double bounce)"
**Why it matters**: The claim that NISAR labels include flooded vegetation, and the planned model, rest on this class.
**Suggestion**: Specify the rule fully, and compare it with established approaches: an HH/HV ratio or HH level with a land-cover gate, as in the OPERA DSWx-S1/NI ATBD's L-band inundated-vegetation section; single-image probabilistic approaches (Grimaldi et al. 2020); the review by Tsyganskaya et al. (2018). Validate it on autumn or winter flood dates against EMSR935's observed layer, and on rice through July, when fields are known to be flooded.
**Severity**: Major
**Confidence**: 4 — core expertise; the rule is marked as not yet final, which I have taken into account

### W6: Literature on L-band rice and on SAR detection of flooded vegetation is nearly absent
**Problem**: The radar physics rests on one 1990 review on flooded forest (Hess et al. 1990). The paper does not cite:
- multi-frequency or L-band rice backscatter studies (Inoue et al. 2002; Rosenqvist 1999; Le Toan et al. 1997);
- reviews of flooded-vegetation detection (Tsyganskaya et al. 2018; Grimaldi et al. 2020);
- double-bounce rice work comparing X-band with L-band polarimetry (Pierdicca et al. 2017);
- L-band inundation mapping in preparation for NISAR (Chapman et al. 2015; Lamb et al. 2025, which ties threshold classification to NISAR's 80 %-at-1-ha wetland requirement);
- the OPERA DSWx-S1/NI ATBD;
- Sentinel-1 rice mapping at a Mediterranean site (Bazzi et al. 2019);
- standard automated Sentinel-1 flood chains (Twele et al. 2016).

Appendix A itself calls L-band seeing water under rice "expected physics", but the paper never cites where that expectation comes from.
**Evidence Anchor**: absence: §2 Background and related work — expected L-band rice backscatter and flooded-vegetation detection literature beyond Hess et al. 1990; checked §2, §4.2, §5.1, §6.1, §6.2, References list
**Why it matters**: Without this literature, a reader cannot tell which part of the June finding is new: the operational-product gap, measured with a pre-registered sample. Mapping the physics is the part that is not new. Several of the open questions in W2, W3 and W5 are already worked out in that literature.
**Suggestion**: Add a short paragraph on frequency-dependent rice backscatter through the season and on flooded-vegetation detection methods. Then state the contribution as the measured gap between early NISAR and the operational C-band product, not as the physics. Severity basis: `references/quality_rubrics.md` Dimension 6 (literature needed to establish the question and its alternatives), and the existence of two dedicated review articles on this exact sub-topic.
**Severity**: Major
**Confidence**: 4 — core literature of my field; existence checked by web search

### W7: "Soaked mud darkens radar" is physically imprecise
**Problem**: Higher soil moisture raises the dielectric constant, which raises backscatter when roughness stays the same. Wet soil darkens only when it is also very smooth (puddled, levelled paddy soil) or carries a thin water film, and then it is close to shallow water anyway.
**Evidence Anchor**: text: §6.2 "Mud can trip both the optical flooding index and NISAR's dark threshold"
**Why it matters**: It affects how the "wet mud" alternative in §5.1 should be framed. It does not change a main claim.
**Suggestion**: Reword as "very smooth, saturated paddy soil or a thin water film". Cite a standard microwave scattering text (e.g., Ulaby & Long 2014).
**Severity**: Minor
**Confidence**: 4 — standard microwave scattering physics

### W8: Unsupported general statement about C-band and young crops
**Problem**: The sentence carries no citation. C-band, and even X-band, can detect flooded rice through double bounce (Pierdicca et al. 2017). The real difference is in the dark-water mechanism at early growth stages.
**Evidence Anchor**: text: §2 "C-band missions such as Sentinel-1 provide frequent, free data but see water under young crops less reliably."
**Why it matters**: It slightly overstates the physics case for L-band.
**Suggestion**: Qualify and cite it, for example "C-band dark-water rules miss water once young crops emerge; C-band double bounce can still reveal some flooded rice".
**Severity**: Minor
**Confidence**: 4 — core expertise

### W9: The label threshold is said to be independent of C-band, but it was checked for agreement with DSWx-S1
**Problem**: §4.2 says the water map "does not depend on the C-band products it is compared with". The threshold was then confirmed, and per the result file chosen among −14 to −18 dB, by its best mean gap to DSWx-S1 on track 058 A. The −15 dB value also comes from a land-class pipeline fallback, with no physical or literature basis given for L-band water.
**Evidence Anchor**: text: §4.2 "does not depend on the C-band products it is compared with"
**Why it matters**: The independence claim is weaker than stated: the labels are calibrated to C-band on canopy-free dates. This is acceptable, but it should be said.
**Suggestion**: State that the threshold was tuned to DSWx-S1 agreement on canopy-free dates. Give a physical basis for it, or a comparison with L-band open-water levels reported for NISAR or ALOS-2 (e.g., Chapman et al. 2015).
**Severity**: Minor
**Confidence**: 4 — read from the authors' result file

### W10: Processing details a SAR reader needs are missing
**Problem**: The speckle filter type (boxcar, Lee, refined Lee) and the effective resolution after a 5 × 5 filter on 20 m data (about 100 m) are not given. Incidence angles over the rice are not given for 066 D, 058 A or Sentinel-1. A ~100 m effective footprint mixes paddies with levees and canals, which matters for a per-field referee.
**Evidence Anchor**: text: §3.2 "after a 5 × 5 speckle filter in linear power"
**Why it matters**: Others need these details to reproduce the work and judge mixed pixels. They do not change the conclusions.
**Suggestion**: Add the filter type, effective resolution, the incidence-angle range per track at the sites, and the GCOV radiometric normalisation used (σ⁰ or γ⁰).
**Severity**: Minor
**Confidence**: 4 — standard SAR reporting practice

### Detailed Comments

#### Literature Review
- **Coverage**: Strong on operational products (DSWx-S1, GFM, EMS, EFAS) and on accuracy-assessment practice (Olofsson et al. 2014). Weak on the physics and methods literature of L-band rice and flooded vegetation (W6).
- **Integration quality**: §2 synthesises rather than lists, and Table 1 is useful. The vegetation paragraph, though, explains the double-bounce mechanism and then never uses it to interpret the dark-threshold result (W2).
- **Research gap argument**: Persuasive for "no independent check of NISAR water over Spain" and "C-band labels miss vegetated water". Less so for "L-band labels capture flooded vegetation", which is not yet shown.

#### Theoretical Framework
- **Appropriateness**: The physical framework (specular open water, double bounce in flooded vegetation, wavelength-dependent penetration) is the right one.
- **Application depth**: Applied only on the surface. The two mechanisms are not tied to the two label classes, and the seasonal behaviour of rice at L-band is not used to interpret the June-to-July fall (W2).
- **Alternative frameworks**: HH/HV ratio or polarimetric-ratio classification (as planned for DSWx-NI), probabilistic single-image methods (Grimaldi et al. 2020) and time-series rice phenology models (Bazzi et al. 2019) are the obvious comparators for the label rules.

#### Academic Argument Quality
- **Factual accuracy**: NISAR wavelength, launch date and repeat cycle, the DSWx-S1 inundated-vegetation rule, and CORINE class 213 are stated correctly. Imprecise: the "mud darkens" physics (W7), the unqualified C-band statement (W8), and the stated threshold for the DANA check (W4).
- **Argument logic**: The main leap is in §5.2, from autumn agreement to "specific to water beneath vegetation" (W1).
- **Terminology precision**: "Water" in the abstract and Table 4 means "HH below −15 dB", while §5.1 concludes it is "wet ground and shallow water among plants". The terms stay consistent once defined, but the abstract's "mapped 6,387.2 ha of water" reads as open water to a SAR reader.

#### Contribution to the Field
- **Incremental contribution**: An early, pre-registered, design-based check showing that a simple L-band HH dark threshold and the operational C-band DSWx-S1 product differ by an order of magnitude over June rice, and that the extra L-band area is optically wet but not open water. This is useful for DSWx-NI development and for anyone using early NISAR GCOV over rice.
- **Positioning**: Fair against operational products (S5). Not yet positioned against the physics literature (W6).
- **Overclaiming**: Moderate. §5.2's conclusion and §6.1's "less biased towards open water" go beyond what the evidence shows (W1, W2).

#### Missing Key References
- Inoue et al. 2002 — season-long multi-frequency (incl. C and L) backscatter of paddy rice; the direct physical basis for the June result.
- Rosenqvist 1999 — L-band (JERS-1) rice backscatter through the season; the effect of planting pattern bears on the +3 dB rule.
- Le Toan et al. 1997 — C-band rice backscatter modelling and monitoring [existence from my own knowledge; not web-checked in this session].
- Tsyganskaya et al. 2018 — review of SAR flooded-vegetation detection.
- Grimaldi et al. 2020 — flood mapping under vegetation from single SAR images.
- Pierdicca et al. 2017 — flooded rice double bounce, X-band compared with L-band polarimetry.
- Chapman et al. 2015 — regional inundation mapping with L-band (ALOS PALSAR).
- Lamb et al. 2025 — L- vs C-band threshold classification of marsh inundation, framed around NISAR's wetland requirement.
- OPERA DSWx-S1/NI ATBD, JPL D-108763 Rev A (2024) — includes the planned L-band inundated-vegetation method.
- Bazzi et al. 2019 — Sentinel-1 rice mapping at a Mediterranean site (Camargue).
- Twele et al. 2016 — automated Sentinel-1 flood mapping chain.
- Ulaby & Long 2014, *Microwave Radar and Radiometric Remote Sensing* (University of Michigan Press) — for soil-moisture and roughness physics (W7) [not web-checked in this session].
- Search lead [UNVERIFIED]: Sentinel-1 or TerraSAR-X studies of the Albufera de València rice calendar and flooding (the Valencia SAR polarimetry groups have worked on Spanish rice phenology), and any published record of the June drainage practice in the Albufera.

~~~yaml suggested-references
- title: "Season-long daily measurements of multifrequency (Ka, Ku, X, C, and L) and full-polarization backscatter signatures over paddy rice field and their relationship with biological variables"
  authors: ["Inoue, Y."]
  year: "2002"
  doi: null
  arxiv_id: null
- title: "Temporal and spatial characteristics of irrigated rice in JERS-1 L-band SAR data"
  authors: ["Rosenqvist, A."]
  year: "1999"
  doi: null
  arxiv_id: null
- title: "Rice crop mapping and monitoring using ERS-1 data based on experiment and modeling results"
  authors: ["Le Toan, T."]
  year: "1997"
  doi: null
  arxiv_id: null
- title: "SAR-based detection of flooded vegetation – a review of characteristics and approaches"
  authors: ["Tsyganskaya, V.", "Martinis, S.", "Marzahn, P.", "Ludwig, R."]
  year: "2018"
  doi: "10.1080/01431161.2017.1420938"
  arxiv_id: null
- title: "Flood mapping under vegetation using single SAR acquisitions"
  authors: ["Grimaldi, S.", "Xu, J.", "Li, Y.", "Pauwels, V.R.N.", "Walker, J.P."]
  year: "2020"
  doi: "10.1016/j.rse.2019.111582"
  arxiv_id: null
- title: "Mapping flooded vegetation using COSMO-SkyMed: Comparison with polarimetric and optical data over rice fields"
  authors: ["Pierdicca, N.", "Pulvirenti, L.", "Boni, G.", "Squicciarino, G.", "Chini, M."]
  year: "2017"
  doi: "10.1109/JSTARS.2017.2711960"
  arxiv_id: null
- title: "Mapping Regional Inundation with Spaceborne L-band SAR"
  authors: ["Chapman, B.", "McDonald, K.", "Shimada, M.", "Rosenqvist, A.", "Schroeder, R.", "Hess, L."]
  year: "2015"
  doi: null
  arxiv_id: null
- title: "Characterizing Tidal Marsh Inundation with Synthetic Aperture Radar, Radiometric Modeling, and In Situ Water Level Observations"
  authors: ["Lamb, B.", "McDonald, K.", "Tzortziou, M.", "Tesser, D."]
  year: "2025"
  doi: "10.3390/rs17020263"
  arxiv_id: null
- title: "OPERA Dynamic Surface Water Extent from Sentinel-1 and NISAR (DSWx-S1/NI) Algorithm Theoretical Basis Document, JPL D-108763 Rev A"
  authors: ["OPERA Project, NASA JPL"]
  year: "2024"
  doi: null
  arxiv_id: null
- title: "Mapping Paddy Rice Using Sentinel-1 SAR Time Series in Camargue, France"
  authors: ["Bazzi, H."]
  year: "2019"
  doi: "10.3390/rs11070887"
  arxiv_id: null
- title: "Sentinel-1-based flood mapping: a fully automated processing chain"
  authors: ["Twele, A.", "Cao, W.", "Plank, S.", "Martinis, S."]
  year: "2016"
  doi: "10.1080/01431161.2016.1192304"
  arxiv_id: null
- title: "Microwave Radar and Radiometric Remote Sensing"
  authors: ["Ulaby, F.T.", "Long, D.G."]
  year: "2014"
  doi: null
  arxiv_id: null
~~~

The suggested-reference check script did not run (not installed). Existence was confirmed by web search for every item except Le Toan et al. 1997 and Ulaby & Long 2014, which are from my own knowledge. DOIs are given only where a search result showed them.

### Questions for Authors
1. With the 513 fixed points, what are NISAR's user's and producer's accuracies (main and strict referee) at −18, −17, −16, −14 and −13 dB? Does stratum B's wet share stay above 0.7 when the threshold moves?
2. What do the 18 June HH and HV distributions look like per stratum? Is there a gap between B and D, or is −15 dB a cut through one mode?
3. Which threshold produced the Pego-Oliva figures (212 ha, 87 %), and why does it differ from §4.2?
4. For the flooded-vegetation class: which reference pass, which HV tolerance, dB or linear? How will it tell flooding onset from normal rice growth through July?
5. Is there any record (water board, farmers' calendar) of when the Albufera paddies were drained in June 2026?

### Minor Issues
- Abstract: "NISAR mapped 6,387.2 ha of water". Consider "NISAR's dark-HH class covered", given the §5.1 conclusion.
- §2: "HV changes little" in flooded vegetation is attributed to Hess et al. 1990 (a flooded-forest review). In herbaceous wetlands and rice the HV response varies; consider a more specific source or softer wording.
- §3.2: state whether GCOV values were used as γ⁰ or converted to σ⁰.
- §5.3: "NISAR's new water is thus in the right place". Add that it covers about a fifth of the outline area.
