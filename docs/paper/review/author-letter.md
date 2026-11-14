# Review Letter

The automatic check of this letter did not run (the script is not installed). The decision package, editorial-decision.md, is the record.

## Decision

Major Revision. This is a fixable result, not a rejection. All four scoring reviewers chose Major Revision, and no reviewer found a fatal error. The main reasons:

- The title promises a flood-extent model, but the model is not in the paper yet.
- The conclusion says NISAR water is a good training label, but the labels you checked are not the labels the model will use, the June check is on farm water, and the training period has no rain flood to learn from.
- Some 18 June numbers look more certain than they are (the unclear points, the bounds, the wet area, and the word pre-registered).
- The June result depends a lot on where the −15 dB threshold sits and on the rules of the DSWx-S1 product, not only on L-band versus C-band.

How to read the tags on each change below. The tags are not an order of work.

- [Tonight: text] means you only change words.
- [Tonight: recompute] means you run your code again on files you already have.
- [Needs new data or the model] means it needs new data, new labels, or the flood-extent model.
- Some changes have two allowed paths, so they carry two tags.

## Strengths

- All four reviewers praised that you report the results that go against you in the main text: the strict referee result, the missed DANA peak, and the alert that never reached red.
- Every number is traced to a result file. Reviewers checked many numbers, and they matched.
- The sample points were saved in git before any scoring, and the git history matches what the paper says.
- The stratified accuracy formulas are correct. The methods reviewer recomputed them from your released labels and got the same values.
- The test for the flood model is written before the model exists, uses three baselines (including persistence), and is run by a different team member. Three reviewers called this good design.
- The paper describes the DSWx-S1 inundated-vegetation rule correctly and says plainly what official systems do better.
- The non-rice control stratum and the autumn comparison are good physical controls.
- The limits in Section 6.2 are written in plain words, including what the map means in towns.
- The question is timely: an early, independent check of NISAR water over a vegetated wetland, while the official NISAR water product is still in development.

## Required Changes

**What the paper claims**

