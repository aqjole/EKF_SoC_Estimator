# Model fit, 3RC (S6)

Written by `python/fit_3rc.py` (`make fit-3rc`). Do not edit by hand.

## Open-loop voltage error on US06, 2RC and 3RC

Both models run without feedback on the US06 file of each temperature, as in `results/model_fit.md`: measured current and temperature, reference SoC, every branch voltage 0 at the first row, the tables of `results/params.csv` (2RC) and `results/params_3rc.csv` (3RC). Error = model minus measured voltage. The window columns run up to the last row with reference SoC >= 10 % (docs/model.md C14).

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

Fit (a) gives R1, tau1, R3 and tau3 from the discharge pulses with tau1 in [0.5, 10] s and tau3 in [10, 50] s; fit (b) gives R2 and tau2 from the 1 h rest with tau2 in [50, 3600] s; R0 is that of `results/params.csv` (docs/decisions.md 1.21). A time constant within 0.1 % of an end of its bounds counts as on the bound; tau2 is counted over the levels with a 1 h rest. Every level fit is in `results/fit_levels_3rc.csv`.

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
