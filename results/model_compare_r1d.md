# Model comparison: 2RC, 2RC-I and 2RC-Id (S8, step A)

Written by `python/compare_r1d.py` (`make ekf-r1d`). Do not edit by hand.

2RC-Id is the 2RC-I model with R1 from the v1.0 table of `results/params.csv` when the held current is negative (docs/decisions.md 1.33). The three filters run experiments 1 to 4 on the 63 runs with the frozen noise settings of `results/ekf_config.json`; the numbers come from `results/ekf_results.csv`, `results/ekf_results_r1i.csv` and `results/ekf_results_r1d.csv`. SoC statistics are over the evaluation runs (tuning cycle excluded). These 62 runs have been inspected in every stage since S2, so this is a comparison on a repeatedly inspected set, not a confirmation (1.32).

## Open loop

The US06 RMSE and the RMSE pooled over every drive run, model minus measured voltage (docs/decisions.md 1.25).

| T (degC) | US06 2RC (mV) | US06 2RC-I (mV) | US06 2RC-Id (mV) | pooled 2RC (mV) | pooled 2RC-I (mV) | pooled 2RC-Id (mV) |
|---|---|---|---|---|---|---|
| 40 | 20.90 | 20.56 | 20.27 | 13.95 | 13.88 | 13.82 |
| 25 | 29.79 | 29.75 | 29.59 | 17.40 | 17.48 | 17.43 |
| 10 | 40.68 | 40.87 | 40.69 | 24.81 | 24.09 | 23.90 |
| 0 | 59.47 | 60.31 | 60.23 | 38.30 | 36.31 | 36.17 |
| -10 | 73.74 | 77.75 | 76.69 | 63.38 | 57.51 | 55.93 |
| -20 | 104.58 | 104.85 | 101.79 | 87.61 | 79.29 | 74.36 |

## Experiment 1

SoC RMSE with the correct initial SoC; change and runs lower are 2RC-Id against 2RC-I.

| T (degC) | evaluation runs | mean 2RC (pp) | mean 2RC-I (pp) | mean 2RC-Id (pp) | mean change (pp) | median 2RC-I (pp) | median 2RC-Id (pp) | runs lower with 2RC-Id |
|---|---|---|---|---|---|---|---|---|
| 40 | 7 | 0.79 | 0.74 | 0.73 | -0.01 | 0.72 | 0.71 | 7 of 7 |
| 25 | 10 | 0.87 | 0.86 | 0.85 | -0.00 | 0.87 | 0.85 | 7 of 10 |
| 10 | 11 | 1.18 | 1.21 | 1.15 | -0.06 | 1.11 | 1.07 | 8 of 11 |
| 0 | 11 | 2.04 | 1.74 | 1.61 | -0.14 | 1.66 | 1.65 | 8 of 11 |
| -10 | 11 | 3.43 | 3.21 | 2.83 | -0.38 | 3.00 | 2.53 | 10 of 11 |
| -20 | 12 | 3.70 | 3.24 | 3.01 | -0.23 | 2.99 | 2.70 | 7 of 12 |

### Per drive cycle

Experiment-1 mean SoC RMSE over the cycle's evaluation runs.

| cycle | runs | 2RC (pp) | 2RC-I (pp) | 2RC-Id (pp) | change (pp) |
|---|---|---|---|---|---|
| HWFET | 5 | 2.26 | 1.77 | 1.73 | -0.04 |
| LA92 | 6 | 1.52 | 1.40 | 1.36 | -0.04 |
| Mix 1 | 5 | 1.71 | 1.64 | 1.68 | +0.03 |
| Mix 2 | 6 | 1.64 | 1.61 | 1.57 | -0.04 |
| Mix 3 | 4 | 1.72 | 1.80 | 1.62 | -0.18 |
| Mix 4 | 4 | 2.63 | 1.73 | 1.72 | -0.01 |
| Mix 5 | 5 | 1.86 | 1.69 | 1.64 | -0.05 |
| Mix 6 | 5 | 2.04 | 2.64 | 2.52 | -0.12 |
| Mix 7 | 5 | 2.21 | 1.98 | 1.88 | -0.11 |
| Mix 8 | 5 | 4.85 | 2.18 | 2.62 | +0.44 |
| UDDS | 6 | 1.72 | 1.63 | 1.57 | -0.06 |
| US06 | 6 | 1.73 | 3.15 | 1.75 | -1.39 |