1. [Title; Abstract; Section 1 Our approach and Contribution 3; Figure 1; Section 6.1; Section 7] The title says “Learning flood extent in Valencia from the first months of NISAR L-band data”, but Sections 4.4 and 5.6 are empty. Choose one path. Path A: add the model and run the Section 4.5 test exactly as written, and report the result even if the model loses to a baseline. Path B: change the title and framing to an independent check of early NISAR water against DSWx-S1 at the Albufera and Pego-Oliva, and move the model idea to a short future-use paragraph. [Tonight: text] for path B; [Needs new data or the model] for path A.
2. [Table 1, row This work] The row says this work has flooded-vegetation labels, covers small coastal wetlands, and is tied to a rain warning. None of this is shown yet. Mark these cells as planned, not yet tested, or replace Table 1 with a table of water-label sources and what each one sees under plants. (One reviewer found Table 1 fair; the editor agreed for the rows about other systems, but not for your own row.) [Tonight: text]
3. [Section 7; Section 6.1] The conclusion says “These results support using NISAR water, together with Sentinel-1, as labels for a model of where water goes”. But you checked only the −15 dB dark map, on one June date, in irrigated rice. The model labels add a flooded-vegetation class and a Sentinel-1 merge, and these were not checked. Limit the conclusion to the layer you checked and the conditions of the check, or score the final label product on the same 513 points and on the DANA. [Tonight: text] or [Needs new data or the model]
4. [Abstract; Section 1 opening; Section 6.2] The opening promises a resident an answer for their own street, but the evidence comes from rice fields and a marsh, and Section 6.2 says town labels are not reliable. Name the first users your evidence serves (civil protection, wetland managers, farmers' water boards). Say that urban flash floods like October 2024 are outside the scope for now. Move the resident goal to future work. [Tonight: text]
5. [Abstract; Section 1; Section 4.6] The abstract says the model works “so that an existing rain alert can be shown as a map of likely flooded places”, but Section 4.6 builds your own traffic light with other thresholds than the official AEMET colours. Either use the official AEMET level, or give your signal a different name (for example, rain scenario 50 mm or 100 mm in 3 days) and fix the abstract. Also say in Section 4.6 that the official warning always comes first. [Tonight: text]
6. [Section 4.4; Section 6.2; Section 6.3] Your own event table shows that the four training flood events are all from before 17 June 2026, when calibrated NISAR data start. In the NISAR period before the DANA there is no rain-driven new flood at either site. The biggest storm (4 October, 124.6 mm) made no new flood, while farmers were re-flooding the rice. So the sentence “With each storm the model sees how the footprint grows with rain” is not true for this period. Say this clearly, give the count of flood events in the NISAR training period, and change or remove that sentence. Then say which design you follow: check the labels now and build the model later; or train on the longer Sentinel-1 record and use NISAR as the check; or use older L-band data. If the model lands tonight, still report the Section 4.5 result exactly as written, and add that a good DANA score cannot show the model learned from storms in this short period. [Tonight: text] for the disclosure; [Needs new data or the model] for a new training design.

**The 18 June numbers and how certain they are**

7. [Abstract; Section 5.1; Table 4] Your headline numbers use only the decided points: 49 of 150 in stratum B and 68 of 150 in stratum D. This assumes the unclear points are wet at the same rate as the decided ones. But almost all unclear points have the same pattern (wet on 8 June, dry on 22 June), so they are not a random group. Write this assumption next to each headline number and give the decided count in the abstract. Add a tipping-point check: how many of the 101 unclear B points must be wet for the rule to pass (the reviewer found about 59). Also report the case where every unclear point is wet. [Tonight: recompute]
8. [Table 4; Section 5.1] The producer's bounds 0.44 / 0.47 are not real bounds, because the estimate 0.52 is outside them. Producer's accuracy is a ratio, so setting all unclear points to the same label does not give the extremes. Compute the true worst case stratum by stratum for NISAR and DSWx-S1, and point by point for the U-Net. The reviewers got about 0.22 to 0.71 for NISAR and about 0.01 to 0.05 for DSWx-S1; please recompute these yourself. Say that the bootstrap interval covers only sampling error. If your numbers confirm it, say that NISAR stays above DSWx-S1 even at the worst case. [Tonight: recompute]
9. [Abstract; Section 1 Contribution 1; Section 7] The words pre-registered and fixed in advance are stronger than the facts. The points and the pass rule were fixed before scoring, but the referee's after-image was changed after the first run. Say exactly this, in one clause, wherever the paper uses these words. [Tonight: text]
10. [Section 4.3; Section 5.1; Table 4] Only the first referee version was fixed before any result was seen, so it is the true confirmatory test. Run it again with its interval (the reviewer read about 0.69 to 0.96 from an older commit) and show it next to version 2. Call version 2 a later improvement and give the reason. Save the exact rule text from Discussion #25 with a date or a commit hash, because a Discussion post can be edited. Say who proposed version 2. [Tonight: recompute] plus [Tonight: text]
11. [Section 4.3; Section 6.2] The paper says “The referee never uses a radar, so the check is not circular.” This is true for the data, but the referee's own accuracy is unknown, and it can make the same mistake as NISAR: wet soil or young, thin rice can make both say wet. Write data-independent instead of independent, and discuss this shared error. Optional: compare stratum B and stratum D after matching them on 8 June EVI or NDVI, or check the referee on a small set of points with a better source. [Tonight: text]; the optional checks are [Tonight: recompute] or [Needs new data or the model]
12. [Section 5.1] The wet-rice area (11,601 ha) has no interval and too many digits. Round it and add the bootstrap interval and the range from all-unclear-dry to all-unclear-wet (the reviewer found about 10,600 to 12,600 ha, and about 4,600 to 13,300 ha). Add the wet share to the bootstrap in june18.py and mention the first-version value. [Tonight: recompute]
13. [Abstract; Section 4.3; Section 5.1] The pass bar (0.7) is lower than the share of wet rice the referee finds overall (0.79). So a map that calls all rice water would also pass, and the abstract phrase “which passes a rule fixed in advance” says less than it seems. Report the comparison that shows real skill: stratum B against stratum D (0.94 against 0.68 with the main referee; 0.10 against 0.12 with the strict referee). Write the base-rate limit next to the word passed. [Tonight: text] (the numbers are already in your result files)

**Radar physics and what the June result means**

14. [Section 5.1 heading; Abstract; Section 1 Contribution 1; Section 6.1; Section 7] The heading “NISAR sees water on 18 June that Sentinel-1 does not” compares a sensor with a product. DSWx-S1 maps water under plants only where its land-cover map says wetland, and rice is cropland. Say the DSWx-S1 product instead of Sentinel-1 in these places, and move the product warning from Section 6.2 into Section 5.1. Optional: add a simple threshold on raw Sentinel-1 VV and VH on the same points. [Tonight: text]; the optional baseline is [Needs new data or the model]
15. [Section 5.2] The sentence “The June disagreement is therefore specific to water beneath vegetation, not a calibration problem.” goes too far. Autumn agreement shows there is no calibration offset, but it does not exclude wet soil or a threshold effect. Write is consistent with instead of therefore, and say wet mud is still possible. Add that on 18 June the morning and evening tracks agree (43.7 % and 46.9 %), which speaks against a look-direction effect. [Tonight: text]
16. [Section 5.1; Table 4; one new figure] On 18 June the middle value of rice HH is about −14.4 dB, very close to your −15 dB cut. Moving the cut by 1 dB changes the NISAR water area by about a quarter, and a random map of the same size would already score about 0.44. Show user's and producer's accuracy for thresholds from −18 to −12 dB on the same 513 points, with both referees; show HH and HV histograms per stratum; and give the same-size random baseline. Say that 0.52 and 6,387 ha belong to the chosen threshold, not to NISAR alone. [Tonight: recompute]
17. [Section 2; Section 4.2; Section 5.1; Section 6.1] Section 2 explains double bounce, where flooded plants look brighter, but your rule keeps only dark pixels. Explain the two cases separately: dark HH means open water or water between thin, young plants; bright HH with a high HH/HV ratio means double bounce in flooded plants. Say the June result is the first case. Your dark share falls from 43.7 % on 18 June to 0.3 % on 24 July while the fields stay flooded, which fits this. Remove the phrase “so labels built from NISAR are less biased towards open water” until the flooded-plant class is checked. [Tonight: text]
18. [Section 5.1; Section 6.2] With the strict referee, the NISAR-only points have no more open water than the rice that neither map flags. You give two explanations and stop. Show the strict shares for all strata side by side. List the other possible explanations: the threshold cuts through one wet-rice group; the optical index misses shallow water under growing plants; a short drainage of the paddies; very smooth wet paddy soil; and young crop stage. Say which test could separate each one. Change the practical reading to: pixels in wet rice where L-band HH is low. [Tonight: text]; HV and HH/HV per stratum would be [Tonight: recompute]
19. [Section 4.2; Figure 1; Table 1] The flooded-vegetation rule (HH up about 3 dB, HV flat) does not say which earlier pass, dB or linear units, how flat HV must be, or what happens when a field stays flooded. In rice, HH also rises when the plants simply grow. Either define the rule fully and test it, or take it out of the labels the paper claims and call it future work. [Tonight: text] for taking it out; [Needs new data or the model] for defining and testing it
20. [Section 2; References] The radar physics rests on one 1990 review about flooded forest. Add a short paragraph on how rice looks at L-band and other bands through the season, and on methods for finding flooded plants with radar. The domain reviewer suggested several sources; check each one yourself before you cite it, because two of them were not checked online. Then describe your contribution as the measured gap between early NISAR and the operational product, not as new physics. [Tonight: text]

**The DANA check at Pego-Oliva**

21. [Section 5.3; Abstract; Section 1 Contribution 2] The 87 % of new water inside the outline has no chance level. If the outline covers much of the scored area, random water would also fall inside. Report the outline's share of the analysed area, the share of the outline that NISAR caught (about 184 of 877 ha, about 21 %), and the same inside-share for DSWx-S1. Call it a map-to-map agreement check. (One reviewer's rough estimate suggests the chance level is low, so this may help your result.) [Tonight: recompute]
22. [Section 4.2; Section 5.3] Section 4.2 defines water as HH below −15 dB, but the Pego-Oliva map used a threshold chosen per scene (Otsu), about −11.85 and −12.03 dB. The paper does not say this. State the method and the values, run the Pego-Oliva check again at −15 dB, and report both results, or explain why the labels use Otsu. [Tonight: text] plus [Tonight: recompute]

