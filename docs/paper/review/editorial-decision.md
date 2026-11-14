# Editorial Decision Package

## Calibration Resolution

`calibration_status: NOT_CALIBRATED`

Current runtime boundary: this package is not upgraded from a candidate or prose-named profile. `PROFILE_MEASURED` is unavailable: no closed profile artifact or replay validator exists in this install, and no `execution_topology_sha256` was produced (see Review Panel Provenance).

## Manuscript Information
- **Title**: Where will the water go? Learning flood extent in Valencia from the first months of NISAR L-band data
- **Manuscript ID**: `docs/paper/review/manuscript-557e3fd.md` (draft of 14 November 2026, commit 557e3fd)
- **Submission Date**: 14 November 2026 (draft date)
- **Decision Date**: 15 November 2026
- **Review Round**: Round 1
- **Mode / contract**: `reviewer_full`, `reviewer/reviewer_full/v2` (panel_size 5)
- **Target venue**: none confirmed. All five cards disclose `criteria_binding_unavailable`. This is an explicitly unbound run: no venue-alignment claim is made anywhere in this package. Field-general expectations for a SAR remote-sensing / flood-mapping research article were applied by the seats.

## Review Panel Provenance (#540/#740)

- **Typed artifact**: none. `scripts/review_panel_provenance.py` (the provenance builder) is not installed in this setup and did not run, so no `review-panel-provenance/1.0` artifact exists.
- **Carrier state**: `invalid`, reason `absent`. Per protocol, every axis is rendered `unknown`; no path or digest is given that could look verified.
- **Artifact SHA-256**: none
- **Panel ID**: none
- **Normalized manifest SHA-256**: none
- **Execution topology SHA-256**: none
- **Fresh-context scope**: `within_panel_attempt_only` (does not compare retries or prior rounds)

| Seat | Role ID | Actor type | Context ID | Peer outputs visible | Model family | Provider | Human reviewer ID |
|---|---|---|---|---|---|---|---|
| EIC | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| R1 | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| R2 | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| R3 | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| DA | unknown | unknown | unknown | unknown | unknown | unknown | unknown |

| Provenance axis | Status (`true` / `false` / `unknown`) |
|---|---|
| Role-separated | unknown |
| Within-panel invocation-context separation | unknown |
| Blind to peer outputs | unknown |
| Model-family distinct | unknown |
| Provider distinct | unknown |
| Human-reviewer distinct | unknown |

- **Binary independence claim**: Not computed. Persona or role diversity proves only role separation; the panel is not relabelled as independent.
- **Correlated-error disclosure (artifact state)**: Model-family provenance is incomplete; cross-family separation is unknown, so correlated-error risk cannot be ruled out.
- **Dispatcher-reported execution (not artifact-verified)**: the dispatching session reports that all five seats ran as separate subagents of one model family (Claude), each with a fresh context and no visibility of the other seats' outputs; that there was one accountable human author and no human reviewer; and that no cross-model run was made. This synthesis was also produced by the same model family. On that report the same-family disclosure applies: All model-executed review seats used one model family; role separation does not remove correlated-error risk. Practical meaning: where several seats agree (for example the wrong producer's bounds, found by both R1 and DA), that agreement is not independent confirmation; the reviewers' recomputations should be re-run by the authors.
- **Cross-model decision check (Step 4b)**: `ARS_CROSS_MODEL` is not set; no cross-model check ran. Single-model decision.

---

## Part 1: Editorial Decision Letter

Dear Authors,

Thank you for submitting your manuscript titled "Where will the water go? Learning flood extent in Valencia from the first months of NISAR L-band data". No target journal was confirmed. Your manuscript has been reviewed through 5 role-separated review seats, including a Journal-Fit Reviewer role. Their execution provenance is reported above and is not reduced to a binary independence claim.

### Decision: Major Revision

Mechanical decision lines (v3.6.2 sprint contract, `reviewer/reviewer_full/v2`):

Binding check: all five cards (EIC, R1, R2, R3, DA) disclose `criteria_binding_unavailable`; explicitly unbound run; no #684 markers expected; no venue-alignment claim.

Role-scoped scoring matrix (only eligible roles count; `not_assessed` excluded):

| Dimension | Priority | Eligible roles | Assessed scores | Verdict (worst) |
|---|---|---|---|---|
| D1 methodology_rigor | mandatory | methodology | R1: block (repairable) | block |
| D2 domain_accuracy | mandatory | domain | R2: block (repairable) | block |
| D3 argumentative_coherence | mandatory | da, methodology | DA: block (repairable); R1: warn | block |
| D4 cross_disciplinary_relevance | high | perspective | R3: warn | warn |
| D5 writing_and_structure | normal | eic | EIC: warn | warn |
| D6 venue_fit_and_contribution | mandatory | eic | EIC: block (repairable) | block |

No seat declared a fatal block.

| Condition | Severity | Quantifier | Evaluation | Fired |
|---|---|---|---|---|
| F1 any mandatory dimension has a fatal block | 95 | any | no fatal block on D1, D2, D3, D6 | false |
| F2 any mandatory dimension scores 'block' | 90 | any | D1, D2, D3, D6 each have ≥1 assessed block | true |
| F3 two or more mandatory dimensions score 'warn' or worse | 70 | majority | D1 (n=1, owner R1 block): true; D2 (n=1, R2 block): true; D3 (n=2, both seats needed: DA block, R1 warn): true; D6 (n=1, EIC block): true → 4 ≥ 2 | true |
| F4 any high-priority dimension scores 'block' | 60 | any | D4 = warn | false |
| F5 any dimension scores 'warn' or worse | 40 | any | D1–D6 | true |
| F0 every dimension scores 'pass' | 10 | all | no | false |

Highest-severity fired condition: F2 (90) → `editorial_decision=major_revision`.

dimension_verdicts: [D1=block, D2=block, D3=block, D4=warn, D5=warn, D6=block]
fired_conditions: [F2, F3, F5]
da_critical_adjudications: [C1=VALIDATED, C2=VALIDATED]
editorial_decision=major_revision

The no-contract decision matrix gives the same result: all four scoring seats recommend Major Revision (Major / Major / Major / Major → Major Revision).

`scripts/check_panel_synthesis.py` did not run (not installed in this setup).

### Reviewer Summary

| Reviewer | Role | Recommendation | Confidence |
|---|---|---|---|
| Journal-Fit Reviewer (EIC) | Senior remote-sensing scholar, editorial experience in SAR applications and operational EO products | Major Revision | 4 |
| Reviewer 1 | Statistician, design-based accuracy assessment of land-cover and change maps | Major Revision | 4 |
| Reviewer 2 | SAR hydrology researcher, L- and C-band open water and flooded vegetation in agricultural wetlands | Major Revision | 4 |
| Reviewer 3 | Disaster-risk researcher, impact-based flood warnings and colour-coded alerts | Major Revision | 3 |
| Devil's Advocate | Fixed adversarial seat | N/A — findings only | N/A — per-finding only |

Confidence is an uncertainty and scope disclosure only. It was not totalled, averaged or used to weight, exclude or resolve any finding.

#### Step 1a — Reviewer Summary Matrix

| Dimension | Journal-Fit Reviewer | R1 (Methodology) | R2 (Domain) | R3 (Cross-disciplinary) |
|---|---|---|---|---|
| Overall Recommendation | Major Revision | Major Revision | Major Revision | Major Revision |
| Confidence / scope disclosure | 4; estimator detail outside seat | 4; SAR physics and optical indices adjacent | 4; sampling statistics outside remit | 3; judging a planned product, not a tested one |
| Key Strengths | traceability (S1); adverse results in main text (S2); timely label question (S3); fair "what others do better" (S4); pre-written model test (S5); data-maturity table (S6) | probability sample committed before scoring (S1); correct stratified estimators, reproduced (S2); adverse results (S3); full re-analysis possible (S4); pre-written test (S5) | strict-referee result up front (S1); DSWx-S1 rule described correctly (S2); physical controls (S3); SAR limits in towns (S4); positioning (S5, see Disagreement 1) | plain-language limits (S1); official zones kept as legal reference (S2); failures reported (S3); test run by a different author (S4); real gap between tools (S5) |
| Key Weaknesses | → Step 1b (W1–W10) | → Step 1b (W1–W13) | → Step 1b (W1–W10) | → Step 1b (W1–W8) |
| Weakness count (critical / major / minor) | 1 / 4 / 5 | 1 / 6 / 6 | 0 / 6 / 4 | 0 / 3 / 5 |
| # of Questions | 4 | 4 | 5 | 4 |
| # of Minor Issues (bullets) | 7 | 4 | 4 | 3 |

Devil's Advocate: 2 CRITICAL (C1, C2), 5 MAJOR (M1–M5), 6 MINOR (m1–m6), 6 ignored alternatives, 4 missing stakeholders, 1 unexamined premise.

#### Step 1b — Weakness Sub-Claim Inventory

Each `SC-n` maps one-to-one to roadmap item `REV-n` (SC-22 has two parts). Only seats that took a position are listed; every unlisted non-DA seat is `not-mentioned` (silence, not opposition). DA positions are shown for traceability but do not enter consensus counts. Severity and confidence are transported from each seat's own finding.

