# Model comparison: 2RC and 2RC-I (S7)

Written by `python/compare_r1i.py` (`make ekf-r1i`). Do not edit by hand.

2RC-I is the 2RC model with R1 read over current (docs/decisions.md 1.28). Both filters run experiments 1 to 4 on the 63 runs with the frozen noise settings of `results/s2/ekf_config.json`; the 2RC numbers come from `results/s2/ekf_results.csv`, the 2RC-I numbers from `results/s7/ekf_results_r1i.csv`. SoC statistics are over the evaluation runs (tuning cycle excluded).

## Open loop

The US06 RMSE and the RMSE pooled over every drive run, model minus measured voltage (docs/decisions.md 1.25).

| T (degC) | US06 2RC (mV) | US06 2RC-I (mV) | pooled 2RC (mV) | pooled 2RC-I (mV) |
|---|---|---|---|---|
| 40 | 20.90 | 20.56 | 13.95 | 13.88 |
| 25 | 29.79 | 29.75 | 17.40 | 17.48 |
| 10 | 40.68 | 40.87 | 24.81 | 24.09 |
| 0 | 59.47 | 60.31 | 38.30 | 36.31 |
| -10 | 73.74 | 77.75 | 63.38 | 57.51 |
| -20 | 104.58 | 104.85 | 87.61 | 79.29 |

## Experiment 1

SoC RMSE with the correct initial SoC. The mean decides the verdict (docs/decisions.md 1.29); the median and the number of runs whose RMSE is lower with 2RC-I show how the change spreads over the runs.

| T (degC) | evaluation runs | mean 2RC (pp) | mean 2RC-I (pp) | mean change (pp) | median 2RC (pp) | median 2RC-I (pp) | runs lower with 2RC-I |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 0.79 | 0.74 | -0.04 | 0.73 | 0.72 | 6 of 7 |
| 25 | 10 | 0.87 | 0.86 | -0.01 | 0.87 | 0.87 | 7 of 10 |
| 10 | 11 | 1.18 | 1.21 | +0.03 | 1.14 | 1.11 | 9 of 11 |
| 0 | 11 | 2.04 | 1.74 | -0.29 | 1.87 | 1.66 | 10 of 11 |
| -10 | 11 | 3.43 | 3.21 | -0.22 | 2.83 | 3.00 | 9 of 11 |
| -20 | 12 | 3.70 | 3.24 | -0.46 | 3.00 | 2.99 | 8 of 12 |

## Experiments 2 to 4

Experiment 4: mean SoC RMSE with the current offset. Reached: evaluation runs whose error stays within +-2 pp from some time on, 2RC / 2RC-I.

| T (degC) | exp4 2RC (pp) | exp4 2RC-I (pp) | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|
| 40 | 1.17 | 1.14 | 6 / 6 | 6 / 6 | 6 / 6 |
| 25 | 1.21 | 1.19 | 9 / 9 | 9 / 9 | 9 / 9 |
| 10 | 1.33 | 1.24 | 11 / 11 | 11 / 11 | 11 / 11 |
| 0 | 2.22 | 1.69 | 11 / 11 | 11 / 11 | 11 / 11 |
| -10 | 3.57 | 3.30 | 4 / 4 | 3 / 3 | 3 / 3 |
| -20 | 3.85 | 3.95 | 6 / 5 | 4 / 4 | 5 / 4 |

## Adoption verdict

Rule (docs/decisions.md 1.29): the experiment-1 mean SoC RMSE is lower than the 2RC value at 4 or more of the six temperatures and higher at none by more than 0.10 pp.

Lower at 5 of 6 temperatures; higher by more than 0.10 pp at: none. **ADOPTED.**