## Suggested Changes

23. [Section 4.3; Section 5.1; Section 6.1] The U-Net learned from DSWx-S1 labels, so its 0.04 repeats the DSWx-S1 result. Say it is not separate evidence about C-band. [Tonight: text]
24. [Section 5.1; Table 4] Show the strict-referee comparison too: NISAR producer's accuracy 0.43 against 0.06 for DSWx-S1 (from numbers.md), with its wide interval, and the strict shares per stratum. This is the fairer comparison. [Tonight: text]
25. [Abstract; Section 1 Contribution 1] Say that the June check is on irrigated rice, not on a flood, and explain why it still tests water under plants. [Tonight: text]
26. [Sections 3.1, 4.7, 5.4, 4.6, 5.5] The land-class model and the Serra d'Espadà site do not support the main argument. Consider moving them to supplementary material, and keeping the rain alert to one paragraph of context. [Tonight: text]
27. [Section 1; Sections 4.4, 4.5, 4.6] Move the GitHub Discussion links and the names of section owners out of the main text, and replace “Our innovation” with a plain description. Keeping the Erasmus story is your choice: one reviewer wants to drop it, another wants to keep it. Either way, it must not suggest that the method answers the 2024 resident question. [Tonight: text]
28. [Appendix A; Appendix B] Appendix A (self-review) is a drafting tool; consider removing it. Appendix B is useful but could be a supplementary table. [Tonight: text]
29. [Section 1; References] Replace the missing citation for the October 2024 DANA with an official or peer-reviewed source, and cite the official ES-Alert text instead of a news article. [Tonight: text]
30. [Section 2; Section 3.3; Section 6.3; Table 4; Sections 5.1 and 5.3] Small points: check the description of Dasgupta et al. against their paper; use the Generalitat Valenciana river-flood footprint or remove it from the data list; call the Section 6.3 expectation a hypothesis; add map figures for the June strata and for Pego-Oliva; add a note on the order of the bound columns in Table 4. [Tonight: text]; figures from existing maps are [Tonight: recompute]
31. [Section 4.2] Call the −15 dB check a consistency check, not a confirmation. The correlation 0.978 depends mostly on one big date (28 October), the other track gives a much weaker fit, and 18 June is not among the 10 paired dates. Report the mean gap, the correlation without 28 October, and both tracks. Also, the threshold was in practice tuned to agree with DSWx-S1, so soften the phrase “does not depend on the C-band products it is compared with” and give a physical reason for −15 dB. [Tonight: text]; the extra numbers are [Tonight: recompute] from nisar_check.json
32. [Section 4.3] Say that the Sentinel-2 image of 23 June was never needed (Landsat was clear for all 513 points). Report how often the 8 June and 22 June labels agree on the control stratum, and mention that the two sensors have different pixel sizes. [Tonight: text] plus [Tonight: recompute]
33. [Table 4] Some intervals look like certainty (0.02–0.02, 1.00–1.00). Print three decimals, give the number of sample points each map calls water, and use a Wilson or logit interval near 0 and 1. [Tonight: recompute]
34. [Section 4.3; Table 3] Say why you chose 150 points per stratum, and give the real number of decided points after unclear points are removed. Plan future samples for a high unclear rate. [Tonight: text]
35. [Section 5.1; Tables 3 and 4] Round 11,601; name the bound columns unclear all dry and unclear all wet in the header; add a decided column to Table 3. [Tonight: text]
36. [Section 5.1; Section 6.2] The phrase “soaked mud, which darkens radar” is not quite right: wet soil usually gets brighter, and it gets darker only when it is very smooth or has a thin water film. Write very smooth, saturated paddy soil or a thin water film, and cite a radar physics textbook. [Tonight: text]
37. [Section 2] The sentence about C-band seeing water under young crops less reliably has no source, and C-band can still see some flooded rice through double bounce. Make it more careful and add a citation. [Tonight: text]
38. [Section 3.2] Add the speckle filter type, the real resolution after the 5 × 5 filter (about 100 m), the incidence angles per track, and whether values are gamma-0 or sigma-0. [Tonight: text]; the values come from your files' metadata
39. [Abstract; Section 2; Section 5.3] Instead of “NISAR mapped 6,387.2 ha” of water, say NISAR's dark-HH class covered this area. Soften the claim that HV changes little in flooded plants, since the 1990 source is about forest. In Section 5.3, add that the new water covers about a fifth of the outline. [Tonight: text]
40. [Section 4.4] Write the display rules before the model lands: at least three states (likely wet, no signal, not assessed); a fixed sentence such as unshaded areas can still flood, follow official warnings; show PATRICOVA zones in towns instead of a terrain-only guess; and keep a few probability bands instead of one cut. If you plan a public map, test it with a few non-expert users first. [Tonight: text]; a user test is [Needs new data or the model]
41. [Section 2; Table 1] Add one paragraph on who issues flood warnings in Valencia (the regional flood plan, the Júcar basin real-time data, 112 and ES-Alert, the national flood-risk rules), and cite work on impact-based warnings. Optionally add a Table 1 column on who issues and who acts. [Tonight: text]
42. [Section 5.6] When the model is scored, also report (outside the pre-registered rule) how much of the real flood it misses, split by land use (towns, roads, farmland, marsh), because a missed street matters more than a false alarm. [Needs new data or the model]
43. [Section 4.4; Section 6.2] Say how the map will treat water that farmers put on the rice on purpose, so the map is not always full. Name farmers' water management as both a source of confusion and a possible source of ground truth. [Tonight: text]
44. [Section 6.2] The map is shown only when the alert is amber or red, but the alert never reached red for DANA Adam. Say this risk in plain words, and consider showing the map for fixed rain scenarios all the time. [Tonight: text]
45. [Section 1; Section 4.6; Section 6.2; Ethics statement] Keep the AEMET colour names and your own colour names clearly apart. End each limit in Section 6.2 with one short clause on what it means for a map user. Add one line to the ethics statement: the output is a research layer, not an official warning. [Tonight: text]

