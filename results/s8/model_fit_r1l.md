# Model fit, 2RC-Il (S8, step C)

Written by `python/fit_r1_low.py` (`make fit-r1l`). Do not edit by hand.

The R1 table of the 2RC-Il model (docs/decisions.md 1.37): the 2RC-I table of `results/s7/r1_current.csv` scaled at low current by factors fitted on the PausCycl files, which are not in the evaluation set.

The 40 and 25 degC slices equal those of `results/s7/r1_current.csv`: yes.

## Factors

r_T scales R1 at and below each level's smallest discharge pulse current and ramps back to 1 at its second pulse (docs/decisions.md 1.37); r_T = 1 at 40 and 25 degC. The four factors are fitted jointly on the PausCycl files, with one free offset per file. The RMSE columns are the open-loop voltage error over the whole file, each model with its own mean removed; they decide nothing.

| T (degC) | r_T | fit offset (mV) | PausCycl 2RC-I (mV) | PausCycl 2RC-Il (mV) |
|---|---|---|---|---|
| 10 | 0.9121 | -5.0 | 7.43 | 7.30 |
| 0 | 0.9667 | -6.5 | 10.91 | 10.92 |
| -10 | 0.8351 | -12.5 | 18.10 | 17.00 |
| -20 | 0.7974 | -11.9 | 30.28 | 28.24 |

## Open-loop US06

Model minus measured voltage over the whole US06 run.

| T (degC) | 2RC-I (mV) | 2RC-Il (mV) |
|---|---|---|
| 40 | 20.56 | 20.56 |
| 25 | 29.75 | 29.75 |
| 10 | 40.87 | 40.90 |
| 0 | 60.31 | 60.36 |
| -10 | 77.75 | 77.38 |
| -20 | 104.85 | 104.12 |

S1 gate: 2RC-Il at 25 degC 29.7545 mV against 30 mV. **PASS.**

## Open-loop error over every drive cycle

Pooled over all rows of a temperature's runs, scored as in docs/decisions.md 1.25.

| T (degC) | runs | 2RC-I pooled RMSE (mV) | 2RC-Il pooled RMSE (mV) | change (%) |
|---|---|---|---|---|
| 40 | 7 | 13.88 | 13.88 | +0.0 |
| 25 | 11 | 17.48 | 17.50 | +0.1 |
| 10 | 11 | 24.09 | 24.37 | +1.2 |
| 0 | 11 | 36.31 | 36.46 | +0.4 |
| -10 | 11 | 57.51 | 57.86 | +0.6 |
| -20 | 12 | 79.29 | 79.09 | -0.3 |
