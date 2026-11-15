# Seat: Peer Reviewer 3 (Perspective) — Phase 1 (paper-content-blind)

Written before the manuscript was opened. Inputs: contract `reviewer/reviewer_full/v2` and metadata only (title "Where will the water go? Learning flood extent in Valencia from the first months of NISAR L-band data"; field: SAR flood mapping with a public-warning application; about 6,500 words).

## Contract Paraphrase

D1 methodology_rigor: from where I sit, this asks whether the study design, the data handling and the reporting of results are solid enough that someone else could rerun the work and trust its numbers. It belongs to the methodology seat; I would only notice it where a design choice changes what a warning user can safely conclude.

D2 domain_accuracy: this asks whether the paper's claims match what the remote-sensing and hydrology evidence actually says, and whether earlier work and terms are described correctly. It belongs to the domain seat; my interest is limited to whether the description of official warning and flood-zone practice would be recognised by people who run those systems.

D3 argumentative_coherence: this asks whether the central thesis holds together and whether the evidence really carries the claims without logical leaps. It belongs to the devil's advocate and methodology seats; from my side the relevant question is whether practical claims about helping people follow from what was measured.

D4 cross_disciplinary_relevance: this is my dimension. It asks whether a reader from an adjacent field — here disaster-risk reduction, risk communication and emergency management — can understand the framing, the key definitions and the stated implications, and whether any claim that crosses into that field (for example, that an output would help residents or authorities) is backed by evidence or by literature from that field rather than asserted.

D5 writing_and_structure: this asks whether the manuscript is well organised, clearly written, has usable figures and tables, and follows venue conventions. It belongs to the journal-fit seat.

D6 venue_fit_and_contribution: this asks whether the paper fits the configured venue and makes an original, significant contribution for that venue's readers. It belongs to the journal-fit seat; with no confirmed venue I make no venue claim.

## Scoring Plan

### D4: cross_disciplinary_relevance
dimension_id: D4
what_to_look_for: Whether the warning-application framing defines its users and use, states what a map pixel or colour means to a non-expert, connects to official hazard maps and impact-based warning practice and risk-communication research, and states limits in plain terms where false reassurance could result.
what_triggers_block: The paper presents its output as fit for direct public warning or resident decision-making without evidence or cited risk-communication support, and does not disclose where the map is known to miss flooding, so a reader could take an unflagged dry area as safe.
what_triggers_warn: The application link is plausible and limits are stated, but the user, the alert meaning, the relation to official flood-zone maps or warning systems, or the plain-language framing of known failure areas is incomplete or left to expert inference.

criteria_binding_unavailable

[CONTRACT-ACKNOWLEDGED]

---

# Seat: Peer Reviewer 3 (Perspective) — Phase 2 (paper-visible)

Manuscript read: `docs/paper/review/manuscript-557e3fd.md` (read-only). Also read: `phase0-field-analysis.md`. The skill's Python checkers (`check_phase_conformance.py` and the others) are not installed and did not run. No target journal is confirmed (`criteria_binding_unavailable`), so this card makes no venue claim. Figures are being added separately and are not treated as a finding.

contract_role: perspective

## Dimension Scores

### D1: methodology_rigor
score: not_assessed

### D2: domain_accuracy
score: not_assessed

### D3: argumentative_coherence
score: not_assessed

### D4: cross_disciplinary_relevance
score: warn
trigger: "the user, the alert meaning, the relation to official flood-zone maps or warning systems, or the plain-language framing of known failure areas is incomplete or left to expert inference"

### D5: writing_and_structure
score: not_assessed

### D6: venue_fit_and_contribution
score: not_assessed

## Review Body

### Reviewer Identity
Peer Reviewer 3, cross-disciplinary / practical: a disaster-risk researcher working on impact-based flood warnings and on how residents read colour-coded alerts. I am an outsider to SAR physics and to sampling statistics and make no judgement on them; what I say about radar or accuracy numbers is taken from the authors' own text.

### Overall Recommendation
Major Revision.

