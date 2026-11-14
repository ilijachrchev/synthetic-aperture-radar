# SAR primer

What you need to know about radar to work on this project, and how each idea maps to our code and data. Written for the prediction work, but useful for everyone.

## 1. What SAR is

**Synthetic Aperture Radar** is a satellite that sends microwave pulses sideways at the ground and records the echo. It brings its own illumination, so it works **day and night and through clouds**. It is not a camera: it does not see colour, heat or infrared. It measures two things per pixel:

| Measured | What it means | Our product |
|---|---|---|
| **Amplitude** (how strong the echo is) | Roughness, structure and wetness of the surface | **GCOV**: radar brightness, 20 m |
| **Phase** (where in its wave cycle the echo returned) | The exact distance to the ground, to a fraction of the wavelength | **GUNW**: ground motion between two dates, 80 m |

"Synthetic aperture" is the trick that gives it detail: the satellite combines echoes collected along hundreds of metres of its orbit as if it had one giant antenna.

## 2. NISAR and L-band

NISAR (NASA and ISRO) carries an **L-band** radar, wavelength **λ ≈ 24.4 cm**. Most free radar you have seen (Sentinel-1, and EGMS, which is built from it) is **C-band**, λ ≈ 5.5 cm.

Longer waves go deeper:

- L-band passes through leaves and reaches trunks and the ground below. That is why NISAR can see **water under vegetation** (flooded rice, marsh) that Sentinel-1 misses.
- L-band stays **coherent** longer over vegetation and farmland, so ground motion can be measured where C-band loses the signal.

Revisit: the same spot is imaged every **12 days** from the same orbit. Over Spain the data starts in **June 2026**, so each track has only about 11 dates. **Long history must come from other sensors** (EGMS, Sentinel-1 water maps, GNSS).

## 3. Brightness (GCOV): what the echo strength tells you

The pulse leaves the satellite at an angle. What comes back depends on the surface:

| Surface | What happens to the pulse | Brightness |
|---|---|---|
| Calm water | Reflects away like a mirror (specular) | **Very dark** |
| Rough ground, crops | Scatters in all directions, some returns | Medium |
| Forest | Bounces around inside the canopy (volume scattering) | Medium-bright, strong in **HV** |
| Flooded vegetation, buildings | Water/ground → stem/wall → back to satellite (**double bounce**) | **Very bright** in HH |
| Burned forest | Canopy gone, less volume scattering | **HV drops** |

**Polarization.** The radar sends and receives horizontally (H) or vertically (V) oriented waves. **HH** (send H, receive H) is sensitive to surfaces and double bounce. **HV** (send H, receive V) only happens when the wave is scrambled, mostly inside vegetation. So HH finds water; HV finds plants.

**Units.** GCOV stores **linear power** (gamma0). Humans and thresholds work in **decibels**: dB = **10·log10(power)** (not 20: it is already power). Average and filter in linear units; convert to dB at the end. Our stacks keep linear power; `pipeline.cv.data.to_db` converts.

**Speckle.** Each pixel is the sum of many small echoes that interfere randomly, so radar images look grainy even over a uniform field. That is why CV uses a 5×5 filter before thresholding.

**Confounders.** Wind roughens water and makes it bright. Rain wets soil and brightens it. Steep slopes facing the radar are bright, slopes facing away are dark or hidden (layover and shadow). A newer processing version (PROVISIONAL → VALIDATED) can shift brightness slightly: that is Luka's point 1 in PR #5.

## 4. Phase (GUNW): measuring ground motion

The radar knows its wave cycle precisely. Compare the phase of the same pixel on two dates and any difference means the distance changed:

```
d = -λ / (4π) · Δφ        (λ ≈ 24.4 cm for NISAR)
```

The 4π (not 2π) is because the wave travels there **and back**. One full colour cycle in an interferogram (a **fringe**, Δφ = 2π) is therefore **λ/2 ≈ 12.2 cm** of motion. Millimetre precision is possible with good data.

Words you will meet:

- **Interferogram**: the phase difference between two dates. GUNW = Geocoded **Unwrapped** iNterferogram, one per pair of dates (12, 24 or 36 days apart).
- **Wrapped vs unwrapped**: raw phase only goes 0 to 2π, then restarts. **Unwrapping** counts the full cycles to get continuous motion. Where unwrapping fails, regions are split into separate **connected components**; motion is only comparable inside one component.
- **Coherence** (0 to 1): how similar the two echoes are. High on rock, cities and dry fields; low on water, moving vegetation, freshly ploughed land. Low-coherence pixels are noise: mask them.
- **Line of sight (LOS)**: radar only measures motion **toward or away from the satellite**, along its slanted viewing direction. It is **not vertical**. Ground sinking 1 cm shows up as roughly 0.7 to 0.9 cm of LOS motion depending on the angle. **Never subtract a vertical series (GNSS up, EGMS vertical) from a LOS series directly**: project one into the other first.
- **Ascending vs descending**: the satellite passes northbound (ascending, A) and southbound (descending, D), looking from opposite sides. With both, you can split LOS into **vertical and east-west**. Lorca has GUNW on **159 A** (19 files), **66 D** (16) and **167 D** (15), so this is possible.
- **Reference point**: an interferogram only gives *relative* motion. Pick a stable pixel (or the GNSS station) and subtract it, or everything floats.
- **Atmosphere and ionosphere**: water vapour delays the wave (troposphere) and charged particles bend it (ionosphere: worse at L-band). These look like motion but are not. GUNW **ships correction layers but does not apply them**: we must apply them ourselves. Ionosphere stripes are a classic false signal.
- **Chaining pairs**: 12-day pairs added head to tail give a time series. NISAR has a permanent gap 27 Jul to 10 Aug 2026, bridged with 24 and 36-day pairs. Tools like MintPy do this as a network inversion.

## 5. Tracks, frames and why we never mix them

An orbit is a **track** (e.g. 066), a cut along it is a **frame** (e.g. 069), and the direction is A or D. Our stack IDs read `track_direction_frame`, e.g. `066_D_069`. Each track sees the ground from a different angle, so brightness and LOS direction differ: **compare only the same track, frame and mode**. That is why there is one stack per site **and track**.

Processing versions: **PROVISIONAL** (Jun to 21 Oct 2026) and **VALIDATED** (21 Oct onward). Each date records its `crid` and `maturity` so you can filter.

## 6. The other sensors we lean on

| Source | What it is | Role for prediction |
|---|---|---|
| **EGMS** (European Ground Motion Service) | C-band Sentinel-1 InSAR processed over all of Europe: millions of points with motion time series every 6 days, 2020 to 2025. **Ortho** products are already split into **vertical** and east-west, on a 100 m grid | The **long history** to train and backtest the Lorca forecast |
| **GNSS** (GPS station LOR1) | A fixed antenna measuring its own 3-D position daily, mm-level, since 2009 | **Ground truth** at one point; anchors EGMS and NISAR |
| **OPERA DSWx-S1** | Water maps made from Sentinel-1 every few days since 2024, 30 m: not water / open water / inundated vegetation | The **history** for the Albufera flooded-area forecast |
| **NISAR GUNW** | L-band motion, Jun to Oct 2026 | **Independent check** of the Lorca forecast: a different satellite, wavelength and processing chain |

## 7. How this maps to our forecasts

**Lorca (ground sinking).** Groundwater pumping makes the Alto Guadalentín basin sink, historically over 10 cm/yr and about 4 cm/yr at LOR1 recently. That is slow and steady, plus a yearly cycle (pumping and recharge), so **trend + annual sine** is the physically sensible model. We train on EGMS/GNSS history, forecast Jun to Oct 2026, then compare with what NISAR measured. Matching geometry (vertical vs LOS) and applying the GUNW corrections are the hard part.

**Albufera (flooded area).** The rice fields are flooded on purpose every year (around November to January, and for planting in spring). That repeats, so a **day-of-year climatology** from the Sentinel-1 water history plus "how far from normal are we right now" is honest and checkable. It is **not** a disaster flood: never call it one.

**What we do not predict:** earthquakes (nobody can), floods from rain (that needs weather forecasts, not radar), soil moisture (signal fades in about 4 days, revisit is 12).

## 8. Further reading

- ASF NISAR docs, phase and interferometry: https://nisar-docs.asf.alaska.edu/phase/
- NASA ARSET / ESA "SAR basics" courses (free, beginner level)
- EGMS product description: https://eea.github.io/CLMS_documents/develop/products/European_Ground_Motion_Service_Product_Description_v3.html
- Our own facts and traps: [RESEARCH.md](RESEARCH.md) §2, §5, §6, §8

<sub>Drafted with SI assistance (Claude Code) from the team's RESEARCH.md, MODELS.md and PR discussions.</sub>
