# Model comparison: 2RC, 2RC-I and 2RC-Il (S8, step C)

Written by `python/compare_r1l.py` (`make ekf-r1l`). Do not edit by hand.

2RC-Il is the 2RC-I model with R1 from `results/r1_low.csv`: the 2RC-I table scaled at and below each level's smallest discharge pulse current by factors fitted on the PausCycl files, ramping back to the 2RC-I values at the level's second pulse (docs/decisions.md 1.37). The table is read at the held |I|, so regen below the second pulse current reads the scaled R1 too, and a US06 change cannot be credited to the discharge rows alone. The three filters run experiments 1 to 4 on the 63 runs with the frozen noise settings of `results/ekf_config.json`; the numbers come from `results/ekf_results.csv`, `results/ekf_results_r1i.csv` and `results/ekf_results_r1l.csv`. SoC statistics are over the evaluation runs (tuning cycle excluded). The 40 degC runs read only unscaled slices and equal 2RC-I (checked). These 62 runs have been inspected in every stage since S2, so this is a comparison on a repeatedly inspected set, not a confirmation (1.32).

## Open loop

The US06 RMSE and the RMSE pooled over every drive run, model minus measured voltage (docs/decisions.md 1.25).

| T (degC) | US06 2RC (mV) | US06 2RC-I (mV) | US06 2RC-Il (mV) | pooled 2RC (mV) | pooled 2RC-I (mV) | pooled 2RC-Il (mV) |
|---|---|---|---|---|---|---|
| 40 | 20.90 | 20.56 | 20.56 | 13.95 | 13.88 | 13.88 |
| 25 | 29.79 | 29.75 | 29.75 | 17.40 | 17.48 | 17.50 |
| 10 | 40.68 | 40.87 | 40.90 | 24.81 | 24.09 | 24.37 |
| 0 | 59.47 | 60.31 | 60.36 | 38.30 | 36.31 | 36.46 |
| -10 | 73.74 | 77.75 | 77.38 | 63.38 | 57.51 | 57.86 |
| -20 | 104.58 | 104.85 | 104.12 | 87.61 | 79.29 | 79.09 |

## Experiment 1

SoC RMSE with the correct initial SoC; change and runs lower are 2RC-Il against 2RC-I.

| T (degC) | evaluation runs | mean 2RC (pp) | mean 2RC-I (pp) | mean 2RC-Il (pp) | mean change (pp) | median 2RC-I (pp) | median 2RC-Il (pp) | runs lower with 2RC-Il |
|---|---|---|---|---|---|---|---|---|
| 40 | 7 | 0.79 | 0.74 | 0.74 | +0.00 | 0.72 | 0.72 | 0 of 7 |
| 25 | 10 | 0.87 | 0.86 | 0.86 | +0.00 | 0.87 | 0.87 | 1 of 10 |
| 10 | 11 | 1.18 | 1.21 | 1.23 | +0.01 | 1.11 | 1.13 | 1 of 11 |
| 0 | 11 | 2.04 | 1.74 | 1.80 | +0.06 | 1.66 | 1.74 | 1 of 11 |
| -10 | 11 | 3.43 | 3.21 | 3.21 | -0.00 | 3.00 | 3.01 | 2 of 11 |
| -20 | 12 | 3.70 | 3.24 | 3.51 | +0.27 | 2.99 | 3.00 | 2 of 12 |

### Per drive cycle

Experiment-1 mean SoC RMSE over the cycle's evaluation runs.

| cycle | runs | 2RC (pp) | 2RC-I (pp) | 2RC-Il (pp) | change (pp) |
|---|---|---|---|---|---|
| HWFET | 5 | 2.26 | 1.77 | 1.80 | +0.03 |
| LA92 | 6 | 1.52 | 1.40 | 1.54 | +0.14 |
| Mix 1 | 5 | 1.71 | 1.64 | 1.66 | +0.02 |
| Mix 2 | 6 | 1.64 | 1.61 | 1.61 | +0.01 |
| Mix 3 | 4 | 1.72 | 1.80 | 1.80 | +0.00 |
| Mix 4 | 4 | 2.63 | 1.73 | 1.78 | +0.04 |
| Mix 5 | 5 | 1.86 | 1.69 | 1.71 | +0.02 |
| Mix 6 | 5 | 2.04 | 2.64 | 2.58 | -0.06 |
| Mix 7 | 5 | 2.21 | 1.98 | 2.01 | +0.03 |
| Mix 8 | 5 | 4.85 | 2.18 | 2.65 | +0.47 |
| UDDS | 6 | 1.72 | 1.63 | 1.73 | +0.10 |
| US06 | 6 | 1.73 | 3.15 | 3.12 | -0.02 |

