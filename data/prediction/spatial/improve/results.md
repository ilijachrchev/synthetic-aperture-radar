**Held-out new water, 20 m pixels** (AP = average precision; hit and false alarms at the frozen threshold)

| candidate | development score | Albufera AP | hit | false alarms | Pego-Oliva AP | hit | false alarms |
|---|---|---|---|---|---|---|---|
| base | 0.379 | 0.466 | 62 % | 58 % | 0.376 | 58 % | 70 % |
| base+blend | 0.378 | 0.469 | 61 % | 56 % | 0.345 | 58 % | 71 % |
| terrain only (baseline) |  | 0.410 | 61 % | 63 % | 0.308 | 57 % | 72 % |
| past wet share (baseline) |  | 0.326 | 8 % | 66 % | 0.315 | 41 % | 69 % |
| mono | 0.384 | 0.489 | 57 % | 54 % | 0.374 | 56 % | 69 % |
| mono+blend | 0.380 | 0.476 | 61 % | 55 % | 0.344 | 57 % | 71 % |
| storm | 0.359 | 0.416 | 72 % | 65 % | 0.357 | 60 % | 73 % |
| storm+blend | 0.367 | 0.472 | 64 % | 60 % | 0.334 | 58 % | 72 % |
| neigh | 0.380 | 0.487 | 55 % | 53 % | 0.365 | 57 % | 69 % |
| neigh+blend | 0.385 | 0.476 | 67 % | 59 % | 0.341 | 62 % | 72 % |
| nisar_flag | 0.380 | 0.472 | 51 % | 51 % | 0.380 | 58 % | 69 % |
| nisar_flag+blend | 0.382 | 0.464 | 60 % | 57 % | 0.348 | 60 % | 71 % |
| mono_storm | 0.370 | 0.410 | 72 % | 65 % | 0.377 | 61 % | 72 % |
| mono_storm+blend | 0.373 | 0.472 | 64 % | 60 % | 0.343 | 58 % | 72 % |
| mono_neigh | 0.386 | 0.493 | 65 % | 59 % | 0.369 | 59 % | 70 % |
| **mono_neigh+blend** (chosen) | 0.387 | 0.483 | 68 % | 60 % | 0.343 | 62 % | 72 % |
| mono_storm_neigh | 0.377 | 0.476 | 68 % | 61 % | 0.377 | 58 % | 70 % |
| mono_storm_neigh+blend | 0.382 | 0.486 | 64 % | 57 % | 0.346 | 58 % | 72 % |

**Held-out new water, 250 m cells** (AP = average precision; hit and false alarms at the frozen threshold)

| candidate | development score | Albufera AP | hit | false alarms | Pego-Oliva AP | hit | false alarms |
|---|---|---|---|---|---|---|---|
| base | 0.379 | 0.410 | 69 % | 54 % | 0.278 | 64 % | 67 % |
| base+blend | 0.378 | 0.398 | 68 % | 52 % | 0.255 | 63 % | 68 % |
| terrain only (baseline) |  | 0.331 | 67 % | 59 % | 0.228 | 61 % | 70 % |
| past wet share (baseline) |  | 0.260 | 11 % | 50 % | 0.232 | 47 % | 63 % |
| mono | 0.384 | 0.425 | 64 % | 49 % | 0.275 | 61 % | 65 % |
| mono+blend | 0.380 | 0.405 | 68 % | 51 % | 0.253 | 62 % | 68 % |
| storm | 0.359 | 0.376 | 78 % | 62 % | 0.262 | 65 % | 69 % |
| storm+blend | 0.367 | 0.404 | 71 % | 56 % | 0.245 | 62 % | 69 % |
| neigh | 0.380 | 0.424 | 62 % | 48 % | 0.267 | 63 % | 65 % |
| neigh+blend | 0.385 | 0.405 | 74 % | 55 % | 0.250 | 67 % | 69 % |
| nisar_flag | 0.380 | 0.409 | 57 % | 45 % | 0.282 | 64 % | 65 % |
| nisar_flag+blend | 0.382 | 0.390 | 67 % | 53 % | 0.255 | 65 % | 68 % |
| mono_storm | 0.370 | 0.367 | 78 % | 63 % | 0.279 | 67 % | 69 % |
| mono_storm+blend | 0.373 | 0.400 | 70 % | 56 % | 0.254 | 63 % | 69 % |
| mono_neigh | 0.386 | 0.427 | 73 % | 54 % | 0.269 | 65 % | 67 % |
| **mono_neigh+blend** (chosen) | 0.387 | 0.411 | 76 % | 56 % | 0.252 | 68 % | 69 % |
| mono_storm_neigh | 0.377 | 0.423 | 75 % | 57 % | 0.276 | 63 % | 67 % |
| mono_storm_neigh+blend | 0.382 | 0.414 | 71 % | 53 % | 0.255 | 63 % | 68 % |