### Confidence Score
3 — the warning and risk-communication points are within my remit; the paper's central model is not built yet, so I am judging a planned product, not a tested one.

Confidence is an uncertainty/scope disclosure only; it never changes consensus counts, severity, decision bearing, or arbitration.

### Calibration Status
`NOT_CALIBRATED`

### Criterion-Bound Judgements
| Dimension / criterion | Criterion source | Judgement | Evidence anchors | Rationale | Uncertainty or scope limit | Decision bearing? |
|---|---|---|---|---|---|---|
| D4 cross_disciplinary_relevance — framing and definitions readable by disaster-risk readers | Contract D4; Card #4 focus 1 and 3 | PARTLY_MEETS | text: §6.2 "not as an observed pattern"; text: §4.4 "probability of water given a rain scenario; shown in the app as" | Limits are written in plain words, but the product's user and what an unshaded area means are not defined | The display is not built yet; judged on the stated plan | yes — the public-warning framing is in the title, abstract and introduction |
| D4 — interdisciplinary claims substantiated | Contract D4; Card #4 focus 1 and 2 | DOES_NOT_MEET | absence: §2 and References — no warning or risk-communication source | The claim that a map helps residents is asserted, not supported by evidence or literature | A user study is not expected of a hackathon paper; a cited basis and softer claim would be | yes — repairable by reframing and citing |
| Significance & Impact (practical) | quality_rubrics.md Dimension 7; Card #4 | PARTLY_MEETS | text: §2 "fall between these tools" | A real gap (small rain-fed wetlands) is named; the practical benefit for people depends on §5.6, which is empty | Model results missing | yes — impact cannot be shown until §5.6 exists |
| Argument Coherence, Methodological Rigor, Evidence Sufficiency, Literature Integration, Writing Quality, Originality | quality_rubrics.md | NOT_ASSESSED | — | Other seats' remit | outside my role | no |

Do not total, weight, average, or mechanically map these judgements to the recommendation.

### Summary Assessment
The paper asks whether early NISAR L-band water maps can teach a model where water collects after rain around Valencia, so that a rain alert can be shown as a map of likely flooded places. The finished part is a careful, honest check of NISAR water against Sentinel-1 on one June date and one October storm; the flood-extent model itself is still a placeholder. From a warning and risk-communication view, the paper is unusually frank about its limits, and it rightly says official flood zones should stay the legal reference. The weakness is the public-warning framing. The opening promises residents an answer to "will my street flood", but the labels and tests sit in rice paddies and a marsh, and the authors themselves say labels in towns are unreliable. The planned display is a binary "likely flooded" layer, gated by the team's own new traffic light, which uses different thresholds from the official AEMET colours. Colour-coded maps of this kind are known to be read as "outside the shading means safe", which is exactly the false reassurance that matters most in built-up streets. None of this needs new data: it needs the user to be named honestly (civil protection, wetland and farm managers, not residents yet), the display rules to be written into the method, and the work to be placed inside the Spanish warning chain. I recommend Major Revision because the framing in the title, abstract and introduction needs substantial rewriting, and because the practical claim cannot be judged until §5.6 exists.

### S1: Limits written in plain words, including towns
§6.2 states each limit in one or two short sentences a non-expert can follow, and the towns item says what the map means there, not only that it is weaker. This is better than most flood-mapping papers I review.
**Evidence Anchor**: text: §6.2 Towns "not as an observed pattern"

### S2: Official zones kept as the legal reference
The paper says SNCZI and PATRICOVA should remain the legal basis and that they answer "can my house ever flood" better than this work. This avoids the common mistake of presenting a research layer as a replacement for official hazard maps.
**Evidence Anchor**: text: §2 "These are the legal reference for planning and should stay so"

### S3: Failures reported where users would care
The missed DANA peak, the alert never reaching red, and the failed strict referee are all reported in the main text. For anyone who later builds a public product from this, knowing where the system missed is the most useful information.
**Evidence Anchor**: text: §5.3 "catching the peak of a flood that lasts a few days is a matter of luck"

