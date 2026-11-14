# Seat report: Devil's Advocate (da)

Contract: reviewer/reviewer_full/v2 (shared/contracts/reviewer/full.json). Paper metadata given in Phase 1: title "Where will the water go? Learning flood extent in Valencia from the first months of NISAR L-band data"; field: SAR flood mapping; about 6,500 words.

`scripts/check_phase_conformance.py` did not run (skill checker scripts are not installed in this setup).

# Phase 1 (written before the manuscript was opened)

## Contract Paraphrase

D1 methodology_rigor. From an adversarial seat, this asks whether the way data was gathered, split, labelled and scored could have produced the reported numbers even if the method did not work; whether someone else could rerun it and get the same thing. It is not mine to score, but any hole I find here that breaks the argument I will still report.

D2 domain_accuracy. This asks whether what the paper says about the field, its sensors, and earlier work is true and fairly told. Not mine to score; I will flag cases where a claim about the field is used as a load-bearing step in the argument and does not hold.

D3 argumentative_coherence. This is my dimension. It asks whether the main claim follows, step by step, from the evidence shown; whether a hidden assumption is doing the work; whether a simpler explanation fits the data as well or better; and whether the conclusions say more than the evidence allows. A fallacy, a circular step, or a data-conclusion mismatch at the core lands here.

D4 cross_disciplinary_relevance. This asks whether readers from nearby fields can follow the framing and whether claims that reach into other fields are backed. Not mine to score; I may name missing stakeholders without elaborating them.

D5 writing_and_structure. This asks whether the paper is organised and clear, and whether figures and tables do their job. Not mine to score.

D6 venue_fit_and_contribution. This asks whether the paper fits its venue and adds something new and significant. Not mine to score; my "so what?" test can still raise a finding where the claimed contribution rests on a broken argument.

## Scoring Plan

### D3: argumentative_coherence
dimension_id: D3
what_to_look_for: Whether each headline claim follows from the presented evidence without circular steps, hidden assumptions, or overreach; whether a more parsimonious rival explanation fits the reported numbers; whether internal statements agree with each other and with the cited result files.
what_triggers_block: A core claim rests on a reasoning step that the paper's own evidence does not support, or a rival explanation fits the reported results at least as well and is not addressed, but the core claim could be rescued by re-analysis, narrowing, or new evidence.
what_triggers_warn: Secondary claims overreach the evidence, a material hidden assumption is unstated, or a plausible rival explanation is acknowledged only weakly, while the central claim still follows from the evidence.
what_triggers_fatal: The paper's own reported data contradicts its central conclusion, or the central conclusion is reached by circular reasoning such that no revision short of a different study could support it.

criteria_binding_unavailable

[CONTRACT-ACKNOWLEDGED]

# Phase 2 (manuscript visible)

Manuscript reviewed: `docs/paper/review/manuscript-557e3fd.md` (read-only). Result files checked: `data/validation/june18/result.json`, `reference.csv`, `strata.json`; `pipeline/validation/june18.py`; `data/prediction/nisar_check.json` and `pipeline/prediction/nisar_check.py`; `data/prediction/flood/events.csv` and `metrics.json`; `docs/paper/numbers.md`; `git log` of the 18 June files. Recomputations below were done with the paper's own estimator on `reference.csv`. Cross-model DA: not configured, so single-model review.

contract_role: da

## Dimension Scores

### D1: methodology_rigor
score: not_assessed

### D2: domain_accuracy
score: not_assessed

### D3: argumentative_coherence
score: block
trigger: "A core claim rests on a reasoning step that the paper's own evidence does not support"
block_class: repairable

### D4: cross_disciplinary_relevance
score: not_assessed

### D5: writing_and_structure
score: not_assessed

### D6: venue_fit_and_contribution
score: not_assessed

## Review Body

### Calibration Status
`NOT_CALIBRATED`

