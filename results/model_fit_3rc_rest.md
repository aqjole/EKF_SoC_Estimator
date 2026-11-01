# Model fit, second 3RC fit (S6)

Written by `python/fit_3rc_rest.py` (`make fit-3rc-rest`). Do not edit by hand.

## Level fits

Per HPPC level, R3, tau3 and one offset fitted on the rest rows of the pulse train from 20 s after each pulse, every 2RC table of `results/params.csv` fixed (docs/decisions.md 1.26). R3 in [0, 0.5] Ohm, tau3 in [10, 100] s. Left out: levels with a discharge pulse cut at 2.8 V. A tau3 within 0.1 % of an end of its bounds counts as on the bound. Offset = measured minus model voltage, constant over the train. Every level fit is in `results/fit_levels_3rc_rest.csv`.

| T (degC) | levels | left out (cut pulse) | failed fits | tau3 on the lower bound | tau3 on the upper bound | median R3 (mOhm) | median tau3 (s) | median offset (mV) | median rest RMSE (mV) |
|---|---|---|---|---|---|---|---|---|---|
| 40 | 11 | 2 | 0 | 0 | 0 | 8.78 | 27.9 | -1.20 | 1.03 |
| 25 | 12 | 3 | 0 | 0 | 0 | 11.38 | 33.4 | -0.76 | 0.85 |
| 10 | 11 | 2 | 0 | 0 | 0 | 13.50 | 37.0 | -0.93 | 1.42 |
| 0 | 10 | 3 | 0 | 0 | 0 | 19.45 | 40.3 | -2.07 | 2.66 |
| -10 | 10 | 3 | 0 | 0 | 0 | 26.04 | 40.6 | -0.71 | 2.10 |
| -20 | 9 | 2 | 0 | 0 | 0 | 52.27 | 57.6 | +0.09 | 1.33 |

## Levels where the v1.0 tau2 is below 150 s

There the upper tau3 bound does not keep the middle branch apart from the slow one (docs/decisions.md 1.26).

| T (degC) | level | v1.0 tau2 (s) | R3 (mOhm) | tau3 (s) |
|---|---|---|---|---|
| 40 | 3 | 105.3 | 9.99 | 27.9 |
| 40 | 4 | 128.4 | 10.81 | 38.5 |
| 40 | 7 | 139.0 | 8.41 | 30.6 |
| 25 | 2 | 147.1 | 8.95 | 26.4 |
| 25 | 3 | 99.6 | 11.38 | 34.2 |

## Open-loop voltage error on US06, 2RC and second 3RC fit

As in `results/model_fit_3rc.md`: measured current and temperature, reference SoC, every branch voltage 0 at the first row, error = model minus measured voltage over the whole run.

| T (degC) | 2RC RMSE (mV) | second 3RC RMSE (mV) | change (mV) |
|---|---|---|---|
| 40 | 20.90 | 26.03 | +5.14 |
| 25 | 29.79 | 39.70 | +9.91 |
| 10 | 40.68 | 54.90 | +14.22 |
| 0 | 59.47 | 74.72 | +15.25 |
| -10 | 73.74 | 98.30 | +24.55 |
| -20 | 104.58 | 144.12 | +39.54 |

Gate: the second 3RC open-loop RMSE at 25 degC is 39.70 mV against the sanity limit of 30 mV. **FAIL.**

## Open-loop error over every drive cycle

Pooled over all rows of a temperature's runs, scored as in docs/decisions.md 1.25; the ceiling is the one of `results/model_fit_3rc.md`.

| T (degC) | runs | 2RC pooled RMSE (mV) | ceiling of 1.25 (mV) | second 3RC pooled RMSE (mV) | second 3RC change (%) |
|---|---|---|---|---|---|
| 40 | 7 | 13.95 | 11.37 | 13.31 | -4.6 |
| 25 | 11 | 17.40 | 14.75 | 17.76 | +2.1 |
| 10 | 11 | 24.81 | 22.05 | 26.84 | +8.2 |
| 0 | 11 | 38.30 | 33.60 | 37.80 | -1.3 |
| -10 | 11 | 63.38 | 46.84 | 48.12 | -24.1 |
| -20 | 12 | 87.61 | 70.33 | 77.13 | -12.0 |