### S4: Test fixed in advance and run by someone other than the model's author
For a tool that might one day inform people, a test written before the model exists and run by a different person is good governance, not only good science.
**Evidence Anchor**: text: §4.5 "is run by a different team member (L. Georgieski) than the model's author"

### S5: A real gap between existing tools
Small rain-fed coastal wetlands and rain falling directly on rice are not covered by river-based forecasting, and the paper says so clearly (Table 1).
**Evidence Anchor**: text: §2 "fall between these tools"

### W1: The user promised in the introduction is not the user the evidence serves
**Problem**: The introduction is built around a resident asking about "my road, field or neighbourhood", and it recalls the 29 October 2024 DANA, whose deaths were mostly in built-up towns of l'Horta Sud hit by flash floods in ephemeral channels. The evidence, however, comes from Albufera rice and the Pego-Oliva marsh, where few people live, and §6.2 says labels in towns are unreliable. A 12-day repeat also cannot see flash floods that last hours.
**Evidence Anchor**: text: §1 Opening "Neither answers the question a resident actually has"
**Why it matters**: A reader from emergency management will take the opening as a claim that the method answers the 2024 question. It does not, and the authors know it does not. The mismatch invites over-trust by exactly the readers who might adopt the tool.
**Suggestion**: Keep the Erasmus anecdote, but say plainly that the method, as tested, speaks to slow-draining wetlands and fields, and that its first users would be civil-protection planners, wetland managers and farmers' water boards, not residents. State that urban flash floods like 2024 are out of scope for now. Move the "resident" goal to future work.
**Severity**: Major
**Confidence**: 4 — core expertise: warning audiences and flood types

### W2: A binary "likely flooded" layer invites reading unshaded places as safe
**Problem**: The planned output turns a probability into a single "likely flooded" class shown when the alert is amber or red. Nothing says what an unshaded pixel means, how towns (terrain-only prediction), "not analysed" areas or places outside the three sites are shown, or whether the probability is kept.
**Evidence Anchor**: text: §4.4 "probability of water given a rain scenario; shown in the app as"
**Why it matters**: Risk-communication research on hazard graphics shows that people treat the edge of a shaded area as a safety line (the hurricane "cone" case, Broad et al. 2007). A street outside the shading that floods is the false-reassurance and liability case. In towns the paper itself expects the model to be weakest.
**Suggestion**: Write display rules into §4.4 before the model lands: (a) at least three states — likely wet, no signal, and not assessed / unreliable (towns, outside sites, masked areas), with "no signal" never drawn as green or labelled safe; (b) a fixed sentence on the map: "Unshaded areas can still flood. Follow official warnings (112 / AEMET)."; (c) show PATRICOVA zones beneath the layer in towns instead of a terrain-only guess; (d) keep the probability in a few bands rather than one cut. If any public display is planned, test it with a handful of non-expert users first (Hagemeier-Klose and Wagner 2009; Meyer et al. 2012 describe practical methods).
**Severity**: Major
**Confidence**: 4 — core expertise: map-based warning interpretation

