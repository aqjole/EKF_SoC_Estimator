# Model fit, 2RC-Ic (S8, step B)

Written by `python/fit_r1_charge.py` (`make fit-r1c`). Do not edit by hand.

The charge-side R1 of the 2RC-Ic model (docs/decisions.md 1.35), read under a negative held current; the discharge side is the 2RC-I table of `results/s7/r1_current.csv`.

## Charge R1 per pulse

Medians over the charge pulses in the fit, per temperature and pulse number. R1 is the fitted value (carried-in decay removed, rows unweighted); the uncorrected and dt-weighted columns are the sensitivity checks of docs/decisions.md 1.35 and do not enter the table. The fit holds R0 at the level's discharge value, so the charge R1 takes up any charge-discharge difference in R0: the step-rule column gives the charge pulse's step-rule R0 minus the level's R0, over the pulses that have one (pulses that miss the 0.3 s rule have none); the count of pulses with one is in brackets. v1.0 R1 is the level's fit (a) value; the 2RC-I discharge R1 is read from `results/s7/r1_current.csv` at the pulse's current and the level's SoC. The R0 + R1 columns compare charge and discharge as the model reads them, both with the level's R0. Pulse numbers mix SoC levels, because the pulses in the fit differ by level.

| T (degC) | pulse | pulses | median I (A) | R1 (mOhm) | uncorrected (mOhm) | dt-weighted (mOhm) | step-rule R0 - level R0 (mOhm) | v1.0 R1 (mOhm) | 2RC-I discharge R1 (mOhm) | charge R0 + R1 (mOhm) | discharge R0 + R1 (mOhm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 | C1 | 10 | 1.497 | 5.79 | 5.63 | 5.79 | +1.64 (10) | 6.10 | 6.90 | 20.19 | 21.63 |
| 40 | C2 | 10 | 2.999 | 5.44 | 5.28 | 5.43 | -4.06 (10) | 6.10 | 6.90 | 19.99 | 21.63 |
| 40 | C3 | 10 | 4.498 | 4.98 | 4.87 | 4.90 | -4.04 (10) | 6.10 | 6.62 | 19.33 | 21.39 |
| 40 | C4 | 9 | 5.997 | 4.63 | 4.57 | 4.42 | -0.59 (9) | 6.12 | 6.36 | 18.96 | 20.99 |
| 25 | C1 | 11 | 1.497 | 7.17 | 7.10 | 7.04 | +1.36 (10) | 6.77 | 8.21 | 24.76 | 25.98 |
| 25 | C2 | 11 | 2.999 | 6.61 | 6.55 | 6.35 | -5.08 (11) | 6.77 | 8.21 | 24.01 | 25.98 |
| 25 | C3 | 10 | 4.498 | 5.66 | 5.55 | 4.99 | -1.65 (10) | 6.82 | 7.95 | 22.68 | 24.93 |
| 25 | C4 | 9 | 5.997 | 5.09 | 4.93 | 4.17 | -1.61 (9) | 6.86 | 7.05 | 22.15 | 24.05 |
| 10 | C1 | 10 | 1.448 | 10.01 | 9.76 | 8.20 | +1.85 (10) | 8.70 | 11.06 | 34.69 | 36.35 |
| 10 | C2 | 9 | 2.896 | 8.18 | 8.10 | 6.45 | -8.92 (9) | 8.55 | 10.29 | 33.90 | 36.01 |
| 10 | C3 | 8 | 4.347 | 6.62 | 6.41 | 5.28 | -4.28 (8) | 8.53 | 9.31 | 32.22 | 34.94 |
| 10 | C4 | 8 | 5.798 | 5.40 | 5.18 | 4.03 | -1.47 (8) | 8.53 | 9.03 | 31.01 | 34.66 |
| 0 | C1 | 9 | 0.748 | 11.70 | 11.15 | 10.40 | -10.49 (5) | 10.98 | 14.74 | 47.17 | 50.05 |
| 0 | C2 | 9 | 1.497 | 10.71 | 10.31 | 9.10 | +4.57 (9) | 10.98 | 14.74 | 45.45 | 50.05 |
| 0 | C3 | 8 | 2.248 | 7.65 | 7.31 | 5.93 | -12.12 (8) | 10.96 | 14.65 | 41.72 | 49.21 |
| 0 | C4 | 8 | 2.999 | 5.71 | 5.25 | 4.51 | -11.92 (8) | 10.96 | 14.65 | 40.07 | 49.21 |
| -10 | C1 | 8 | 0.748 | 25.99 | 25.73 | 26.39 | +0.22 (4) | 19.51 | 30.81 | 77.92 | 82.77 |
| -10 | C2 | 7 | 1.497 | 24.20 | 23.80 | 23.86 | +15.15 (7) | 17.73 | 30.16 | 75.85 | 82.46 |
| -10 | C3 | 7 | 2.248 | 19.42 | 18.82 | 19.81 | +0.13 (7) | 17.73 | 28.45 | 71.05 | 80.75 |
| -10 | C4 | 7 | 2.999 | 13.58 | 13.50 | 13.46 | -3.56 (7) | 17.73 | 26.74 | 64.94 | 79.03 |
| -20 | C1 | 7 | 0.373 | 78.77 | 78.66 | 80.40 | +57.73 (3) | 48.95 | 85.38 | 155.77 | 164.01 |
| -20 | C2 | 6 | 0.748 | 74.34 | 74.06 | 76.08 | +15.58 (2) | 46.74 | 85.22 | 152.31 | 163.04 |
| -20 | C3 | 6 | 1.121 | 66.35 | 66.21 | 67.75 | +54.24 (5) | 46.74 | 80.77 | 145.13 | 158.90 |
| -20 | C4 | 6 | 1.497 | 56.27 | 56.04 | 57.03 | +41.49 (6) | 46.74 | 76.89 | 133.18 | 155.41 |

## Pulses in the fit

Charge pulses per temperature: in the fit, and left out by reason. Pulses that miss the 0.3 s rule of decisions 1.12 are kept (1.35). Beyond the SoC span of the levels with a pulse in the fit, the table holds the end values.

| T (degC) | charge pulses | in the fit | 4.2 V limit or short | fit (a) failed | R1 <= 0 | 0.3 s misses kept | SoC span of the levels |
|---|---|---|---|---|---|---|---|
| 40 | 44 | 39 | 5 | 0 | 0 | 0 | 0.08 to 0.95 |
| 25 | 48 | 41 | 7 | 0 | 0 | 1 | 0.03 to 0.95 |
| 10 | 44 | 35 | 9 | 0 | 0 | 0 | 0.11 to 0.95 |
| 0 | 40 | 34 | 6 | 0 | 0 | 4 | 0.14 to 0.95 |
| -10 | 40 | 29 | 11 | 0 | 0 | 4 | 0.14 to 0.89 |
| -20 | 36 | 25 | 11 | 0 | 0 | 9 | 0.24 to 0.89 |

## Open-loop US06

Model minus measured voltage over the whole US06 run.

| T (degC) | 2RC-I (mV) | 2RC-Ic (mV) |
|---|---|---|
| 40 | 20.56 | 20.62 |
| 25 | 29.75 | 29.92 |
| 10 | 40.87 | 41.08 |
| 0 | 60.31 | 60.65 |
| -10 | 77.75 | 76.71 |
| -20 | 104.85 | 102.89 |

S1 gate: 2RC-Ic at 25 degC 29.9166 mV against 30 mV. **PASS.**
