# Field Analysis Report (academic-paper-reviewer, Phase 0)

*Reviewed file: `docs/paper/paper.md` at the commit that adds this report. Skill: academic-paper-reviewer v1.11.1 (imbad0202/academic-research-skills), installed as text only; its Python checker scripts are not run in this install, so the script-based attachments (acronym check, suggested-reference check, reviewer claim check, panel synthesis checker) will each say they did not run.*

## Paper Basic Information
- **Title**: Where will the water go? Learning flood extent in Valencia from the first months of NISAR L-band data
- **Abstract length**: about 320 words
- **Full text length**: about 6,500 words (including tables and appendices)
- **Number of references**: 16

## Field Analysis

| Dimension | Analysis Result |
|-----------|----------------|
| Primary Discipline | Remote sensing of surface water (SAR flood mapping) |
| Secondary Disciplines | Hydrology / flood-hazard mapping; applied machine learning on rasters; disaster-risk communication |
| Research Paradigm | Quantitative |
| Methodology Type | Accuracy assessment by stratified sampling (validation study) + statistical modelling / machine learning (planned flood-extent model) |
| Target Journal Tier | `criteria_binding_unavailable`. Field-general observation: a hackathon technical report written in the structure of a short remote-sensing journal article |
| Paper Maturity | First draft: complete structure and results for the validation parts; the central model (§4.4, §5.6) is still a placeholder |

## Target Journal
`criteria_binding_unavailable`. No venue was confirmed by the authors.

## Coverage

| Part | Status |
|------|--------|
| Body sections 1–7 | read |
| Abstract | read |
| Table 1 (NISAR maturity) | read |
| Table 2 (strata) | read |
| Table 3 (accuracy on 18 June) | read |
| Figure 1 (pipeline, Mermaid text) | read (as text; the rendered diagram was not viewed) |
| Map figures | none (the paper has no map figure yet; §5.6 plans one) |
| Appendices A (self-review) and B (claim–evidence map) | read |
| Supplementary files cited (`numbers.md`, result JSON files) | not read by the panel: they are data files, not part of the manuscript; reviewers may ask for them |

## Reviewer Configuration Cards

### Reviewer Configuration Card #1

**Role**: EIC
**Display role**: Journal-Fit Reviewer
**Identity Description**: Senior remote-sensing scholar with editorial experience in SAR applications and operational Earth-observation products.
**Review Focus**:
  1. Check whether the contribution claimed in the Introduction is supported by results present in this draft, given that the flood-extent model is a placeholder [§1 Contributions; §4.4; §5.6].
  2. Check whether the title and abstract promise more than the results deliver [Title; Abstract].
  3. Check whether the paper's positioning against operational products (DSWx-S1, Copernicus EMS) is fair [§2].
**Will particularly care about**: Whether a paper whose central model is not yet built can be framed as "learning flood extent", or should be framed as a label-validation study.
**Possible blind spots**: Statistical detail of the sample design.

### Reviewer Configuration Card #2

**Role**: Peer Reviewer 1
**Display role**: Peer Reviewer 1 — Methodology
**Identity Description**: Statistician specialising in design-based accuracy assessment of land-cover and change maps (stratified estimators, bootstrap intervals, treatment of unresolved reference labels).
**Review Focus**:
  1. Check the stratified estimators and the handling of "unclear" points (decided-only estimates vs bounds), including why the NISAR producer's estimate lies outside its own bounds [§4.3; Table 3].
  2. Check whether the referee is independent of the maps scored and whether the rule change from v1 to v2 after seeing v1 results weakens the pre-registration claim [§4.3 transparency note].
  3. Check whether the derived wet-rice area (decided points only) is reported with appropriate uncertainty [§5.1].
**Will particularly care about**: That 101 of 150 points in the key stratum are unclear, and what that does to the headline numbers.
**Possible blind spots**: SAR physics and hydrology.

### Reviewer Configuration Card #3

**Role**: Peer Reviewer 2
**Display role**: Peer Reviewer 2 — Domain (SAR water and flood mapping)
**Identity Description**: SAR hydrology researcher working on L- and C-band detection of open water and flooded vegetation in agricultural wetlands.
**Review Focus**:
  1. Check whether a single −15 dB HH threshold is appropriate for L-band water among young rice, and whether the flooded-vegetation rule (HH +3 dB, HV flat) is described enough to reproduce [§4.2].
  2. Check whether the interpretation of the strict-referee result (water under plants vs wet mud) is supported or only one of several explanations [§5.1].
  3. Check literature coverage on L-band rice/flood studies and SAR flood products [§2] [unverified].
**Will particularly care about**: Whether "NISAR sees water Sentinel-1 misses" is distinguished from "NISAR's threshold is darker-biased in June".
**Possible blind spots**: Sampling statistics; end-user communication.

### Reviewer Configuration Card #4

**Role**: Peer Reviewer 3
**Display role**: Peer Reviewer 3 — Cross-disciplinary / Practical (flood-risk communication and early warning)
**Identity Description**: Disaster-risk researcher on impact-based flood warnings and how residents interpret colour-coded alerts.
**Review Focus**:
  1. Check whether the proposed "alert shown as a map of likely flooded places" would help or mislead residents, especially in towns where the paper says labels are unreliable [§1; §6.2 Towns].
  2. Check how the work relates to official flood-zone maps and impact-based warning systems that already exist in Spain [§2] [unverified].
  3. Check whether the limits are communicated in a way a non-expert reader would understand [§6.2].
**Will particularly care about**: Liability and false reassurance: a map that says "dry" for a street that floods.
**Possible blind spots**: Radar physics; statistics.

## Review Strategy Recommendations
- The draft has two parts with different maturity: a finished validation study and an unfinished model. Reviewers should judge the finished part on its merits and state what the unfinished part needs, not penalise placeholders as errors.
- Tension to expect: Reviewer 1 may find the validation sound but narrow (one date, many unclear points); Reviewer 3 may find the practical story the strongest part. The Devil's Advocate seat (fixed, not configured here) should test the core argument "NISAR water is a good label for where water goes".
