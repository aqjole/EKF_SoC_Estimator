# Model fit

Written by `python/fit_all.py` (`make fit`). Do not edit by hand.

## Open-loop voltage error on US06

The 2RC model (docs/model.md Eq. 1 and Eq. 2) runs without any feedback on the US06 file of each temperature (docs/decisions.md 1.4). No fit uses these files.

What drives the simulation:

- the measured current (positive = discharge) and the measured cell temperature of every row;
- the reference SoC from the cycler's Ah counter, `SoC0 - Ah_removed / Q_ref` (Eq. 3, C13), so only the voltage model is under test, not the SoC estimate;
- the tables of `results/params.csv` (the numbers the C file holds), read with the clamped bilinear lookup of Eq. 4;
- V1 = V2 = 0 at the first row: the model starts relaxed.

Error = model voltage minus measured voltage. RMSE and max |error| run over all rows used after the loader rules, not over the SoC >= 10 % window of the EKF experiments. Duration is the last Time minus the first Time of those rows.

| T (degC) | file | rows used | duration (s) | RMSE (mV) | max abs error (mV) |
|---|---|---|---|---|---|
| 40 | `40degC/11-06-18_19.09 556_US06_40degC_LGHG2.mat` | 39960 | 3995.9 | 36.49 | 90.45 |
| 25 | `25degC/10-29-18_10.08 551_US06_25degC_LGHG2.mat` | 40154 | 4015.3 | 51.84 | 128.17 |
| 10 | `10degC/11-13-18_18.38 567_US06_10degC_LGHG2.mat` | 38718 | 3871.6 | 44.85 | 137.25 |
| 0 | `0degC/11-30-18_19.02 589_US06_0degC_LGHG2.mat` | 33806 | 3380.4 | 68.37 | 212.90 |
| -10 | `n10degC/12-15-18_03.03 601_US06_n10degC_LGHG2.mat` | 31912 | 3191.1 | 79.93 | 298.67 |
| -20 | `n20degC/12-25-18_01.31 610_US06_n20degC_LGHG2.mat` | 27605 | 2760.4 | 121.80 | 324.63 |

Gate: the open-loop RMSE at 25 degC is 51.84 mV against the sanity limit of 30 mV. **FAIL.** The limit is a bug check, not a published target.

Plots: `results/plots/s1/model_fit_<folder>.png`, measured and model voltage over time with the error below.

## HPPC pulses left out of the fits

The fits use discharge pulses only (docs/decisions.md 1.12). A discharge pulse is left out when it is cut by the limit (shorter than 9 s, or at 2.8 V), or, if it is not cut, when its current never reaches 98 % of the command within 0.3 s of the pulse's first row with current (the 98 % rule). Charge pulses are never fitted; the table counts those cut by the 4.2 V limit. A fit that did not converge is counted per level: the fast fit gives R0, R1 and tau1, the slow fit gives R2 and tau2 (the last level has none).

| T (degC) | levels | discharge pulses | cut by limit | 98 % rule not met | left out | used | charge pulses cut at 4.2 V | failed fast fits | failed slow fits |
|---|---|---|---|---|---|---|---|---|---|
| 40 | 11 | 44 | 3 | 0 | 3 | 41 | 5 | 0 | 0 |
| 25 | 12 | 48 | 6 | 0 | 6 | 42 | 7 | 0 | 0 |
| 10 | 11 | 44 | 4 | 0 | 4 | 40 | 9 | 0 | 0 |
| 0 | 10 | 40 | 5 | 0 | 5 | 35 | 6 | 0 | 0 |
| -10 | 10 | 40 | 4 | 0 | 4 | 36 | 11 | 0 | 0 |
| -20 | 9 | 36 | 2 | 0 | 2 | 34 | 11 | 0 | 0 |

## OCV

OCV fallback (the 25 degC curve used at every temperature): no. Monotone on the measured range at 6 of 6 temperatures. The valid SoC range per temperature is in `results/params.md`.