### US06

Experiment-1 SoC RMSE of the US06 run.

| T (degC) | 2RC (pp) | 2RC-I (pp) | 2RC-Id (pp) | change (pp) |
|---|---|---|---|---|
| 40 | 1.04 | 0.98 | 0.95 | -0.02 |
| 25 | 1.05 | 1.02 | 1.02 | +0.00 |
| 10 | 1.18 | 2.28 | 1.79 | -0.49 |
| 0 | 1.13 | 2.99 | 1.09 | -1.90 |
| -10 | 3.23 | 6.25 | 3.25 | -3.00 |
| -20 | 2.75 | 5.36 | 2.42 | -2.94 |

## Experiments 2 to 4

Experiment 4: mean SoC RMSE with the current offset. Reached: evaluation runs whose error stays within +-2 pp from some time on, 2RC / 2RC-I / 2RC-Id.

| T (degC) | exp4 2RC (pp) | exp4 2RC-I (pp) | exp4 2RC-Id (pp) | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|---|
| 40 | 1.17 | 1.14 | 1.13 | 6 / 6 / 6 | 6 / 6 / 6 | 6 / 6 / 6 |
| 25 | 1.21 | 1.19 | 1.19 | 9 / 9 / 9 | 9 / 9 / 9 | 9 / 9 / 9 |
| 10 | 1.33 | 1.24 | 1.17 | 11 / 11 / 11 | 11 / 11 / 11 | 11 / 11 / 11 |
| 0 | 2.22 | 1.69 | 1.57 | 11 / 11 / 11 | 11 / 11 / 11 | 11 / 11 / 11 |
| -10 | 3.57 | 3.30 | 2.83 | 4 / 4 / 5 | 3 / 3 / 3 | 3 / 3 / 3 |
| -20 | 3.85 | 3.95 | 2.82 | 6 / 5 / 4 | 4 / 4 / 2 | 5 / 4 / 4 |

## Open-loop US06 error by current band

Mean error in mV, model minus measured. A row's band is set by its own current, the current at the voltage sample (docs/decisions.md 1.33). The branch states carry over between rows, so a band's error also holds what the rows before it left in the branches.

