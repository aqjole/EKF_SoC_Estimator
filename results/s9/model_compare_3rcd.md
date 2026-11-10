# 3RC-D comparison (S9)

Written by `python/compare_3rcd.py` (`make ekf-3rcd`).

The standard cycles were held out of the final parameter fit. Prior diagnostics and the low-SoC boundary choice used these runs, and they share segments with the Mix runs (docs/decisions.md 1.40 and 1.41).

All models use the frozen S2 noise settings. The adoption guards compare 3RC-D with 2RC-I.

## Standard cycles

Open-loop RMSE is pooled over window rows in mV. SoC RMSE is in pp. The lower count compares 3RC-D with 2RC-I.

| T (degC) | runs | 2RC voltage | 2RC-I voltage | 3RC-D voltage | 2RC exp1 mean | 2RC-I exp1 mean | 3RC-D exp1 mean | 2RC exp1 median | 2RC-I exp1 median | 3RC-D exp1 median | runs lower |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 | 4 | 13.48 | 13.41 | 9.69 | 0.84 | 0.79 | 0.42 | 0.80 | 0.77 | 0.40 | 4 |
| 25 | 3 | 13.75 | 13.68 | 10.27 | 0.87 | 0.86 | 0.58 | 0.88 | 0.87 | 0.70 | 3 |
| 10 | 4 | 23.04 | 22.28 | 15.53 | 1.20 | 1.44 | 1.09 | 1.11 | 1.26 | 1.13 | 4 |
| 0 | 4 | 35.48 | 33.61 | 19.92 | 1.66 | 1.90 | 1.69 | 1.42 | 1.69 | 1.32 | 3 |
| -10 | 4 | 55.38 | 49.62 | 32.07 | 3.04 | 3.64 | 2.69 | 3.03 | 3.06 | 1.62 | 3 |
| -20 | 4 | 83.20 | 76.31 | 47.11 | 2.88 | 3.07 | 2.88 | 2.92 | 2.56 | 2.08 | 3 |

Reached counts are in the order 2RC / 2RC-I / 3RC-D.

| T (degC) | 2RC exp4 mean | 2RC-I exp4 mean | 3RC-D exp4 mean | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|---|
| 40 | 1.19 | 1.15 | 0.76 | 3 / 3 / 4 | 3 / 3 / 4 | 3 / 3 / 4 |
| 25 | 1.25 | 1.25 | 0.81 | 3 / 3 / 3 | 3 / 3 / 3 | 3 / 3 / 3 |
| 10 | 1.33 | 1.46 | 1.34 | 4 / 4 / 4 | 4 / 4 / 4 | 4 / 4 / 4 |
| 0 | 1.91 | 1.83 | 1.81 | 4 / 4 / 4 | 4 / 4 / 4 | 4 / 4 / 4 |
| -10 | 3.11 | 3.40 | 2.44 | 3 / 3 / 3 | 2 / 2 / 3 | 2 / 2 / 3 |
| -20 | 3.44 | 3.32 | 2.74 | 2 / 2 / 4 | 0 / 1 / 3 | 2 / 1 / 4 |

### Experiment 1 by standard cycle

| Cycle | 2RC (pp) | 2RC-I (pp) | 3RC-D (pp) |
|---|---|---|---|
| HWFET | 2.2604 | 1.7695 | 1.0105 |
| LA92 | 1.5225 | 1.4045 | 1.0898 |
| UDDS | 1.7213 | 1.6296 | 1.2762 |
| US06 | 1.7290 | 3.1468 | 2.9328 |

### Experiment 1 by run

| Folder | Cycle | 2RC (pp) | 2RC-I (pp) | 3RC-D (pp) |
|---|---|---|---|---|
| 40degC | UDDS | 0.8086 | 0.8116 | 0.6077 |
| 40degC | HWFET | 0.7961 | 0.6532 | 0.2868 |
| 40degC | LA92 | 0.7285 | 0.7276 | 0.3831 |
| 40degC | US06 | 1.0405 | 0.9777 | 0.4169 |
| 25degC | UDDS | 0.8801 | 0.8656 | 0.6978 |
| 25degC | LA92 | 0.6802 | 0.6939 | 0.3157 |
| 25degC | US06 | 1.0462 | 1.0183 | 0.7399 |
| 10degC | UDDS | 1.0422 | 0.9488 | 0.8405 |
| 10degC | HWFET | 0.9618 | 0.9371 | 0.6377 |
| 10degC | LA92 | 1.6314 | 1.5809 | 1.4621 |
| 10degC | US06 | 1.1828 | 2.2807 | 1.4134 |
| 0degC | UDDS | 1.4977 | 1.3104 | 1.1899 |
| 0degC | HWFET | 2.6663 | 2.0790 | 1.3523 |
| 0degC | LA92 | 1.3513 | 1.2369 | 1.2945 |
| 0degC | US06 | 1.1304 | 2.9916 | 2.9079 |
| n10degC | UDDS | 2.8252 | 2.7224 | 1.9179 |
| n10degC | HWFET | 3.7917 | 3.3888 | 1.1354 |
| n10degC | LA92 | 2.3299 | 2.1916 | 1.3239 |
| n10degC | US06 | 3.2252 | 6.2547 | 6.3977 |
| n20degC | UDDS | 3.2740 | 3.1185 | 2.4031 |
| n20degC | HWFET | 3.0863 | 1.7893 | 1.6404 |
| n20degC | LA92 | 2.4139 | 1.9963 | 1.7594 |
| n20degC | US06 | 2.7491 | 5.3576 | 5.7209 |

