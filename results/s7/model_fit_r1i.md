# Model fit, 2RC-I (S7)

Written by `python/fit_r1_current.py` (`make fit-r1i`). Do not edit by hand.

## R1 per pulse

Per usable HPPC discharge pulse, R1 in the window of fit (a) (the pulse and its 40 s rest, one free constant) with R0 and tau1 held at the level's fit (a) values (docs/decisions.md 1.28). Medians over the levels; v1.0 R1 is the level fit of S1. D1 is the smallest current and also the only pulse that follows the move and its 1 h rest, so a current effect and a history effect on D1 cannot be told apart. Left out: pulses with R1 at or below 0. Every pulse fit is in `results/s7/fit_pulses_r1i.csv`.

| T (degC) | v1.0 R1 (mOhm) | D1 I (A) | D1 R1 (mOhm) | D2 I (A) | D2 R1 (mOhm) | D3 I (A) | D3 R1 (mOhm) | D4 I (A) | D4 R1 (mOhm) | pulses used | left out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 | 6.08 | 3.00 | 6.44 | 6.00 | 6.26 | 12.00 | 6.08 | 18.00 | 5.78 | 41 | 0 |
| 25 | 6.78 | 3.00 | 8.45 | 6.00 | 7.93 | 12.00 | 6.98 | 18.00 | 6.33 | 42 | 0 |
| 10 | 8.85 | 2.90 | 11.78 | 5.80 | 10.45 | 11.60 | 8.90 | 17.40 | 8.29 | 40 | 0 |
| 0 | 11.56 | 3.00 | 15.75 | 6.00 | 14.49 | 12.00 | 11.88 | 18.00 | 10.23 | 35 | 0 |
| -10 | 21.52 | 1.50 | 33.48 | 3.00 | 30.09 | 6.00 | 23.96 | 12.00 | 14.92 | 36 | 0 |
| -20 | 60.81 | 0.75 | 98.77 | 1.50 | 86.62 | 3.00 | 66.50 | 6.00 | 41.38 | 34 | 0 |

## Open-loop voltage error on US06, 2RC and 2RC-I

As in `results/s1/model_fit.md`: measured current and temperature, reference SoC, every branch voltage 0 at the first row, error = model minus measured voltage over the whole run.

| T (degC) | 2RC RMSE (mV) | 2RC-I RMSE (mV) | change (mV) |
|---|---|---|---|
| 40 | 20.90 | 20.56 | -0.34 |
| 25 | 29.79 | 29.75 | -0.04 |
| 10 | 40.68 | 40.87 | +0.19 |
| 0 | 59.47 | 60.31 | +0.85 |
| -10 | 73.74 | 77.75 | +4.00 |
| -20 | 104.58 | 104.85 | +0.27 |

Gate: the 2RC-I open-loop RMSE at 25 degC is 29.75 mV against the sanity limit of 30 mV. **PASS.**

## Open-loop error over every drive cycle

Pooled over all rows of a temperature's runs, scored as in docs/decisions.md 1.25.

| T (degC) | runs | 2RC pooled RMSE (mV) | 2RC-I pooled RMSE (mV) | change (%) |
|---|---|---|---|---|
| 40 | 7 | 13.95 | 13.88 | -0.5 |
| 25 | 11 | 17.40 | 17.48 | +0.5 |
| 10 | 11 | 24.81 | 24.09 | -2.9 |
| 0 | 11 | 38.30 | 36.31 | -5.2 |
| -10 | 11 | 63.38 | 57.51 | -9.3 |
| -20 | 12 | 87.61 | 79.29 | -9.5 |