| sub_claim_id | parent_weakness | reviewer_id | position | evidence_pointer | severity | confidence |
|---|---|---|---|---|---|---|
| SC-1 | titular flood-extent model absent | EIC | raised | W1; text: Title; §1 "A flood-extent model trained on NISAR water labels" | critical | 5 |
| SC-1 | | R1 | corroborated | W8; text: §4.4 "To be filled from Z. Stoimchev's model once on GitHub" | critical | 5 |
| SC-1 | | R3 | corroborated | Criterion row "Significance & Impact (practical)": benefit "depends on §5.6, which is empty" | major [SEVERITY-SOURCE: letter-fallback] | 3 [CONFIDENCE-SOURCE: report-level] |
| SC-1 | | DA | corroborated | m5; text: Abstract "The flood-extent model and its independent test against EMSR935 are" | minor | 4 |
| SC-2 | decided-only estimates / missing-at-random | R1 | raised | W1; text: §5.1 "101 of 150 B points are unclear because the two optical looks disagree" | major | 5 |
| SC-2 | | EIC | corroborated | W2; text: Abstract "where only NISAR sees water, the referee agrees in" | major | 3 |
| SC-2 | | DA | corroborated | M4 (decided subset chosen by referee stability) | major | 5 |
| SC-3 | producer's bounds wrongly computed | R1 | raised | W2; table: Table 4, NISAR row bounds 0.44 / 0.47 | major | 5 |
| SC-3 | | EIC | corroborated | W2 and Q4 (0.52 outside its own bounds) | major | 3 |
| SC-3 | | DA | corroborated | M4; text: §5.1 "The bounds show how much this matters" | major | 5 |
| SC-4 | sensor contrast vs product contrast | EIC | raised | W3; text: §5.1 heading "NISAR sees water on 18 June that Sentinel-1 does not" | major | 4 |
| SC-4 | | R2 | corroborated | W1 suggestion (3): separate sensor from product with raw Sentinel-1 σ⁰ | major | 4 |
| SC-5 | U-Net is not independent C-band evidence | EIC | raised | W3 ("not an independent C-band baseline") | major | 4 |
| SC-5 | | DA | corroborated | m2; text: §4.3 "was trained on DSWx-S1 labels and is scored on the same points" | minor | 4 |
| SC-6 | strict-referee comparison not reported side by side | EIC | raised | W3 (strict producer's 0.43 vs 0.06 in `numbers.md`) | major | 4 |
| SC-6 | | R2 | corroborated | W3 suggestion: strict shares for all strata | major | 3 |
| SC-7 | Table 1 "This work" row credits undemonstrated capabilities | EIC | raised | W4; table: Table 1, row "This work" | major | 4 |
| SC-7 | | R2 | disputed | S5 and criterion row "Originality / positioning": "Table 1 is fair" | n/a (strength) | 4 |
| SC-8 | validated label ≠ model label; §7 overreach | EIC | raised | W5; text: §4.2 "The labels for the flood-extent model add a flooded-vegetation class" | major | 4 |
| SC-8 | | R2 | corroborated | W2 (do not claim reduced open-water bias until double-bounce class validated); W5 (rule placeholder) | major | 4 |
| SC-8 | | DA | corroborated | C1; text: §7 "These results support using NISAR water, together with Sentinel-1, as labels for a model of where water goes" | critical | 4 |
| SC-9 | June check is irrigation water, not flood | EIC | raised | W6; text: §3.1 "here is often farm water, not a flood" | minor | 4 |
| SC-9 | | DA | corroborated | C1 (condition change); Unexamined Premise | critical | 4 |
| SC-10 | Pego-Oliva 87 % has no chance baseline and no recall | R1 | raised | W7; text: §5.3 "of it lies inside the official flood outline" | major | 3 |
| SC-10 | | R2 | corroborated | W4 (give outline recall ≈ 184 of 877 ha) | major | 4 |
| SC-10 | | EIC | corroborated | W6 and Minor Issue §5.3 (share of outline captured) | minor | 4 |
| SC-10 | | DA | corroborated | m6; text: §5.3 "NISAR's new water is thus in the right place" | minor | 4 |
| SC-11 | side components dilute focus | EIC | raised | W7; text: §3.1 "used only for the land-class model" | minor | 4 |
| SC-12 | hackathon / team-process framing of the opening | EIC | raised | W8; text: §1 "Two of the authors were Erasmus students in Valencia in autumn 2026" | minor | 4 |
| SC-12 | | R3 | disputed (remedy) | W1 suggestion: keep the Erasmus anecdote | major | 4 |
| SC-13 | Appendices A and B are drafting tools | EIC | raised | W9; text: Appendix A "Self-review (five dimensions)" | minor | 4 |
| SC-14 | "pre-registered" wording covers v1, headline is v2 | R1 | raised | W3; text: §1 Contributions "An independent, pre-registered check of early NISAR water maps." | major | 4 |
| SC-14 | | EIC | corroborated | W10; text: Abstract "fixed in git before scoring and judged by an optical-only referee" | minor | 4 |
| SC-15 | missing official sources | R3 | raised | W8; text: §1 "[citation needed: official report]" | minor | 4 |
| SC-15 | | EIC | corroborated | Minor Issue §1 (citation needed) | minor [SEVERITY-SOURCE: letter-fallback] | 4 [CONFIDENCE-SOURCE: report-level] |
| SC-16 | EIC minor-issue bundle | EIC | raised | Minor Issues (Dasgupta description; GV footprint unused §3.3; §6.3 hypothesis label; map figures; Table 4 column order) | minor [SEVERITY-SOURCE: letter-fallback] | 4 [CONFIDENCE-SOURCE: report-level] |
| SC-17 | v1 should be the confirmatory result, with its interval | R1 | raised | W3 (v1 interval 0.69–0.96 absent; rule text not archived; proposer not named) | major | 4 |
| SC-17 | | DA | corroborated | m3 (`with_ci=False`) | minor | 5 |
| SC-18 | referee accuracy unknown; shares map's error | R1 | raised | W4; text: §4.3 "The referee never uses a radar, so the check is not circular." | major | 4 |
| SC-18 | | DA | corroborated | M1 (crop stage as common cause of NISAR-dark and referee-wet) | major | 3 |
| SC-19 | wet-rice area has no interval | R1 | raised | W5; text: §5.1 "of the rice was wet around 18 June" | minor | 5 |
| SC-20 | Pego-Oliva uses undisclosed Otsu threshold | R1 | raised | W6; absence: §4.2 and §5.3 threshold method | major | 4 |
| SC-20 | | R2 | corroborated | W4; text: §5.3 "when the threshold is moved by ±1 dB" | major | 4 |
| SC-20 | | DA | corroborated | M5; text: §4.2 "Open water is a pixel whose 5 × 5-filtered HH is below −15.0 dB" | major | 5 |
| SC-21 | §5.2 "therefore" overstates | R1 | raised | W9; text: §5.2 "The June disagreement is therefore specific to water beneath vegetation, not a calibration problem." | minor | 4 |
| SC-21 | | R2 | corroborated | W1 suggestion (5) and same anchor | major | 4 |
| SC-21 | | DA | corroborated | M1 (non sequitur) | major | 3 |
| SC-22a | threshold "confirmation" is weak evidence | R1 | raised | W10; text: §4.2 "NISAR's dark share of the rice and DSWx-S1's flooded share correlate at r = 0.978" | minor | 4 |
| SC-22a | | R2 | corroborated | W1 bullet 4 (058 A pairs exclude 18 June; picked by best mean gap) | major | 4 |
| SC-22a | | DA | corroborated | m1 (066 D r = 0.337; −18 dB fits better there) | minor | 5 |
| SC-22b | threshold said to be independent of C-band | R2 | raised | W9; text: §4.2 "does not depend on the C-band products it is compared with" | minor | 4 |
| SC-22b | | R1 | corroborated | W10 ("The yardstick is DSWx-S1") | minor | 4 |
| SC-23 | referee bracket mixes sensors and footprints | R1 | raised | W11; text: §4.3 "Sentinel-2, 23 June where Landsat is cloudy" | minor | 3 |
| SC-24 | degenerate percentile-bootstrap intervals | R1 | raised | W12; table: Table 4, CI "0.02–0.02", user's 1.00 | minor | 5 |
| SC-25 | no sample-size justification | R1 | raised | W13; absence: §4.3 sample-size rationale | minor | 4 |
| SC-26 | R1 minor-issue bundle | R1 | raised | Minor Issues (rounding 11,601; column headers; decided column in Table 3) | minor [SEVERITY-SOURCE: letter-fallback] | 4 [CONFIDENCE-SOURCE: report-level] |
| SC-27 | −15 dB cut sits inside the June rice distribution | R2 | raised | W1; numbers from `nisar_check.json` | major | 4 |
| SC-27 | | DA | corroborated | M2 (same-area random map ≈ 0.44); Ignored Alternative 2 | major | 5 |
| SC-28 | pass bar below referee base rate; B vs D contrast unreported | R2 | raised | W1 bullet 3 (D 46 of 68 = 0.68 vs B 0.94) | major | 4 |
| SC-28 | | DA | corroborated | M3; text: §4.3 "if its user's accuracy in stratum B is at least 0.7" | major | 5 |
| SC-29 | dark-HH class is not the flooded-vegetation mechanism | R2 | raised | W2; text: §6.1 "so labels built from NISAR are less biased towards open water" | major | 4 |
| SC-29 | | DA | corroborated | m4 | minor | 3 |
| SC-30 | strict result: rival explanations not discussed | R2 | raised | W3; text: §5.1 "Two explanations fit" | major | 3 |
| SC-30 | | DA | corroborated | M1; Ignored Alternatives 1 and 3 | major | 3 |
| SC-31 | flooded-vegetation rule not reproducible, ambiguous in rice | R2 | raised | W5; text: §4.2 "where HH rises by about 3 dB between passes while HV stays flat (double bounce)" | major | 4 |
| SC-32 | L-band rice and flooded-vegetation literature absent | R2 | raised | W6; absence: §2 beyond Hess et al. 1990 | major | 4 |
| SC-33 | "soaked mud darkens radar" imprecise | R2 | raised | W7; text: §6.2 "Mud can trip both the optical flooding index and NISAR's dark threshold" | minor | 4 |
| SC-34 | unsupported C-band statement | R2 | raised | W8; text: §2 "C-band missions such as Sentinel-1 provide frequent, free data but see water under young crops less reliably." | minor | 4 |
| SC-35 | SAR processing details missing | R2 | raised | W10; text: §3.2 "after a 5 × 5 speckle filter in linear power" | minor | 4 |
| SC-36 | R2 minor-issue bundle | R2 | raised | Minor Issues (abstract "mapped … of water"; HV attribution; γ⁰/σ⁰; §5.3 fifth of outline) | minor [SEVERITY-SOURCE: letter-fallback] | 4 [CONFIDENCE-SOURCE: report-level] |
| SC-37 | promised user (resident) is not the user served | R3 | raised | W1; text: §1 "Neither answers the question a resident actually has" | major | 4 |
| SC-37 | | DA | corroborated | Missing Stakeholders (residents of built-up areas) | n/a | n/a |
| SC-38 | binary "likely flooded" layer invites "unshaded = safe" | R3 | raised | W2; text: §4.4 "probability of water given a rain scenario; shown in the app as" | major | 4 |
| SC-39 | "existing rain alert" is a new traffic light | R3 | raised | W3; text: §4.6 "a traffic light per site from the largest 3-day rain total" | major | 4 |
| SC-40 | Spanish warning chain / impact-based warning literature absent | R3 | raised | W4; absence: §2 and References | minor | 3 |
| SC-41 | F1 treats a miss like a false alarm | R3 | raised | W5; text: §4.5 "The model is said to add value if its F1 beats all three baselines" | minor | 3 |
| SC-42 | farm water may fill the map | R3 | raised | W6; text: §3.1 "here is often farm water, not a flood" | minor | 3 |
| SC-43 | map hidden when the coarse alert stays low | R3 | raised | W7; text: §5.5 "amber two to three days ahead, never red" | minor | 3 |
| SC-44 | R3 minor-issue bundle | R3 | raised | Minor Issues (colour names; per-limit user clause in §6.2; ethics line) | minor [SEVERITY-SOURCE: letter-fallback] | 3 [CONFIDENCE-SOURCE: report-level] |
| SC-45 | training window holds no rain-driven flood | DA | raised | C2; text: §4.6 "holds only 4 new-flood events in 504 passes"; §6.3 "With each storm the model sees how the footprint grows with rain" | critical | 4 |

Step 1c surface-form parity: applied. No sub-claim was down-rated for informal wording or up-rated for technical precision. The seats' own recomputations (bounds 0.22–0.71, area interval, random baseline 0.44, 066 D r = 0.337) were treated as reviewer claims to be re-run by the authors, not as verified values.

### Consensus Analysis

#### Points of Agreement (Consensus)

Strength consensus:
- **[CONSENSUS-4] Adverse results are reported in the main text.** EIC S2, R1 S3, R2 S1, R3 S3 all credit the strict-referee failure, the missed DANA peak and the alert never reaching red being reported in Results.
- **[CONSENSUS-3] The flood-model test is written before the model exists, with strong baselines and a different scorer.** EIC S5, R1 S5, R3 S4; R2 silent.
- **Recommendation consensus**: all four scoring seats recommend Major Revision.

Weakness consensus:
- **[CONSENSUS-3] SC-1: the titular flood-extent model is absent, so the title's claim cannot be judged.** EIC W1 (critical), R1 W8 (critical), R3 criterion row (practical benefit depends on the empty §5.6); R2 silent. DA m5 agrees. All agree on the remedy: deliver §4.4/§5.6 and run §4.5 as written, or re-title and re-frame as a label-validation study.
- **[CONSENSUS-3] SC-10: the Pego-Oliva 87 % inside-share needs a chance baseline and the recall of the outline.** R1 W7, R2 W4, EIC W6 and Minor Issue; R3 silent. DA m6 agrees, and DA's rough area estimate suggests the baseline will favour the paper.

Corroborated findings (2 of 4, no conflict): SC-2, SC-3, SC-4, SC-6, SC-8, SC-14, SC-15, SC-20, SC-21, SC-22a, SC-22b.
Single-reviewer findings (1 of 4, no conflict): all other sub-claims except the two SPLITs below and SC-45 (DA only). Each is retained and judged against its anchored evidence.

Severity differences that are not conflicts. Operational rule used here: a severity difference is treated as `disputed` only when a seat argues the problem is not real, proposes an incompatible remedy, or argues its own lower severity against another seat. One-step differences that arise because a point sits inside a larger bundle, with compatible remedies, are recorded but not arbitrated.
- SC-14: R1 major, EIC minor. EIC explicitly defers the substance to the methodology seat ("The substance of whether the change matters is the methodology seat's question"). Remedy compatible. Obligation set from R1's D3 warn.
- SC-21: R1 minor, R2 major (inside R2 W1). Same remedy (reword "therefore").
- SC-10: R1 and R2 major, EIC minor (inside EIC W6). Same remedy.
- SC-22a: R1 and DA minor, R2 major (bullet inside R2 W1). Same remedy.

#### Points of Disagreement

**Disagreement 1: Is Table 1 fair? (SC-7)**
- **EIC view**: Table 1 credits "This work" with flooded-vegetation labels, coverage of small coastal wetlands and a tie to a rain warning, none of which is demonstrated; it compares planned capabilities with operational ones (W4, major).
- **R2 view**: Table 1 places the work fairly against the operational systems, without overclaiming (S5; criterion row "Originality / positioning": MEETS).
- **Disagreement type**: Existence disagreement.
- **Editor's Resolution**: EIC upheld for the "This work" row; R2 upheld for the rows describing existing systems. The "This work" row must mark planned features as planned (or Table 1 is replaced by a table of water-label sources).
- **Resolution Rationale**: Evidence first. The manuscript's own text marks the flooded-vegetation rule as **[PLACEHOLDER: final label rules and per-pass counts]** (§4.2) and the model as a placeholder (§4.4); no section tests coverage of small wetlands. R2's own W2 and W5 state that the flooded-vegetation class is not yet defined or validated, which supports EIC on exactly these cells. Expertise: positioning against operational products is the Journal-Fit seat's remit (D6). R2's fairness judgement is not contradicted for the five existing-system rows, and EIC S4 agrees that the prose positioning in §6.1 is fair.

**Disagreement 2: Should the opening keep the Erasmus anecdote? (SC-12)**
- **EIC view**: the anecdote, GitHub Discussion references, named section owners and "Our innovation" make the paper read as a team report; open with the Valencia flood problem and the label gap (W8, minor).
- **R3 view**: keep the Erasmus anecdote, but say plainly that the method as tested speaks to slow-draining wetlands and fields, not to residents or urban flash floods (W1 suggestion).
- **Disagreement type**: Direction disagreement (incompatible remedy for the same sentence).
- **Editor's Resolution**: Left to the authors' judgement (author autonomy). Both seats agree on what matters: the opening must not imply that the method answers the 2024 resident question. That agreed part is required under REV-37 (R20). Removing Discussion references, owner notes and "Our innovation" from the main text is consider-level (REV-12).
- **Resolution Rationale**: Neither side's evidence decides it; it is a convention and audience question. The author has stated that the immediate audience is a hackathon jury, for which a short personal opening is common; a journal version would follow EIC's field convention.

**Noted perspective difference (no sub-claim conflict)**: EIC rates Originality PARTLY_MEETS (the titular contribution is absent), R2 rates Originality / positioning MEETS (the first sample-based check of NISAR water over Spain is a real, narrow contribution). Both agree the label check is original; the difference is fully captured by SC-1 and needs no separate arbitration.

### Devil's Advocate CRITICAL adjudication

**C1 — The main conclusion does not follow from what was checked.**
- **DA's argument**: The §7 conclusion moves from a −15 dB dark-HH map agreeing with an optical wetness index on one dry-season date in irrigated rice to "NISAR water is a suitable label for where flood water goes after rain". The object changes (the model labels add a flooded-vegetation class and a Sentinel-1 merge whose rules are a placeholder), the condition changes (irrigation water vs rain-driven flooding), and the meaning changes (the strict test says the extra water is not open water). Anchor: text: §7 "These results support using NISAR water, together with Sentinel-1, as labels for a model of where water goes"; §4.2 "final label rules and per-pass counts". Confidence 4.
- **Corroboration**: EIC W5 (same gap, same §7 sentence, major); R2 W2 and W5 (dark-HH is not the flooded-vegetation signal; the flooded-vegetation rule is unvalidated); EIC W6 (June is farm water) supports the condition change; R3 W6 (farm water).
- **Journal-Fit Reviewer's assessment**: EIC W5 independently makes the core point and calls the link between "we checked the labels" and "these labels are fit for the model" the bridge of the whole argument. Supports the DA.
- **Editor's adjudication**: **VALIDATED.** The manuscript's own §4.2 placeholder and §5.1 strict-referee result confirm each step of the DA's argument. Repairable.
- **Required author response**: REV-08 (R6), with REV-09 (S3), REV-29 (R16), REV-31 (R18).

**C2 — The NISAR training window contains no rain-driven flood to learn from.**
- **DA's argument**: The model trains on NISAR passes from 17 June to the cut-off, with the DANA held out. All four training new-flood events in the repository's event table (2025-05-17, 2025-10-14, 2025-11-26, 2026-01-07) predate NISAR's calibrated data; the largest storm inside the window (124.6 mm, 4 October, Albufera) has negative excess area (−72 ha) while NISAR rice water rises from 5.8 to 31.0 % because farmers re-flood the paddies. The only flood the model could learn from is the test event. Anchor: text: §4.6 "holds only 4 new-flood events in 504 passes"; §6.3 "With each storm the model sees how the footprint grows with rain". Confidence 4. DA's own caveat: the event table's flood labels come from Sentinel-1 DSWx, not NISAR.
- **Corroboration**: No scoring seat raised this point directly. Related: EIC W6 (flood evidence is thin), EIC criterion row Significance (significance for flood forecasting is projected, not shown), R3 W6 (farm water in labels), DA Unexamined Premise.
- **Journal-Fit Reviewer's assessment**: The EIC card does not address C2.
- **Editor's adjudication**: **VALIDATED.** Checked against the manuscript: §4.4 trains on passes from 17 June excluding the DANA window; §6.2 states "DANA "Adam" is the only large flood in the period"; Table 2 places calibrated NISAR data from 17 June 2026. To confirm the DA's quoted dates, the editor opened `data/prediction/flood/events.csv` read-only: the `new_flood = 1` rows in the train split are exactly albufera 2025-05-17, albufera 2026-01-07, pego_oliva 2025-10-14 and pego_oliva 2025-11-26; the largest train-split storm after 17 June 2026 is albufera 2026-10-04 (124.6 mm, excess −72.06 ha). This check adds no new review comment. The exact NISAR-side count is not reported in the manuscript and must be given by the authors. Repairable by disclosure and re-framing, or by changing the label source.
- **Required author response**: REV-45 (R22). If the teammate's model lands before the deadline, the §4.5 result should still be reported exactly as pre-registered, and it must be read with this limit stated: a pass on the DANA would not show that the model learned rain-to-extent from storms in the NISAR window.

DA MAJOR and MINOR findings: all are carried into the roadmap (M1 → REV-18, REV-21, REV-30; M2 → REV-27; M3 → REV-28; M4 → REV-02, REV-03; M5 → REV-20; m1 → REV-22; m2 → REV-05; m3 → REV-17; m4 → REV-29; m5 → REV-01; m6 → REV-10). DA's ignored alternatives 4–6 (Sentinel-1 as teacher, archive L-band, rain-volume HAND fill) are options inside REV-45 and are not separately required. Note: the DA card gives the EMSR935 outline as "about 887 ha"; the manuscript states 877 ha (§5.3), which this package uses.

No DA CRITICAL was rejected, so no rejection rationale line is needed.

### Decision Rationale

All four scoring seats recommend Major Revision, and the contract arithmetic agrees: four mandatory dimensions carry a repairable block (F2). No seat found a fatal flaw, so Reject is not supported: every seat says the finished validation work is careful, traceable and unusually honest (CONSENSUS-4 on adverse results reported in the main text; R1 reproduced the stratified estimators from the released labels).

The decision rests on four repairable problems. First, the paper's titular contribution, a learned flood-extent model, does not exist in this draft (CONSENSUS-3, critical; EIC W1, R1 W8). Second, the conclusion that NISAR water is fit as a model label goes beyond what was checked: the validated layer is not the planned label, the check is on irrigation water, and the training window holds no rain-driven flood (DA C1 and C2, both validated; EIC W5). Third, the headline 18 June numbers are reported more firmly than the evidence allows: the producer's bounds are wrongly computed, the decided-only estimates assume that two-thirds of the key stratum is missing at random, the wet area has no interval, and "pre-registered" covers v1 while the headline shows v2 (R1 W1–W5, EIC W2, W10, DA M4). Fourth, the reading "NISAR sees water Sentinel-1 misses" is not separated from where the −15 dB threshold cuts the June rice backscatter, from the DSWx-S1 product rules, or from rival explanations of the strict result (R2 W1–W3, EIC W3, DA M1–M3).

A stricter decision is not warranted because each block names a narrower contribution that the existing evidence supports. A lighter decision is not possible because the title, abstract and conclusion must change, and several numbers must be recomputed. Many required items are text changes or recomputations from files the authors already hold; only the model path and some optional checks need new work.

### Blocking Issues (0–3, immutable source order)

The three critical-severity items. The other blocked dimensions (D1 via R2, R3, R11; D2 via R14, R16, R17) are cleared by required items listed below.

| Transport ref | Blocking issue | Source reviewer(s) | Evidence anchor | Resolving roadmap item |
|---|---|---|---|---|
| R1 | The titular flood-extent model is absent; title, abstract, contributions and conclusion promise it | EIC, R1, R3 (+DA) | text: Title "Learning flood extent in Valencia from the first months of NISAR L-band data"; text: §4.4 "To be filled from Z. Stoimchev's model once on GitHub" | REV-01 |
| R6 | The conclusion endorses labels that were not the ones checked, on water that was not flood water | EIC, R2, DA (C1) | text: §7 "These results support using NISAR water, together with Sentinel-1, as labels for a model of where water goes" | REV-08 |
| R22 | The training window contains no rain-driven flood, so "learning where water goes" cannot be shown from it | DA (C2) | text: §6.3 "With each storm the model sees how the footprint grows with rain" | REV-45 |

---

## Part 2: Revision Roadmap

Machine artifact: the closed `revision-roadmap/1.0` JSON was not emitted. It requires `base_draft_sha256`, a `block_manifest_sha256` and block ids (`B0001…`) from a bound block manifest; no block manifest exists in this install and `scripts/revision_roadmap.py` is not installed. The tables below are the roadmap record; `proposed_targets` are given as section locators only. Consensus labels follow the protocol (CONSENSUS-3, SPLIT, corroborated 2/4, single 1/4, DA-CRITICAL); the schema enum has no "corroborated" value.

**Author-context tag** (last column). Added at the author's request because of the jury deadline. It is a fixed mapping from the typed cost scope, not a time estimate, not a work order and not a rank: **T** = text change only; **F** = recompute from files already in the repository; **N** = needs new data or the flood-extent model. Two tags mean two allowed paths.

### Required Revisions (Must Fix)

| Transport ref | Item | Revision Item | Sub-Claim(s) | Severity | Evidence Anchor | Confidence | Source | Obligation class | Cost scope | Bounded consequence | Author-context tag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | REV-01 | Deliver the model and run §4.5 as written, or re-title and re-frame as a label-validation study | SC-1 | critical | text: Title; text: §4.4 "To be filled from Z. Stoimchev's model once on GitHub" | 5 — core editorial (EIC); 5 (R1) | EIC, R1, R3 (+DA m5) | must_fix | section: Title, Abstract, §1, Fig. 1, §6.1, §7 (path b) / new_data: §4.4, §5.6 (path a) | claim_scope_unsupported → claim: title | T (b) / N (a) |
| R2 | REV-02 | Name the missing-at-random assumption at each headline number; give decided n; add tipping-point analysis and the unclear = wet scenario | SC-2 | major | text: §5.1 "101 of 150 B points are unclear because the two optical looks disagree" | 5 — core expertise (R1); 3 (EIC) | R1, EIC (+DA M4) | must_fix | re_analysis: Abstract, §5.1, Table 4 | evidence_gap_remains → claim: Abstract headline estimates | F (optional relabel subsample: N) |
| R3 | REV-03 | Replace producer's "bounds" with true worst-case bounds and explain why a ratio can fall outside fixed scenarios | SC-3 | major | table: Table 4, NISAR row — producer's 0.52, bounds 0.44 / 0.47 | 5 — recomputed (R1); 3 (EIC) | R1, EIC (+DA M4) | must_fix | re_analysis: Table 4, §5.1 | reporting_requirement_unmet → table: Table 4 | F |
| R4 | REV-04 | Re-word the sensor contrast as a contrast with the DSWx-S1 product; move the §6.2 caveat into §5.1 | SC-4 | major | text: §5.1 heading "NISAR sees water on 18 June that Sentinel-1 does not" | 4 — SAR products (EIC); 4 (R2) | EIC, R2 | must_fix | sentence: §5.1 heading, Abstract, §1 Contribution 1, §6.1, §7 (optional new_data: raw Sentinel-1 threshold baseline) | claim_scope_unsupported → claim: §5.1 heading | T (+N optional) |
| R5 | REV-07 | Mark planned features in Table 1's "This work" row as planned, or replace Table 1 with a water-label-source table | SC-7 | major | table: Table 1 — row "This work" | 4 — operational products (EIC) | EIC (SPLIT with R2, arbitrated) | must_fix | sentence: Table 1 | claim_scope_unsupported → table: Table 1 | T |
| R6 | REV-08 | Limit the §7 conclusion to the −15 dB layer that was checked, or score the final label product on the 513 points and the DANA | SC-8 | major (EIC, R2); critical (DA C1) | text: §7 "These results support using NISAR water, together with Sentinel-1, as labels for a model of where water goes" | 4 — editorial and SAR-label (EIC); 4 (R2); 4 (DA) | EIC, R2, DA-CRITICAL C1 | must_fix | sentence: §7, §6.1 / new_data: final label rules (§4.2) | claim_scope_unsupported → claim: §7 conclusion | T / N |
| R7 | REV-10 | Pego-Oliva: add the chance baseline (outline share of analysed area), the recall of the outline, and DSWx-S1's inside-share; call it a map-to-map agreement check | SC-10 | major | text: §5.3 "of it lies inside the official flood outline" | 3 — baseline not computable from released files (R1); 4 (R2) | R1, R2, EIC (+DA m6) | must_fix | re_analysis: §5.3, Abstract, §1 Contribution 2 | evidence_gap_remains → claim: §5.3 87 % | F |
| R8 | REV-14 | Say exactly what was fixed before scoring: the points and the pass rule; the referee's after-image was revised once after a first run | SC-14 | major (R1); minor (EIC) | text: §1 Contributions "An independent, pre-registered check of early NISAR water maps." | 4 — git timeline (R1); 4 (EIC) | R1, EIC | must_fix | sentence: Abstract, §1 Contribution 1, §7 | claim_scope_unsupported → claim: pre-registration | T |
| R9 | REV-17 | Report v1 as the confirmatory result with its interval; call v2 a post-hoc refinement with its reason; archive the Discussion #25 rule text with a timestamp; say who proposed v2 | SC-17 | major | text: §4.3 "after a team review, the after-image was changed to the closest clear look" | 4 — git timeline; Discussion text not seen (R1) | R1 (+DA m3) | must_fix | re_analysis: §4.3, §5.1, Table 4 | reader_traceability_reduced → claim: pre-registered verdict | F + T |
| R10 | REV-18 | Call the referee data-independent (not independent); discuss shared error with NISAR (wet soil, crop stage); optionally check it on a small better-quality set or match B and D on 8 June EVI | SC-18 | major | text: §4.3 "The referee never uses a radar, so the check is not circular." | 4 — response-design principles (R1) | R1 (+DA M1) | must_fix | sentence: §4.3, §6.2 (optional re_analysis: EVI matching; optional new_data: VHR or field check) | interpretive_ambiguity_remains → claim: referee independence | T (+F, N optional) |
| R11 | REV-19 | Give the wet-rice area an interval and round it; note the v1 value; add the wet share to the bootstrap | SC-19 | minor | text: §5.1 "of the rice was wet around 18 June, consistent with the flooded period of the rice calendar" | 5 — recomputed (R1) | R1 | must_fix | re_analysis: §5.1 | reporting_requirement_unmet → claim: §5.1 wet area | F |
| R12 | REV-20 | State that Pego-Oliva used per-scene Otsu (−11.85 / −12.03 dB), not −15 dB; re-run at −15 dB and report both, or explain the choice | SC-20 | major | absence: §4.2 and §5.3 — threshold method and values for the Pego-Oliva new-water map; checked §4.2, §5.3, Table 2, §6.2, Data and code availability | 4 — read from result file (R1); 4 (R2); 5 (DA) | R1, R2 (+DA M5) | must_fix | sentence: §4.2, §5.3; re_analysis: §5.3 | method_reproducibility_unresolved → claim: §1 Contribution 2 | T + F |
| R13 | REV-21 | Change §5.2 "therefore" to "is consistent with"; say autumn agreement rules out a radiometric offset only; add the same-day two-track agreement on 18 June | SC-21 | minor (R1); major (R2) | text: §5.2 "The June disagreement is therefore specific to water beneath vegetation, not a calibration problem." | 4 — inference logic (R1); 4 (R2) | R1, R2 (+DA M1) | must_fix | sentence: §5.2 | claim_scope_unsupported → section: §5.2 | T |
| R14 | REV-27 | Show how NISAR's accuracy and area depend on the threshold: sweep −18 to −12 dB on the 513 points (main and strict referee), per-stratum HH/HV histograms, same-area random baseline | SC-27 | major | text: §5.2 "The June disagreement is therefore specific to water beneath vegetation, not a calibration problem."; dataset: `nisar_check.json` dark shares | 4 — SAR thresholding (R2); 5 (DA) | R2 (+DA M2) | must_fix | re_analysis: §5.1, Table 4, new figure | evidence_gap_remains → claim: producer's 0.52 as a sensor property | F |
| R15 | REV-28 | Report the B vs D contrast (0.94 vs 0.68; strict 0.10 vs 0.12) and state that the 0.7 bar sits below the referee's base rate (0.79), so the rule cannot tell NISAR from over-mapping | SC-28 | major | text: §4.3 "if its user's accuracy in stratum B is at least 0.7" | 4 (R2); 5 — recomputed (DA) | R2 (+DA M3) | must_fix | sentence: §4.3, §5.1, Abstract | claim_scope_unsupported → claim: "passes a rule fixed in advance" | T |
| R16 | REV-29 | Describe two mechanisms separately (dark HH = open water or water among sparse plants; bright HH + high HH/HV = double bounce); place the June result in the first; remove "less biased towards open water" until the double-bounce class is validated | SC-29 | major | text: §6.1 "so labels built from NISAR are less biased towards open water" | 4 — core expertise (R2) | R2 (+DA m4) | must_fix | section: §2, §4.2, §5.1, §6.1 | claim_scope_unsupported → claim: §6.1 | T |
| R17 | REV-30 | Interpret the strict result fully: report strict shares for all strata, list rival explanations (threshold continuum, optical loss under canopy, drainage, smooth puddled soil, crop stage) and what evidence would separate them; re-phrase the practical reading | SC-30 | major | text: §5.1 "Two explanations fit: water beneath young rice plants (which L-band can reach and the optical open-water index cannot), or soaked mud, which darkens radar" | 3 — adjacent on optical index (R2); 3 (DA) | R2 (+DA M1) | must_fix | section: §5.1, §6.2 (optional re_analysis: HV and HH/HV per stratum) | interpretive_ambiguity_remains → claim: §5.1 practical reading | T (+F optional) |
| R18 | REV-31 | Fully specify the flooded-vegetation rule and validate it, or remove it from the claimed label definition (§4.2, Fig. 1, Table 1) and state it as future work | SC-31 | major | text: §4.2 "where HH rises by about 3 dB between passes while HV stays flat (double bounce)" | 4 — core expertise (R2) | R2 | must_fix | sentence: §4.2, Fig. 1, Table 1 / new_data: rule validation | method_reproducibility_unresolved → claim: flooded-vegetation labels | T / N |
| R19 | REV-32 | Add a short paragraph on L-band and multi-frequency rice backscatter and on flooded-vegetation detection; state the contribution as the measured gap to the operational product | SC-32 | major | absence: §2 — L-band rice backscatter and flooded-vegetation detection literature beyond Hess et al. 1990; checked §2, §4.2, §5.1, §6.1, §6.2, References | 4 — core literature (R2) | R2 | must_fix | section: §2, References | evidence_gap_remains → section: §2 | T |
| R20 | REV-37 | Name the users the evidence serves (civil protection, wetland managers, water boards); state that urban flash floods like 2024 are out of scope; move the resident goal to future work | SC-37 | major | text: §1 "Neither answers the question a resident actually has" | 4 — warning audiences (R3) | R3 (+DA stakeholders) | must_fix | section: Abstract, §1, §6.2 | claim_scope_unsupported → claim: §1 opening | T |
| R21 | REV-39 | Make the abstract match §4.6: either drive the map from the official AEMET level, or rename the team's signal so it cannot be confused with AEMET colours; state that official warnings take precedence | SC-39 | major | text: §4.6 "a traffic light per site from the largest 3-day rain total" | 4 — colour-coded warnings (R3) | R3 | must_fix | sentence: Abstract, §1, §4.6 | interpretive_ambiguity_remains → claim: Abstract "existing rain alert" | T |
| R22 | REV-45 | State that the NISAR training window holds no rain-driven new-flood event at either site (give the NISAR-side count); remove or condition the §6.3 storm-learning sentence; choose: label validation now and model later, Sentinel-1 as teacher with NISAR as check, or archive L-band | SC-45 | critical | text: §4.6 "holds only 4 new-flood events in 504 passes"; text: §6.3 "With each storm the model sees how the footprint grows with rain" | 4 — computed from repo events table (DA) | DA-CRITICAL C2 | must_fix | sentence: §4.4, §6.2, §6.3 / new_data: alternative training design | claim_scope_unsupported → claim: §6.3 | T / N |

### Required Item Details

> **Ordinal contract (#576/#670):** `R<n>` is a transport reference, never a work rank. Numbering follows the immutable roadmap source order filtered to `obligation_class == must_fix`. Reviewer recomputed values quoted below are checks for the authors to reproduce, not verified numbers.

**R1: The titular model is absent**
- **Problem**: Title, abstract approach, §1 approach and Contribution 3, Fig. 1, Table 1 and §6.1 present a model that learns where water goes; §4.4 is a plan and §5.6 is empty.
- **Source**: EIC W1 (critical); R1 W8 (critical); R3 criterion row Significance (practical); DA m5.
- **Requirement**: Path (a): fill §4.4 and §5.6 and run the §4.5 test as written, reporting the verdict whichever way it falls. Path (b): re-title and re-frame as an independent check of early NISAR L-band water against DSWx-S1 over the Albufera and Pego-Oliva; move the flood-extent idea to an "intended use" paragraph; mark Contribution 3 and Fig. 1's model part as future work.
- **Acceptance criteria**: Either §5.6 reports the pre-registered §4.5 verdict with all three baselines, or no title, abstract, contribution or conclusion sentence claims a learned flood-extent result.

**R2: Decided-only estimates and the missing-at-random assumption**
- **Problem**: Every headline estimate uses only decided points (49 of 150 in B, 68 of 150 in D) and silently assumes unclear points are wet at the same rate; the unclear points share one systematic pattern.
- **Source**: R1 W1; EIC W2; DA M4.
- **Requirement**: State the assumption next to each headline number and give the decided n in the abstract; add a tipping-point analysis (R1: the rule holds on all 150 B points only if about 59 of 101 unclear points are wet); report the unclear = wet scenario. Optional: label a random subsample of unclear points with a better source.
- **Acceptance criteria**: Abstract and §5.1 show decided n and the assumption, and a tipping-point value for stratum B is reported from the authors' own computation.

**R3: Producer's bounds**
- **Problem**: Table 4's producer's "bounds" (0.44 / 0.47) are not bounds; the 0.52 estimate lies outside them.
- **Source**: R1 W2; EIC W2 and Q4; DA M4.
- **Requirement**: Replace with stratum-level worst-case bounds for NISAR and DSWx-S1 and point-level bounds for the U-Net (R1 and DA recomputed about 0.22–0.71 for NISAR and 0.01–0.05 for DSWx-S1); keep the two fixed scenarios only as labelled cases; explain the ratio behaviour; say the bootstrap CI is sampling error only; state that the ranking survives the correct bounds if the authors' numbers confirm it.
- **Acceptance criteria**: Table 4 reports bounds that contain the point estimate, computed by the authors from `reference.csv`, with the method stated in the caption.

**R4: Sensor contrast vs product contrast**
- **Problem**: 0.52 vs 0.02 compares NISAR plus a threshold with DSWx-S1, a product that issues inundated vegetation only on wetland land cover; headings and contributions read it as C-band vs L-band.
- **Source**: EIC W3; R2 W1 (suggestion 3).
- **Requirement**: Say "the DSWx-S1 product" in the §5.1 heading, abstract, Contribution 1, §6.1 and §7; move the §6.2 product caveat into §5.1. Optional: a like-for-like raw Sentinel-1 VV/VH threshold on the same points.
- **Acceptance criteria**: No sentence attributes the 0.02 to C-band physics without naming the DSWx-S1 product rules.

**R5: Table 1 "This work" row**
- **Problem**: The row credits flooded-vegetation labels, small-wetland coverage and a tie to a rain warning that are not demonstrated.
- **Source**: EIC W4 (SPLIT with R2 S5; resolved for EIC on this row).
- **Requirement**: Mark planned features as planned (for example, planned; not yet tested), or replace Table 1 with a table of water-label sources and what each sees under vegetation.
- **Acceptance criteria**: Every "This work" cell is either demonstrated in the Results or explicitly marked as planned.

**R6: Conclusion endorses labels that were not checked**
- **Problem**: §7 endorses NISAR water plus Sentinel-1 as model labels; the validated layer is −15 dB dark HH on one irrigation date, while the model labels add an unvalidated flooded-vegetation class and a Sentinel-1 merge.
- **Source**: EIC W5; R2 W2, W5; DA C1 (validated).
- **Requirement**: Limit the §7 and §6.1 conclusions to the −15 dB open-water / wet-ground layer that was checked, under the stated conditions; or score the final label product on the same 513 points and the DANA.
- **Acceptance criteria**: The conclusion names the exact layer and condition that were checked, or reports a score for the final label product.

**R7: Pego-Oliva chance baseline and recall**
- **Problem**: The 87 % inside-share has no chance baseline; recall (about 184 of 877 ha, about 21 %) is only implicit; no comparable DSWx-S1 figure.
- **Source**: R1 W7; R2 W4; EIC W6 and Minor Issue; DA m6.
- **Requirement**: Report the outline's share of the analysed area as the baseline, the recall, and DSWx-S1's inside-share; call the analysis a map-to-map agreement check.
- **Acceptance criteria**: §5.3 reports inside-share, chance baseline and recall side by side for NISAR and DSWx-S1.

**R8: Pre-registration wording**
- **Problem**: Abstract, Contribution 1 and §7 present the v2 numbers as the result of a pre-registered check, but the referee's after-image changed after v1 was scored.
- **Source**: R1 W3; EIC W10.
- **Requirement**: Say that the points and pass rule were fixed before scoring and that the referee's after-image was revised once after a first run, with both versions pointing the same way.
- **Acceptance criteria**: Every use of "pre-registered" or "fixed in advance" states what was fixed and mentions the one referee revision.

**R9: v1 as the confirmatory result**
- **Problem**: Only v1 was fixed before any referee output was seen; its interval is not in the paper (v1 was re-scored without intervals); the rule text is on an editable Discussion; the v2 proposer built two of the judged products.
- **Source**: R1 W3; DA m3.
- **Requirement**: Re-compute and report v1 with its interval next to v2 (R1 read 0.69–0.96 from commit `54fdc99`); call v2 a post-hoc refinement and give the reason; quote or archive the Discussion #25 rule text with a timestamp or commit hash; say who proposed v2.
- **Acceptance criteria**: Table 4 or §5.1 shows v1 with its interval, and the rule text is archived with a fixed identifier.

**R10: Referee independence and shared error**
- **Problem**: The referee is independent of radar data but its accuracy is unknown, and its main error (wet soil, crop stage) is shared with NISAR; the verdict flips under the strict variant.
- **Source**: R1 W4; DA M1.
- **Requirement**: Write data-independent instead of independent and say what this does and does not rule out; discuss correlated error as a threat to user's accuracy in B. Optional: check the referee on a small set with very-high-resolution imagery or irrigation records; match B and D on 8 June EVI or NDVI.
- **Acceptance criteria**: §4.3 no longer claims the check is free of shared error, and §6.2 discusses correlated error between map and referee.

**R11: Wet-rice area interval**
- **Problem**: 11,601 ha is given with no interval and five significant figures; its sensitivity to the referee is larger than its sampling error.
- **Source**: R1 W5.
- **Requirement**: Report a rounded value with a stratified-bootstrap interval and the all-dry / all-wet range (R1's recomputation: about 10,600–12,600 ha; 4,600–13,300 ha); note the v1 value; add the wet share to the bootstrap in `june18.py`.
- **Acceptance criteria**: §5.1 gives the area with an interval and the unclear-point range, from the authors' own code.

**R12: Pego-Oliva threshold**
- **Problem**: §4.2 defines water as HH below −15 dB, but the Pego-Oliva map uses per-scene Otsu (−11.85 / −12.03 dB); the ±1 dB range in §5.3 is around Otsu. The two checks do not test the same detector.
- **Source**: R1 W6; R2 W4; DA M5.
- **Requirement**: State the method and thresholds; re-run the Pego-Oliva check at −15 dB and report both, or explain why the labels will use Otsu.
- **Acceptance criteria**: §5.3 names the threshold used and reports the result at −15 dB.

**R13: §5.2 "therefore"**
- **Problem**: Autumn agreement rules out a radiometric offset, not wet soil or a threshold effect; "therefore specific to water beneath vegetation" overstates.
- **Source**: R1 W9; R2 W1 (suggestions 4–5); DA M1.
- **Requirement**: Write "is consistent with"; say again that wet mud remains possible; add the 18 June two-track agreement (43.7 % vs 46.9 %) as evidence against a look-direction artefact.
- **Acceptance criteria**: §5.2 claims only what autumn agreement can rule out.

**R14: Threshold dependence of the June numbers**
- **Problem**: Median rice HH on 18 June is about −14.4 / −14.8 dB, right at the −15 dB cut; one dB moves the NISAR area by about a quarter; a same-area random map would score about 0.44 producer's accuracy.
- **Source**: R2 W1; DA M2 and Ignored Alternative 2.
- **Requirement**: Report user's and producer's accuracy against threshold (−18 to −12 dB) on the fixed 513 points under both referees; show per-stratum HH and HV histograms; report a same-area random baseline; say that 0.52 and 6,387 ha belong to the chosen cut.
- **Acceptance criteria**: A threshold-sweep table or figure and the random baseline appear in §5.1, computed by the authors.

**R15: The pass rule and the B vs D contrast**
- **Problem**: The 0.7 bar sits below the referee's base rate in the rice (0.79), so a map calling all rice water would pass; the contrast that tells skill from coverage (B 0.94 vs D 0.68; strict 0.10 vs 0.12) is not reported.
- **Source**: R2 W1 (bullet 3); DA M3.
- **Requirement**: Report the B vs D contrast under both referees and state the base-rate limit of the rule next to "passed".
- **Acceptance criteria**: §5.1 and the abstract no longer present the pass as evidence of skill without the B vs D contrast and the base rate.

**R16: Two radar mechanisms**
- **Problem**: §2 explains double bounce (bright HH), but the −15 dB rule keeps dark pixels; the dark class shrinks from 43.7 % (18 June) to 0.3 % (24 July) while paddies stay flooded.
- **Source**: R2 W2; DA m4.
- **Requirement**: State the two mechanisms separately in §2 and §4.2; describe the June result as the dark, sparse-plant mechanism; drop "less biased towards open water" until the double-bounce class is defined and validated; cite growth-stage studies.
- **Acceptance criteria**: No sentence claims the checked labels capture flooded vegetation by double bounce.

**R17: Strict-referee interpretation**
- **Problem**: Under the strict referee, NISAR-only points carry no more open-water signal than the rice background; the paper names two explanations and stops.
- **Source**: R2 W3; DA M1, Ignored Alternatives 1 and 3.
- **Requirement**: Report strict-referee shares for all strata with small numbers stated; list the rival explanations and the evidence that could separate them; re-phrase the practical reading as pixels in wet rice where L-band HH is low.
- **Acceptance criteria**: §5.1 lists all candidate explanations with the test that would separate each.

**R18: Flooded-vegetation rule**
- **Problem**: The +3 dB HH / flat HV rule leaves reference pass, units, HV tolerance and persistent flooding undefined, and would also fire on normal rice growth.
- **Source**: R2 W5.
- **Requirement**: Specify the rule fully and validate it (autumn or winter flood dates against EMSR935's observed layer; rice through July), comparing with the OPERA DSWx-S1/NI L-band approach and published reviews; or remove it from the claimed label definition and state it as future work.
- **Acceptance criteria**: The rule is either fully specified with a validation result, or absent from the labels the paper claims.

**R19: Missing physics literature**
- **Problem**: The radar physics rests on one 1990 flooded-forest review; L-band rice and flooded-vegetation detection work is not cited.
- **Source**: R2 W6.
- **Requirement**: Add a short paragraph on frequency-dependent rice backscatter through the season and on flooded-vegetation detection; check every suggested reference before citing it (R2 did not web-check Le Toan et al. 1997 or Ulaby & Long 2014); restate the contribution as the measured gap to the operational product.
- **Acceptance criteria**: §2 cites checked L-band rice and flooded-vegetation sources, and the contribution sentence claims the measured gap, not the physics.

**R20: Who the map is for**
- **Problem**: The opening promises residents an answer for their street; the evidence comes from rice paddies and a marsh, and §6.2 says town labels are unreliable.
- **Source**: R3 W1; DA Missing Stakeholders.
- **Requirement**: Name the first users the evidence serves; state that urban flash floods like 2024 are out of scope; move the resident goal to future work.
- **Acceptance criteria**: Abstract and §1 name the intended first users and the out-of-scope case.

**R21: "Existing rain alert"**
- **Problem**: The abstract says an existing alert will be shown as a map; §4.6 builds the team's own traffic light with different thresholds from AEMET.
- **Source**: R3 W3.
- **Requirement**: Drive the map from the official AEMET level, or rename the team's signal (for example, rain scenario: 50 mm / 100 mm in 3 days) and correct the abstract; state in §4.6 that official warnings take precedence.
- **Acceptance criteria**: Abstract and §4.6 describe the same alert, and the team's signal cannot be confused with AEMET colours.

**R22: No flood in the training window**
- **Problem**: As designed, the model trains on NISAR passes from 17 June with the DANA held out; by the repository's event table no rain-driven new-flood event falls in that window at either site.
- **Source**: DA C2 (validated).
- **Requirement**: State this in §4.4 and §6.2 and give the NISAR-side event count; remove or condition the §6.3 sentence about learning from each storm; state which design the paper follows: label validation now and model later, Sentinel-1 as teacher with NISAR as check, or archive L-band labels.
- **Acceptance criteria**: The manuscript states the number of rain-driven flood events in the NISAR training window and no sentence claims the model learned rain-to-extent from them.

### Suggested Revisions (Should Fix / Consider)

| Transport ref | Item | Revision Item | Sub-Claim(s) | Severity | Evidence Anchor | Confidence | Source | Obligation class | Cost scope | Bounded consequence | Author-context tag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 | REV-05 | Say the U-Net repeats the DSWx-S1 result and is not independent C-band evidence | SC-5 | major | text: §4.3 "was trained on DSWx-S1 labels and is scored on the same points" | 4 (EIC); 4 (DA) | EIC (+DA m2) | should_fix | sentence: §4.3, §5.1, §6.1 | interpretive_ambiguity_remains → claim: three-map corroboration | T |
| S2 | REV-06 | Report the strict-referee comparison (NISAR producer's 0.43 vs DSWx-S1 0.06 per `numbers.md`, wide interval) and strict shares per stratum | SC-6 | major | text: §5.1 "The result that goes against us: not open water." | 4 (EIC); 3 (R2) | EIC, R2 | should_fix | sentence: §5.1, Table 4 | reporting_requirement_unmet → table: Table 4 | T |
| S3 | REV-09 | Say in the abstract and Contribution 1 that the June check is on irrigated rice and why it still tests under-vegetation water | SC-9 | minor | text: §3.1 "here is often farm water, not a flood" | 4 (EIC) | EIC (+DA C1) | should_fix | sentence: Abstract, §1 | claim_scope_unsupported → claim: Contribution 1 | T |
| S4 | REV-11 | Move the land-class model and Espadà to a supplement; keep the alert to one paragraph of context | SC-11 | minor | text: §3.1 "used only for the land-class model" | 4 (EIC) | EIC | consider | section: §3.1, §4.7, §5.4, §4.6, §5.5 | editorial_conformance_unmet → manuscript | T |
| S5 | REV-12 | Opening: authors' choice on the anecdote (SPLIT, author autonomy); move Discussion references and owner notes out of the main text; replace "Our innovation" | SC-12 | minor | text: §1 "Two of the authors were Erasmus students in Valencia in autumn 2026" | 4 (EIC); 4 (R3) | EIC, R3 (SPLIT) | consider | sentence: §1, §4.4, §4.5, §4.6 | editorial_conformance_unmet → section: §1 | T |
| S6 | REV-13 | Remove Appendix A; turn Appendix B into a supplementary traceability table | SC-13 | minor | text: Appendix A "Self-review (five dimensions)" | 4 (EIC) | EIC | consider | section: Appendices A, B | editorial_conformance_unmet → manuscript | T |
| S7 | REV-15 | Cite an official account of the 2024 DANA and the official ES-Alert text | SC-15 | minor | text: §1 "[citation needed: official report]" | 4 (R3); 4 (EIC) | R3, EIC | should_fix | sentence: §1, References | reader_traceability_reduced → claim: §1 opening | T |
| S8 | REV-16 | EIC minor issues: check the Dasgupta et al. description against the arXiv paper; use or drop the GV river-flood footprint (§3.3); label §6.3 as a hypothesis; add map figures for §5.1 and §5.3; footnote Table 4's bound columns | SC-16 | minor [SEVERITY-SOURCE: letter-fallback] | text: §3.3 "the Generalitat Valenciana river-flood footprint for DANA" | 4 [CONFIDENCE-SOURCE: report-level] | EIC | consider | sentence: §2, §3.3, §6.3, Table 4; other (figures): §5.1, §5.3 | reader_traceability_reduced → manuscript | T (figures: F) |
| S9 | REV-22 | Call the −15 dB check a consistency check: report mean absolute gap, r without 28 October, both tracks, that 18 June is not in the 058 A pairs; say the threshold was tuned to DSWx-S1 agreement on canopy-free dates; give a physical basis | SC-22a, SC-22b | minor (R1, R2 W9, DA); major (R2 W1 bullet) | text: §4.2 "was later confirmed on the second Albufera track, which played no part in choosing it" | 4 (R1); 4 (R2); 5 (DA) | R1, R2 (+DA m1) | should_fix | sentence: §4.2; re_analysis: §4.2 from `nisar_check.json` | claim_scope_unsupported → claim: threshold "confirmed" | T + F |
| S10 | REV-23 | Say the Sentinel-2 23 June fallback was not used; report 8 June S2 vs 22 June Landsat agreement on stratum E; mention the footprint mismatch | SC-23 | minor | text: §4.3 "on the closest clear look after (Landsat 9, 22 June; Sentinel-2, 23 June where Landsat is cloudy)" | 3 (R1) | R1 | should_fix | sentence: §4.3; re_analysis: stratum E | method_reproducibility_unresolved → section: §4.3 | T + F |
| S11 | REV-24 | Print three decimals, the number of map-water sample points per map, and a Wilson- or logit-based interval near 0 and 1 | SC-24 | minor | table: Table 4, DSWx-S1 and U-Net rows — CI "0.02–0.02", user's 1.00 | 5 (R1) | R1 | should_fix | re_analysis: Table 4 | reporting_requirement_unmet → table: Table 4 | F |
| S12 | REV-25 | State the basis for n = 150 per stratum and the effective n after unclear points; plan future samples for the unclear rate | SC-25 | minor | absence: §4.3 — sample-size rationale; checked §4.3, Table 3, Appendix A, `june18.py` docstring | 4 (R1) | R1 | consider | sentence: §4.3, Table 3 | reporting_requirement_unmet → section: §4.3 | T |
| S13 | REV-26 | R1 minor issues: round 11,601; label Table 4 bound columns "unclear all dry / all wet"; add a "decided" column to Table 3 | SC-26 | minor [SEVERITY-SOURCE: letter-fallback] | table: Table 3 | 4 [CONFIDENCE-SOURCE: report-level] | R1 | consider | sentence: §5.1, Tables 3–4 | reader_traceability_reduced → table: Tables 3–4 | T |
| S14 | REV-33 | Re-word soaked mud darkening radar as very smooth, saturated paddy soil or a thin water film; cite a scattering text | SC-33 | minor | text: §6.2 "Mud can trip both the optical flooding index and NISAR's dark threshold" | 4 (R2) | R2 | should_fix | sentence: §5.1, §6.2 | interpretive_ambiguity_remains → section: §6.2 | T |
| S15 | REV-34 | Qualify and cite the C-band young-crop sentence (C-band double bounce can still reveal some flooded rice) | SC-34 | minor | text: §2 "C-band missions such as Sentinel-1 provide frequent, free data but see water under young crops less reliably." | 4 (R2) | R2 | should_fix | sentence: §2 | claim_scope_unsupported → section: §2 | T |
| S16 | REV-35 | Add speckle filter type, effective resolution (about 100 m), incidence angles per track, and γ⁰ or σ⁰ | SC-35 | minor | text: §3.2 "after a 5 × 5 speckle filter in linear power" | 4 (R2) | R2 | should_fix | sentence: §3.2 | method_reproducibility_unresolved → section: §3.2 | T (values from metadata: F) |
| S17 | REV-36 | R2 minor issues: abstract "NISAR mapped … of water" → NISAR's dark-HH class covered; soften the HV attribution to Hess et al. 1990; §5.3 add that new water covers about a fifth of the outline | SC-36 | minor [SEVERITY-SOURCE: letter-fallback] | text: Abstract "NISAR mapped 6,387.2 ha" | 4 [CONFIDENCE-SOURCE: report-level] | R2 | consider | sentence: Abstract, §2, §5.3 | interpretive_ambiguity_remains → claim: Abstract | T |
| S18 | REV-38 | Write display rules into §4.4: at least three states (likely wet, no signal, not assessed); a fixed sentence that unshaded areas can still flood; PATRICOVA beneath in towns; probability bands; test with a few non-expert users if shown publicly | SC-38 | major | text: §4.4 "probability of water given a rain scenario; shown in the app as" | 4 (R3) | R3 | should_fix | section: §4.4 (optional new_data: user test) | claim_scope_unsupported → section: §4.4 | T (+N optional) |
| S19 | REV-40 | Add one paragraph on the Spanish warning chain (Decree 81/2010, SAIH Júcar, 112 / ES-Alert, RD 903/2010) and impact-based warnings (WMO-No. 1150; Potter et al. 2018); optional Table 1 column | SC-40 | minor | absence: §2 and References — civil-protection warning chain and impact-based warning literature; checked §1, §2, Table 1, §6.1, References | 3 (R3) | R3 | should_fix | section: §2, Table 1 | evidence_gap_remains → section: §2 | T |
| S20 | REV-41 | Outside the pre-registered rule, report the share of the observed flood missed, split by land use, and EMSR935 gaps | SC-41 | minor | text: §4.5 "The model is said to add value if its F1 beats all three baselines" | 3 (R3) | R3 | consider | new_data: §5.6 (needs model) | evidence_gap_remains → section: §5.6 | N |
| S21 | REV-42 | Say how deliberate farm water is handled in the display; name farmers' water management as confounder and possible ground truth | SC-42 | minor | text: §3.1 "here is often farm water, not a flood" | 3 (R3) | R3 | consider | sentence: §4.4, §6.2 | interpretive_ambiguity_remains → section: §6.2 | T |
| S22 | REV-43 | State in §6.2 that the map is hidden whenever the coarse alert stays low; consider showing fixed rain scenarios at all times | SC-43 | minor | text: §5.5 "amber two to three days ahead, never red" | 3 (R3) | R3 | consider | sentence: §6.2 | interpretive_ambiguity_remains → section: §6.2 | T |
| S23 | REV-44 | R3 minor issues: keep AEMET and team colour names apart; end each §6.2 limit with what it means for a map user; add an ethics line that the output is a research layer, not an official warning | SC-44 | minor [SEVERITY-SOURCE: letter-fallback] | text: Ethics statement "no human participants or personal data are involved" | 3 [CONFIDENCE-SOURCE: report-level] | R3 | consider | sentence: §1, §4.6, §6.2, Ethics | editorial_conformance_unmet → section: Ethics | T |

### Source-Traceability Checklist

> Immutable source order (seat order EIC, R1, R2, R3, DA, then the seat's finding ordinal). This is not a work order. Author triage (`will_address`, `wont_address`, `not_on_point`) is collected later in a separate author-adjudication sidecar.

- [ ] REV-01 / R1 — obligation `must_fix`: model delivered and tested, or paper re-titled and re-framed as label validation
- [ ] REV-02 / R2 — obligation `must_fix`: missing-at-random assumption, decided n, tipping point
- [ ] REV-03 / R3 — obligation `must_fix`: true worst-case producer's bounds
- [ ] REV-04 / R4 — obligation `must_fix`: product (DSWx-S1) contrast, not sensor contrast
- [ ] REV-05 / S1 — obligation `should_fix`: U-Net not independent
- [ ] REV-06 / S2 — obligation `should_fix`: strict-referee comparison side by side
- [ ] REV-07 / R5 — obligation `must_fix`: Table 1 "This work" row
- [ ] REV-08 / R6 — obligation `must_fix`: conclusion limited to the checked layer (DA C1)
- [ ] REV-09 / S3 — obligation `should_fix`: June check is irrigated rice
- [ ] REV-10 / R7 — obligation `must_fix`: Pego-Oliva baseline and recall
- [ ] REV-11 / S4 — obligation `consider`: side components to supplement
- [ ] REV-12 / S5 — obligation `consider`: opening and team-process framing
- [ ] REV-13 / S6 — obligation `consider`: Appendices A and B
- [ ] REV-14 / R8 — obligation `must_fix`: pre-registration wording
- [ ] REV-15 / S7 — obligation `should_fix`: official sources for 2024 DANA and ES-Alert
- [ ] REV-16 / S8 — obligation `consider`: EIC minor issues
- [ ] REV-17 / R9 — obligation `must_fix`: v1 confirmatory with interval; rule text archived
- [ ] REV-18 / R10 — obligation `must_fix`: referee data-independent; correlated error
- [ ] REV-19 / R11 — obligation `must_fix`: wet-area interval
- [ ] REV-20 / R12 — obligation `must_fix`: Pego-Oliva threshold disclosed and re-run at −15 dB
- [ ] REV-21 / R13 — obligation `must_fix`: §5.2 "therefore"
- [ ] REV-22 / S9 — obligation `should_fix`: threshold consistency check and independence wording
- [ ] REV-23 / S10 — obligation `should_fix`: referee bracket sensors
- [ ] REV-24 / S11 — obligation `should_fix`: intervals near 0 and 1
- [ ] REV-25 / S12 — obligation `consider`: sample-size rationale
- [ ] REV-26 / S13 — obligation `consider`: R1 minor issues
- [ ] REV-27 / R14 — obligation `must_fix`: threshold sweep, histograms, random baseline
- [ ] REV-28 / R15 — obligation `must_fix`: B vs D contrast and base-rate limit of the rule
- [ ] REV-29 / R16 — obligation `must_fix`: two radar mechanisms
- [ ] REV-30 / R17 — obligation `must_fix`: strict-referee rival explanations
- [ ] REV-31 / R18 — obligation `must_fix`: flooded-vegetation rule specified and validated, or removed
- [ ] REV-32 / R19 — obligation `must_fix`: L-band rice and flooded-vegetation literature
- [ ] REV-33 / S14 — obligation `should_fix`: mud wording
- [ ] REV-34 / S15 — obligation `should_fix`: C-band sentence
- [ ] REV-35 / S16 — obligation `should_fix`: SAR processing details
- [ ] REV-36 / S17 — obligation `consider`: R2 minor issues
- [ ] REV-37 / R20 — obligation `must_fix`: intended users and scope
- [ ] REV-38 / S18 — obligation `should_fix`: display rules
- [ ] REV-39 / R21 — obligation `must_fix`: rain-alert naming
- [ ] REV-40 / S19 — obligation `should_fix`: Spanish warning chain
- [ ] REV-41 / S20 — obligation `consider`: misses by land use
- [ ] REV-42 / S21 — obligation `consider`: farm water in display
- [ ] REV-43 / S22 — obligation `consider`: map gated on the alert
- [ ] REV-44 / S23 — obligation `consider`: R3 minor issues
- [ ] REV-45 / R22 — obligation `must_fix`: training window has no flood (DA C2)

Counts: must_fix 22, should_fix 12, consider 11; total 45.

### Journal-Supplied Deadline (Optional Transport)

- **Exact deadline from source letter**: `NOT PROVIDED` (no journal).
- Author-stated context, transported only: the NASA Space Apps jury presentation is in about 12 hours, and the flood-extent model is being built by a teammate and may land before then. This package infers no deadline, duration or work estimate from it; the author-context tag column is the only place it is reflected.

### Response Letter Template

Please use `templates/revision_response_template.md` (in the academic-paper-reviewer skill) to respond to every item. Must include:
1. Response and revision description for each Required Revision (R1–R22).
2. Response for each Suggested Revision (S1–S23): adopted, or the reason for not adopting.
3. Change markup in the revised manuscript.
4. A cross-reference table of new section or paragraph locations.

### Closing

We encourage you to carefully consider the reviewers' comments and submit a substantially revised manuscript. The revised manuscript will undergo another round of review. The finished validation work is a sound basis for that revision.

---

## Part 3: Reviewer Report Summary (Appendix)

### Journal-Fit Review Report Summary
- Recommendation: Major Revision | Confidence: 4
- Key Point: The finished label checks are transparent and timely, but the title, abstract, contributions, Table 1 and conclusion promise a learned flood-extent model that does not exist yet; deliver it or re-frame as a label-validation study.

### Reviewer 1 (Methodology) Summary
- Recommendation: Major Revision | Confidence: 4
- Key Point: The stratified design and estimators are correct and reproducible, but the producer's bounds are wrong, the wet area has no interval, decided-only estimates assume two-thirds of stratum B is missing at random, and "pre-registered" covers v1 while v2 is the headline.

### Reviewer 2 (Domain) Summary
- Recommendation: Major Revision | Confidence: 4
- Key Point: The June gap is driven largely by where −15 dB cuts the rice backscatter and by DSWx-S1 product rules; dark HH is not the double-bounce flooded-vegetation signal; the DANA check uses a different threshold; the L-band rice literature is missing.

### Reviewer 3 (Perspective) Summary
- Recommendation: Major Revision | Confidence: 3
- Key Point: The plain-language limits are good, but the paper promises residents a street-level answer the evidence cannot give, plans a binary map that invites "unshaded = safe", and calls its own new traffic light an existing alert.

### Devil's Advocate Summary
- Recommendation: N/A — findings only
- Key Challenge: The check shows a −15 dB dark map agreeing with an optical wetness index in irrigated June rice, not that NISAR labels teach where storm water goes; the labels to be used were not checked, and the training window contains no rain-driven flood (C1 and C2, both validated).

### Full reviewer reports

Attached by path (same folder): `seat-eic.md`, `seat-methodology.md`, `seat-domain.md`, `seat-perspective.md`, `seat-da.md`; Phase 0 cards: `phase0-field-analysis.md`.

---

## Attachment: Suggested-Reference Check (advisory, #1001)

The suggested-reference check did not run (script not installed). R2 and R3 report that they confirmed most suggested works by web search; R2 did not web-check Le Toan et al. 1997 or Ulaby & Long 2014.

## Attachment: Reviewer Claim Check (advisory, #1002)

The reviewer claim check did not run (script not installed).

## Attachment: Acronym Check (advisory, #849)

The acronym check did not run (script not installed).