### US06

Experiment-1 SoC RMSE of the US06 run.

| T (degC) | 2RC (pp) | 2RC-I (pp) | 2RC-Il (pp) | change (pp) |
|---|---|---|---|---|
| 40 | 1.04 | 0.98 | 0.98 | +0.00 |
| 25 | 1.05 | 1.02 | 1.02 | -0.00 |
| 10 | 1.18 | 2.28 | 2.12 | -0.16 |
| 0 | 1.13 | 2.99 | 2.94 | -0.06 |
| -10 | 3.23 | 6.25 | 5.34 | -0.91 |
| -20 | 2.75 | 5.36 | 6.34 | +0.99 |

## Experiments 2 to 4

Experiment 4: mean SoC RMSE with the current offset. Reached: evaluation runs whose error stays within +-2 pp from some time on, 2RC / 2RC-I / 2RC-Il.

| T (degC) | exp4 2RC (pp) | exp4 2RC-I (pp) | exp4 2RC-Il (pp) | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|---|
| 40 | 1.17 | 1.14 | 1.14 | 6 / 6 / 6 | 6 / 6 / 6 | 6 / 6 / 6 |
| 25 | 1.21 | 1.19 | 1.19 | 9 / 9 / 9 | 9 / 9 / 9 | 9 / 9 / 9 |
| 10 | 1.33 | 1.24 | 1.25 | 11 / 11 / 11 | 11 / 11 / 11 | 11 / 11 / 11 |
| 0 | 2.22 | 1.69 | 1.74 | 11 / 11 / 11 | 11 / 11 / 11 | 11 / 11 / 11 |
| -10 | 3.57 | 3.30 | 3.39 | 4 / 4 / 4 | 3 / 3 / 3 | 3 / 3 / 3 |
| -20 | 3.85 | 3.95 | 3.24 | 6 / 5 / 5 | 4 / 4 / 4 | 5 / 4 / 4 |

## Open-loop US06 error by current band

Mean error in mV, model minus measured. A row's band is set by its own current, the current at the voltage sample (docs/decisions.md 1.33). The branch states carry over between rows, so a band's error also holds what the rows before it left in the branches.

