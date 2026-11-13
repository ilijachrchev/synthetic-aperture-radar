# Research

> Snapshot from 13 Nov 2026, for team planning. Short on purpose.
> ✔ = checked against primary data or two independent sources · ~ = one source · ? = our guess
> Drafted with an SI assistant (see the README). This file is evidence, not the idea: the team picks the concept (Space Apps rule).

## 1. Rules that shape everything

- **SI rule:** SI must not come up with the idea. Describe all SI use, watermark SI images and video, flag SI code and data in text and metadata. ✔
- **Demo:** a video of 30 seconds or less, **or** at most 7 slides, in English (a video may use another language with English subtitles). Going over the limit means no global judging. ✔
- **Links:** public, no login needed. This repo is private today, so it must be made public before we submit. ✔
- **Valencia timing:** hackathon started Fri 20:30. Jury presentations Sun 16:00. Awards 18:30. ✔
- **Judging criteria:** impact, creativity, validity, relevance, presentation. ✔

## 2. NISAR data that exists

| Maturity | Acquisitions | Use it for |
|---|---|---|
| BETA | Oct 2025 to Jan 2026 (subset) | Nothing: not calibrated |
| PROVISIONAL | 17 Jun to 21 Oct 2026, plus 302 frames back to Oct 2025 | Main time series |
| VALIDATED | 21 Oct 2026 onward | Newest scenes; GUNW has barely started (tracks 139 to 141 only) |

- **Products:** GCOV is radar brightness, HH and HV, 20 m, already on a map grid, 1 to 7 GB per file. GUNW is 12-day ground-motion pairs, 80 m, about 2 GB. ✔
- **Revisit:** 12 days per track, 2 to 4 tracks per site. Permanent gap 27 Jul to 10 Aug 2026, bridged by 24 and 36-day pairs. ✔
- **Access:** free Earthdata login. Files are cloud-optimized, so we stream a small area over HTTPS (about 1 min per layer ~). Never download whole files. ✔
- **No login needed:** NASA's CMR search and the preview PNGs, both readable from a browser (CORS). A preview can be placed on the map within 1 to 5 px by fitting its 4 corners to the frame outline. ✔
- **Not available:** soil moisture (SME2) after 21 Oct, glacier offsets (GOFF) over Spain. GIBS NISAR map tiles break at zoom 12 and above (fine at 10 and below). ✔
- **Gotchas:** only compare the same track, frame and mode (2005 vs 4005; some dates are HH only). Valencia straddles UTM zones 30 and 31. GUNW ships ionosphere, troposphere and tide corrections but does not apply them, and ionosphere stripes are not ground motion. ✔
