# Seat report: Peer Reviewer 1 (Methodology)

Panel: academic-paper-reviewer, mode `reviewer_full`, contract `reviewer/reviewer_full/v2`.
Phase 1 was written to this file before the manuscript was opened. Phase 2 follows below it.

Checker note: `scripts/check_phase_conformance.py` did not run (the skill's Python checker scripts are not installed in this setup).

---

# PHASE 1 (paper-content-blind)

## Contract Paraphrase

D1 (methodology_rigor), mandatory. From the methods side, this asks whether the study design can actually produce the numbers it reports and whether someone else could rerun it. For a map-accuracy study that means: the sampling design is stated and probability-based, the estimator matches the design (strata weights used, not a plain count of points), uncertainty is reported for every headline estimate, points without a clear reference label are handled in a stated and defensible way, the reference labelling is independent of the map being judged, rules were fixed before results were seen (or changes are disclosed and their effect shown), and code and data are available to re-derive the numbers.

D2 (domain_accuracy), mandatory. This asks whether claims about the domain, here SAR water mapping and the sensor itself, match current knowledge and whether prior work is reported correctly. It belongs to the domain seat; I do not score it.

D3 (argumentative_coherence), mandatory. From my side this asks whether the conclusions follow from the evidence the methods produce. The thing to check is the step from the accuracy numbers and their intervals to the words in the abstract, discussion and conclusion: no claim stronger than the interval allows, no derived quantity reported as firmer than its inputs, and no contradiction between what the methods section says was done and what the results claim.

D4 (cross_disciplinary_relevance), high. This asks whether readers from neighbouring fields can follow the framing and whether interdisciplinary claims are backed. It belongs to the perspective seat; I do not score it.

D5 (writing_and_structure), normal. This asks about organisation, clarity, figures and tables, and venue conventions. It belongs to the journal-fit seat; I do not score it.

D6 (venue_fit_and_contribution), mandatory. This asks whether the paper fits the venue and adds something new and significant. It belongs to the journal-fit seat; I do not score it.

## Scoring Plan

### D1: methodology_rigor
dimension_id: D1
what_to_look_for: probability sampling design with stated strata and inclusion probabilities; stratum-weighted estimators of user, producer and overall accuracy and of area; intervals for every headline estimate with method stated; explicit rule for unresolved reference points with sensitivity bounds; independent reference labelling; disclosure of any rule changes made after seeing results; code and data that re-derive every number
what_triggers_block: a headline accuracy or area estimate whose estimator does not match the sampling design, or whose uncertainty is missing or wrongly computed, or whose handling of unresolved points can move the estimate by more than the reported effect without this being shown
what_triggers_warn: methods correct in outline but with a gap that limits trust or rerun, such as an undisclosed interval method, a reference process not shown to be independent, a post-hoc rule change disclosed but not bounded, or a derived quantity given without its own interval
what_triggers_fatal: the reported accuracy numbers cannot be produced by the stated design at all, for example reference labels taken from the map under test, a non-probability sample treated as design-based, or numbers that the released code and data contradict

### D3: argumentative_coherence
dimension_id: D3
what_to_look_for: each claim in abstract, discussion and conclusion traced to a reported estimate and its interval; claims scaled to the share of decided reference points; derived quantities carried with their uncertainty; no contradiction between methods and results
what_triggers_block: a central claim that the reported intervals or the unresolved-point share do not support, such as a ranking or superiority claim between maps whose intervals overlap, stated without qualification
what_triggers_warn: claims broadly supported but worded more firmly than the evidence, such as a point estimate quoted without its interval, or a caveat present in the methods but missing where the claim is made
what_triggers_fatal: the central conclusion is contradicted by the paper's own reported results

criteria_binding_unavailable

[CONTRACT-ACKNOWLEDGED]

---

# PHASE 2 (paper-visible)

Manuscript reviewed: `docs/paper/review/manuscript-557e3fd.md` (draft of 14 November 2026). Method checked against `pipeline/validation/june18.py`, `data/validation/june18/{strata.json, points.csv, reference.csv, result.json}`, `data/prediction/nisar_check.json`, `docs/paper/numbers.md` and the git history of commits `682d951`, `54fdc99`, `e5a2d30`, `de3e9f8` (read-only). The reviewer's own recomputations below were run from `reference.csv` with a small throwaway script; they are offered for human audit, not as verified truth.

contract_role: methodology

## Dimension Scores

### D1: methodology_rigor
score: block
trigger: "whose uncertainty is missing or wrongly computed"
block_class: repairable

### D2: domain_accuracy
score: not_assessed

### D3: argumentative_coherence
score: warn
trigger: "claims broadly supported but worded more firmly than the evidence"

### D4: cross_disciplinary_relevance
score: not_assessed

### D5: writing_and_structure
score: not_assessed

### D6: venue_fit_and_contribution
score: not_assessed

## Review Body

### Reviewer Identity

Peer Reviewer 1 (Methodology), Card #2: a statistician who works on design-based accuracy assessment of land-cover and land-change maps (stratified estimators, bootstrap intervals, reference points that cannot be labelled). I review the 18 June sample check, the Pego-Oliva event check and the pre-specified model test as designs. I do not judge SAR physics, the literature, or venue fit.

### Overall Recommendation

Major Revision.

### Confidence Score

4. Design-based accuracy assessment is my core field. SAR scattering physics and the optical rice-flooding index sit next to my field, not inside it.

### Calibration Status

`NOT_CALIBRATED`

### Score rationale

D1 is scored block (repairable) because the uncertainty on headline estimates is wrongly computed or missing. The "bounds" in Table 4 for producer's accuracy are not bounds (W2). The derived wet-rice area has no interval at all (W5). Both are cheap to fix, and with the correct numbers the main ranking (NISAR far above DSWx-S1) still holds. The decided-only treatment of a 67 % unclear rate in stratum B (W1) and the referee's unknown quality (W4) need real extra analysis, though not new satellite data. D3 is scored warn: the claims are mostly worded with care, but "pre-registered" and "passes" appear in the abstract and contributions without the conditions they depend on (W1, W3).

### Summary Assessment

The paper wants to use NISAR L-band water maps as training labels for a flood-extent model, and it tests those labels first. The test is a stratified sample of 513 points on 18 June 2026, scored by an optical-only referee, plus a check of one event against Copernicus EMSR935. The design is better than most in this area. It uses a probability sample stratified by map class, the points were committed to git before scoring (I checked that `points.csv` and `strata.json` have not changed since `682d951`), the estimators are correctly stratum-weighted (I re-derived 0.940 and 0.517 from `reference.csv`), and the authors report the results that go against them. The main weakness is that the headline numbers come from only the points the referee could decide, while most points in the key stratum cannot be decided (101 of 150 in B, 82 of 150 in D). Nearly all of those points show the same pattern, wet on 8 June and dry on 22 June, so "unclear" points are not a random subset. The sensitivity analysis meant to cover this is computed wrongly for producer's accuracy, the wet-area estimate has no interval, and the pre-registration claim covers v1 of the referee, not the v2 numbers shown in the headline. None of this breaks the qualitative finding: under the full worst-case range, NISAR's producer's accuracy (about 0.22–0.71) stays far above DSWx-S1's (about 0.01–0.05). But the precision and the "passes a rule fixed in advance" wording are stated more firmly than the evidence allows. The flood-extent model, which the title names, is not in this draft yet. I recommend Major Revision.

### Criterion-Bound Judgements

| Dimension / criterion | Criterion source | Judgement | Evidence anchors | Rationale | Uncertainty or scope limit | Decision bearing? |
|---|---|---|---|---|---|---|
| Sampling design (probability, stratified by map class) | Olofsson et al. 2014 sampling design; Card #2 | MEETS | §4.3, Table 3; `points.csv` unchanged since `682d951` | Grid with random offset, then simple random sampling within strata, fixed seed, committed before scoring | Strata A and C are a full census of grid candidates; this is fine but should be said | no; it is sound |
| Estimators match design | Olofsson et al. 2014 analysis design | MEETS | §4.3; `june18.py` `map_accuracy` | Correct stratified ratio estimators; U-Net scored with the general form even though it was not used to stratify | Reviewer re-derived only NISAR and DSWx-S1 | no |
| Uncertainty on headline estimates | Olofsson et al. 2014 (intervals for accuracy and area); Card #2 item 3 | DOES_NOT_MEET | Table 4 producer's bounds; §5.1 wet area | Bounds wrongly computed (W2); area has no interval (W5); intervals at 0 or 1 come from a degenerate bootstrap (W12) | Sampling intervals are fine if the missing-at-random assumption holds | yes; it drives the D1 block |
| Handling of unresolved reference labels | Card #2 item 1; stats standards §1.6 (missing-data handling) | PARTLY_MEETS | §4.3 "Unclear points are not imputed"; §5.1 counts | No imputation and bounds were reported, which is good, but the missing-at-random assumption is never named or tested, and the unclear pattern is systematic (W1) | The true wet state of unclear points cannot be known from the released data | yes |
| Reference independence and quality | Olofsson et al. 2014 response design (reference better than map); Card #2 item 2 | PARTLY_MEETS | §4.3 referee; §5.1 strict result | Independent of radar data, but its own accuracy is unknown, it shares the wet-soil error with NISAR, and the verdict flips under the strict variant (W4) | Reviewer is not an expert in optical rice indices | yes |
| Pre-registration and post-hoc changes | Card #2 item 2; stats standards §4.2 (HARKing) | PARTLY_MEETS | §4.3 transparency note; commits `54fdc99`, `e5a2d30` | Change disclosed and v1 reported, but v2 is shown as the pre-registered headline; v1's interval (0.69–0.96) is left out (W3) | Discussion #25 text and timestamps not seen by this reviewer | yes; it bears on D3 wording |
| Event check design (Pego-Oliva) | Olofsson et al. 2014 (map-to-map comparison is not accuracy assessment) | DOES_NOT_MEET | §5.3; `nisar_check.json` thresholds | Threshold method not disclosed (W6); share-inside figure has no chance baseline (W7) | Reviewer cannot compute the baseline from released files | yes, for contribution 2 |
| Reproducibility | Contract D1 | EXCEEDS | Data and code availability; `reference.csv` | Per-point labels, code and seeds released; reviewer reproduced the estimators | Land-class numbers come from an unmerged branch | no |
| Conclusions within evidence | Contract D3 | PARTLY_MEETS | Abstract; §1 contributions; §5.2 | Mostly careful, with adverse results stated, but "pre-registered", "passes" and "therefore" go beyond the evidence (W3, W9) | none identified | yes; it drives the D3 warn |

I did not total, weight or map these judgements to the recommendation.

### Statistical reporting completeness (stats standards §6)

| Item | State | Note |
|---|---|---|
| Descriptive statistics | COMPLETE | Per-stratum wet/dry/unclear counts given for v2 and strict; v1 counts only in `result.json` |
| Effect sizes | NOT_APPLICABLE | The accuracy measures are themselves the estimates of interest |
| Confidence intervals or other uncertainty | PARTLY_COMPLETE | Missing for wet area (W5) and Pego-Oliva (W7); producer's bounds wrong (W2) |
| Assumption checks | PARTLY_COMPLETE | Missing-at-random for unclear points not stated (W1) |
| Power or precision justification | MISSING | No target precision for n = 150 per stratum, and no allowance for the unclear rate (W13) |
| Missing-data handling | PARTLY_COMPLETE | Method stated (decided-only plus bounds); assumption and tipping point missing (W1) |
| Format and tables | PARTLY_COMPLETE | "0.02–0.02" and "1.00–1.00" (W12) |
| Red-flag follow-up | partly resolved | Referee rule changed after v1 was seen: verdict unchanged under v1, so the risk is contained but should be shown (W3) |

### S1: Probability sample committed before scoring

The stratified design follows Olofsson et al. (2014). The candidate grid uses a random offset, sampling within strata is random with a fixed seed, and a non-rice control stratum is included. `points.csv` and `strata.json` are byte-identical between commit `682d951` (sample) and HEAD, and the v1 scoring commit `54fdc99` came after it. This is the core of an honest accuracy assessment, and many SAR water papers skip it.
**Evidence Anchor**: text: §4.3 "points are drawn at random per stratum with a fixed seed (Table 3)"

### S2: Estimators correctly stratum-weighted, with a third map on the same sample

`map_accuracy` uses the standard stratified ratio estimators (per-stratum proportions weighted by stratum area share). The U-Net, which was not used to build the strata, is scored with the general form, which is correct. Recomputing from `reference.csv` gives NISAR user's 0.940 and producer's 0.517, matching `result.json`.
**Evidence Anchor**: `text: §4.3 "User's and producer's accuracy are stratum-weighted (weight = stratum share of the rice) over decided points"`

### S3: Results that go against the authors are reported

The strict referee result (NISAR fails), the v1 result, the missed DANA peak and the alert never reaching red are all in the main text, not hidden in a supplement.
**Evidence Anchor**: `text: §5.1 "The result that goes against us: not open water."`

### S4: Full re-analysis is possible

The released per-point labels (each optical look, v1, v2 and strict) and the code let a reader recompute every 18 June estimate, which this review did. `numbers.md` traces every printed value to a file.
**Evidence Anchor**: text: Data and code availability "Code and result files:"

### S5: The model test is fixed before the model exists, with strong baselines and a separate scorer

§4.5 holds out the event, separates EMSR935's observed and modelled layers, masks the "not analysed" areas, sets three baselines including persistence, names a pass rule, and gives scoring to a team member who is not the model's author. It also discloses its own amendment. This is a good confirmatory design.
**Evidence Anchor**: `text: §4.5 "The model is said to add value if its F1 beats all three baselines; otherwise we report that it does not."`

### W1: Decided-only estimates assume that unclear points are missing at random, which the data argue against

- **Problem**: Every headline estimate (B share 0.94, NISAR producer's 0.52, wet area 79 %) uses only the decided points, so it assumes that, within each stratum, unclear points are wet at the same rate as decided ones. That assumption is never named. It covers 101 of 150 points in B and 82 of 150 in D. In `reference.csv` the unclear points share one pattern: 95 of 101 in B and 78 of 82 in D are wet on 8 June and dry on 22 June, and so are all 13 unclear control-cropland points (stratum E). These points are a systematic group, not a random one. The paper names two causes: the canopy hides water, which would make them truly wet, and drainage, which would make them dry. Neither cause yields the decided-only value. If every unclear point is wet (the paper's own preferred cause), NISAR's producer's accuracy is 0.47, not 0.52. The pre-registered rule holds on all 150 B points only if at least about 59 of the 101 unclear points are truly wet, since (46 + u)/150 ≥ 0.70 needs u ≥ 59. Under decided-only the implied rate is 94 %.
- **Evidence Anchor**: `text: §5.1 "101 of 150 B points are unclear because the two optical looks disagree"`
- **Why it matters**: The "passes" verdict, and how precise the producer's accuracy looks, depend on an untested assumption about two-thirds of the key stratum.
- **Suggestion**: State the missing-at-random assumption next to each headline number. Add a tipping-point analysis: the share of unclear B (and D) points that must be wet for the rule to pass, and for producer's accuracy to cross chosen values. Report the scenario that matches the paper's preferred cause (unclear = wet). A stronger but costlier option: label a random subsample of unclear points with a better reference (very-high-resolution imagery near 18 June, or sowing and drainage records from the irrigation communities) and estimate their wet rate, as a two-phase design.
- **Severity**: Major
- **Confidence**: 5, core expertise in missing reference labels in stratified designs

### W2: The producer's-accuracy "bounds" in Table 4 are not bounds, and the decided-only value lies outside them

- **Problem**: Table 4 gives NISAR producer's accuracy as 0.52 with "bounds" 0.44 / 0.47, so the point estimate sits outside its own bounds. The cause: producer's accuracy is a ratio whose numerator rises only with wet points in map-water strata (A, B), while its denominator rises with wet points everywhere. Setting all unclear points dry, or all wet, does not reach the extremes. Because the NISAR and DSWx-S1 maps are constant within each stratum, the true extremes come from assigning unclear points stratum by stratum. Recomputed from `reference.csv`: NISAR producer's 0.223 (A, B dry; C, D wet) to 0.709 (A, B wet; C, D dry), and DSWx-S1 0.013 to 0.051. For the U-Net, whose map varies within strata, point-level assignment is needed. User's accuracy bounds (0.32 / 0.98) are correct, because the user's denominator is fixed.
- **Evidence Anchor**: `table: Table 4, NISAR row — producer's 0.52, 95 % CI 0.48–0.57, bounds 0.44 / 0.47`
- **Why it matters**: The table is the paper's main evidence. A reader takes the bounds as the full uncertainty from unclear points and concludes it is about ±0.05, when it is about ±0.25. The ranking survives the correct bounds (NISAR's minimum 0.22 is above DSWx-S1's maximum 0.05), which the paper could say plainly.
- **Suggestion**: Replace the two fixed scenarios with true worst-case bounds (stratum-level for NISAR and DSWx-S1, point-level for the U-Net). Keep the two scenarios as labelled cases if wanted, and explain why a ratio estimate can fall outside them. Also note that the bootstrap CI (0.48–0.57) covers sampling error only, conditional on W1's assumption.
- **Severity**: Major
- **Confidence**: 5, recomputed from the released data, and the ratio-estimator behaviour is standard

### W3: The "pre-registered" label covers referee v1, but the headline shows v2, defined after v1 was seen

- **Problem**: The git history shows the order: sample and v1 referee code (`682d951`, 20:52), v1 scored and seen (`54fdc99`, 20:56: B 25 of 30 wet, 0.83, CI 0.69–0.96, passes), then v2 written after the team review (`e5a2d30`, 21:17), then v2 scored (`de3e9f8`, 21:21). v2 changed the after-image (Sentinel-2 23 June to Landsat 9 22 June). It also added the bounds, the strict variant and the U-Net, which were additions rather than changes. The pass rule did not change, and v1 also passes, which limits the damage. Still, only v1 was fixed before any referee output was seen. The abstract and Contribution 1 present the v2 numbers as the result of a pre-registered check. The v1 interval (0.69–0.96) is not in the paper: `result.json` now stores v1 without intervals. The text calls the reviewer "a team review", but the commit names the team member who built the per-pass water maps and the app U-Net, two of the products being judged.
- **Evidence Anchor**: `text: §1 Contributions "An independent, pre-registered check of early NISAR water maps."`
- **Why it matters**: Changing the reference definition after seeing results is a forking-paths risk, even when well motivated. The v2 change moved the B share from 0.83 to 0.94 and the decided B count from 30 to 49, both in NISAR's favour. Readers should be able to see that the confirmatory result is v1 and that v2 is a sensitivity analysis.
- **Suggestion**: Report v1 as the confirmatory result, with its interval (0.69–0.96) and the verdict, in the abstract or in Table 4 next to v2. Call v2 a post-hoc refinement and give the reason. Quote, or archive with a timestamp (e.g. Zenodo or OSF), the exact Discussion #25 rule text, including whether it named decided-only scoring and the interval method. Say who proposed the v2 change.
- **Severity**: Major
- **Confidence**: 4, timeline from git; the Discussion #25 text was not seen

### W4: The referee is independent of radar data but not shown to be accurate, and it shares the map's main error

- **Problem**: The referee is the only reference. It applies index thresholds (LSWI + 0.05 ≥ EVI, from 500 m MODIS composites, or MNDWI > 0) to two single dates around 18 June. "Independent" here means only that no radar data are used. The referee's own accuracy at Albufera is never measured. Its main known error, wet soil tripping LSWI, is the same as NISAR's main known error, wet soil darkening HH. When map and reference share an error, agreement goes up. That fits what happens when the referee is narrowed to MNDWI alone: the B share falls from 0.94 to 0.10 and the verdict flips. So the verdict depends entirely on which of two untested indices counts as truth.
- **Evidence Anchor**: `text: §4.3 "The referee never uses a radar, so the check is not circular."`
- **Why it matters**: Good practice (Olofsson et al. 2014) requires reference data of higher quality than the map, or a stated estimate of reference error. Without it, "NISAR passes" really means "NISAR agrees with one optical index that responds to the same surface states".
- **Suggestion**: Use "data-independent" rather than "independent" and say what this does and does not rule out. Check the referee on a small set of points with a better source (very-high-resolution imagery, field photos, or irrigation-community flooding dates) and report its agreement. Discuss correlated error as a threat to user's accuracy in B in particular.
- **Severity**: Major
- **Confidence**: 4, core on response-design principles; adjacent on optical rice indices

### W5: The derived wet-rice area has no interval, and its sensitivity to the referee is larger than its sampling error

- **Problem**: §5.1 reports 11,601 ha (79 %) of wet rice with no interval and five significant figures. My stratified bootstrap from `reference.csv` (2,000 resamples) gives about 10,600–12,600 ha, assuming missing-at-random. With every unclear point dry or every one wet, the range is 4,583–13,299 ha. The v1 commit reported about 10,000 ha (8,500–11,400). The v2 point estimate lies outside the v1 interval, so the after-image choice alone moved the area by more than the sampling uncertainty. v2's code no longer bootstraps the wet share, so the interval was lost between versions.
- **Evidence Anchor**: `text: §5.1 "of the rice was wet around 18 June, consistent with the flooded period of the rice calendar"`
- **Why it matters**: An area estimate is a main output of an Olofsson-style design. Giving it without uncertainty, while citing that good practice, is a reporting gap. The number currently supports only a side claim, which is why I rate it Minor.
- **Suggestion**: Report the area as "about 11,600 ha (95 % CI about 10,600–12,600; 4,600–13,300 ha if every unclear point is dry or wet)", recomputed by the authors, and note the v1 value. Add the wet share to the bootstrap draws in `june18.py`.
- **Severity**: Minor
- **Confidence**: 5, recomputed from the released data

### W6: The Pego-Oliva event check uses a different, undisclosed water threshold

- **Problem**: §4.2 defines water as filtered HH below −15.0 dB, and §5.3 says the threshold "is moved by ±1 dB". `nisar_check.json` shows the Pego-Oliva new-water map uses Otsu per scene, with thresholds of −11.85 dB (16 Oct) and −12.03 dB (28 Oct), about 3 dB looser than the method in §4.2. The manuscript never states this.
- **Evidence Anchor**: `absence: §4.2 and §5.3 — expected a statement of the threshold method and values used for the Pego-Oliva new-water map; checked §4.2, §5.3, Table 2, §6.2, Data and code availability`
- **Why it matters**: Contribution 2 is offered as support for using NISAR water (made at −15 dB) as labels, but it tests a different detector. A reader cannot rerun it from the text.
- **Suggestion**: State the method and the thresholds. Also report the result at −15 dB, or explain why the labels will use Otsu.
- **Severity**: Major
- **Confidence**: 4, read from the result file; the reason for the choice is not known

### W7: "87 % inside the outline" has no chance baseline and no recall figure

- **Problem**: The share of new NISAR water that falls inside the EMSR935 outline is reported without the share of the analysed area that lies inside the outline. If the outline (877 ha) covers most of the mapped area, randomly placed water would also fall mostly inside. Recall (184 of 877 ha, about 21 %) is given only indirectly. No intervals are given, and the reference is another map, with imagery 8 days earlier than the NISAR pass.
- **Evidence Anchor**: `text: §5.3 "of it lies inside the official flood outline"`
- **Why it matters**: Without a baseline, 87 % cannot be read as skill. The figure is in the abstract.
- **Suggestion**: Report the outline's share of the analysed area as the chance baseline, plus recall and the comparable DSWx-S1 inside-share. Call the analysis a map-to-map agreement check, not an accuracy assessment.
- **Severity**: Major
- **Confidence**: 3, the baseline cannot be computed from released files, so its size is unknown

### W8: The flood-extent model named in the title has no method or results yet

- **Problem**: §4.4 and §5.6 are placeholders. The design of the model, its features, its spatial blocking and the result of the pre-specified test in §4.5 are absent, so the title's main claim cannot be reviewed. The authors flag this openly. It is a known draft gap, not a flaw in the completed work, and every other finding here stands on its own.
- **Evidence Anchor**: `text: §4.4 "To be filled from Z. Stoimchev's model once on GitHub"`
- **Why it matters**: As submitted, the paper cannot be accepted under its current title. Either the model results are added under the §4.5 rule, or the paper is reframed as a label-validation study.
- **Suggestion**: Fill §4.4 and §5.6 as planned and report the §4.5 verdict whatever it is. If the model is late, retitle the paper around the label check.
- **Severity**: Critical
- **Confidence**: 5, plain from the text

### W9: Autumn agreement is used as proof that the June gap is about vegetation

- **Problem**: The autumn agreement between the radars fits the vegetation explanation, but it does not rule out the paper's other explanation for June, wet soil, which §5.1 says optical data cannot separate. "Therefore" overstates what the data show.
- **Evidence Anchor**: `text: §5.2 "The June disagreement is therefore specific to water beneath vegetation, not a calibration problem."`
- **Why it matters**: It conflicts with the more careful reading in §5.1.
- **Suggestion**: Write "is consistent with" and say again that wet mud remains possible.
- **Severity**: Minor
- **Confidence**: 4, logic of the inference

### W10: Threshold confirmation by correlation across dates is weak evidence

- **Problem**: r = 0.978 across 10 dates on track 058 A is driven by one large date (28 October, 30.8 % against 32.1 %). Most other dates are near 0 %. The −16 dB threshold gives a higher r (0.982). The yardstick is DSWx-S1, which the paper argues misses June water.
- **Evidence Anchor**: `text: §4.2 "NISAR's dark share of the rice and DSWx-S1's flooded share correlate at r = 0.978"`
- **Why it matters**: The −15 dB threshold is called "confirmed", but this test can barely tell thresholds apart.
- **Suggestion**: Report the mean absolute gap (the criterion that `threshold_choice` actually used) and r without the 28 October date. Call it a consistency check.
- **Severity**: Minor
- **Confidence**: 4, read from `nisar_check.json`

### W11: The bracket mixes sensors and footprints, which can create "unclear" labels

- **Problem**: The before look is Sentinel-2 (B8A/B11, 20 m) and the after look is Landsat 9 (30 m), both averaged to 20 m and then over a 3 × 3 window (60 m) around each point, while NISAR is judged per 20 m pixel. Index thresholds tuned on one sensor are applied to another without adjustment. All 513 points were clear on Landsat, so the Sentinel-2 23 June fallback was never used, but the text implies that it was.
- **Evidence Anchor**: `text: §4.3 "on the closest clear look after (Landsat 9, 22 June; Sentinel-2, 23 June where Landsat is cloudy)"`
- **Why it matters**: Differences between the sensors are a third possible cause of the wet-then-dry pattern behind W1. The 13 such flips on non-rice control cropland hint at a cause other than canopy.
- **Suggestion**: Say that the fallback was not used. Report how often the 8 June Sentinel-2 and 22 June Landsat labels agree on points that should be stable (stratum E). Mention the footprint mismatch.
- **Severity**: Minor
- **Confidence**: 3, adjacent on cross-sensor index consistency

### W12: Intervals at 0 or 1 come from a degenerate percentile bootstrap

- **Problem**: DSWx-S1 producer's CI is printed as "0.02–0.02" (actually 0.018–0.022). The U-Net user's accuracy is 1.00 with CI 1.00–1.00, but the U-Net says water at only 12 of 513 points. The B-share interval ends at 1.00. A Wilson interval for 46 of 49 is about 0.835–0.979.
- **Evidence Anchor**: `table: Table 4, DSWx-S1 and U-Net rows — CI "0.02–0.02", user's 1.00`
- **Why it matters**: Percentile bootstraps cover poorly near 0 and 1, and a CI of zero width looks like certainty.
- **Suggestion**: Print three decimals, give the number of map-water sample points for each map, and use or add a Wilson- or logit-based interval near the boundary. The verdict does not change.
- **Severity**: Minor
- **Confidence**: 5, standard interval behaviour

### W13: No sample-size or target-precision justification

- **Problem**: n = 150 per stratum is not justified against a target standard error, and the design did not allow for the unclear rate (now 67 % in B).
- **Evidence Anchor**: `absence: §4.3 — expected a sample-size rationale or target precision; checked §4.3, Table 3, Appendix A, june18.py docstring`
- **Why it matters**: Olofsson et al. (2014) recommend planning sample size against precision. With two-thirds of B undecided, the effective size is 49, not 150.
- **Suggestion**: State the basis for 150. For future dates, plan the sample to allow for the expected unclear rate.
- **Severity**: Minor
- **Confidence**: 4, standard design guidance

### Detailed Comments

#### Research Questions & Hypotheses
The 18 June question ("is NISAR's extra water real?") is clear and turned into a falsifiable rule, which is good. The rule tests user's accuracy in B only. The headline comparison of producer's accuracy (0.52 against 0.02) is descriptive and was not pre-registered. That is fine, but it should be labelled as such.

#### Research Design
The stratified design suits a two-map disagreement question. The weak point is the response design (the referee): it never observes 18 June, it brackets the date with looks 10 days before and 4 days after, and its quality is unknown (W4, W11).

#### Sampling Strategy
The sampling is sound (S1). Strata A and C are full censuses of grid candidates, so their bootstrap variance is conservative. Saying so would help. The effective sample size after unclear points are dropped is not reported in Table 3.

#### Data Collection
The optical processing in `june18.py` checks itself (it fails loudly on wrong reflectance scale). Per-point records for every look are released (S4).

#### Analysis Methods
The estimators are correct (S2). The handling of unclear points is the decisive gap (W1, W2). The wet area has no interval (W5). The intervals near the boundary are degenerate (W12).

#### Results Presentation
Table 4 should add true bounds, the v1 row with its interval, and the decided n for each map. The Pego-Oliva paragraph needs a baseline and the threshold method (W6, W7).

#### Reproducibility
Excellent for the 18 June and Pego-Oliva checks. The land-class numbers in §5.4 come from an unmerged branch.

#### Methodological Fallacies Detected
- The forking-paths risk from changing the referee after v1 was seen is contained, because v1 also passes, but it is not presented that way (W3).
- Correlated error between map and reference can inflate agreement (W4).
- Ignorable missingness is assumed under a missingness pattern that is systematic (W1).
- Confirmation by correlation driven by a single high-leverage date (W10).

### Questions for Authors

1. What is the exact text and timestamp of the Discussion #25 rule? Did it specify decided-only scoring and the bootstrap interval, or were those set later?
2. Can a random subsample of the unclear B and D points be labelled with a better source (very-high-resolution imagery, field photos, or sowing and drainage dates from the irrigation communities)? Even 30 points would put a number on the missing-at-random assumption.
3. Why was the Landsat 9 image of 22 June not in v1? Was its existence known before v1 was scored?
4. What share of the EMSR935 analysed area lies inside the outline at Pego-Oliva, and what is the inside-share at −15 dB?

### Minor Issues

- "roughly 11,601 ha": round to match the precision (W5).
- The abstract's "fixed in git before scoring" is true of the points, not of the v2 referee; say which.
- In Table 4, label the bound columns "unclear all dry / all wet" in the column header itself.
- Table 3 could add a "decided" column per stratum.

## Arithmetic Receipts

### AR1
procedure_id: grim
evidence_anchor: text: §5.1 "46 of 49 decided points are wet"
reported_inputs: n = 49 decided points; 46 wet; reported share 0.94; binary scale 0 to 1; two decimals
assumptions: rounding to nearest at two decimals, licensed by the manuscript's statement that values are read from result files rounded in docs/paper/numbers.md; truncation not assumed
derivation: 46 / 49 = 0.93878; 0.93878 lies in [0.935, 0.945)
derived_value_or_range: 0.93878
comparison_rule: derived value must lie inside the two-decimal rounding interval of the reported value
rounding_interval: [0.935, 0.945)
nearest_achievable: 45/49 = 0.91837; 46/49 = 0.93878; 47/49 = 0.95918
status: consistent

### AR2
procedure_id: grim
evidence_anchor: text: §5.1 "stratum B has 3 wet / 26 dry / 121 unclear"
reported_inputs: n = 29 decided points; 3 wet; reported share 0.10; binary scale 0 to 1; two decimals
assumptions: rounding to nearest at two decimals, licensed as in AR1; truncation not assumed
derivation: 3 / 29 = 0.10345; 0.10345 lies in [0.095, 0.105)
derived_value_or_range: 0.10345
comparison_rule: derived value must lie inside the two-decimal rounding interval of the reported value
rounding_interval: [0.095, 0.105)
nearest_achievable: 2/29 = 0.06897; 3/29 = 0.10345; 4/29 = 0.13793
status: consistent

### AR3
procedure_id: grim
evidence_anchor: text: §5.1 "of decided cropland points are wet"
reported_inputs: reported share 2.9 percent; stratum E has 150 points (Table 3); decided count not stated in the manuscript
assumptions: none beyond the manuscript; the decided denominator for stratum E is not reported
derivation: the analytic n for the decided E points is not given in the manuscript, so reachability cannot be tested
derived_value_or_range: not derived
comparison_rule: two-decimal rounding interval reachability, not applied
status: not_computable
not_computable_reason: analytic_n_ambiguous
