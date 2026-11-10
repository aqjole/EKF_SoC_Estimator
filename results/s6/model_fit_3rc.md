# Model fit, 3RC (S6)

Written by `python/fit_3rc.py` (`make fit-3rc`). Do not edit by hand.

## Open-loop voltage error on US06, 2RC and 3RC

Both models run without feedback on the US06 file of each temperature, as in `results/s1/model_fit.md`: measured current and temperature, reference SoC, every branch voltage 0 at the first row, the tables of `results/s1/params.csv` (2RC) and `results/s6/params_3rc.csv` (3RC). Error = model minus measured voltage. The window columns run up to the last row with reference SoC >= 10 % (docs/model.md C14).

| T (degC) | 2RC RMSE (mV) | 3RC RMSE (mV) | 3RC - 2RC (mV) | 2RC RMSE, SoC_ref >= 10 % (mV) | 3RC RMSE, SoC_ref >= 10 % (mV) |
|---|---|---|---|---|---|
| 40 | 20.90 | 27.91 | +7.01 | 18.31 | 20.74 |
| 25 | 29.79 | 46.79 | +17.01 | 22.20 | 26.35 |
| 10 | 40.68 | 60.00 | +19.32 | 40.68 | 60.00 |
| 0 | 59.47 | 61.99 | +2.52 | 59.47 | 61.99 |
| -10 | 73.74 | 87.11 | +13.37 | 73.74 | 87.11 |
| -20 | 104.58 | 103.29 | -1.29 | 104.58 | 103.29 |

Gate: the 3RC open-loop RMSE at 25 degC is 46.79 mV against the sanity limit of 30 mV. **FAIL.** The limit is a bug check, not a published target.

## 3RC level fits

Fit (a) gives R1, tau1, R3 and tau3 from the discharge pulses with tau1 in [0.5, 10] s and tau3 in [10, 50] s; fit (b) gives R2 and tau2 from the 1 h rest with tau2 in [50, 3600] s; R0 is that of `results/s1/params.csv` (docs/decisions.md 1.21). A time constant within 0.1 % of an end of its bounds counts as on the bound; tau2 is counted over the levels with a 1 h rest. Every level fit is in `results/s6/fit_levels_3rc.csv`.

| T (degC) | levels | failed fast fits | failed slow fits | tau1 on a bound | tau3 on a bound | tau2 on a bound | median tau3 (s) | median R3 (mOhm) |
|---|---|---|---|---|---|---|---|---|
| 40 | 11 | 0 | 0 | 1 | 2 | 0 | 17.4 | 7.68 |
| 25 | 12 | 0 | 0 | 1 | 2 | 0 | 23.8 | 11.25 |
| 10 | 11 | 0 | 0 | 4 | 1 | 0 | 26.5 | 14.85 |
| 0 | 10 | 0 | 0 | 4 | 1 | 0 | 17.0 | 13.44 |
| -10 | 10 | 0 | 0 | 9 | 2 | 0 | 28.2 | 29.79 |
| -20 | 9 | 0 | 0 | 9 | 3 | 0 | 17.1 | 29.78 |

Plot: `results/plots/s6/params_3rc.png`, the seven fitted tables against SoC, as `params.png` of S1.

## Ceiling: a third branch added to the 2RC model

A constant third branch, R3 in {2, 5, 10, 20} mOhm and tau3 in {10, 20, 30, 50} s, is added to the unchanged 2RC tables, and the lowest open-loop US06 RMSE is kept (docs/decisions.md 1.24). It is chosen on the validation file itself, so it bounds from above what a middle branch adds while R1, tau1, R2 and tau2 stay as fitted; it is not a fit.

| T (degC) | 2RC RMSE (mV) | best with a third branch (mV) | change (mV) | R3 (mOhm) | tau3 (s) |
|---|---|---|---|---|---|
| 40 | 20.90 | 19.07 | -1.83 | 2 | 20 |
| 25 | 29.79 | 29.04 | -0.75 | 2 | 20 |
| 10 | 40.68 | 39.77 | -0.91 | 2 | 20 |
| 0 | 59.47 | 57.70 | -1.77 | 5 | 20 |
| -10 | 73.74 | 71.27 | -2.48 | 5 | 30 |
| -20 | 104.58 | 102.56 | -2.01 | 10 | 30 |