| T (degC) | band (A) | 2RC (mV) | 2RC-I (mV) | 2RC-Il (mV) |
|---|---|---|---|---|
| 40 | regen, I <= -0.05 | -1.6 | -1.3 | -1.3 |
| 40 | rest, abs(I) < 0.05 | -29.4 | -29.3 | -29.3 |
| 40 | 0.05 <= I < 1.5 | -1.4 | -1.8 | -1.8 |
| 40 | 1.5 <= I < 3 | +8.9 | +7.8 | +7.8 |
| 40 | 3 <= I < 6 | +10.3 | +9.3 | +9.3 |
| 40 | I >= 6 | +11.1 | +10.5 | +10.5 |
| 25 | regen, I <= -0.05 | -3.6 | -3.3 | -3.3 |
| 25 | rest, abs(I) < 0.05 | -52.9 | -52.9 | -52.9 |
| 25 | 0.05 <= I < 1.5 | -5.4 | -6.0 | -6.0 |
| 25 | 1.5 <= I < 3 | +5.0 | +3.3 | +3.3 |
| 25 | 3 <= I < 6 | +6.0 | +4.3 | +4.3 |
| 25 | I >= 6 | +4.6 | +3.3 | +3.3 |
| 10 | regen, I <= -0.05 | +3.7 | +4.7 | +4.2 |
| 10 | rest, abs(I) < 0.05 | -62.3 | -62.2 | -62.2 |
| 10 | 0.05 <= I < 1.5 | -6.9 | -8.3 | -8.0 |
| 10 | 1.5 <= I < 3 | +6.5 | +2.1 | +3.3 |
| 10 | 3 <= I < 6 | +4.5 | -0.3 | +0.8 |
| 10 | I >= 6 | -5.6 | -10.1 | -9.5 |
| 0 | regen, I <= -0.05 | +6.5 | +9.2 | +8.6 |
| 0 | rest, abs(I) < 0.05 | -60.7 | -60.5 | -60.5 |
| 0 | 0.05 <= I < 1.5 | -10.7 | -14.8 | -14.6 |
| 0 | 1.5 <= I < 3 | +10.4 | -1.2 | -0.3 |
| 0 | 3 <= I < 6 | +7.8 | -5.4 | -4.5 |
| 0 | I >= 6 | -4.2 | -16.5 | -16.0 |
| -10 | regen, I <= -0.05 | +29.5 | +41.4 | +40.0 |
| -10 | rest, abs(I) < 0.05 | -13.4 | -12.9 | -13.0 |
| -10 | 0.05 <= I < 1.5 | -10.4 | -18.0 | -17.3 |
| -10 | 1.5 <= I < 3 | +22.6 | -0.6 | +1.6 |
| -10 | 3 <= I < 6 | +11.7 | -13.2 | -12.1 |
| -10 | I >= 6 | -33.3 | -44.8 | -44.4 |
| -20 | regen, I <= -0.05 | +41.8 | +73.1 | +68.6 |
| -20 | rest, abs(I) < 0.05 | -37.9 | -37.3 | -37.5 |
| -20 | 0.05 <= I < 1.5 | +0.5 | -11.8 | -9.8 |
| -20 | 1.5 <= I < 3 | +31.1 | -3.0 | -1.2 |
| -20 | 3 <= I < 6 | -9.7 | -18.9 | -18.3 |
| -20 | I >= 6 | -52.4 | -25.3 | -30.0 |

Steps whose held |I| lies from 0.05 A up to the temperature's second pulse current I_2 (the median over its levels), where 2RC-Il reads a scaled R1 (docs/decisions.md 1.37); 40 and 25 degC are not scaled, although the 25 degC runs read the 10 degC slice with a small weight. Then the R1 ratio of 1.32: the median R1 of the model at 1.5 A over the grid SoC 0.5 to 0.95, divided by the median v1.0 R1 there.

| T (degC) | I_2 (A) | US06 steps with a scaled R1 (%) | R1 ratio 2RC-I | R1 ratio 2RC-Il |
|---|---|---|---|---|
| 40 | n/a | n/a | 1.23 | 1.23 |
| 25 | n/a | n/a | 1.26 | 1.26 |
| 10 | 5.80 | 63.1 | 1.29 | 1.17 |
| 0 | 6.00 | 63.7 | 1.44 | 1.39 |
| -10 | 3.00 | 40.6 | 1.99 | 1.66 |
| -20 | 1.50 | 28.7 | 1.74 | 1.74 |

## Guards and adoption verdict

The guards of docs/decisions.md 1.32, 2RC-Il against the incumbent 2RC-I, which is also the model S8 starts from, so the stage-budget check is the same comparison. Values are those of the results CSVs (4 decimals); a guard whose value lies within 0.0001 of its limit is recomputed from unrounded values, which decide (1.35).

| guard | value | result |
|---|---|---|
| 1. S1 gate | US06 at 25 degC: 29.7545 mV (limit 30) | pass |
| 2. rule of 1.22 | lower at 1 of 6; higher by more than 0.10 pp at -20 degC (recomputed from unrounded values) | FAIL |
| 3. run increase | largest +1.0142 pp; above the limit of +0.50: Mix 8 at -10 degC +1.0142, US06 at -20 degC +0.9855, Mix 8 at -20 degC +0.9425, LA92 at -20 degC +0.7413 | FAIL |
| 4. largest cycle increase | +0.4739 pp (Mix 8, limit +0.25) | FAIL |
| 5. worst run | 6.4687 pp against 6.3441 pp | FAIL |
| 6. experiments 2 to 4 | largest exp4 increase +0.0895 pp (limit +0.10); fewer reached: none | pass |

Guards recomputed from unrounded values: 2. rule of 1.22 (unrounded margin 0.00e+00). Guard 2 is recomputed whenever a temperature's change is exactly 0, as at 40 degC by construction; an unchanged mean does not count as lower (1.37).

**NOT ADOPTED.**
