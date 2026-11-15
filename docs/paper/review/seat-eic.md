# Seat Report: Journal-Fit Reviewer (eic)

Contract: reviewer/reviewer_full/v2 (panel_size 5). Paper metadata used in Phase 1: title "Where will the water go? Learning flood extent in Valencia from the first months of NISAR L-band data"; field: SAR remote sensing of surface water / flood mapping; about 6,500 words.

Checker note: `scripts/check_phase_conformance.py` did not run (scripts not installed in this setup).

---

# Phase 1 — Paper-content-blind pre-commitment

## Contract Paraphrase

D1 (methodology_rigor, mandatory, owned by the methodology seat): the study's design, the way data are prepared and handled, how statistics and uncertainty are reported, and whether another group could rerun the work must reach the level a peer reviewer in this field expects. From an editorial view, this is the floor that makes every later claim trustworthy; I do not score it.

D2 (domain_accuracy, mandatory, owned by the domain seat): what the paper says about the field must match current knowledge, earlier work must be described correctly, and domain terms and reported results must be free of factual error. Editorially this protects readers from being misled about the state of the art; I do not score it.

D3 (argumentative_coherence, mandatory, owned by the devil's advocate with the methodology seat also eligible): the central thesis must hang together, the evidence presented must actually support the claims made, and there must be no reasoning error that breaks the main argument. Editorially this is where over-claiming is caught; I do not score it, though my fit assessment will note title-to-conclusion alignment.

D4 (cross_disciplinary_relevance, high, owned by the perspective seat): definitions, framing and consequences should be understandable to readers from neighbouring fields, and any claim that crosses fields must be backed up. I do not score it.

D5 (writing_and_structure, normal, owned by me): the manuscript should be well organised, explain itself clearly, present figures and tables that do their job, and follow the conventions of the kind of venue it targets. Editorially this decides whether a reader can follow and check the work without friction.

D6 (venue_fit_and_contribution, mandatory, owned by me): the manuscript should suit the intended venue and offer something new and meaningful for that venue's readers. With no confirmed venue, I judge it against field-general expectations for a SAR remote-sensing / flood-mapping research article: is the contribution real, is it stated honestly, and is it the kind of thing such readers would value.

## Scoring Plan

### D5: writing_and_structure
dimension_id: D5
what_to_look_for: Logical section order, a clear statement of question and contribution, precise exposition that lets a reader verify each step, figures and tables that carry the key evidence, and adherence to research-article conventions for the field.
what_triggers_block: The organisation or exposition is so unclear or internally contradictory that a reader cannot tell what was done, what was found, or which result supports which claim.
what_triggers_warn: Structure is followable but has material clarity problems, such as key evidence missing from figures or tables, sections that mix results and plans, or framing text that does not match the section content.

### D6: venue_fit_and_contribution
dimension_id: D6
what_to_look_for: A defensible contribution stated in title, abstract and introduction that the reported results actually deliver; fair positioning against existing methods and operational products; and a scope and article type that field-general SAR flood-mapping readers would find original and useful.
what_triggers_block: The headline contribution promised in title, abstract or introduction is not delivered by the reported results, though a narrower contribution that the results do support exists and could be reframed.
what_triggers_warn: The contribution is real but over-stated, unevenly positioned against prior work or operational products, or framed for an article type that only partly matches what was done.
what_triggers_fatal: No original or significant contribution remains for any field-relevant readership even after reframing, because the reported results are absent, invalid, or duplicate existing work.

criteria_binding_unavailable

[CONTRACT-ACKNOWLEDGED]

---

# Phase 2 — Paper-visible review

Manuscript: `docs/paper/review/manuscript-557e3fd.md` (draft of 14 November 2026). Checker note: `scripts/check_phase_conformance.py` did not run (scripts not installed in this setup). No target venue was confirmed, so this card applies field-general expectations for a SAR remote-sensing / flood-mapping research article and makes no claim about any specific venue's criteria.

contract_role: eic
## Dimension Scores

### D1: methodology_rigor
score: not_assessed

### D2: domain_accuracy
score: not_assessed

### D3: argumentative_coherence
score: not_assessed

### D4: cross_disciplinary_relevance
score: not_assessed

### D5: writing_and_structure
score: warn
trigger: "sections that mix results and plans, or framing text that does not match the section content"

### D6: venue_fit_and_contribution
score: block
trigger: "The headline contribution promised in title, abstract or introduction is not delivered by the reported results"
block_class: repairable

## Review Body

### Reviewer Identity
Journal-Fit Reviewer (Card #1): senior remote-sensing scholar with editorial experience in SAR applications and operational Earth-observation products. Review focus: whether the claimed contribution is delivered while the flood-extent model is a placeholder; whether title and abstract over-promise; whether the positioning against operational products is fair.

### Overall Recommendation
Major Revision (preliminary signal for the synthesizer). The block on D6 is repairable in either of two ways: (a) deliver the flood-extent model and the pre-written EMSR935 test, or (b) re-title and re-frame the paper as what it already is, an early independent check of NISAR L-band water maps against Sentinel-1 / DSWx-S1 over Valencia. Option (b) could be done in one revision; option (a) depends on work not yet done.

### Confidence Score
4. Strong on positioning, framing and SAR water products; methodological detail of the stratified estimators is outside my seat (the methodology seat's remit).

Confidence is an uncertainty/scope disclosure only; it never changes consensus counts, severity, decision bearing, or arbitration.

### Calibration Status
`NOT_CALIBRATED`

### Criterion-Bound Judgements

| Dimension / criterion | Criterion source | Judgement | Evidence anchors | Rationale | Uncertainty or scope limit | Decision bearing? |
|---|---|---|---|---|---|---|
| Originality | quality_rubrics.md Dim. 1; Card #1 focus 1 | PARTLY_MEETS | text: §1 "no independent check of its water maps over Spain existed"; text: §1 Contribution 3 placeholder | The early, pre-committed check of NISAR water is new and timely; the "learning flood extent" contribution that the title names does not exist yet | Novelty of the label check depends on literature the domain seat should confirm | yes: the claimed originality rests on an absent result |
| Significance & Impact | quality_rubrics.md Dim. 7 | PARTLY_MEETS | text: §6.1 "Our contribution is narrower"; text: §6.3 "The team's view is that this approach becomes more useful" | Demonstrated significance is for NISAR as a label source in vegetated wetlands; significance for flood forecasting is projected, not shown | One date, one event | yes: significance claims exceed demonstrated results |
| Argument Coherence (title to conclusion only) | review_criteria_framework.md §1; eic Step 4 | DOES_NOT_MEET | text: Title "Learning flood extent"; text: §7 "The flood-extent model and its independent test against EMSR935 are" | Title, abstract opening and contributions promise a learned flood-extent map; the conclusion can only report label checks | D3 itself is scored by other seats | yes: drives the D6 block |
| Literature Integration / positioning | quality_rubrics.md Dim. 6; Card #1 focus 3 | PARTLY_MEETS | table: Table 1 "This work" row; text: §6.1 "What others do better" | Prose positioning is fair and modest; Table 1 credits this work with capabilities not yet demonstrated and compares a sensor-plus-threshold with a product under rules it was not built for | Correctness of individual citations is the domain seat's remit | yes: positioning is part of the contribution claim |
| Evidence Sufficiency (contribution-level) | quality_rubrics.md Dim. 3 | PARTLY_MEETS | text: Appendix B "needs evidence [PLACEHOLDER]"; table: Table 4 | The label-validation claims are supported (authors' own claim map agrees); the flood-extent claim has no evidence | Statistical adequacy deferred to methodology seat | yes |
| Writing Quality / structure | quality_rubrics.md Dim. 5; contract D5 | PARTLY_MEETS | text: §4.4 "To be filled from Z. Stoimchev's model once on GitHub"; text: §5.4 "not yet merged" | Clear, plain prose and good traceability; structure mixes results with plans and carries side components (land-class model, Espadà site) not needed for the argument | Figures are being added separately and were not judged | partly: D5 warn |
| Methodological Rigor | quality_rubrics.md Dim. 2 | NOT_ASSESSED | — | Owned by the methodology seat | — | no (outside this seat) |

Do not total, weight, average, or mechanically map these judgements to the recommendation.

### Summary Assessment
The manuscript asks whether early NISAR L-band data can turn a rain alert into a map of likely flooded places around Valencia. What it actually delivers is three completed checks and one missing core: (1) a pre-committed, stratified, optical-referee check on 18 June 2026 showing that a −15 dB HH NISAR threshold finds about half of the wet rice where the DSWx-S1 product finds almost none, with an honest strict-referee result showing the extra water is not open water; (2) an autumn agreement check between the two radars; (3) a DANA "Adam" check at Pego-Oliva where most new NISAR water falls inside EMSR935 but the 12-day repeat misses the peak. The flood-extent model, the paper's titular contribution, is a placeholder in §4.4 and §5.6. The finished parts are transparent, number-traceable and unusually frank about adverse results, and the early independent look at NISAR water over a vegetated Mediterranean wetland is timely for the SAR flood-mapping community. But the title, abstract opening, Contribution 3, Table 1 and the conclusion all frame the work as learning flood extent, which the draft cannot show. Two framing issues also weaken the finished part: the headline comparison is NISAR-plus-threshold against a product with built-in land-cover rules, and the labels that were validated are not the labels the model would use. I recommend Major Revision: either complete the model and its pre-written test, or re-frame the paper as a label-validation study, which the current evidence supports well.

### S1: Traceability and disclosure of analysis changes
Every headline number is tied to a result file (I spot-checked the 18 June values in `numbers.md` against the manuscript; they agree), sample points and the pass rule were committed before scoring, and the change of the referee's after-image from v1 to v2 is disclosed with commit hashes and both versions reported. This is above the usual standard for the field.
**Evidence Anchor**: text: §4.3 "The pass rule itself did not change. Both versions are reported."

### S2: Adverse results reported in the main text
The strict open-water referee failing, the missed DANA peak and the alert never reaching red are all reported in Results, not hidden in limitations. Editors and readers can trust a paper that does this.
**Evidence Anchor**: text: §5.1 "The result that goes against us: not open water."

### S3: Timely, original label-quality question
An independent check of NISAR water maps while DSWx-NI is still under development, over a vegetated wetland where C-band is known to struggle, is a genuinely useful early contribution for SAR flood-mapping readers.
**Evidence Anchor**: text: §1 "no independent check of its water maps over Spain existed"

### S4: Modest, fair statement of what operational systems do better
The discussion states plainly that SNCZI/PATRICOVA, EFAS/GloFAS/Flood Hub and Copernicus EMS remain better for their own jobs and narrows the claimed niche.
**Evidence Anchor**: text: §6.1 "Official flood zones (SNCZI, PATRICOVA) remain the right answer"

### S5: Model test written down before the model exists, with strong baselines
The held-out DANA test against the observed EMSR935 layer, scored against low-terrain, past-water and persistence baselines with a rule fixed in advance and run by a different author, is a good design for the missing part.
**Evidence Anchor**: text: §4.5 "The model is said to add value if its F1 beats all three baselines"

### S6: Explicit data-maturity reporting
Table 2 states the BETA/PROVISIONAL/VALIDATED status, dates and the permanent gap, so readers can judge how early and provisional the data are.
**Evidence Anchor**: table: Table 2 — NISAR data maturity and products used

### W1: The titular contribution, a learned flood-extent model, is not in the paper
**Problem**: The title, the abstract's stated approach, the Introduction's "Our approach" paragraph, Contribution 3, Figure 1, Table 1 and §6.1 all present a model that learns where water goes from rain, terrain and land cover. §4.4 is a planned design and §5.6 is empty. No result in the draft shows that such a model works, beats a baseline, or exists.
**Evidence Anchor**: text: Title "Learning flood extent in Valencia from the first months of NISAR L-band data"; §1 "A flood-extent model trained on NISAR water labels"
**Why it matters**: A reader or editor takes the title as the claim to be judged. As drafted, the main claim cannot be judged, so the paper cannot be accepted under its current framing, however good the finished parts are.
**Suggestion**: Choose one path before resubmission. (a) Deliver §4.4/§5.6 and run the §4.5 test as written, reporting the result whichever way it falls. (b) Re-title and re-frame as a label-validation study (for example, "Does early NISAR L-band see water that Sentinel-1 misses? An independent check over the Albufera and Pego-Oliva") and move the flood-extent idea to a short "intended use" paragraph in the Discussion. Path (b) fits a letter-length article and needs no new data.
**Severity**: Critical
**Confidence**: 5 — core editorial judgement; the placeholder status is stated by the authors

### W2: Abstract headline numbers hide the small decided base and do not match their own bounds
**Problem**: The abstract reports the stratum-B agreement (0.94, interval 0.86–1.00) and NISAR producer's accuracy 0.52 without saying that only 49 of 150 stratum-B points were decided (101 unclear). Table 4 gives NISAR producer's bounds of 0.44 / 0.47 (every unclear point dry / wet), so the headline 0.52 lies outside the range its own bounds span, and user's accuracy ranges 0.32 to 0.98 across the bounds. A reader of the abstract alone would take the result as far firmer than it is.
**Evidence Anchor**: text: Abstract "where only NISAR sees water, the referee agrees in"
**Why it matters**: The 18 June check is the paper's strongest finished result and the basis of any re-framing. If the abstract overstates its certainty, the re-framed paper inherits the problem.
**Suggestion**: State the decided count and the bounds in the abstract (one clause), and explain in §5.1 why a decided-only estimate can fall outside the all-dry / all-wet bounds (the methodology seat should check that explanation). Consider leading with the bounds rather than the decided-only point estimate.
**Severity**: Major
**Confidence**: 3 — editorial reading of the abstract; the estimator question is the methodology seat's remit

### W3: Headline comparison is NISAR-plus-threshold against a product with built-in rules, presented as NISAR against Sentinel-1
**Problem**: The 0.52 vs 0.02 contrast compares a −15 dB HH threshold on NISAR with DSWx-S1, a product that by design issues inundated vegetation only on wetland land cover and targets water bodies over about 3 ha. The authors say so in §6.2, but §5.1's heading, Contribution 1 and §6.1 read it as a sensor contrast ("Sentinel-1 does not", "the C-band product ... miss almost entirely"). The C-band U-Net was trained on DSWx-S1 labels, so it is not an independent C-band baseline either. In addition, the strict referee shows the NISAR class is "wet ground", not the open-water class DSWx-S1 aims at, so the two maps are partly measuring different things.
**Evidence Anchor**: text: §5.1 heading "NISAR sees water on 18 June that Sentinel-1 does not"
**Why it matters**: Operational-product readers will see this as an unfair comparison: the product is scored on a class it was not designed to map in this land-cover setting. The defensible finding is "the operational C-band product misses this water", not "C-band misses it".
**Suggestion**: Either add a like-for-like C-band baseline (e.g. a Sentinel-1 VV/VH threshold or a change rule on the same points), or re-word the heading, Contribution 1, abstract and §6.1 to say "the DSWx-S1 product" throughout and move the §6.2 caveat into §5.1. Also report that, under the strict referee, NISAR producer's accuracy is still higher than DSWx-S1 (0.43 vs 0.06 in `numbers.md`, with a wide interval), which is the fairer form of the comparison.
**Severity**: Major
**Confidence**: 4 — core competence in SAR water products and their documented rules

### W4: Table 1 credits "This work" with capabilities that are not yet demonstrated
**Problem**: Table 1 lists this work as driven by "rain of the warning, terrain, land cover, soil moisture", with labels "incl. flooded vegetation", covering small coastal wetlands ("yes"), and tied to a rain warning ("yes"). The model is unbuilt (§4.4), the flooded-vegetation label rule is a placeholder (§4.2), and coverage of small wetlands has not been tested. Meanwhile operational systems are rated on what they have shown in operation. The cell "not tested here" for Dasgupta et al. and the use of a "Water labels" column for observation-only products (GFM, DSWx-S1) also mix categories.
**Evidence Anchor**: table: Table 1 — row "This work", columns "Covers small coastal wetlands" and "Tied to a rain warning"
**Why it matters**: A positioning table is how editors and readers judge novelty at a glance. Comparing planned capabilities with operational ones overstates the gap the paper fills.
**Suggestion**: Mark planned features as planned (e.g. "planned; not yet tested") or, under the re-framing in W1, replace Table 1 with a table about water-label sources (DSWx-S1, GFM, EMS, NISAR threshold) and what each sees under vegetation, which the paper can actually support.
**Severity**: Major
**Confidence**: 4 — core competence in operational flood products

### W5: The labels that were validated are not the labels the model would use
**Problem**: The 18 June and autumn checks validate one thing: open water from a −15 dB HH threshold. The labels proposed for the flood-extent model add a flooded-vegetation class (HH +3 dB, HV flat) and merge NISAR with Sentinel-1 per pass, and those rules are a placeholder with no check. Yet the Conclusion says the results support using NISAR water "together with Sentinel-1, as labels for a model of where water goes".
**Evidence Anchor**: text: §4.2 "The labels for the flood-extent model add a flooded-vegetation class"
**Why it matters**: This weakens even the re-framed contribution: the paper validates a label that the downstream use would not use as-is. The link between "we checked the labels" and "these labels are fit for the model" is the bridge of the whole argument.
**Suggestion**: Either score the final label (threshold plus flooded-vegetation class plus Sentinel-1 merge) on the same 18 June points and the DANA, or limit the conclusion to the −15 dB open-water/wet-ground layer that was actually checked.
**Severity**: Major
**Confidence**: 4 — editorial and SAR-label competence; the argument gap is visible in the text

### W6: The main validation date tests farm irrigation water, not flood water
**Problem**: The 18 June check is on deliberately flooded rice paddies. It shows that NISAR sees water among young rice, which is relevant physics, but it is not a flood event. The only flood check (DANA, Pego-Oliva) has two NISAR passes, misses the peak and reports only the share of new water inside the outline (212 ha against an 877 ha outline). For a flood-mapping readership, the evidence that NISAR labels capture flood water specifically is thin.
**Evidence Anchor**: text: §3.1 "here is often farm water, not a flood"
**Why it matters**: The paper's framing is flood mapping; the strongest evidence is about irrigation water. The authors acknowledge this, but the abstract and contributions do not.
**Suggestion**: Say in the abstract and Contribution 1 that the June check is on irrigated rice and explain why it is still a useful test of under-vegetation water; for the DANA, also report the share of the EMSR935 observed flood that NISAR captured, so both directions are visible.
**Severity**: Minor
**Confidence**: 4 — field framing judgement

### W7: Side components dilute the paper's focus
**Problem**: The land-class model (§4.7, §5.4) and the Serra d'Espadà site serve only as a "candidate land-cover feature" for an unbuilt model; their results come from an unmerged branch. The rain-threshold alert (§4.6, §5.5) is a separate component with two test events and is not listed among the contributions. Together with the placeholders, the paper reads as a project report covering five components rather than an article with one argument.
**Evidence Anchor**: text: §3.1 "used only for the land-class model"
**Why it matters**: Readers lose the thread, and reviewers must judge results that do not bear on the main claim.
**Suggestion**: Under either path in W1, move the land-class model and Espadà to supplementary material or a separate note; keep the alert to one paragraph of context (it motivates "when" but is not evidence for "where").
**Severity**: Minor
**Confidence**: 4 — editorial structure judgement

### W8: Hackathon and team-process framing in the main text
**Problem**: The opening anecdote about two authors as Erasmus students, references to GitHub Discussions #25 and #29 as places where design was agreed, named team members as owners of placeholder sections, and "Our innovation" phrasing are unusual for a research article and make the paper read as a team report.
**Evidence Anchor**: text: §1 "Two of the authors were Erasmus students in Valencia in autumn 2026"
**Why it matters**: It does not affect the results, but it affects how a field-general research readership receives the work.
**Suggestion**: Open with the Valencia flood problem and the label gap; keep commit hashes (they support S1) but move Discussion references and author-ownership notes to Data availability or a supplement; replace "Our innovation" with a plain statement of the approach.
**Severity**: Minor
**Confidence**: 4 — editorial convention

### W9: Self-review and claim-evidence appendices belong outside the article
**Problem**: Appendix A (self-review with pass/needs-revision labels) and Appendix B (claim-evidence map) are drafting tools. Appendix B is useful to reviewers, but neither is a standard article component, and Appendix A rates the paper's own contribution as "pass".
**Evidence Anchor**: text: Appendix A "Self-review (five dimensions)"
**Why it matters**: Minor presentation issue; it could look like the authors are pre-judging review.
**Suggestion**: Remove Appendix A from the submission; turn Appendix B into a supplementary traceability table or a cover-letter attachment.
**Severity**: Minor
**Confidence**: 4 — editorial convention

### W10: The abstract's pre-registration wording omits the referee revision
**Problem**: The abstract says points were "fixed in git before scoring" and the rule was "fixed in advance", which is true, but the referee definition (the after-image) was changed after a first scored run (v1). The body discloses this well; the abstract does not.
**Evidence Anchor**: text: Abstract "fixed in git before scoring and judged by an optical-only referee"
**Why it matters**: "Pre-registered" is a strong signal to readers; the abstract should not be more confident than the body. The substance of whether the change matters is the methodology seat's question.
**Suggestion**: Add one clause to the abstract ("the referee's after-image was revised once after a first run; both versions agree in direction").
**Severity**: Minor
**Confidence**: 4 — editorial reading; substance deferred to methodology seat

### Detailed Comments

#### Journal Fit
No venue was confirmed, so no venue-specific fit claim is made. Field-general: the finished material (an early, independent, sample-based check of a new mission's water maps against an operational product, with one event check) is a natural short-article or letter-length contribution for SAR remote-sensing readers. As a full research article on learned flood extent, it is not yet ready, because the core result is missing. The length (about 6,500 words) is reasonable for a full article but long for what is finished; a re-framed version would be shorter.

#### Originality
Original in timing and question (NISAR water vs DSWx-S1 over a vegetated Mediterranean wetland in the first calibrated months). The "learn flood extent from satellite water labels" idea is, as the authors fairly say, already explored with C-band labels (Nevo et al. 2022; Dasgupta et al. 2022); the new element would be L-band labels, which is exactly the part not yet demonstrated beyond the threshold check.

#### Significance
Demonstrated significance: NISAR can supply water labels in vegetated settings that the operational C-band product does not. Projected significance (a rain-conditioned flood map for residents) is argued but not shown; §6.3 is a statement of belief, which the authors label as such in Appendix B but not in §6.3 itself.

#### Structural Coherence
Title, abstract and contributions promise a model; results and conclusion deliver label checks. Placeholders sit inside Methods and Results, and §5.3 ends with a bold motivating statement for the unbuilt model. Once the framing is fixed (W1), the remaining structure is sound and easy to follow.

#### Title & Abstract
The title over-promises (W1). The abstract is dense with numbers (about 320 words) and gives the decided-point estimates without their base or bounds (W2), and omits the referee revision (W10). It does, to its credit, state the strict-referee result and the missed peak, and it calls the work "a demonstration of what is possible, not proof".

#### Conclusion
The conclusion is honest about the placeholder and the data regime, but its central sentence ("These results support using NISAR water, together with Sentinel-1, as labels") goes beyond what was checked (W5).

### Questions for Authors
1. If the flood-extent model is not ready by resubmission, will you re-title and re-frame the paper as a label-validation study, or delay submission until §4.5 is run?
2. Will the model's labels be the −15 dB threshold that was checked, or the threshold plus flooded-vegetation class plus Sentinel-1 merge? If the latter, can that combined label be scored on the same 513 points?
3. Can you add a like-for-like C-band baseline (a Sentinel-1 backscatter threshold or change rule on the same points), so the contrast is sensor against sensor rather than sensor-plus-threshold against product?
4. Why does the decided-only NISAR producer's accuracy (0.52) fall outside the all-dry / all-wet bounds (0.44 / 0.47), and which number should a reader treat as the headline?

### Minor Issues
- §1: "[citation needed: official report]" for the 29 October 2024 DANA must be filled.
- §2 / References: the description of Dasgupta et al. [2022] (CNN with rain, soil moisture and terrain inputs, Sentinel-1 labels) should be checked against the arXiv paper; I could not confirm it from the manuscript, and the domain seat may wish to verify it.
- §3.3: the Generalitat Valenciana river-flood footprint is listed as data but not used anywhere in the draft.
- §5.3: report the share of the EMSR935 observed outline captured by NISAR's new water alongside the 87 % inside share.
- §6.3: label the improvement expectation as a hypothesis in the text, as Appendix B already does.
- Figures: a map figure of the 18 June strata with NISAR and DSWx-S1 water, and one of the Pego-Oliva new water against the EMSR935 outline, would carry §5.1 and §5.3 far better than numbers alone (figures are being added separately; not judged here).
- Table 4: "Producer's bounds" column order (dry / wet) is the reverse of what readers might expect for DSWx-S1 (0.04 / 0.02); a footnote would help.