### What the paper genuinely does well
The 18 June sample was committed to git (`682d951`) before the first score (`54fdc99`), the rule change to v2 was committed (`e5a2d30`) before v2 ran (`de3e9f8`), and the git order matches the paper's account. The paper reports the result that goes against it (strict referee) in the abstract. The held-out DANA test is written down before the model exists and was tightened with a persistence baseline. Every number I spot-checked (0.52, 0.02, 0.04, 0.94, 0.86–1.00, 46/3/101, 3/26/121, 6,387.2 ha, 249.6 ha, 87 %, 212 ha, 11,601 ha) matches its result file. The Pego-Oliva location result is a real signal: 184 of 212 ha of new water falls inside an outline of about 887 ha, inside an area of interest of roughly 100,000 ha (my rough area from the GeoJSON, sea included), far above chance.

### Criterion-Bound Judgements
| Dimension / criterion | Criterion source | Judgement | Evidence anchors | Rationale | Uncertainty or scope limit | Decision bearing? |
|---|---|---|---|---|---|---|
| Core thesis challenge | DA agent, challenge 1 | DOES_NOT_MEET | C1, C2 | The thesis "NISAR per-pass water is a good label for where flood water goes" is not what the evidence tests | Model is a placeholder; judged on the stated argument only | yes: core claim |
| Cherry-picking | DA agent, challenge 2 | PARTLY_MEETS | M2, m1 | Adverse strict result is reported, but the favourable threshold-confirmation track is reported and the less favourable one is not | none identified | no |
| Confirmation bias | DA agent, challenge 3 | PARTLY_MEETS | M3, m3 | Pre-registration is real, but the rule's bar sits below the referee's base rate, so it cannot fail for a map that over-maps | none identified | yes: rule is the headline proof |
| Logic chain validation | DA agent, challenge 4 | DOES_NOT_MEET | C1, M1, M5 | Steps from "dark HH in June rice" to "label for storm water" skip object, condition, and definition changes | none identified | yes |
| Overgeneralisation | DA agent, challenge 5 | PARTLY_MEETS | C1, m5 | Limits section is honest ("demonstration, not proof"), but title and conclusion still generalise | none identified | no |
| Alternative paths | DA agent, challenge 6 | PARTLY_MEETS | Ignored alternatives below | Baselines for the model test are good; rivals to the 18 June reading are not tested | availability of archive L-band unverified | no |
| Stakeholder blind spots | DA agent, challenge 7 | PARTLY_MEETS | Missing stakeholders below | Water managers who set the label signal are absent | named only, not elaborated (R3's role) | no |
| So what? | DA agent, challenge 8 | PARTLY_MEETS | C2 | If the model cannot learn rain effects from this window, the delivered contribution is a one-date label check | depends on placeholder results | yes |
| Field-norm self-calibration | DA agent, challenge 9 | MEETS | all rows | No CRITICAL or MAJOR band below rests on a field norm; each rests on the paper's own numbers or recomputation | none identified | no |

### Strongest Counter-Argument
The paper shows that a dark-HH threshold placed 0.6 dB below the median backscatter of the June rice (median −14.41 dB, threshold −15 dB) marks 44 % of a field that its own referee calls 79 % wet, and that a product built not to map inundated vegetation outside wetlands marks 1.7 %. Almost everything else follows from those two areas. A map that marked the rice at random with NISAR's area would get a producer's accuracy of about 0.44; NISAR gets 0.52. A map that called all rice water would clear the pre-registered 0.7 bar, because the referee's base rate is 0.79. The only contrast that tells skill apart from coverage, NISAR-only points against points neither map flags, goes from 0.68 to 0.94 under the main referee and disappears under the open-water referee (0.10 against 0.12). That is what one expects if both instruments respond to crop stage: sparse young rice is dark at L-band and has low EVI, which is exactly what the test "LSWI + 0.05 ≥ EVI" rewards. On this reading the check shows that NISAR picks out the least-grown paddies in a field the farm calendar already says is flooded. It does not show that NISAR finds flood water Sentinel-1 misses. The jump to labels then fails twice. The labels the model will use (dark water plus a +3 dB flooded-vegetation rule, merged with Sentinel-1) are not the map that was checked. And the training window from 17 June to the DANA contains, by the repository's own event table, no rain-driven new flood at either site: even a 124.6 mm storm in early October produced none, while farmers were re-flooding paddies in the same weeks. A rain-conditioned model trained there can learn the farm calendar and static low ground, not where storm water goes. The only flood that could teach it is the test event.

### Review narrative
C1 is a logic-chain break. The conclusion moves from "a −15 dB dark map agrees with an optical wetness index on one dry-season date in irrigated rice" to "NISAR water is a suitable label for where flood water goes after rain". Three things change along the way and none is tested. The object changes: the labels add a flooded-vegetation class and a Sentinel-1 merge whose rules are still a placeholder. The condition changes: irrigation water in June against rain-driven flooding. And the meaning changes: the paper's own strict test concludes the extra water is not open water. A label class that is "wet ground and water among plants" in managed paddies will mostly encode the farm calendar. Narrowing the conclusion to what was checked, or checking the actual label product on rain events, repairs this.

C2 is a foundation problem for the "learning" half of the title. The paper's training design (§4.4) uses NISAR passes from 17 June to the cut-off minus the DANA window. The repository's event table (`data/prediction/flood/events.csv`, the same data behind §4.6) lists four training new-flood events: 2025-05-17, 2025-10-14, 2025-11-26 and 2026-01-07. All four are before NISAR's first calibrated acquisition. In the NISAR window before the DANA there are none at either site. The largest storm in that window (124.6 mm in 3 days at Albufera on 4 October) has a negative excess area (−72 ha), and NISAR's rice dark share rose from 5.8 to 13.7 to 31.0 % on 4, 16 and 28 October because farmers re-flood the paddies. So the only rain–water co-variation in training is the farm calendar. The §6.3 promise that "with each storm the model sees how the footprint grows" has, in this window, zero storms with a flood to see. The caveat is that `events.csv` labels come from Sentinel-1 DSWx, not NISAR. But the NISAR labels merge Sentinel-1 on each pass, and the paper gives no NISAR-side event count to contradict it. This is repairable only by reframing: label validation now, model later. Alternatively, train on the 2024–2026 Sentinel-1 record and keep NISAR as the check, which is how the repository's own prediction pipeline describes itself (`pipeline/prediction/nisar_check.py` docstring).

M1 to M5 weaken the 18 June claim without, each on its own, killing it. NISAR-only points are clearly wetter than "neither" points under the main referee (odds ratio about 7), so some signal exists. The question is what the signal is.

### MINOR issues
| # | Dimension | Issue Description | Evidence Anchor | Confidence |
|---|-----------|-------------------|-----------------|------------|
| m1 | Cherry-picking | The threshold is said to be "confirmed" by r = 0.978 on track 058 A. On track 066 D (the track used for 18 June), r at −15 dB is 0.337 with June included, and −18 dB fits DSWx-S1 better (mean gap 4.64 against 11.72 points). The 058 A value rests on 10 dates, 7 of them near 0 %, with one large autumn point. On 058 A, 18 June has no DSWx pair. Report both tracks, or drop "confirmed". | text: §4.2 "was later confirmed on the second Albufera track, which played no part in choosing it" | 5 (read from nisar_check.json) |
| m2 | Logic chain | The U-Net is trained on DSWx-S1 labels, so its 0.04 is not independent evidence; it repeats the DSWx-S1 result. Presenting three maps reads as more corroboration than there is. | text: §4.3 "was trained on DSWx-S1 labels and is scored on the same points" | 4 (argument structure) |
| m3 | Confirmation bias | The referee was changed after v1 results were seen. The paper discloses this, and v1 points the same way, but v1 was scored without an interval (`with_ci=False` in june18.py), so the paper cannot say v1 also met the rule's interval clause. Report the v1 interval. | text: §4.3 "after a team review, the after-image was changed to the closest clear look" | 5 (read from code) |
| m4 | Logic chain | §2 says flooded vegetation in HH can look brighter (double bounce), but the checked detector keeps only dark pixels. The proposed explanation needs a specular, sparse-stem mechanism, not double bounce. State which mechanism applies at −15 dB, and note that the double-bounce class is not checked anywhere. | text: §5.1 "water beneath young rice plants (which L-band can reach and the optical open-water index cannot)" | 3 (adjacent field: SAR physics) |
| m5 | Overgeneralisation | Title and abstract promise learned flood extent while the model and its test are placeholders. The honest limits section does not undo the title. | text: Abstract "The flood-extent model and its independent test against EMSR935 are" | 4 (argument structure) |
| m6 | Evidence gap | "In the right place" needs a chance reference (share of the scored area inside the outline) and the recall: 184 of 877 outline ha is about 21 %. Both help the paper; neither is stated. | text: §5.3 "NISAR's new water is thus in the right place" | 4 (rough area from GeoJSON) |

### Ignored Alternative Explanations/Paths
1. **Crop stage as a common cause.** Low biomass lowers L-band HH and lowers EVI, which trips the referee's LSWI clause. This explains the B-against-D lift, the vanishing lift under the open-water referee, the 101 unclear B points (canopy grew between looks), and the seasonal rise in rice HH (−14.4 dB on 18 June to −9 dB by late July). A test: compare referee wetness within B and D after matching on 8 June NDVI or EVI.
2. **Threshold placement.** On 18 June the rice dark share is 54.5 / 43.7 / 32.2 / 20.4 / 9.4 % at −14 to −18 dB, and the per-scene Otsu threshold (−9.81 dB) would call about 90 % of the rice water. The 6,387 ha and the 0.52 belong to the chosen cut, not to NISAR. Report producer's and user's accuracy against threshold.
3. **Managed water, not storm water.** Albufera water levels and paddy flooding are set by people (sowing flood, eixugó drainage, autumn re-flooding). The paper names eixugó as a referee limit but not as a rival meaning for the labels.
4. **Sentinel-1 as teacher, NISAR as check.** The 2024–2026 Sentinel-1 record holds the four training events. The repository's own prediction code is built this way. The paper does not say why it reverses the roles.
5. **Archive L-band.** ALOS-2 PALSAR-2 or SAOCOM acquisitions over past Valencian floods, including October 2024, could supply L-band flood labels with rain-driven positives. Availability and licensing over these sites are unverified by me.
6. **Rain-volume fill on terrain.** A HAND-based fill scaled by event rain is a cheap physical baseline between "low terrain only" and a learned model.

### Missing Stakeholder Perspectives
- Rice farmers and the Albufera irrigation communities, whose decisions produce most of the observed water signal.
- The river basin authority (Confederación Hidrográfica del Júcar) and the managers of the lagoon outlets and of the Pego-Oliva natural park.
- Regional civil protection, who would issue or be blamed for an alert-as-map.
- Residents of built-up areas, where the paper says its labels are unreliable.

### Unexamined Premise
The paper assumes that water seen on a pass is a hydrological response, so that "where water was" can teach "where water goes given rain". At both study sites a large share of observed water is a management decision (paddy flooding, drainage, outlet control) on a calendar that partly lines up with autumn rain. If that premise fails, the labels teach the model a farming schedule, and rain will look like it predicts water only because both come in October.

### Observations (Non-Defects)
- The "unclear points are not imputed" choice is honest, but with 101 of 150 unclear in B, the decided subset is chosen by the referee's own stability. Missing-not-at-random is likely, which M4 covers in part.
- A GitHub Discussion post can be edited. A commit hash or tag for the rule text, next to the Discussion link, would make the pre-registration harder to doubt.
- The Pego-Oliva DANA pair mixes PROVISIONAL and VALIDATED processing. The paper says so, and this cuts against the 87 % less than it might seem, because both dates went through the same Otsu step.

#### CRITICAL
| # | Dimension | Issue Description | Evidence Anchor | Confidence | Field-Norm Boundary | Evidence-Crossing Rationale |
|---|-----------|-------------------|-----------------|------------|---------------------|-----------------------------|
| C1 | Logic chain / core thesis | The main conclusion (NISAR water is a suitable label for a model of where water goes) does not follow from the evidence. What was checked is a −15 dB dark-HH map on one dry-season date in irrigated rice. The labels to be used add a flooded-vegetation class and a Sentinel-1 merge whose rules are a placeholder. The target is rain-driven flooding, and the paper's own strict test says the extra water is not open water. Object, condition and meaning all change without a test. Repairable: narrow the conclusion to what was checked, or check the actual label product on rain events. | text: §7 "These results support using NISAR water, together with Sentinel-1, as labels for a model of where water goes"; §4.2 "final label rules and per-pass counts" | 4 (core: argument analysis) | | |
| C2 | Foundation / so what | The training window (NISAR passes 17 June to cut-off, DANA held out) contains no rain-driven new-flood event at either site. All 4 training events in events.csv (2025-05-17, 2025-10-14, 2025-11-26, 2026-01-07) predate NISAR's calibrated data. The largest storm in the window (124.6 mm, 4 Oct, Albufera) has −72 ha excess, while NISAR rice water rises 5.8 to 31.0 % from farm re-flooding in the same weeks. A rain-conditioned model cannot learn the rain-to-extent mapping from these labels; the only flood is the test. Repairable only by reframing or by changing the label source. | text: §4.6 "holds only 4 new-flood events in 504 passes"; §6.3 "With each storm the model sees how the footprint grows with rain" | 4 (computed from the repo's events.csv; labels there are Sentinel-1-derived) | | |