| T (degC) | band (A) | 2RC (mV) | 2RC-I (mV) | 2RC-Id (mV) |
|---|---|---|---|---|
| 40 | regen, I <= -0.05 | -1.6 | -1.3 | -1.9 |
| 40 | rest, abs(I) < 0.05 | -29.4 | -29.3 | -29.4 |
| 40 | 0.05 <= I < 1.5 | -1.4 | -1.8 | -1.8 |
| 40 | 1.5 <= I < 3 | +8.9 | +7.8 | +7.7 |
| 40 | 3 <= I < 6 | +10.3 | +9.3 | +9.2 |
| 40 | I >= 6 | +11.1 | +10.5 | +10.5 |
| 25 | regen, I <= -0.05 | -3.6 | -3.3 | -4.3 |
| 25 | rest, abs(I) < 0.05 | -52.9 | -52.9 | -52.9 |
| 25 | 0.05 <= I < 1.5 | -5.4 | -6.0 | -6.3 |
| 25 | 1.5 <= I < 3 | +5.0 | +3.3 | +3.2 |
| 25 | 3 <= I < 6 | +6.0 | +4.3 | +4.2 |
| 25 | I >= 6 | +4.6 | +3.3 | +3.3 |
| 10 | regen, I <= -0.05 | +3.7 | +4.7 | +1.9 |
| 10 | rest, abs(I) < 0.05 | -62.3 | -62.2 | -62.3 |
| 10 | 0.05 <= I < 1.5 | -6.9 | -8.3 | -9.1 |
| 10 | 1.5 <= I < 3 | +6.5 | +2.1 | +1.9 |
| 10 | 3 <= I < 6 | +4.5 | -0.3 | -0.5 |
| 10 | I >= 6 | -5.6 | -10.1 | -10.3 |
| 0 | regen, I <= -0.05 | +6.5 | +9.2 | +2.2 |
| 0 | rest, abs(I) < 0.05 | -60.7 | -60.5 | -60.8 |
| 0 | 0.05 <= I < 1.5 | -10.7 | -14.8 | -16.4 |
| 0 | 1.5 <= I < 3 | +10.4 | -1.2 | -1.7 |
| 0 | 3 <= I < 6 | +7.8 | -5.4 | -5.8 |
| 0 | I >= 6 | -4.2 | -16.5 | -16.8 |
| -10 | regen, I <= -0.05 | +29.5 | +41.4 | +23.4 |
| -10 | rest, abs(I) < 0.05 | -13.4 | -12.9 | -13.5 |
| -10 | 0.05 <= I < 1.5 | -10.4 | -18.0 | -21.1 |
| -10 | 1.5 <= I < 3 | +22.6 | -0.6 | -2.1 |
| -10 | 3 <= I < 6 | +11.7 | -13.2 | -14.0 |
| -10 | I >= 6 | -33.3 | -44.8 | -45.5 |
| -20 | regen, I <= -0.05 | +41.8 | +73.1 | +35.8 |
| -20 | rest, abs(I) < 0.05 | -37.9 | -37.3 | -38.1 |
| -20 | 0.05 <= I < 1.5 | +0.5 | -11.8 | -16.1 |
| -20 | 1.5 <= I < 3 | +31.1 | -3.0 | -5.8 |
| -20 | 3 <= I < 6 | -9.7 | -18.9 | -20.0 |
| -20 | I >= 6 | -52.4 | -25.3 | -48.7 |

Steps whose held current is negative (the steps where 2RC-Id switches R1), and the R1 ratio of docs/decisions.md 1.32: the median 2RC-I R1 at 1.5 A over the grid SoC 0.5 to 0.95, divided by the median v1.0 R1 there.

| T (degC) | US06 steps with held I < 0 (%) | R1 ratio |
|---|---|---|
| 40 | 19.0 | 1.23 |
| 25 | 18.9 | 1.26 |
| 10 | 19.3 | 1.29 |
| 0 | 18.4 | 1.44 |
| -10 | 19.0 | 1.99 |
| -20 | 17.5 | 1.74 |

## Guards and adoption verdict

The guards of docs/decisions.md 1.32, 2RC-Id against the incumbent 2RC-I. For step A the incumbent is 2RC-I, the model S8 starts from, so the stage-budget check is the same comparison. Values are those of the results CSVs (4 decimals), not the rounded values shown above.

| guard | value | result |
|---|---|---|
| 1. S1 gate | US06 at 25 degC: 29.5914 mV (limit 30) | pass |
| 2. rule of 1.22 | lower at 6 of 6; higher by more than 0.10 pp at none | pass |
| 3. run increase | largest +0.8513 pp; above the limit of +0.50: Mix 8 at -10 degC +0.8513, Mix 8 at -20 degC +0.7612, Mix 6 at -20 degC +0.6387, Mix 8 at 0 degC +0.6236 | FAIL |
| 4. largest cycle increase | +0.4403 pp (Mix 8, limit +0.25) | FAIL |
| 5. worst run | 6.9828 pp against 6.3441 pp | FAIL |
| 6. experiments 2 to 4 | largest exp4 increase -0.0059 pp (limit +0.10); fewer reached: exp2 at -20 degC, exp3_low at -20 degC | FAIL |

**NOT ADOPTED.**

## Test for step B

docs/decisions.md 1.33: the experiment-1 US06 SoC RMSE of 2RC-Id is lower than 2RC-I by at least 0.10 pp at each of 0, -10, -20 degC. Change: -1.9049 pp at 0 degC, -3.0040 pp at -10 degC, -2.9414 pp at -20 degC.

**MET: step B is written.**