## Ceiling over every drive cycle

The ceiling above, repeated on every run of the evaluation set and the tuning cycle and pooled per temperature (docs/decisions.md 1.25). R3 in {2, 5, 10, 20, 35, 50, 70, 100} mOhm and tau3 in {10, 20, 30, 50, 100} s. The pooled RMSE is over all rows of a temperature's runs together, error = model minus measured voltage over the whole run, as for US06 above. Like the ceiling above it is chosen on the data it is scored on; it is not a fit. A run is helped when its own best branch lowers its RMSE by more than 10 %.

| T (degC) | runs | 2RC pooled RMSE (mV) | best with a third branch (mV) | change (%) | R3 (mOhm) | tau3 (s) | runs helped |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 13.95 | 11.37 | -18.5 | 5 | 20 | 6 |
| 25 | 11 | 17.40 | 14.75 | -15.3 | 5 | 20 | 9 |
| 10 | 11 | 24.81 | 22.05 | -11.1 | 5 | 20 | 6 |
| 0 | 11 | 38.30 | 33.60 | -12.3 | 10 | 20 | 8 |
| -10 | 11 | 63.38 | 46.84 | -26.1 | 20 | 30 | 10 |
| -20 | 12 | 87.61 | 70.33 | -19.7 | 35 | 30 | 10 |

## Ceiling per drive run

Each run with its own best third branch on the same grid. Mean error = model minus measured voltage, averaged over the run; a positive mean is a model that drops too little voltage.