## Calibration runs (in-sample)

Open-loop RMSE is pooled over window rows in mV. SoC RMSE is in pp. The lower count compares 3RC-D with 2RC-I.

| T (degC) | runs | 2RC voltage | 2RC-I voltage | 3RC-D voltage | 2RC exp1 mean | 2RC-I exp1 mean | 3RC-D exp1 mean | 2RC exp1 median | 2RC-I exp1 median | 3RC-D exp1 median | runs lower |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 | 3 | 12.65 | 12.48 | 7.88 | 0.71 | 0.68 | 0.34 | 0.71 | 0.67 | 0.34 | 3 |
| 25 | 8 | 17.24 | 17.33 | 9.71 | 0.84 | 0.83 | 0.46 | 0.83 | 0.80 | 0.47 | 8 |
| 10 | 7 | 25.89 | 25.18 | 14.80 | 1.17 | 1.08 | 0.80 | 1.14 | 1.11 | 0.79 | 5 |
| 0 | 7 | 40.01 | 37.95 | 19.56 | 2.25 | 1.65 | 1.04 | 1.87 | 1.66 | 0.99 | 7 |
| -10 | 7 | 68.05 | 62.07 | 30.44 | 3.65 | 2.96 | 1.13 | 2.70 | 3.00 | 1.21 | 7 |
| -20 | 8 | 89.93 | 80.88 | 46.42 | 4.10 | 3.32 | 1.36 | 3.28 | 2.99 | 1.22 | 8 |

Reached counts are in the order 2RC / 2RC-I / 3RC-D.

| T (degC) | 2RC exp4 mean | 2RC-I exp4 mean | 3RC-D exp4 mean | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|---|
| 40 | 1.15 | 1.12 | 0.69 | 3 / 3 / 3 | 3 / 3 / 3 | 3 / 3 / 3 |
| 25 | 1.15 | 1.12 | 0.78 | 7 / 7 / 8 | 7 / 7 / 8 | 7 / 7 / 8 |
| 10 | 1.33 | 1.11 | 0.90 | 7 / 7 / 7 | 7 / 7 / 7 | 7 / 7 / 7 |
| 0 | 2.40 | 1.61 | 1.17 | 7 / 7 / 7 | 7 / 7 / 7 | 7 / 7 / 7 |
| -10 | 3.84 | 3.24 | 1.28 | 1 / 1 / 7 | 1 / 1 / 7 | 1 / 1 / 7 |
| -20 | 4.06 | 4.26 | 2.50 | 4 / 3 / 7 | 4 / 3 / 6 | 3 / 3 / 6 |

## Guards and adoption verdict

The guards of decisions 1.40 use the results CSVs, with comparisons near a limit recomputed from the unrounded traces under decisions 1.35. The S1 gate always uses the full-precision open-loop RMSE.

| guard | value | result |
|---|---|---|
| 1. S1 gate | US06 at 25 degC: 23.1312 mV (limit 30) | pass |
| 2. rule of 1.22 | lower at 6 of 6; higher by more than 0.10 pp at none | pass |
| 3. run increase | largest +0.3633 pp; above the limit of +0.50: none | pass |
| 4. largest cycle increase | -0.2140 pp (US06, limit +0.25) | pass |
| 5. worst run | 6.3977 pp against 6.2547 pp | FAIL |
| 6. experiments 2 to 4 | largest exp4 increase -0.0231 pp (limit +0.10); fewer reached: none | pass |

Guard inputs from unrounded traces. SoC changes are in pp and temperatures follow the table order above.

| guard | unrounded values |
|---|---|
| 1 | 23.1311726867 mV |
| 2 | -0.368887963988 / -0.274791007635 / -0.348463181403 / -0.218290291317 / -0.945664213542 / -0.184481834437 |
| 3 | Largest run increase +0.363345204516 |
| 4 | HWFET -0.75897260076, LA92 -0.314749266258, UDDS -0.353382739644, US06 -0.213977987074 |
| 5 | Worst run 6.25470078654 to 6.39769391382 |
| 6 | Experiment 4 changes -0.39122867284 / -0.440535446313 / -0.125721508815 / -0.0231267648174 / -0.957504088039 / -0.579297591924 |

**NOT ADOPTED.**