## Questions for the Authors

- Did you know about the Landsat 9 image of 22 June before you scored the first referee version, and why was it not in that version?
- Has anyone in Valencian civil protection or the Júcar basin authority seen the idea? One conversation could show where, if anywhere, the map fits.

## Appendix

### How This Review Was Run

- Five AI-simulated reviewer roles read the paper: a Journal-Fit Reviewer (editor view), three peer reviewers (methods and statistics, radar and water physics, flood warnings and risk communication), and a Devil's Advocate who tries to break the main argument. An editorial synthesis then combined their reports.
- The dispatching session reports that each role ran as a separate instance of the same AI model family (Claude), each with a fresh context and without seeing the other reports. The synthesis used the same model family. No other AI model was used as a cross-check.
- The provenance record that should prove these facts could not be built (the tool is not installed), so these facts are reported, not verified.
- This letter is for reading. A re-review or the revision coach uses the decision package (editorial-decision.md), not this letter.

### Limits of This Review

- This review is AI-simulated. It is not calibrated against human reviewers.
- Because all reviewers are the same model family, their mistakes can be shared. When several reviewers agree, that is not independent proof. Please recompute every number a reviewer gives before you use it.
- The body of the paper, the abstract, Tables 1 to 4, and both appendices were read. Figure 1 was read as Mermaid text only; the drawn diagram was not seen. The paper has no map figures yet, and figures being made separately were not judged.
- The data files (numbers.md and the result files) are not part of the manuscript. Some reviewers opened them to check numbers; the panel as a whole did not review them.
- No target journal was chosen, so no journal-specific rules were applied.