### W3: "An existing rain alert" is in fact a new traffic light with different thresholds
**Problem**: The abstract says an existing alert will be shown as a map, and §1 describes AEMET yellow/orange/red (60/100/180 mm in 12 h). §4.6, however, builds the team's own traffic light from a 3-day total (amber 50 mm, red 100 mm, from IFS 9 km). A resident would then see two colour schemes with the same names and different meanings, plus ES-Alert messages from civil protection.
**Evidence Anchor**: text: §4.6 "a traffic light per site from the largest 3-day rain total"
**Why it matters**: Consistency between warning sources is one of the strongest factors in whether people act (Mileti and Sorensen 1990). An app showing amber while AEMET shows orange, or the reverse, can delay action or reduce trust in both. The same section reports the alert stayed amber for DANA "Adam", so the colour would have been milder than the event.
**Suggestion**: Either drive the map from the official AEMET level itself (which matches the abstract's wording), or rename the team's signal so it cannot be confused with official colours (for example "rain scenario: 50 mm / 100 mm in 3 days") and correct the abstract. State in §4.6 that the official warning always takes precedence.
**Severity**: Major
**Confidence**: 4 — core expertise: colour-coded warning systems

### W4: The work is not placed inside the Spanish warning chain or the impact-based warning literature
**Problem**: §2 covers hazard maps (SNCZI, PATRICOVA) and river forecasts, but not who issues flood warnings in Valencia and what they use: the regional civil-protection Special Flood Plan (Decree 81/2010) and the municipal action plans that sit under it, the Júcar basin authority's real-time hydrological data (SAIH Júcar), the 112 Comunitat Valenciana as issuer of ES-Alert, or the flood risk maps (not only hazard zones) produced under the EU Floods Directive and Royal Decree 903/2010. It also cites no work on impact-based warnings, the move the paper is implicitly making from "how much rain" to "what will flood".
**Evidence Anchor**: absence: §2 and References — expected civil-protection warning chain and impact-based warning literature; checked §1, §2, Table 1, §6.1, References
**Why it matters**: Readers from emergency management will ask "who would use this, and where does it plug in?" Without this, the practical claim reads as a gap that official systems have already partly filled.
**Suggestion**: Add one paragraph to §2 naming these actors, and one row or column to Table 1 ("Who issues it / who acts on it"). Cite WMO-No. 1150 (2015) for impact-based warnings and Potter et al. (2018), which found impact-based warnings changed risk perception more than intended action — a useful caution for the paper's own claim.
**Severity**: Minor
**Confidence**: 3 — adjacent field: Spanish civil-protection structures checked by web search, not by practice

### W5: The pre-registered score treats a missed flooded street the same as a false alarm
**Problem**: The test in §4.5 rules on F1, which weighs misses and false alarms equally. For a warning product, a miss (map says nothing, street floods) costs far more than a false alarm. The EMSR935 observed layer comes from optical imagery, which tends to under-map flooded streets between buildings, so urban misses may not be visible to the test at all.
**Evidence Anchor**: text: §4.5 "The model is said to add value if its F1 beats all three baselines"
**Why it matters**: A model can win on F1 and still miss the places that matter most for people.
**Suggestion**: Keep the pre-registered rule unchanged, but report as context (clearly outside the rule) the share of the observed flood that the model misses, split by land use (built-up, roads, farmland, marsh), and say where EMSR935 has "not analysed" or built-up gaps. §5.6 already plans a towns split; extend it to misses.
**Severity**: Minor
**Confidence**: 3 — adjacent field: warning verification practice; the scoring statistics belong to Reviewer 1

### W6: Deliberately flooded paddies may fill the "likely flooded" map and wear out attention
**Problem**: The paper notes that water in the Albufera rice is often farm water, managed by people, not a flood. A model trained on these labels may mark much of the rice as "likely flooded" whenever it rains during the flooded season.
**Evidence Anchor**: text: §3.1 "here is often farm water, not a flood"
**Why it matters**: A warning map that is mostly shaded over places that are always wet tells users little and trains them to ignore it (the "cry-wolf" concern discussed by Mileti and Sorensen 1990). Farmers and the bodies that operate the paddy gates are stakeholders who know when water is deliberate, but they are not mentioned.
**Suggestion**: In §4.4 or §6.2, say how farm water is handled in the display (for example, show only water beyond the usual seasonal level), and name farmers' water management as both a confounder and a possible source of ground truth.
**Severity**: Minor
**Confidence**: 3 — adjacent field: stakeholder analysis; the labelling details belong to Reviewer 2

### W7: The map is hidden whenever the coarse "when" signal stays low
**Problem**: The map is shown only when the alert is amber or red. §5.5 reports that the 9 km forecast smoothed DANA "Adam" and never reached red. If the "when" signal under-warns, the "where" map is never shown at all.
**Evidence Anchor**: text: §5.5 "amber two to three days ahead, never red"
**Why it matters**: Gating a hazard map on a signal known to miss local extremes turns a timing error into a silent absence of information.
**Suggestion**: State this dependency in §6.2 in plain words, and consider showing the map for fixed rain scenarios at all times, with the alert only highlighting which scenario is currently forecast.
**Severity**: Minor
**Confidence**: 3 — core expertise: warning design; forecast skill outside my remit

### W8: Public-facing claims rest on a missing citation and a secondary news source
**Problem**: The 2024 DANA sentence carries "[citation needed: official report]", and the description of the ES-Alert message for DANA "Adam" is sourced to a French-language news article rather than the official message.
**Evidence Anchor**: text: §1 Opening "[citation needed: official report]"
**Why it matters**: Statements about what the authorities told residents are sensitive; readers from the warning community will want the primary text.
**Suggestion**: Cite the official ES-Alert text (112 Comunitat Valenciana / Generalitat) and an official or peer-reviewed account of the 2024 event.
**Severity**: Minor
**Confidence**: 4 — core expertise: sourcing of warning records

### Detailed Comments

#### Assumption Audit
- **Explicit assumptions**: That rain, terrain and land cover explain where water collects; that NISAR passes are honest labels (tested, and bounded by the strict referee). The paper is clear that official zones stay the reference.
- **Implicit assumptions**: (1) That giving residents a map will lead to better action. Warning research suggests the link from information to action is weak and depends on trust, consistency and personal relevance (Potter et al. 2018 found perception changed more than intended action). (2) That "where water collects" is the same as "where it is dangerous". Impact depends on depth, speed and exposure; a shallow wet paddy and a fast-flowing street are both "water" in this framework. (3) That the "when" signal is good enough to gate the "where" map (W7).
- **Paradigmatic assumptions**: The paper treats flooding as a physical extent to be predicted per pixel. Impact-based warning practice treats it as hazard times exposure times vulnerability. Adding even a simple exposure layer (buildings, roads) would make the output speak the language of the warning community.

#### Cross-Disciplinary Connections
- **Parallel research**: Studies of how the public reads flood hazard maps and web maps (Hagemeier-Klose and Wagner 2009; Meyer et al. 2012) and of hazard-graphic misreading (Broad et al. 2007) bear directly on the planned display.
- **Borrowing opportunities**: The impact-based warning framework (WMO-No. 1150) offers a ready vocabulary for the "when / where" split the paper already uses: the rain alert is the hazard forecast, the map is a step toward impact.
- **Methodological borrowing**: A short think-aloud test with five to ten non-expert users of a mock-up map is cheap and would catch the "unshaded means safe" reading before release.

#### Practical Impact
- **Real-world application**: The most realistic near-term users are regional civil protection, the Albufera and Pego-Oliva wetland managers, and farmers' water boards, who would use the layer as planning context, not as a warning.
- **Implementation feasibility**: The 12-day repeat and five months of data mean the model cannot yet be trusted for timing; the paper says so. Integration would require agreement with the bodies that issue warnings, which the paper does not discuss.
- **Stakeholders**: Missing voices are civil-protection operators, municipal emergency planners, farmers and paddy-gate operators, and people less familiar with local warnings (visitors, students, non-Spanish speakers — the authors' own opening example). Reports after 2024 indicate many victims were found on ground floors, in garages and car parks [UNVERIFIED — figures differ between sources]; a map of fields and marshes does not address that exposure.

#### Broader Implications
- **Ethical dimensions**: The main ethical risk is false reassurance. The ethics statement covers data use only; it should also say the output is not an official warning and must not be presented as one.
- **Social impact**: A clearly scoped tool for wetland and farm planning carries little risk; a resident-facing map without the safeguards in W2 and W3 could cause harm in the place where the model is weakest.
- **Future directions**: Exposure-weighted evaluation; co-design of the display with Valencian civil protection; testing against municipal flood records in towns, where satellites are weakest.

### Cross-Disciplinary Reading Recommendations
- Broad, K., Leiserowitz, A., Weinkle, J., Steketee, M. (2007). Misinterpretations of the "cone of uncertainty" in Florida during the 2004 hurricane season. *Bulletin of the American Meteorological Society* 88, 651–668. Existence confirmed by web search. Classic evidence that the edge of a shaded hazard area is read as a safety line.
- Hagemeier-Klose, M., Wagner, K. (2009). Evaluation of flood hazard maps in print and web mapping services as information tools in flood risk communication. *Natural Hazards and Earth System Sciences* 9, 563–574. Confirmed. How lay users read flood maps; they find gauge levels easier than return periods.
- Meyer, V., Kuhlicke, C., Luther, J., et al. (2012). Recommendations for the user-specific enhancement of flood maps. *Natural Hazards and Earth System Sciences* 12, 1701–1716. Confirmed. Separate map designs for planners, emergency managers and the public.
- Potter, S.H., Kreft, P.V., Milojev, P., et al. (2018). The influence of impact-based severe weather warnings on risk perceptions and intended protective actions. *International Journal of Disaster Risk Reduction*. Existence confirmed; volume and pages not confirmed.
- WMO (2015). *WMO Guidelines on Multi-hazard Impact-based Forecast and Warning Services*, WMO-No. 1150. Confirmed.
- Mileti, D.S., Sorensen, J.H. (1990). *Communication of Emergency Public Warnings: A Social Science Perspective and State-of-the-Art Assessment*. ORNL-6609, Oak Ridge National Laboratory. Confirmed. Warning consistency, credibility and the "cry-wolf" question.
- Spanish context (legal texts, not scholarly works): Decree 81/2010 of the Consell (Valencian Special Flood Plan); Royal Decree 903/2010 (flood risk evaluation and management, transposing Directive 2007/60/EC). Both confirmed by web search; check whether the Valencian plan has since been replaced before citing it as current.

~~~yaml suggested-references
- title: "Misinterpretations of the \"cone of uncertainty\" in Florida during the 2004 hurricane season"
  authors: ["Broad, K.", "Leiserowitz, A.", "Weinkle, J.", "Steketee, M."]
  year: "2007"
  doi: null
  arxiv_id: null
- title: "Evaluation of flood hazard maps in print and web mapping services as information tools in flood risk communication"
  authors: ["Hagemeier-Klose, M.", "Wagner, K."]
  year: "2009"
  doi: "10.5194/nhess-9-563-2009"
  arxiv_id: null
- title: "Recommendations for the user-specific enhancement of flood maps"
  authors: ["Meyer, V.", "Kuhlicke, C.", "Luther, J."]
  year: "2012"
  doi: "10.5194/nhess-12-1701-2012"
  arxiv_id: null
- title: "The influence of impact-based severe weather warnings on risk perceptions and intended protective actions"
  authors: ["Potter, S.H.", "Kreft, P.V.", "Milojev, P."]
  year: "2018"
  doi: null
  arxiv_id: null
- title: "WMO Guidelines on Multi-hazard Impact-based Forecast and Warning Services (WMO-No. 1150)"
  authors: ["World Meteorological Organization"]
  year: "2015"
  doi: null
  arxiv_id: null
- title: "Communication of Emergency Public Warnings: A Social Science Perspective and State-of-the-Art Assessment"
  authors: ["Mileti, D.S.", "Sorensen, J.H."]
  year: "1990"
  doi: null
  arxiv_id: null
~~~

### Questions for Authors
1. Who is the first intended user of the map — residents, civil protection, or wetland and farm managers — and would the team accept naming that user in the title or abstract?
2. What will the app show for a street in a town where the prediction rests on terrain and rain alone: a coloured layer, a "not assessed" mark, or the PATRICOVA zone?
3. Will the map be driven by the official AEMET level or by the team's own 3-day traffic light? If the latter, how will the app avoid conflicting with AEMET colours and ES-Alert messages?
4. Has anyone in Valencian civil protection or the Júcar basin authority seen the idea? A single conversation would tell you where (if anywhere) it fits.

### Minor Issues
- §1: "yellow, orange and red" (AEMET) and "amber, red" (§4.6) use different names for colour levels; pick wording that keeps them clearly apart.
- §6.2 would read better for non-experts if each limit ended with one short "what this means for a map user" clause, as the towns item already does.
- Ethics statement: add one line that the output is a research layer, not an official warning.