**The storm, 20 m** (22 Oct = first Sentinel-1 pass after the DANA rain; forecast = the same pass with the rain the IFS run of the issue day forecast; scenarios = likely new water in ha at 0, 50, 100 and 200 mm)

| candidate | Albufera 22 Oct | Albufera forecast | Albufera scenarios | Pego-Oliva 22 Oct | Pego-Oliva forecast | Pego-Oliva scenarios |
|---|---|---|---|---|---|---|
| base | 0.639 | 0.460 | 1,010 / 1,657 / 1,660 / 3,557 | 0.396 | 0.358 | 405 / 471 / 430 / 513 |
| base+blend | 0.702 | 0.630 | 1,333 / 1,706 / 1,713 / 1,976 | 0.371 | 0.354 | 449 / 478 / 460 / 487 |
| terrain only (baseline) | 0.677 | 0.677 |  | 0.351 | 0.351 |  |
| past wet share (baseline) | 0.574 | 0.574 |  | 0.326 | 0.326 |  |
| mono | 0.687 | 0.580 | 1,149 / 1,804 / 1,824 / 4,448 | 0.390 | 0.363 | 376 / 482 / 483 / 604 |
| mono+blend | 0.705 | 0.653 | 1,458 / 1,796 / 1,811 / 2,119 | 0.370 | 0.358 | 445 / 486 / 486 / 514 |
| storm | 0.508 | 0.440 | 1,696 / 2,439 / 2,412 / 5,719 | 0.401 | 0.365 | 513 / 585 / 560 / 762 |
| storm+blend | 0.694 | 0.662 | 1,697 / 1,968 / 1,924 / 2,515 | 0.373 | 0.357 | 490 / 515 / 496 / 554 |
| neigh | 0.688 | 0.649 | 1,030 / 1,493 / 1,588 / 3,927 | 0.355 | 0.346 | 362 / 436 / 438 / 534 |
| neigh+blend | 0.696 | 0.672 | 1,674 / 1,925 / 1,981 / 2,386 | 0.352 | 0.348 | 483 / 514 / 516 / 564 |
| nisar_flag | 0.689 | 0.673 | 1,878 / 2,781 / 2,902 / 5,835 | 0.447 | 0.366 | 513 / 587 / 616 / 701 |
| nisar_flag+blend | 0.696 | 0.685 | 1,889 / 2,173 / 2,224 / 2,379 | 0.399 | 0.363 | 510 / 531 / 547 / 566 |
| mono_storm | 0.467 | 0.400 | 1,756 / 2,617 / 2,692 / 6,104 | 0.420 | 0.379 | 505 / 590 / 624 / 980 |
| mono_storm+blend | 0.695 | 0.664 | 1,687 / 1,980 / 2,005 / 2,643 | 0.380 | 0.364 | 475 / 506 / 512 / 594 |
| mono_neigh | 0.688 | 0.652 | 1,531 / 2,104 / 2,149 / 5,075 | 0.352 | 0.335 | 455 / 542 / 544 / 802 |
| **mono_neigh+blend** (chosen) | 0.707 | 0.677 | 1,838 / 2,136 / 2,157 / 2,578 | 0.352 | 0.343 | 508 / 544 / 545 / 620 |
| mono_storm_neigh | 0.568 | 0.575 | 1,396 / 1,959 / 2,016 / 5,726 | 0.384 | 0.361 | 416 / 456 / 458 / 724 |
| mono_storm_neigh+blend | 0.709 | 0.675 | 1,582 / 1,856 / 1,870 / 2,457 | 0.365 | 0.356 | 454 / 469 / 469 / 565 |