### Reviewer Summaries

- Journal-Fit Reviewer: the finished checks are clear and honest, but the title, abstract, contributions, Table 1 and conclusion promise a model that does not exist yet; build it or re-frame the paper as a label check.
- Methods reviewer: the sample design and formulas are correct and repeatable, but the bounds are wrong, the wet area has no interval, the decided-only numbers hide many unclear points, and pre-registered really covers only the first referee version.
- Radar and water reviewer: the June gap depends mostly on where −15 dB cuts the rice backscatter and on DSWx-S1's rules; the dark class is not the flooded-plant signal; the DANA check used another threshold; and the L-band rice literature is missing.
- Flood-warning reviewer: the limits are written well, but the paper promises residents an answer it cannot give, plans a yes-or-no map that people may read as unshaded means safe, and calls its own new traffic light an existing alert.
- Devil's Advocate: the check shows a dark radar map agreeing with an optical wetness index in irrigated June rice, not that NISAR labels can teach where storm water goes; the planned labels were not checked, and the training period has no rain flood.

### Advisory Checks

- Acronym check: did not run (the script is not installed).
- Suggested-reference check: did not run (the script is not installed). The reviewers checked most suggested sources by web search; two were not checked.
- Reviewer claim check: did not run (the script is not installed).
- These checks do not change the decision.

### Item Map

| Item | Record ref |
|------|------------|
| 1 | R1 |
| 2 | R5 |
| 3 | R6 |
| 4 | R20 |
| 5 | R21 |
| 6 | R22 |
| 7 | R2 |
| 8 | R3 |
| 9 | R8 |
| 10 | R9 |
| 11 | R10 |
| 12 | R11 |
| 13 | R15 |
| 14 | R4 |
| 15 | R13 |
| 16 | R14 |
| 17 | R16 |
| 18 | R17 |
| 19 | R18 |
| 20 | R19 |
| 21 | R7 |
| 22 | R12 |
| 23 | S1 |
| 24 | S2 |
| 25 | S3 |
| 26 | S4 |
| 27 | S5 |
| 28 | S6 |
| 29 | S7 |
| 30 | S8 |
| 31 | S9 |
| 32 | S10 |
| 33 | S11 |
| 34 | S12 |
| 35 | S13 |
| 36 | S14 |
| 37 | S15 |
| 38 | S16 |
| 39 | S17 |
| 40 | S18 |
| 41 | S19 |
| 42 | S20 |
| 43 | S21 |
| 44 | S22 |
| 45 | S23 |
