# Model fit

Written by `python/fit_all.py` (`make fit`). Do not edit by hand.

## Open-loop voltage error on US06

The 2RC model (docs/model.md Eq. 1 and Eq. 2) runs without any feedback on the US06 file of each temperature (docs/decisions.md 1.4). No fit uses these files.

What drives the simulation:

- the measured current (positive = discharge) and the measured cell temperature of every row;
- the reference SoC from the cycler's Ah counter, `SoC0 - Ah_removed / Q_ref` (Eq. 3, C13), so only the voltage model is under test, not the SoC estimate;
- the tables of `results/s1/params.csv` (the numbers the C file holds), read with the clamped bilinear lookup of Eq. 4;
- V1 = V2 = 0 at the first row: the model starts relaxed.

Error = model voltage minus measured voltage. RMSE and max |error| run over all rows used after the loader rules, and the gate uses this RMSE (docs/decisions.md 1.1). The last column is the RMSE over the rows up to the last one with reference SoC >= 10 % (the evaluation window of the EKF experiments, docs/model.md C14), for information only: no window is chosen to pass the gate. Duration is the last Time minus the first Time of the rows used.

| T (degC) | file | rows used | duration (s) | RMSE (mV) | max abs error (mV) | RMSE over SoC_ref >= 10 % (mV) |
|---|---|---|---|---|---|---|
| 40 | `40degC/11-06-18_19.09 556_US06_40degC_LGHG2.mat` | 39960 | 3995.9 | 20.90 | 79.80 | 18.31 |
| 25 | `25degC/10-29-18_10.08 551_US06_25degC_LGHG2.mat` | 40154 | 4015.3 | 29.79 | 79.59 | 22.20 |
| 10 | `10degC/11-13-18_18.38 567_US06_10degC_LGHG2.mat` | 38718 | 3871.6 | 40.68 | 140.37 | 40.68 |
| 0 | `0degC/11-30-18_19.02 589_US06_0degC_LGHG2.mat` | 33806 | 3380.4 | 59.47 | 235.77 | 59.47 |
| -10 | `n10degC/12-15-18_03.03 601_US06_n10degC_LGHG2.mat` | 31912 | 3191.1 | 73.74 | 291.03 | 73.74 |
| -20 | `n20degC/12-25-18_01.31 610_US06_n20degC_LGHG2.mat` | 27605 | 2760.4 | 104.58 | 368.87 | 104.58 |

Gate: the open-loop RMSE at 25 degC is 29.79 mV against the sanity limit of 30 mV. **PASS.** The limit is a bug check, not a published target.

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

Plot: `results/plots/s1/params.png`, R0, R1, tau1, R2 and tau2 against SoC, the HPPC level fits (dots) and the table on the SoC grid (dashed), one colour per temperature.

## OCV

The OCV table is the C/20 discharge curve plus a correction onto the HPPC rest voltages (docs/decisions.md 1.1; the correction at every rest point is in `results/s1/ocv_correction.csv`). OCV fallback (the 25 degC curve used at every temperature): no. Monotone on the measured range at 6 of 6 temperatures. The valid SoC range per temperature is in `results/s1/params.md`.

Plots: `results/plots/s1/ocv.png`, the C/20 curve (dashed), the corrected OCV (solid) and the HPPC rest voltages (dots) with the correction in mV below; `results/plots/s1/docv.png`, dOCV/dSoC on the SoC grid.
