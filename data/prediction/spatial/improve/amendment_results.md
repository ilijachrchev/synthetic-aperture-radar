**Variant 6, development check** (new-water F1 at 20 m on the held-back blocks of every development target, frozen threshold; the setting is chosen on the mean of the two sites)

| setting | mean F1 | Albufera F1 | hit | false alarms | Pego-Oliva F1 | hit | false alarms |
|---|---|---|---|---|---|---|---|
| min0px (chosen) | 0.4133 | 0.3747 | 46 % | 68 % | 0.4519 | 64 % | 65 % |
| min3px | 0.4037 | 0.3641 | 43 % | 69 % | 0.4433 | 61 % | 65 % |
| min5px | 0.3923 | 0.3520 | 40 % | 69 % | 0.4327 | 58 % | 66 % |
| min10px | 0.3742 | 0.3326 | 36 % | 69 % | 0.4159 | 53 % | 66 % |
| min0px_majority | 0.3518 | 0.3094 | 31 % | 69 % | 0.3942 | 47 % | 66 % |
| min3px_majority | 0.3484 | 0.3057 | 30 % | 69 % | 0.3910 | 46 % | 66 % |
| min25px | 0.3468 | 0.3027 | 30 % | 69 % | 0.3909 | 47 % | 66 % |
| min5px_majority | 0.3438 | 0.3007 | 29 % | 69 % | 0.3868 | 45 % | 66 % |
| min10px_majority | 0.3320 | 0.2881 | 27 % | 69 % | 0.3759 | 42 % | 66 % |
| min25px_majority | 0.3122 | 0.2663 | 24 % | 70 % | 0.3581 | 39 % | 67 % |

**Variant 6 on the held-out window** (`mono_neigh+blend`; with min3px (not chosen, information only); scored once)

*Albufera*

| | AP 20 m | hit | false alarms | AP 250 m | hit | false alarms |
|---|---|---|---|---|---|---|
| whole window: without the filter | 0.483 | 68 % | 60 % | 0.411 | 76 % | 56 % |
| whole window: with min3px (not chosen, information only) | 0.478 | 66 % | 60 % | 0.411 | 73 % | 56 % |
| DANA passes, 22 and 23 Oct: without the filter | 0.676 | 73 % | 41 % | 0.627 | 79 % | 37 % |
| DANA passes, 22 and 23 Oct: with min3px (not chosen, information only) | 0.675 | 72 % | 41 % | 0.627 | 78 % | 36 % |
| 22 Oct, forecast rain of 17 Oct: without the filter | 0.677 | 69 % | 36 % | 0.620 | 75 % | 31 % |
| 22 Oct, forecast rain of 17 Oct: with min3px (not chosen, information only) | 0.675 | 68 % | 36 % | 0.620 | 73 % | 30 % |

*Pego-Oliva*

| | AP 20 m | hit | false alarms | AP 250 m | hit | false alarms |
|---|---|---|---|---|---|---|
| whole window: without the filter | 0.343 | 62 % | 72 % | 0.252 | 68 % | 69 % |
| whole window: with min3px (not chosen, information only) | 0.336 | 59 % | 73 % | 0.251 | 65 % | 69 % |
| DANA passes, 22 and 23 Oct: without the filter | 0.416 | 48 % | 55 % | 0.370 | 53 % | 49 % |
| DANA passes, 22 and 23 Oct: with min3px (not chosen, information only) | 0.413 | 47 % | 55 % | 0.370 | 52 % | 49 % |
| 22 Oct, forecast rain of 17 Oct: without the filter | 0.343 | 39 % | 62 % | 0.311 | 45 % | 57 % |
| 22 Oct, forecast rain of 17 Oct: with min3px (not chosen, information only) | 0.341 | 38 % | 63 % | 0.311 | 43 % | 57 % |

**Fit, then test** (the fit version learned from Albufera's held-out passes; Pego-Oliva never entered a fit or a choice; terrain only is the fit version's own terrain half; frozen = the chosen `mono_neigh+blend` without the October passes)

| | AP 20 m | hit | false alarms | AP 250 m | hit | false alarms |
|---|---|---|---|---|---|---|
| (a) Albufera, DANA passes, fitted fit version | 0.736 | 84 % | 45 % | 0.669 | 89 % | 42 % |
| terrain only | 0.706 | 74 % | 40 % | 0.645 | 80 % | 36 % |
| past wet share | 0.537 | 4 % | 60 % | 0.506 | 5 % | 41 % |
| frozen, no October | 0.676 | 73 % | 41 % | 0.627 | 79 % | 37 % |
| (a) Albufera, whole window, fitted fit version | 0.589 | 78 % | 61 % | 0.497 | 84 % | 57 % |
| terrain only | 0.530 | 70 % | 62 % | 0.446 | 77 % | 58 % |
| past wet share | 0.329 | 8 % | 65 % | 0.261 | 12 % | 49 % |
| frozen, no October | 0.483 | 68 % | 60 % | 0.411 | 76 % | 56 % |
| (b) Pego-Oliva, DANA passes, test fit version | 0.444 | 55 % | 56 % | 0.390 | 62 % | 50 % |
| terrain only | 0.425 | 49 % | 55 % | 0.372 | 55 % | 49 % |
| past wet share | 0.388 | 20 % | 62 % | 0.356 | 25 % | 51 % |
| frozen, no October | 0.416 | 48 % | 55 % | 0.370 | 53 % | 49 % |
| (b) Pego-Oliva, whole window, test fit version | 0.364 | 65 % | 73 % | 0.267 | 72 % | 69 % |
| terrain only | 0.323 | 61 % | 73 % | 0.237 | 67 % | 69 % |
| past wet share | 0.315 | 41 % | 69 % | 0.232 | 47 % | 63 % |
| frozen, no October | 0.343 | 62 % | 72 % | 0.252 | 68 % | 69 % |
| (c) Pego-Oliva, 22 Oct, forecast rain, test fit version | 0.374 | 48 % | 62 % | 0.330 | 55 % | 56 % |
| terrain only | 0.359 | 43 % | 62 % | 0.315 | 49 % | 56 % |
| past wet share | 0.326 | 15 % | 72 % | 0.307 | 20 % | 63 % |
| frozen, no October | 0.343 | 39 % | 62 % | 0.311 | 45 % | 57 % |