#### MAJOR
| # | Dimension | Issue Description | Evidence Anchor | Confidence | Field-Norm Boundary | Evidence-Crossing Rationale |
|---|-----------|-------------------|-----------------|------------|---------------------|-----------------------------|
| M1 | Rival explanation | Crop stage is a likely common cause of both NISAR-dark and referee-wet: sparse canopy lowers L-band HH and lowers EVI, which the LSWI + 0.05 ≥ EVI clause rewards. Under the open-water referee, NISAR-only points are no wetter than points neither map flags (0.10 against 0.12). Autumn agreement over bare paddies rules out a calibration offset, but not a vegetation effect without water, so "therefore water beneath vegetation" is a non sequitur. Test it by matching B and D on 8 June EVI or NDVI. | text: §5.2 "The June disagreement is therefore specific to water beneath vegetation, not a calibration problem." | 3 (adjacent field: SAR and optical physics) | | |
| M2 | Evidence / cherry-picking | The headline producer's gap mostly reflects mapped area, not skill. NISAR maps 43.7 % of the scored rice, and a random map of that size scores about 0.44 against NISAR's 0.52. DSWx-S1 maps 1.7 %, so its producer's accuracy is capped near 0.02 by area alone. NISAR's area is set by a threshold 0.6 dB below the rice median HH: the dark share moves 54.5 to 9.4 % from −14 to −18 dB (nisar_check.json). Report a same-area random baseline and accuracy against threshold. | table: Table 4 — NISAR producer's 0.52 against DSWx-S1 0.02 | 5 (recomputed from reference.csv and strata weights) | | |
| M3 | Confirmation bias | The pre-registered bar (B share at least 0.7, lower bound at least 0.6) sits below the referee's base rate in the rice (0.79). A map calling all rice water would pass it: on decided points it scores user's 0.79 and producer's 1.00. The pass therefore cannot tell NISAR apart from over-mapping. The contrast that can (B 0.94 against D 0.68) is never reported. | text: §4.3 "if its user's accuracy in stratum B is at least 0.7" | 5 (recomputed with june18.py estimator) | | |
| M4 | Evidence gap | The reported "bounds" are not bounds. They set every unclear point to the same label. Setting unclear points per stratum (B dry, D wet, and the reverse) gives a NISAR producer's range of 0.22 to 0.71, against the stated 0.44 / 0.47 and a point estimate of 0.52 that lies above both. The decided-only estimate also rests on 49 of 150 B points, chosen by the referee's own stability across dates. | text: §5.1 "The bounds show how much this matters" | 5 (recomputed from reference.csv) | | |
| M5 | Internal consistency | "Per-pass water" is not one definition. §4.2 defines water as HH below −15 dB, but the DANA check uses a per-scene Otsu threshold (−11.85 / −12.03 dB, nisar_check.json pego_oliva_dana), and the ±1 dB range in §5.3 is around Otsu. The code docstring says this baseline "over-maps water (precision about 0.2)". So the 87 % result does not check the map validated on 18 June, and the 18 June result does not check the map used at Pego. The 62 % at +1 dB also shows the DANA result is fragile. | text: §4.2 "Open water is a pixel whose 5 × 5-filtered HH is below −15.0 dB" | 5 (read from result file and code) | | |