| T (degC) | cycle | 2RC RMSE (mV) | mean error (mV) | best with a third branch (mV) | R3 (mOhm) | tau3 (s) |
|---|---|---|---|---|---|---|
| 40 | UDDS | 14.58 | +9.1 | 11.28 | 10 | 30 |
| 40 | HWFET | 12.26 | +3.7 | 10.05 | 5 | 20 |
| 40 | LA92 | 12.95 | +6.7 | 8.81 | 5 | 20 |
| 40 | US06 | 20.90 | +0.1 | 19.07 | 2 | 20 |
| 40 | Mix 1 | 12.46 | +5.9 | 8.73 | 5 | 20 |
| 40 | Mix 2 | 12.81 | +3.8 | 10.16 | 5 | 20 |
| 40 | Mix 3 | 12.80 | +2.7 | 10.63 | 5 | 20 |
| 25 | UDDS | 13.22 | +8.5 | 8.36 | 10 | 30 |
| 25 | LA92 | 12.77 | +2.5 | 9.70 | 5 | 20 |
| 25 | US06 | 29.79 | -7.1 | 29.04 | 2 | 20 |
| 25 | Mix 1 | 15.93 | +2.6 | 13.79 | 5 | 20 |
| 25 | Mix 2 | 18.91 | +1.7 | 17.22 | 5 | 20 |
| 25 | Mix 3 | 18.26 | +6.4 | 14.84 | 5 | 20 |
| 25 | Mix 4 | 15.53 | +5.7 | 11.86 | 5 | 20 |
| 25 | Mix 5 | 18.20 | +2.4 | 15.95 | 5 | 20 |
| 25 | Mix 6 | 18.92 | +5.9 | 15.14 | 5 | 30 |
| 25 | Mix 7 | 19.09 | +6.3 | 15.06 | 5 | 30 |
| 25 | Mix 8 | 18.17 | +9.1 | 14.77 | 5 | 30 |
| 10 | UDDS | 13.65 | +8.6 | 8.66 | 10 | 30 |
| 10 | HWFET | 24.06 | +4.4 | 21.45 | 5 | 20 |
| 10 | LA92 | 24.27 | +15.8 | 15.41 | 10 | 30 |
| 10 | US06 | 40.68 | -9.8 | 39.77 | 2 | 20 |
| 10 | Mix 1 | 32.39 | -1.4 | 30.74 | 5 | 20 |
| 10 | Mix 2 | 24.33 | +4.9 | 22.63 | 5 | 20 |
| 10 | Mix 4 | 25.85 | +1.4 | 23.63 | 5 | 20 |
| 10 | Mix 5 | 30.32 | +1.8 | 27.91 | 5 | 20 |
| 10 | Mix 6 | 25.24 | +12.3 | 18.63 | 10 | 30 |
| 10 | Mix 7 | 21.89 | +7.7 | 16.67 | 10 | 30 |
| 10 | Mix 8 | 19.93 | +11.0 | 15.82 | 10 | 50 |
| 0 | UDDS | 23.48 | +12.3 | 17.43 | 20 | 50 |
| 0 | HWFET | 45.88 | +13.2 | 39.34 | 10 | 20 |
| 0 | LA92 | 31.89 | +11.6 | 25.58 | 10 | 30 |
| 0 | US06 | 59.47 | -9.6 | 57.70 | 5 | 20 |
| 0 | Mix 1 | 45.96 | +7.0 | 42.98 | 10 | 20 |
| 0 | Mix 2 | 34.90 | +17.5 | 29.58 | 10 | 30 |
| 0 | Mix 4 | 48.05 | -0.8 | 45.03 | 10 | 20 |
| 0 | Mix 5 | 41.80 | +11.4 | 37.05 | 10 | 20 |
| 0 | Mix 6 | 35.79 | +8.7 | 28.47 | 10 | 20 |
| 0 | Mix 7 | 38.98 | +12.2 | 30.61 | 10 | 20 |
| 0 | Mix 8 | 32.90 | +15.8 | 26.19 | 10 | 20 |
| -10 | UDDS | 40.46 | +31.3 | 18.07 | 50 | 50 |
| -10 | HWFET | 74.37 | +52.8 | 38.44 | 35 | 30 |
| -10 | LA92 | 54.15 | +31.4 | 29.75 | 35 | 50 |
| -10 | US06 | 73.74 | -0.2 | 71.27 | 5 | 30 |
| -10 | Mix 1 | 71.45 | +36.9 | 57.06 | 20 | 30 |
| -10 | Mix 2 | 59.52 | +34.8 | 40.78 | 20 | 30 |
| -10 | Mix 3 | 77.30 | +39.6 | 60.47 | 20 | 30 |
| -10 | Mix 5 | 64.78 | +38.4 | 48.76 | 20 | 30 |
| -10 | Mix 6 | 76.46 | +33.6 | 56.06 | 35 | 30 |
| -10 | Mix 7 | 69.49 | +35.0 | 48.12 | 20 | 30 |
| -10 | Mix 8 | 57.92 | +31.2 | 34.62 | 35 | 30 |
| -20 | UDDS | 69.85 | +53.2 | 35.35 | 70 | 50 |
| -20 | HWFET | 100.27 | +54.8 | 70.36 | 35 | 30 |
| -20 | LA92 | 77.54 | +44.4 | 54.14 | 35 | 30 |
| -20 | US06 | 104.58 | -2.9 | 102.56 | 10 | 30 |
| -20 | Mix 1 | 86.11 | +45.9 | 72.57 | 35 | 30 |
| -20 | Mix 2 | 85.39 | +43.5 | 56.77 | 35 | 30 |
| -20 | Mix 3 | 85.55 | +39.1 | 78.37 | 20 | 30 |
| -20 | Mix 4 | 92.84 | +52.4 | 69.22 | 35 | 30 |
| -20 | Mix 5 | 72.50 | +44.2 | 59.19 | 20 | 30 |
| -20 | Mix 6 | 103.43 | +42.6 | 88.48 | 35 | 30 |
| -20 | Mix 7 | 96.33 | +42.8 | 80.92 | 35 | 30 |
| -20 | Mix 8 | 94.56 | +53.6 | 50.98 | 50 | 50 |
