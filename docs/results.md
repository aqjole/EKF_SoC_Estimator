# Results in full

The detail behind the [README](../README.md): the dataset, every `make` target, the results of every stage with all their tables and plots, and the C port. Every table between `<!-- results:<key>:begin -->` and `<!-- results:<key>:end -->` markers is copied from a file in `results/` by `python/update_readme.py`; `make readme-check` and CI fail when this file and `results/` disagree. The rules behind each result are in [`decisions.md`](decisions.md), the equations in [`model.md`](model.md).

## Dataset

LG 18650HG2 Li-ion Battery Data, P. Kollmeyer, M. Naguib and M. Skells, McMaster University, Mendeley Data, version 2, DOI [10.17632/b5mj79w5w9.2](https://doi.org/10.17632/b5mj79w5w9.2), licence CC BY 4.0. A new LG HG2 cell (nominal 3 Ah) was tested in a thermal chamber at 40, 25, 10, 0, -10 and -20 degC.

What this project uses from it, at all six temperatures:

- the C/20 discharge, for the OCV table;
- the HPPC test, for R0, R1, tau1, R2 and tau2 and for the OCV correction;
- the drive cycles UDDS, HWFET, LA92, US06 and the eight random mixes of them (Mix 1 to Mix 8), for the open-loop model check and the EKF experiments;
- the 1C and C/20 capacity tests, to document capacity and ageing.

The evaluation set is 62 drive-cycle runs (`docs/decisions.md` 1.5). Mix 1 at 25 degC is the tuning cycle; it is reported and flagged, but it is not in the set. Left out: the 25 degC HWFET file (it holds no current), the 40 degC Mix 4 to 8 files (partial runs), the -10 degC Mix 4 file (a corrupt log) and the PausCycl files (short runs the dataset readme does not list as tests). Mix 3 has no file at 10 and 0 degC. Tables show `n/a` where a run does not exist. The campaign ran 25 degC first, then 40, 10, 0, -10 and -20 degC, so the cell aged between temperatures. The measured capacities per folder:

<!-- results:capacity:begin -->

**C/20 and 1C capacities per folder**

The two 1C columns are the folder's first and second 1C run in the order they ran (the readme puts the first before UDDS and the second before Mix 3). A folder with only one 1C file has it in the first-run column if it started before the folder's UDDS file, otherwise in the second-run column. *cell T* is the temperature the cell was actually at (min / max over the discharge). *C/20 charge* is the Ah put back by the charge part of the same C20DisCh file (highest counter after the discharge minus the counter at the end of the discharge); it is shown for comparison only.

| folder | C/20 discharge (Ah) | C/20 charge, same file (Ah) | charge / discharge | 1C first run (Ah) | first run: file, cell T (degC) | 1C second run (Ah) | second run: file, cell T (degC) |
|---|---|---|---|---|---|---|---|
| 25degC | 2.7807 | 2.9709 | 1.068 | 2.7264 | `551_Cap_1C_25degC_LGHG2`, 23.9 / 25.4 | 2.6928 | `552_Cap_1C_25degC_LGHG2`, 23.8 / 25.4 |
| 40degC | 2.6899 | 2.8668 | 1.066 | missing | no file | 2.5004 | `557_Cap_1C_40degC_LGHG2`, 1.3 / 30.7; **off-temperature**, not a 40 degC capacity |
| 10degC | 2.6488 | 2.6959 | 1.018 | 2.4851 | `571_Cap_1C`, 0.7 / 3.6; **off-temperature**, not a 10 degC capacity | 2.5465 | `576_Cap_1C_10degC_LGHG2`, 9.1 / 11.0 |
| 0degC | 2.5986 | 2.6869 | 1.034 | 2.4734 | `589_Cap_1C_10degC_LGHG2`, -0.6 / 2.2; named 10 degC, valid as 0 degC | missing | no file |
| n10degC | 2.5636 | 2.6018 | 1.015 | 2.2634 | `596_Cap_1C_n10degC_LGHG2`, -10.1 / -6.4 | 2.2319 | `602_Cap_1C_n10degC_LGHG2`, -10.0 / -6.5 |
| n20degC | 2.4948 | 2.4526 | 0.983 | 1.6713 | `610_Cap_1C_n20degC_LGHG2`, -19.8 / -15.4 | 1.6172 | `611_Cap_1C_n20degC_LGHG2`, -19.9 / -15.6 |

- 40degC: the only 1C file, `557_Cap_1C_40degC_LGHG2`, started after the folder's UDDS (`556_UDDS_40degC_LGHG2`), so it is the second run; the first run is missing. Before UDDS, where the readme puts the first 1C test, the data shows an unlogged discharge: `556_Charge2` opens at rest at 3.046 V, 65 min after 556_Charge1 ended at 4.193 V.
- `40degC/557_Cap_1C_40degC_LGHG2`: cell at 30.7 degC when the discharge starts, 1.3 / 30.7 degC min / max over it; folder 40 degC. Not a 40 degC capacity.
- `10degC/571_Cap_1C`: cell at 3.6 degC when the discharge starts, 0.7 / 3.6 degC min / max over it; folder 10 degC. Not a 10 degC capacity.
- 0degC: the only 1C file, `589_Cap_1C_10degC_LGHG2`, started before the folder's UDDS (`589_UDDS_0degC_LGHG2`), so it is the first run; the second run is missing.
- `0degC/589_Cap_1C_10degC_LGHG2`: cell at -0.6 degC when the discharge starts, -0.6 / 2.2 degC min / max over it; folder 0 degC. The name says 10 degC, but this is the 0 degC 1C test.
- The C/20, 0.5C and 2C tests all start their discharge within 5 degC of the folder temperature.

<!-- results:capacity:end -->

## How to run: every target

Requirements: Python 3.12, CMake and a C99 compiler. `make arm` also needs `arm-none-eabi-gcc`, the release named in `results/c_footprint.md`. `make octave` needs GNU Octave 8 or later with `octave-cli` on PATH; `results/equivalence_octave.md` was written with GNU Octave 8.4.0 (`docs/decisions.md` 1.20).

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
make data        # download the raw .mat files into data/raw/ and verify their sha256
make all         # every stage below, in order
```

| target | stage | what it does | writes |
|---|---|---|---|
| `make data` | | fetches the dataset file by file and checks each file against `data/checksums.sha256` | `data/raw/` (git-ignored) |
| `make inventory` | S0 | lists every file and measures the capacity tests | `results/data_inventory.md`, `results/capacity.md` |
| `make checks` | S0 | measures the dataset properties the docs cite | `results/data_checks.md` |
| `make fit` | S1 | fits the OCV and 2RC tables, runs the US06 open-loop check, generates the C tables | `results/params.*`, `results/model_fit.md`, `results/plots/s1/`, `c/src/ekf_params.c` |
| `make tune` | S2 | tunes the noise settings on the tuning cycle and freezes them; not part of `make all` | `results/tuning.md`, `results/ekf_config.json` |
| `make ekf` | S2 | runs the four experiments on the evaluation set and the tuning cycle | `results/ekf_results.csv`, `results/ekf_summary.md`, `results/plots/s2/` |
| `make c` | S3 | builds the C library in the float and double builds and runs ctest | `c/build/` (git-ignored) |
| `make equiv` | S3 | runs the C filter against the Python filter on every run | `results/equivalence.md`, `results/plots/s3/` |
| `make arm` | S3 | cross-compiles for a Cortex-M4 and checks for double-precision helpers | `results/c_footprint.md` |
| `make sensitivity` | S5 | runs experiment 1 with the filter capacity at -5 % and +5 % and at 1 Hz | `results/sensitivity.*`, `results/plots/s5/sensitivity_*.png` |
| `make octave` | S5 | runs the Octave filter against the Python filter on every run; slow, because Octave runs the filter row by row | `results/equivalence_octave.md`, `results/plots/s5/equivalence_octave_25degC.png` |
| `make fit-3rc` | S6 | fits the 3RC model from the same HPPC files, runs both models open loop on US06, and the third-branch ceiling check on US06 and on every drive run; needs `make fit` | `results/fit_levels_3rc.csv`, `results/params_3rc.csv`, `results/model_fit_3rc.md`, `results/plots/s6/` |
| `make fit-3rc-rest` | S6 | fits the middle branch alone on the HPPC pulse trains with the 2RC tables fixed, and runs the result open loop on US06 and on every drive run; needs `make fit` | `results/fit_levels_3rc_rest.csv`, `results/params_3rc_rest.csv`, `results/model_fit_3rc_rest.md`, `results/plots/s6/params_3rc_rest.png` |
| `make fit-r1i` | S7 | fits R1 per HPPC discharge pulse and builds the R1 table over current, then runs the 2RC-I model open loop on US06 and on every drive run; needs `make fit` | `results/fit_pulses_r1i.csv`, `results/r1_current.csv`, `results/model_fit_r1i.md`, `results/plots/s7/r1_current.png` |
| `make ekf-r1i` | S7 | runs experiments 1 to 4 on the 2RC-I model and writes the comparison with the adoption verdict; needs `make ekf` and `make fit-r1i` | `results/ekf_results_r1i.csv`, `results/model_compare_r1i.md`, `results/plots/s7/model_compare_r1i.png` |
| `make ekf-r1d` | S8 | runs experiments 1 to 4 on the 2RC-Id model (v1.0 R1 under regen) and writes the comparison with the guards and the verdict; needs `make ekf` and `make ekf-r1i` | `results/ekf_results_r1d.csv`, `results/model_compare_r1d.md`, `results/plots/s8/model_compare_r1d.png` |
| `make fit-r1c` | S8 | fits a charge-side R1 per HPPC charge pulse and builds its table over current, then runs the 2RC-Ic model open loop on US06; needs `make fit` and `make fit-r1i` | `results/fit_pulses_r1c.csv`, `results/r1_charge.csv`, `results/model_fit_r1c.md`, `results/plots/s8/r1_charge.png` |
| `make ekf-r1c` | S8 | runs experiments 1 to 4 on the 2RC-Ic model and writes the four-model comparison with the guards and the verdict; needs `make ekf`, `make ekf-r1i`, `make ekf-r1d` and `make fit-r1c` | `results/ekf_results_r1c.csv`, `results/model_compare_r1c.md`, `results/plots/s8/model_compare_r1c.png` |
| `make fit-r1l` | S8 | fits one low-current R1 factor per temperature on the PausCycl files and builds the 2RC-Il table, then runs it open loop on US06 and on every drive run; needs `make fit` and `make fit-r1i` | `results/r1_low.csv`, `results/model_fit_r1l.md` |
| `make ekf-r1l` | S8 | runs experiments 1 to 4 on the 2RC-Il model and writes the comparison with the guards and the verdict; needs `make ekf`, `make ekf-r1i` and `make fit-r1l` | `results/ekf_results_r1l.csv`, `results/model_compare_r1l.md`, `results/plots/s8/model_compare_r1l.png` |
| `make fit-3rcd` | S9 | fits R3 and the R2 scale on the 40 Mix runs, then scores the exported model open loop on both splits and the US06 gate. Needs `make fit` and `make fit-r1i` | `results/fit_nodes_3rcd.csv`, `results/params_3rcd.csv`, `results/model_fit_3rcd.md`, `results/plots/s9/params_3rcd.png` |
| `make ekf-3rcd` | S9 | runs experiments 1 to 4 with the frozen noise settings after the S1 gate passes and decides adoption on the 23 standard-cycle runs. Needs `make ekf`, `make ekf-r1i` and `make fit-3rcd` | `results/ekf_results_3rcd.csv`, `results/model_compare_3rcd.md`, `results/plots/s9/model_compare_3rcd.png` |
| `make accuracy` | S10 | runs the fit and evaluation followed by the separate diagnosis under decisions 1.44 and 1.47 | the following three targets |
| `make diagnose-accuracy` | S10 | checks residuals and timing and measures local Jacobian terms on all 63 incumbent experiment-1 trajectories | `results/accuracy_diagnostics.md`, `results/accuracy_residual_bins.csv`, `results/accuracy_jacobian.csv`, `results/plots/s10/accuracy_residuals.png` |
| `make fit-3rcd0` | S10 | fits the S9 parameterization using v1.0 R1 and the frozen inputs | `results/params_3rcd0.csv`, `results/fit_nodes_3rcd0.csv`, `results/model_fit_3rcd0.md`, `results/plots/s10/params_3rcd0.png` |
| `make ekf-3rcd0` | S10 | applies the S1 gate, runs the frozen experiments and guards, and scores the unfitted S9 R1 substitution and sensitivity | `results/ekf_results_3rcd0.csv`, `results/model_compare_3rcd0.md`, `results/sensitivity_3rcd0.csv`, `results/plots/s10/model_compare_3rcd0.png` |
| `make tune-3rcd0` | S11 A | searches 864 grid points and 81 refinement points on 40 Mix runs; not in `make all` | `results/tuning_3rcd0.md`, `results/ekf_config_3rcd0.json`, `results/plots/s11/tuning_3rcd0.png` |
| `make ekf-3rcd0n` | S11 A | evaluates the settings candidate in Python on all 63 runs, eight adoption guards and wrong-start diagnostics | `results/model_compare_3rcd0n.md`, `results/ekf_results_3rcd0n.csv`, `results/plots/s11/model_compare_3rcd0n.png` |
| `make diagnose-regen` | S11 B | finds the regen rows at the 4.2 V limit in all 63 runs and reports each model's experiment-1 SoC error change across them, from the stored traces | `results/regen_limit.md`, `results/regen_limit.csv`, `results/plots/s11/regen_limit.png` |
| `make diagnose-starts` | S12 A | the history before each run, the 189 wrong-start cases of 3RC-D0 replayed with their start measures, and the branch prior alone on the 40 Mix runs through the native evaluator | `results/start_cases.md`, `results/start_cases.csv`, `results/plots/s12/start_cases.png` |
| `make c-3rcd0` | S11 | regenerates the 3RC-D0 C tables and test vectors, builds float and double with `-DEKF_USE_3RCD0=ON` and runs the unit tests | `c/src/ekf_params_3rcd0.c`, `c/include/ekf_params_3rcd0.h`, `c/tests/vectors/vectors_3rcd0.h` |
| `make equiv-3rcd0` | S11 | compares both 3RC-D0 builds with the Python traces in six experiment cases on all 63 runs | `results/equivalence_3rcd0.md`, `results/equivalence_3rcd0.csv` |
| `make arm-3rcd0` | S11 | cross-compiles the 3RC-D0 build for a Cortex-M4 with `-fstack-usage` | `results/c_footprint_3rcd0.md` |
| `make readme` | S4 | copies the results tables into `README.md` and this file | `README.md`, `docs/results.md` |
| `make readme-check` | S4 | fails if `README.md` or this file is out of sync with `results/` | |

Notes:

- The raw data is downloaded by `data/download.sh` and is never committed. The committed fixtures let the unit tests and the C equivalence tests run without it.
- `make ekf` takes several minutes on a cold run. It caches per-run traces in `results/runs/` (git-ignored) and reuses them while they are newer than the code, so a second run takes seconds.
- Unit tests: `.venv/bin/python -m pytest python/tests -q`. Tests that need the raw data are skipped when `data/raw/` is empty.

## Results

### S1: model fit

The 2RC model runs open loop (no feedback) on the US06 cycle of each temperature. No fit uses these files.

<!-- results:model_fit:begin -->

**Open-loop voltage error on US06**

The 2RC model (docs/model.md Eq. 1 and Eq. 2) runs without any feedback on the US06 file of each temperature (docs/decisions.md 1.4). No fit uses these files.

What drives the simulation:

- the measured current (positive = discharge) and the measured cell temperature of every row;
- the reference SoC from the cycler's Ah counter, `SoC0 - Ah_removed / Q_ref` (Eq. 3, C13), so only the voltage model is under test, not the SoC estimate;
- the tables of `results/params.csv` (the numbers the C file holds), read with the clamped bilinear lookup of Eq. 4;
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

<!-- results:model_fit:end -->

![US06 open-loop model fit at 25 degC](../results/plots/s1/model_fit_25degC.png)

The OCV per temperature: the C/20 discharge curve, the corrected OCV and the HPPC rest voltages, with the correction below.

![OCV per temperature](../results/plots/s1/ocv.png)

<details>
<summary>The OCV correction at every HPPC rest point</summary>

<!-- results:ocv_correction:begin -->

**OCV correction from the HPPC rest voltages**

At each rest point (the last row of every 1 h rest after a move, and the last row before the first discharge pulse of level 1) delta = V rest - V C/20 at the same SoC, and a PCHIP through the deltas, held flat beyond the first and last point, is added to the C/20 curve (docs/decisions.md 1.1).

| T (degC) | SoC (%) | V rest (V) | V C/20 (V) | delta (mV) |
|---|---|---|---|---|
| 40 | 100 | 4.1807 | 4.1735 | 7.23 |
| 40 | 94.61 | 4.1062 | 4.1003 | 5.933 |
| 40 | 89.21 | 4.0848 | 4.0787 | 6.09 |
| 40 | 78.42 | 4.0095 | 4.0032 | 6.324 |
| 40 | 67.63 | 3.9136 | 3.9044 | 9.145 |
| 40 | 56.84 | 3.7969 | 3.7899 | 7.053 |
| 40 | 46.06 | 3.7002 | 3.6924 | 7.794 |
| 40 | 35.27 | 3.6179 | 3.607 | 10.89 |
| 40 | 24.48 | 3.5063 | 3.4944 | 11.95 |
| 40 | 13.69 | 3.3704 | 3.3371 | 33.33 |
| 40 | 8.296 | 3.2154 | 3.1593 | 56.07 |
| 25 | 100 | 4.1853 | 4.176 | 9.25 |
| 25 | 94.61 | 4.1067 | 4.0986 | 8.157 |
| 25 | 89.21 | 4.0842 | 4.076 | 8.174 |
| 25 | 78.42 | 4.01 | 3.9996 | 10.4 |
| 25 | 67.63 | 3.9141 | 3.8988 | 15.25 |
| 25 | 56.84 | 3.7986 | 3.7848 | 13.8 |
| 25 | 46.06 | 3.6991 | 3.6871 | 12.06 |
| 25 | 35.27 | 3.6299 | 3.6121 | 17.73 |
| 25 | 24.48 | 3.5137 | 3.4976 | 16.1 |
| 25 | 13.69 | 3.408 | 3.3694 | 38.63 |
| 25 | 8.296 | 3.2771 | 3.2208 | 56.23 |
| 25 | 2.902 | 3.1227 | 3.0287 | 93.95 |
| 10 | 100 | 4.1927 | 4.173 | 19.7 |
| 10 | 94.79 | 4.1084 | 4.0944 | 14.06 |
| 10 | 89.57 | 4.0855 | 4.0735 | 12.01 |
| 10 | 79.14 | 4.023 | 4.0096 | 13.37 |
| 10 | 68.71 | 3.9252 | 3.9071 | 18.07 |
| 10 | 58.28 | 3.8148 | 3.7988 | 16.01 |
| 10 | 47.85 | 3.7116 | 3.7014 | 10.21 |
| 10 | 37.43 | 3.6378 | 3.6231 | 14.65 |
| 10 | 27 | 3.5316 | 3.5271 | 4.469 |
| 10 | 16.57 | 3.3996 | 3.4141 | -14.54 |
| 10 | 11.35 | 3.2555 | 3.2483 | 7.158 |
| 0 | 100 | 4.188 | 4.1627 | 25.26 |
| 0 | 94.61 | 4.1032 | 4.0819 | 21.29 |
| 0 | 89.21 | 4.0818 | 4.0626 | 19.16 |
| 0 | 78.42 | 4.0107 | 3.989 | 21.68 |
| 0 | 67.63 | 3.9107 | 3.8799 | 30.76 |
| 0 | 56.85 | 3.7932 | 3.7713 | 21.94 |
| 0 | 46.06 | 3.689 | 3.67 | 18.98 |
| 0 | 35.27 | 3.6203 | 3.5939 | 26.37 |
| 0 | 24.48 | 3.5029 | 3.484 | 18.97 |
| 0 | 13.69 | 3.3138 | 3.2829 | 30.87 |
| -10 | 100 | 4.19 | 4.1366 | 53.41 |
| -10 | 94.61 | 4.0998 | 4.0625 | 37.28 |
| -10 | 89.21 | 4.0793 | 4.046 | 33.28 |
| -10 | 78.42 | 4.0071 | 3.9699 | 37.21 |
| -10 | 67.63 | 3.8895 | 3.8571 | 32.31 |
| -10 | 56.84 | 3.7925 | 3.7589 | 33.59 |
| -10 | 46.06 | 3.6862 | 3.6552 | 30.99 |
| -10 | 35.27 | 3.6113 | 3.5752 | 36.1 |
| -10 | 24.48 | 3.5021 | 3.4721 | 29.99 |
| -10 | 13.69 | 3.2686 | 3.2302 | 38.44 |
| -20 | 100 | 4.1883 | 4.0747 | 113.6 |
| -20 | 94.61 | 4.0929 | 4.0171 | 75.86 |
| -20 | 89.21 | 4.0739 | 4.0011 | 72.75 |
| -20 | 78.42 | 3.9844 | 3.9223 | 62.05 |
| -20 | 67.63 | 3.881 | 3.8199 | 61.15 |
| -20 | 56.84 | 3.7834 | 3.7279 | 55.48 |
| -20 | 46.06 | 3.6712 | 3.615 | 56.14 |
| -20 | 35.27 | 3.5813 | 3.5266 | 54.7 |
| -20 | 24.48 | 3.4965 | 3.4282 | 68.38 |

<!-- results:ocv_correction:end -->

</details>

### S2: EKF experiments

Four experiments run on every evaluation run and the tuning cycle with the same frozen noise settings. Experiment 1 starts at the correct SoC. Experiment 2 starts with the SoC too low. Experiment 3 restarts the filter mid-run with a start too low and one too high. Experiment 4 adds a constant offset to the current seen by the filter and by coulomb counting. The experiment 3 start values are in the table titles below. The offset size is set in `docs/decisions.md` 1.7 and stated in the experiment 4 section of `results/ekf_summary.md`.

<!-- results:ekf_legend:begin -->

**Legend**

- 63 runs (the evaluation set and the tuning cycle), one row per run and experiment in `results/ekf_results.csv`. The noise settings are the frozen ones of `results/ekf_config.json`: q_soc = 1e-07 1/s, q_v = 1e-06 V^2/s, r = 0.01 V^2, and the same for every experiment and temperature.
- Error = estimate - reference; the reference follows the cycler's Ah counter (docs/model.md C4).
- Evaluation window: from the filter start to the last sample where the reference SoC is at least 10 % (docs/model.md C14). Every metric is over this window. Times are in s since the filter start.
- `*` marks the tuning cycle (Mix 1 at 25 degC), on which the noise settings were tuned for experiments 2 and 4 (the mean of their SoC RMSE, docs/decisions.md 1.16). `n/a`: no run exists. `not reached`: the error is outside the band at the end of the window, or the run is still apart from the run with the correct init; it is not an average.
- `mean` rows average the evaluation runs of the column (tuning cycle excluded); `mean of reached` leaves out the runs that did not reach; `reached` counts them.

<!-- results:ekf_legend:end -->

#### Experiment 1: correct initial SoC

<!-- results:ekf_exp1:begin -->

**Experiment 1: correct initial SoC / SoC RMSE (pp)**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.81 | 0.88 | 1.04 | 1.50 | 2.83 | 3.27 |
| HWFET | 0.80 | n/a | 0.96 | 2.67 | 3.79 | 3.09 |
| LA92 | 0.73 | 0.68 | 1.63 | 1.35 | 2.33 | 2.41 |
| US06 | 1.04 | 1.05 | 1.18 | 1.13 | 3.23 | 2.75 |
| Mix 1 | 0.69 | 0.61* | 0.90 | 1.98 | 2.39 | 2.59 |
| Mix 2 | 0.71 | 0.87 | 1.14 | 1.48 | 2.69 | 2.92 |
| Mix 3 | 0.73 | 1.14 | n/a | n/a | 3.11 | 1.90 |
| Mix 4 | n/a | 1.09 | 1.52 | 1.87 | n/a | 6.05 |
| Mix 5 | n/a | 0.69 | 1.22 | 2.06 | 2.70 | 2.64 |
| Mix 6 | n/a | 0.58 | 1.20 | 1.87 | 2.57 | 3.96 |
| Mix 7 | n/a | 0.80 | 1.11 | 1.76 | 3.74 | 3.64 |
| Mix 8 | n/a | 0.95 | 1.08 | 4.73 | 8.38 | 9.12 |
| **mean** | 0.79 | 0.87 | 1.18 | 2.04 | 3.43 | 3.70 |

**Experiment 1: correct initial SoC / Coulomb counting against the reference: SoC RMSE (pp)**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.11 | 0.02 | 0.00 | 0.02 | 0.12 | 0.03 |
| HWFET | 0.00 | n/a | 0.00 | 0.01 | 0.00 | 0.00 |
| LA92 | 0.09 | 0.06 | 0.02 | 0.04 | 0.02 | 0.04 |
| US06 | 0.01 | 0.03 | 0.13 | 0.18 | 0.03 | 0.13 |
| Mix 1 | 0.12 | 0.05* | 0.02 | 0.00 | 0.03 | 0.01 |
| Mix 2 | 0.03 | 0.02 | 0.00 | 0.03 | 0.01 | 0.00 |
| Mix 3 | 0.02 | 0.09 | n/a | n/a | 0.06 | 0.01 |
| Mix 4 | n/a | 0.01 | 0.02 | 0.04 | n/a | 0.01 |
| Mix 5 | n/a | 0.01 | 0.02 | 0.03 | 0.00 | 0.06 |
| Mix 6 | n/a | 0.01 | 0.03 | 0.05 | 0.10 | 0.02 |
| Mix 7 | n/a | 0.02 | 0.09 | 0.01 | 0.03 | 0.01 |
| Mix 8 | n/a | 0.08 | 0.03 | 0.03 | 0.09 | 0.03 |
| **mean** | 0.06 | 0.03 | 0.03 | 0.04 | 0.05 | 0.03 |

<!-- results:ekf_exp1:end -->

#### Experiment 2: initial SoC too low

<!-- results:ekf_exp2:begin -->

**Experiment 2: initial SoC 20 pp too low / SoC RMSE (pp)**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.84 | 0.90 | 1.02 | 1.48 | 2.80 | 3.49 |
| HWFET | 1.22 | n/a | 1.18 | 2.87 | 4.32 | 7.00 |
| LA92 | 0.80 | 0.69 | 2.00 | 1.32 | 2.38 | 2.73 |
| US06 | 0.99 | 0.93 | 1.20 | 1.22 | 3.21 | 2.50 |
| Mix 1 | 0.76 | 0.65* | 0.90 | 1.96 | 2.36 | 2.48 |
| Mix 2 | 0.78 | 0.90 | 1.17 | 1.48 | 2.65 | 2.89 |
| Mix 3 | 0.91 | 1.19 | n/a | n/a | 3.14 | 1.93 |
| Mix 4 | n/a | 1.04 | 1.51 | 2.37 | n/a | 16.97 |
| Mix 5 | n/a | 0.71 | 1.14 | 1.98 | 2.64 | 2.40 |
| Mix 6 | n/a | 0.61 | 1.27 | 1.77 | 2.35 | 3.53 |
| Mix 7 | n/a | 1.05 | 1.43 | 3.52 | 3.42 | 14.36 |
| Mix 8 | n/a | 0.95 | 1.06 | 6.26 | 9.65 | 23.71 |
| **mean** | 0.90 | 0.90 | 1.26 | 2.39 | 3.54 | 7.00 |

**Experiment 2: initial SoC 20 pp too low / Convergence time t_conv (s): the error stays within +-2 pp from then on**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | not reached | 14023.5 | 13997.2 | 13174.3 | 12118.2 | 7361.4 |
| HWFET | 912.6 | n/a | 3808.2 | 4406.0 | 4479.2 | 2829.5 |
| LA92 | 7.1 | 8136.2 | 8504.3 | 7622.1 | 7103.8 | not reached |
| US06 | 3188.5 | 3268.4 | 3285.6 | 3148.9 | not reached | not reached |
| Mix 1 | 7.1 | 2.4* | 6236.3 | 6221.5 | not reached | not reached |
| Mix 2 | 5.7 | 7235.2 | 6329.9 | 6668.9 | not reached | 3764.8 |
| Mix 3 | 891.2 | 6452.7 | n/a | n/a | not reached | 3845.9 |
| Mix 4 | n/a | not reached | 6272.3 | 6232.9 | n/a | 4249.0 |
| Mix 5 | n/a | 2.5 | 6089.8 | 5961.8 | not reached | 4130.3 |
| Mix 6 | n/a | 2.4 | 6781.1 | 5702.8 | 5304.9 | not reached |
| Mix 7 | n/a | 941.3 | 6227.2 | 5714.6 | not reached | not reached |
| Mix 8 | n/a | 7731.5 | 6687.5 | 7119.3 | not reached | not reached |
| **mean of reached** | 835.4 | 5310.4 | 6747.2 | 6543.0 | 7251.5 | 4363.5 |
| **reached** | 6 of 7 | 9 of 10 | 11 of 11 | 11 of 11 | 4 of 11 | 6 of 12 |

<!-- results:ekf_exp2:end -->

![Experiment 2, US06 at 25 degC](../results/plots/s2/trace_exp2_US06_25degC.png)
![Experiment 2, US06 at -20 degC](../results/plots/s2/trace_exp2_US06_n20degC.png)

#### Experiment 3: restart mid-run with a wrong SoC

<!-- results:ekf_exp3:begin -->

**Experiment 3, low start: initial SoC 50 % from a reference of 70 % / Convergence time t_conv (s): the error stays within +-2 pp from then on**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | not reached | 8634.3 | 8816.6 | 8253.7 | 7551.3 | not reached |
| HWFET | 184.6 | n/a | 2067.4 | 2719.1 | not reached | not reached |
| LA92 | 129.1 | 4863.3 | 5369.4 | 4866.9 | 4501.9 | not reached |
| US06 | 1959.1 | 2078.9 | 2113.7 | 2163.0 | not reached | not reached |
| Mix 1 | 390.7 | 667.2* | 4141.2 | 4166.5 | 3802.3 | not reached |
| Mix 2 | 170.1 | 4348.2 | 3580.6 | 3977.5 | not reached | 1418.4 |
| Mix 3 | 369.3 | 4630.7 | n/a | n/a | not reached | 1397.9 |
| Mix 4 | n/a | not reached | 3644.9 | 3802.2 | n/a | 1935.3 |
| Mix 5 | n/a | 124.9 | 4145.9 | 4059.9 | not reached | 2257.5 |
| Mix 6 | n/a | 157.2 | 4187.1 | 3217.7 | not reached | not reached |
| Mix 7 | n/a | 154.4 | 4057.8 | 3737.3 | not reached | not reached |
| Mix 8 | n/a | 4321.1 | 3314.2 | 3695.2 | not reached | not reached |
| **mean of reached** | 533.8 | 3257.0 | 4130.8 | 4059.9 | 5285.2 | 1752.3 |
| **reached** | 6 of 7 | 9 of 10 | 11 of 11 | 11 of 11 | 3 of 11 | 4 of 12 |

**Experiment 3, high start: initial SoC 90 % from a reference of 70 % / Convergence time t_conv (s): the error stays within +-2 pp from then on**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | not reached | 8634.3 | 8816.6 | 8253.7 | 7542.8 | 3820.0 |
| HWFET | 0.2 | n/a | 2564.1 | 2711.4 | not reached | 1823.7 |
| LA92 | 0.1 | 4858.3 | 5369.5 | 4866.9 | 4510.4 | not reached |
| US06 | 0.1 | 2014.8 | 2113.6 | 2164.5 | not reached | not reached |
| Mix 1 | 29.5 | 79.9* | 4141.1 | 4165.9 | 3798.8 | not reached |
| Mix 2 | 23.4 | 4339.5 | 3586.5 | 3977.5 | not reached | not reached |
| Mix 3 | 93.5 | 4629.9 | n/a | n/a | not reached | 1391.5 |
| Mix 4 | n/a | not reached | 3644.9 | 3802.2 | n/a | 1936.9 |
| Mix 5 | n/a | 340.1 | 4145.2 | 4057.0 | not reached | 2122.9 |
| Mix 6 | n/a | 1055.3 | 4188.1 | 3207.5 | not reached | not reached |
| Mix 7 | n/a | 1155.0 | 4088.6 | 3736.2 | not reached | not reached |
| Mix 8 | n/a | 4317.9 | 3314.2 | 3693.2 | not reached | not reached |
| **mean of reached** | 24.5 | 3482.8 | 4179.3 | 4057.8 | 5284.0 | 2219.0 |
| **reached** | 6 of 7 | 9 of 10 | 11 of 11 | 11 of 11 | 3 of 11 | 5 of 12 |

<!-- results:ekf_exp3:end -->

#### Experiment 4: current-sensor offset

<!-- results:ekf_exp4:begin -->

**Experiment 4: current offset / EKF error at the end of the window (pp)**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | -2.32 | -1.41 | -0.44 | -0.29 | +0.77 | +2.40 |
| HWFET | -0.99 | n/a | +0.59 | +1.04 | -1.31 | -0.35 |
| LA92 | -1.20 | -2.06 | -1.20 | -0.21 | +0.70 | +3.65 |
| US06 | -1.35 | -1.62 | +0.58 | +1.85 | +6.67 | +4.13 |
| Mix 1 | -1.78 | -1.68* | +0.85 | +0.16 | -1.80 | +3.45 |
| Mix 2 | -1.84 | -2.06 | +0.41 | +0.12 | +5.94 | +6.50 |
| Mix 3 | -1.33 | -1.99 | n/a | n/a | +6.42 | +0.42 |
| Mix 4 | n/a | -2.78 | +0.32 | +1.24 | n/a | -0.54 |
| Mix 5 | n/a | +0.30 | +0.97 | +0.16 | -2.19 | -0.11 |
| Mix 6 | n/a | -1.97 | -0.64 | -0.35 | -1.90 | +4.95 |
| Mix 7 | n/a | -1.87 | -0.44 | -0.58 | -2.23 | +2.53 |
| Mix 8 | n/a | -1.98 | -0.17 | -0.99 | -2.79 | +5.84 |
| **mean** | -1.54 | -1.74 | +0.07 | +0.20 | +0.75 | +2.74 |

**Experiment 4: current offset / Coulomb counting error at the end of the window (pp)**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | -30.71 | -30.57 | -29.75 | -28.10 | -24.90 | -16.32 |
| HWFET | -9.91 | n/a | -10.56 | -9.94 | -8.97 | -6.66 |
| LA92 | -18.46 | -18.21 | -17.98 | -16.39 | -14.42 | -10.54 |
| US06 | -6.76 | -6.75 | -7.94 | -7.05 | -6.42 | -5.71 |
| Mix 1 | -13.99 | -13.83* | -14.42 | -13.45 | -12.55 | -9.07 |
| Mix 2 | -14.63 | -14.47 | -15.53 | -14.40 | -13.03 | -8.60 |
| Mix 3 | -13.49 | -13.23 | n/a | n/a | -11.13 | -9.01 |
| Mix 4 | n/a | -14.62 | -14.80 | -13.65 | n/a | -9.21 |
| Mix 5 | n/a | -12.76 | -13.45 | -12.95 | -12.00 | -9.17 |
| Mix 6 | n/a | -14.23 | -14.75 | -12.55 | -11.34 | -8.86 |
| Mix 7 | n/a | -13.26 | -13.99 | -12.31 | -11.13 | -8.14 |
| Mix 8 | n/a | -15.86 | -16.32 | -15.20 | -13.58 | -9.39 |
| **mean** | -15.42 | -15.39 | -15.41 | -14.18 | -12.68 | -9.22 |

**Experiment 4: current offset / Expected coulomb-counting drift over the window (pp)**

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | -30.52 | -30.50 | -29.75 | -28.06 | -24.69 | -16.36 |
| HWFET | -9.91 | n/a | -10.56 | -9.92 | -8.97 | -6.66 |
| LA92 | -18.32 | -18.12 | -17.94 | -16.32 | -14.42 | -10.50 |
| US06 | -6.75 | -6.70 | -7.74 | -6.75 | -6.38 | -5.51 |
| Mix 1 | -13.80 | -13.74* | -14.45 | -13.45 | -12.51 | -9.06 |
| Mix 2 | -14.55 | -14.50 | -15.53 | -14.44 | -13.04 | -8.60 |
| Mix 3 | -13.51 | -13.06 | n/a | n/a | -11.03 | -9.02 |
| Mix 4 | n/a | -14.60 | -14.77 | -13.59 | n/a | -9.20 |
| Mix 5 | n/a | -12.77 | -13.42 | -12.98 | -12.00 | -9.08 |
| Mix 6 | n/a | -14.21 | -14.69 | -12.48 | -11.18 | -8.83 |
| Mix 7 | n/a | -13.23 | -13.85 | -12.29 | -11.18 | -8.13 |
| Mix 8 | n/a | -15.71 | -16.27 | -15.15 | -13.45 | -9.34 |
| **mean** | -15.34 | -15.34 | -15.36 | -14.13 | -12.62 | -9.19 |

<!-- results:ekf_exp4:end -->

![Experiment 4, US06 at 25 degC](../results/plots/s2/trace_exp4_US06_25degC.png)
![Experiment 4, US06 at -20 degC](../results/plots/s2/trace_exp4_US06_n20degC.png)

SoC RMSE per experiment against temperature, one point per run, the tuning cycle marked:

![SoC RMSE per experiment and temperature](../results/plots/s2/summary_rmse.png)

### S3: C port equivalence

The C filter (`c/tools/ekf_run_csv`) runs experiment 1 on every evaluation run and the tuning cycle, in the float and the double build. delta SoC is the Python SoC minus the C SoC on every row, in pp.

<!-- results:equivalence:begin -->

**Result**

| build | threshold (pp) | max \|delta SoC\| (pp) | worst run | largest RMS (pp) | result |
|---|---|---|---|---|---|
| float | 0.1 | 1.85e-02 | HWFET at -20 degC (610) | 6.00e-03 | PASS |
| double | 0.001 | 5.00e-09 | HWFET at -20 degC (610) | 2.89e-09 | PASS |

**Per temperature**

| T (degC) | runs | float max (pp) | float largest RMS (pp) | double max (pp) | double largest RMS (pp) |
|---|---|---|---|---|---|
| 40 | 7 | 9.07e-04 | 2.35e-04 | 5.00e-09 | 2.88e-09 |
| 25 | 11 | 7.75e-04 | 2.56e-04 | 5.00e-09 | 2.80e-09 |
| 10 | 11 | 1.02e-03 | 3.62e-04 | 5.00e-09 | 2.89e-09 |
| 0 | 11 | 3.08e-03 | 6.90e-04 | 5.00e-09 | 2.89e-09 |
| -10 | 11 | 7.35e-03 | 6.63e-04 | 5.00e-09 | 2.89e-09 |
| -20 | 12 | 1.85e-02 | 6.00e-03 | 5.00e-09 | 2.89e-09 |

<!-- results:equivalence:end -->

![Python minus C SoC at -20 degC](../results/plots/s3/equivalence_n20degC.png)

The per-run table is in `results/equivalence.md`.

### S5: sensitivity

Experiment 1 again on the same 63 runs, with the frozen noise settings, changing one thing at a time (`docs/decisions.md` 1.18, 1.19). These S5 averages include the 62 evaluation runs and the tuning cycle; the S2 evaluation averages above exclude the tuning cycle. The tables are in `results/sensitivity.md`.

**Capacity error.** A stand-in for ageing (`docs/decisions.md` 1.18).

<!-- results:sensitivity_capacity:begin -->

**Capacity error: the filter capacity at -5 % and +5 %**

- The filter and the coulomb counter both believe 0.95 Q_ref and 1.05 Q_ref (Q_ref = 2.7807 Ah) and start from the reference SoC at the first row (experiment 1).
- Every cell is the mean SoC RMSE in pp over the evaluation window of the folder's runs; nominal is the experiment-1 value of `results/ekf_results.csv`; the reference SoC does not change.

| T (degC) | runs | EKF -5 % | EKF nominal | EKF +5 % | coulomb counting -5 % | coulomb counting nominal | coulomb counting +5 % |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 1.11 | 0.79 | 0.63 | 2.67 | 0.06 | 2.32 |
| 25 | 11 | 1.11 | 0.85 | 0.81 | 2.62 | 0.04 | 2.32 |
| 10 | 11 | 1.43 | 1.18 | 1.19 | 2.79 | 0.03 | 2.47 |
| 0 | 11 | 2.43 | 2.04 | 1.88 | 2.74 | 0.04 | 2.42 |
| -10 | 11 | 3.85 | 3.43 | 3.29 | 2.58 | 0.05 | 2.26 |
| -20 | 12 | 4.02 | 3.70 | 3.67 | 1.95 | 0.03 | 1.73 |
| all | 63 | 2.43 | 2.10 | 2.02 | 2.54 | 0.04 | 2.24 |

Largest per-run EKF RMSE: 9.35 pp (Mix 8 at -20 degC, -5 %); largest per-run coulomb-counting RMSE: 3.19 pp (US06 at 10 degC, -5 %).

Plot: `results/plots/s5/sensitivity_capacity.png`.

<!-- results:sensitivity_capacity:end -->

![Mean SoC RMSE per temperature with the filter capacity at -5 %, nominal and +5 %](../results/plots/s5/sensitivity_capacity.png)

On the folder means, the capacity error moves the EKF far less than it moves coulomb counting at every temperature. From 40 to 0 degC the EKF with the wrong capacity still has a lower mean RMSE than coulomb counting with it. At -10 and -20 degC coulomb counting with the wrong capacity has the lower mean: there the EKF's mean error at the nominal capacity is already larger than the mean drift of a 5 % capacity error. Single runs can go the other way at a given temperature; `results/sensitivity.csv` lists every run.

**Sample rate.** Every 10th row is kept (1 Hz), dt is recomputed between the kept rows and each kept current is held over the whole step.

<!-- results:sensitivity_rate:begin -->

**Sample rate: every 10th row (1 Hz)**

- The 1 Hz run keeps rows 0, 10, 20, ... of the loader's run and recomputes dt between them. The kept sample's current is held over the whole step (docs/model.md C11), the reference SoC is read at the kept rows and the evaluation window is C14 on them.
- RMSE cells are means over the folder's runs; max |error| cells are the largest over the folder's runs. The 0.1 s columns are experiment 1 of `results/ekf_results.csv`.

| T (degC) | runs | EKF RMSE 0.1 s | EKF RMSE 1 s | EKF max \|error\| 0.1 s | EKF max \|error\| 1 s | coulomb counting RMSE 0.1 s | coulomb counting RMSE 1 s |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 0.79 | 0.66 | 2.27 | 2.10 | 0.06 | 0.43 |
| 25 | 11 | 0.85 | 0.70 | 3.34 | 2.28 | 0.04 | 0.53 |
| 10 | 11 | 1.18 | 1.12 | 5.01 | 3.84 | 0.03 | 0.58 |
| 0 | 11 | 2.04 | 1.65 | 10.20 | 5.41 | 0.04 | 0.54 |
| -10 | 11 | 3.43 | 3.00 | 15.57 | 9.60 | 0.05 | 0.56 |
| -20 | 12 | 3.70 | 3.79 | 18.53 | 11.57 | 0.03 | 0.25 |
| all | 63 | 2.10 | 1.92 | 18.53 | 11.57 | 0.04 | 0.48 |

Plot: `results/plots/s5/sensitivity_rate.png`.

<!-- results:sensitivity_rate:end -->

![Mean SoC RMSE per temperature at 0.1 s and 1 s, EKF and coulomb counting](../results/plots/s5/sensitivity_rate.png)

At 1 Hz the EKF's mean RMSE is lower in every folder except -20 degC, and its largest |error| is lower in all six. Coulomb counting gets clearly worse, because holding one current sample for a whole second misses the changes in between. The EKF's mean RMSE over all runs does not rise with it, although single runs do get worse at 1 Hz (`results/sensitivity.csv`); this run does not separate the reasons.

### S5: Octave port

The Octave filter (`octave/ekf_run_csv.m`, double precision, plain GNU Octave) follows `python/ekfsoc/ekf.py` function for function and reads the same input files as the C tool (`docs/decisions.md` 1.20). It runs experiment 1 on the same 63 runs, and delta SoC is the Python SoC minus the Octave SoC on every row, in pp.

<!-- results:equivalence_octave:begin -->

**Result**

| build | threshold (pp) | max \|delta SoC\| (pp) | worst run | largest RMS (pp) | result |
|---|---|---|---|---|---|
| octave | 0.001 | 8.67e-12 | Mix 6 at -20 degC (611) | 1.79e-12 | PASS |

**Per temperature**

| T (degC) | runs | octave max (pp) | octave largest RMS (pp) |
|---|---|---|---|
| 40 | 7 | 1.78e-13 | 2.82e-14 |
| 25 | 11 | 1.55e-13 | 2.64e-14 |
| 10 | 11 | 1.08e-12 | 3.46e-13 |
| 0 | 11 | 7.55e-13 | 3.28e-13 |
| -10 | 11 | 2.19e-12 | 2.68e-13 |
| -20 | 12 | 8.67e-12 | 1.79e-12 |

<!-- results:equivalence_octave:end -->

![Python minus Octave SoC on US06 at 25 degC](../results/plots/s5/equivalence_octave_25degC.png)

The per-run table is in `results/equivalence_octave.md`.

### S6: a third RC branch (negative result)

S6 asked whether a third, middle RC branch between the fast and the slow one improves the model. The rules were fixed in `docs/decisions.md` before any 3RC number existed: the middle branch is fitted with the fast one on the same HPPC discharge pulses, each branch has its own time-constant bounds, the S1 sanity gate applies, and the 3RC model would be adopted only if it lowered the experiment-1 SoC error broadly (1.21, 1.22). The code handles two or three branches, and every 2RC result above regenerates byte for byte.

<!-- results:model_fit_3rc:begin -->

**Open-loop voltage error on US06, 2RC and 3RC**

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

**Ceiling: a third branch added to the 2RC model**

A constant third branch, R3 in {2, 5, 10, 20} mOhm and tau3 in {10, 20, 30, 50} s, is added to the unchanged 2RC tables, and the lowest open-loop US06 RMSE is kept (docs/decisions.md 1.24). It is chosen on the validation file itself, so it bounds from above what a middle branch adds while R1, tau1, R2 and tau2 stay as fitted; it is not a fit.

| T (degC) | 2RC RMSE (mV) | best with a third branch (mV) | change (mV) | R3 (mOhm) | tau3 (s) |
|---|---|---|---|---|---|
| 40 | 20.90 | 19.07 | -1.83 | 2 | 20 |
| 25 | 29.79 | 29.04 | -0.75 | 2 | 20 |
| 10 | 40.68 | 39.77 | -0.91 | 2 | 20 |
| 0 | 59.47 | 57.70 | -1.77 | 5 | 20 |
| -10 | 73.74 | 71.27 | -2.48 | 5 | 30 |
| -20 | 104.58 | 102.56 | -2.01 | 10 | 30 |

**Ceiling over every drive cycle**

The ceiling above, repeated on every run of the evaluation set and the tuning cycle and pooled per temperature (docs/decisions.md 1.25). R3 in {2, 5, 10, 20, 35, 50, 70, 100} mOhm and tau3 in {10, 20, 30, 50, 100} s. The pooled RMSE is over all rows of a temperature's runs together, error = model minus measured voltage over the whole run, as for US06 above. Like the ceiling above it is chosen on the data it is scored on; it is not a fit. A run is helped when its own best branch lowers its RMSE by more than 10 %.

| T (degC) | runs | 2RC pooled RMSE (mV) | best with a third branch (mV) | change (%) | R3 (mOhm) | tau3 (s) | runs helped |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 13.95 | 11.37 | -18.5 | 5 | 20 | 6 |
| 25 | 11 | 17.40 | 14.75 | -15.3 | 5 | 20 | 9 |
| 10 | 11 | 24.81 | 22.05 | -11.1 | 5 | 20 | 6 |
| 0 | 11 | 38.30 | 33.60 | -12.3 | 10 | 20 | 8 |
| -10 | 11 | 63.38 | 46.84 | -26.1 | 20 | 30 | 10 |
| -20 | 12 | 87.61 | 70.33 | -19.7 | 35 | 30 | 10 |

<!-- results:model_fit_3rc:end -->

The 3RC model fails the sanity gate and is worse than the 2RC model open loop on US06 at most temperatures, so it is not adopted; the EKF experiments and the C port were not run on it (`docs/decisions.md` 1.24). On the HPPC pulses it was fitted to, the middle branch does fit better. On US06 it hurts, for two measured reasons:

- The middle branch takes part of the slow branch's change inside each pulse window, so its resistance comes out too high; a synthetic check with a known slow branch shows the same bias (`docs/decisions.md` 1.24).
- US06 asks for little middle-branch resistance. The first ceiling table adds the best constant third branch from a small grid to the unchanged 2RC model, chosen on the US06 file itself: the gain is small at every temperature, and the best resistance is far below what the HPPC fit gives.

The second reason holds for US06 only. US06 has the lowest mean open-loop error of all drive cycles at every temperature, while nearly every other run has a positive one: the model drops too little voltage under sustained discharge, which is what a middle branch adds. The second ceiling table repeats the check on every drive run, pooled per temperature. There a constant third branch lowers the open-loop error at every temperature, most at -10 and -20 degC, and the resistance it asks for is of the same order as the HPPC fit's (`docs/decisions.md` 1.25; `results/model_fit_3rc.md` also lists the level fits and every run). So the drive cycles do ask for a middle branch; what failed first is fitting it from 50 s pulse windows.

A second fit, recorded before it ran, kept every 2RC table and fitted only the middle branch, on the rests of the whole HPPC pulse train, which resolve its time constant (`docs/decisions.md` 1.26). It follows the pulse train closely, but it fails the gate as well. The branch it finds is larger and slower than the drive cycles ask for, so it lowers the pooled error at -10 and -20 degC and raises the US06 error at every temperature (`docs/decisions.md` 1.27; `results/model_fit_3rc_rest.md` also lists the level fits). An independent reimplementation reproduced these numbers. Under the rule fixed in advance this ends the middle branch in S6, and the 2RC model stays.

<!-- results:model_fit_3rc_rest:begin -->

**Open-loop voltage error on US06, 2RC and second 3RC fit**

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

**Open-loop error over every drive cycle**

Pooled over all rows of a temperature's runs, scored as in docs/decisions.md 1.25; the ceiling is the one of `results/model_fit_3rc.md`.

| T (degC) | runs | 2RC pooled RMSE (mV) | ceiling of 1.25 (mV) | second 3RC pooled RMSE (mV) | second 3RC change (%) |
|---|---|---|---|---|---|
| 40 | 7 | 13.95 | 11.37 | 13.31 | -4.6 |
| 25 | 11 | 17.40 | 14.75 | 17.76 | +2.1 |
| 10 | 11 | 24.81 | 22.05 | 26.84 | +8.2 |
| 0 | 11 | 38.30 | 33.60 | 37.80 | -1.3 |
| -10 | 11 | 63.38 | 46.84 | 48.12 | -24.1 |
| -20 | 12 | 87.61 | 70.33 | 77.13 | -12.0 |

<!-- results:model_fit_3rc_rest:end -->

![3RC parameters against SoC](../results/plots/s6/params_3rc.png)

![Middle branch of the second 3RC fit against SoC](../results/plots/s6/params_3rc_rest.png)

### S7: R1 that depends on current (adopted)

S7 asked whether the cold error comes from a resistance that falls as the current grows. In the 2RC-I model, R1 is read over temperature, SoC and the size of the current instead of temperature and SoC; every other table and the frozen filter settings stay as in v1.0. The rules were fixed in `docs/decisions.md` before any result existed: R1 is fitted once per HPPC discharge pulse in the windows of the S1 fit, the S1 gate applies, and the model is adopted only under the rule S6 used (1.28, 1.29). R1 falls with the pulse current at every temperature, little at 40 degC and by more than half at -20 degC:

<!-- results:model_fit_r1i:begin -->

**R1 per pulse**

Per usable HPPC discharge pulse, R1 in the window of fit (a) (the pulse and its 40 s rest, one free constant) with R0 and tau1 held at the level's fit (a) values (docs/decisions.md 1.28). Medians over the levels; v1.0 R1 is the level fit of S1. D1 is the smallest current and also the only pulse that follows the move and its 1 h rest, so a current effect and a history effect on D1 cannot be told apart. Left out: pulses with R1 at or below 0. Every pulse fit is in `results/fit_pulses_r1i.csv`.

| T (degC) | v1.0 R1 (mOhm) | D1 I (A) | D1 R1 (mOhm) | D2 I (A) | D2 R1 (mOhm) | D3 I (A) | D3 R1 (mOhm) | D4 I (A) | D4 R1 (mOhm) | pulses used | left out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 | 6.08 | 3.00 | 6.44 | 6.00 | 6.26 | 12.00 | 6.08 | 18.00 | 5.78 | 41 | 0 |
| 25 | 6.78 | 3.00 | 8.45 | 6.00 | 7.93 | 12.00 | 6.98 | 18.00 | 6.33 | 42 | 0 |
| 10 | 8.85 | 2.90 | 11.78 | 5.80 | 10.45 | 11.60 | 8.90 | 17.40 | 8.29 | 40 | 0 |
| 0 | 11.56 | 3.00 | 15.75 | 6.00 | 14.49 | 12.00 | 11.88 | 18.00 | 10.23 | 35 | 0 |
| -10 | 21.52 | 1.50 | 33.48 | 3.00 | 30.09 | 6.00 | 23.96 | 12.00 | 14.92 | 36 | 0 |
| -20 | 60.81 | 0.75 | 98.77 | 1.50 | 86.62 | 3.00 | 66.50 | 6.00 | 41.38 | 34 | 0 |

<!-- results:model_fit_r1i:end -->

![R1 against the pulse current](../results/plots/s7/r1_current.png)

The 2RC-I model passes the gate and the adoption rule, so it is adopted (`docs/decisions.md` 1.31):

<!-- results:model_compare_r1i:begin -->

**Open loop**

The US06 RMSE and the RMSE pooled over every drive run, model minus measured voltage (docs/decisions.md 1.25).

| T (degC) | US06 2RC (mV) | US06 2RC-I (mV) | pooled 2RC (mV) | pooled 2RC-I (mV) |
|---|---|---|---|---|
| 40 | 20.90 | 20.56 | 13.95 | 13.88 |
| 25 | 29.79 | 29.75 | 17.40 | 17.48 |
| 10 | 40.68 | 40.87 | 24.81 | 24.09 |
| 0 | 59.47 | 60.31 | 38.30 | 36.31 |
| -10 | 73.74 | 77.75 | 63.38 | 57.51 |
| -20 | 104.58 | 104.85 | 87.61 | 79.29 |

**Experiment 1**

SoC RMSE with the correct initial SoC. The mean decides the verdict (docs/decisions.md 1.29); the median and the number of runs whose RMSE is lower with 2RC-I show how the change spreads over the runs.

| T (degC) | evaluation runs | mean 2RC (pp) | mean 2RC-I (pp) | mean change (pp) | median 2RC (pp) | median 2RC-I (pp) | runs lower with 2RC-I |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 0.79 | 0.74 | -0.04 | 0.73 | 0.72 | 6 of 7 |
| 25 | 10 | 0.87 | 0.86 | -0.01 | 0.87 | 0.87 | 7 of 10 |
| 10 | 11 | 1.18 | 1.21 | +0.03 | 1.14 | 1.11 | 9 of 11 |
| 0 | 11 | 2.04 | 1.74 | -0.29 | 1.87 | 1.66 | 10 of 11 |
| -10 | 11 | 3.43 | 3.21 | -0.22 | 2.83 | 3.00 | 9 of 11 |
| -20 | 12 | 3.70 | 3.24 | -0.46 | 3.00 | 2.99 | 8 of 12 |

**Experiments 2 to 4**

Experiment 4: mean SoC RMSE with the current offset. Reached: evaluation runs whose error stays within +-2 pp from some time on, 2RC / 2RC-I.

| T (degC) | exp4 2RC (pp) | exp4 2RC-I (pp) | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|
| 40 | 1.17 | 1.14 | 6 / 6 | 6 / 6 | 6 / 6 |
| 25 | 1.21 | 1.19 | 9 / 9 | 9 / 9 | 9 / 9 |
| 10 | 1.33 | 1.24 | 11 / 11 | 11 / 11 | 11 / 11 |
| 0 | 2.22 | 1.69 | 11 / 11 | 11 / 11 | 11 / 11 |
| -10 | 3.57 | 3.30 | 4 / 4 | 3 / 3 | 3 / 3 |
| -20 | 3.85 | 3.95 | 6 / 5 | 4 / 4 | 5 / 4 |

**Adoption verdict**

Rule (docs/decisions.md 1.29): the experiment-1 mean SoC RMSE is lower than the 2RC value at 4 or more of the six temperatures and higher at none by more than 0.10 pp.

Lower at 5 of 6 temperatures; higher by more than 0.10 pp at: none. **ADOPTED.**

<!-- results:model_compare_r1i:end -->

![2RC and 2RC-I against temperature](../results/plots/s7/model_compare_r1i.png)

The gain is a cold one. At 0 to -20 degC the experiment-1 mean falls by 0.2 to 0.5 pp; at the warmer temperatures it moves by a few hundredths. Most runs end lower at every temperature, but in the cold part of the mean gain comes from a few runs that improve a lot, Mix 8 and Mix 4 among them, which open under load; the cold medians barely move. US06, the cycle with the highest currents, gets worse from 10 degC down, with its error roughly doubled (`docs/decisions.md` 1.31, `results/ekf_results_r1i.csv`), so the 2RC-I model is better on average, not for every load. An independent reimplementation reproduced the fit, the table and the filter runs. The C library is not ported yet: the R1 table over current adds about 12 kB, and the port gets its own decision first (1.30).

### S8: R1 by the sign of the current and at low current (three negative results)

S8 asked why the 2RC-I model makes US06 worse from 10 degC down. Under regen the model reads R1 from the discharge table at the size of the current, and at low current that value is well above the v1.0 R1 (about 1.3 times at 25 degC and 2 times at -10 degC at 1.5 A, `results/model_compare_r1d.md`). The rules were fixed in `docs/decisions.md` 1.32 before any S8 result existed: a new model must pass the S1 gate, the rule of S6 and S7, and four guards against 2RC-I. No single run or cycle may get worse beyond a fixed limit, the worst run may not rise, and the experiment-4 mean and the experiment 2 and 3 reached counts may not get worse beyond theirs. These 62 runs have been inspected in every stage since S2, so S8 is a comparison on a repeatedly inspected set, not a confirmation.

- **Step A, 2RC-Id** (1.33, 1.34): the v1.0 R1 under regen, nothing refitted. US06 comes back to about the 2RC values at 0 to -20 degC (about half way at 10 degC), but Mix 8 at 0 to -20 degC and Mix 6 at -20 degC get worse beyond the limit, the worst run rises, and fewer -20 degC runs reach the 2 pp band. Not adopted.
- **Step B, 2RC-Ic** (1.35, 1.36): a charge-side R1 fitted on the HPPC charge pulses. US06 recovers only at -20 degC, while LA92 and Mix 8 in the cold, the worst run and the -20 degC reached counts get worse. Its open-loop voltage error under regen is closer to zero than 2RC-Id's at 10 and 0 degC, yet its US06 SoC error stays near 2RC-I there, so the regen voltage error does not predict the US06 SoC error. Not adopted. In the US06 table below, the change column is 2RC-Ic minus 2RC-I.
- **Step C, 2RC-Il** (1.37, 1.38): R1 at and below the smallest discharge pulse current scaled by one factor per temperature, fitted on the PausCycl files, which are not in the evaluation set. The fitted R1 there is 3 to 20 % lower than 2RC-I's, and it fits those files better in the cold, but not the drive cycles' open-loop voltage. US06 improves at 10 to -10 degC but gets worse at -20 degC, and Mix 8, LA92 and the worst run get worse; the experiment-1 mean is lower at only one temperature. Not adopted. The second US06 table below has 2RC, 2RC-I and 2RC-Il, its change column 2RC-Il minus 2RC-I.

<!-- results:s8_us06:begin -->

**Experiment 1 / US06**

Experiment-1 SoC RMSE of the US06 run.

| T (degC) | 2RC (pp) | 2RC-I (pp) | 2RC-Id (pp) | 2RC-Ic (pp) | change (pp) |
|---|---|---|---|---|---|
| 40 | 1.04 | 0.98 | 0.95 | 0.94 | -0.03 |
| 25 | 1.05 | 1.02 | 1.02 | 1.03 | +0.01 |
| 10 | 1.18 | 2.28 | 1.79 | 2.30 | +0.02 |
| 0 | 1.13 | 2.99 | 1.09 | 3.14 | +0.14 |
| -10 | 3.23 | 6.25 | 3.25 | 5.84 | -0.41 |
| -20 | 2.75 | 5.36 | 2.42 | 2.39 | -2.97 |

<!-- results:s8_us06:end -->

![The four models against temperature](../results/plots/s8/model_compare_r1c.png)

<!-- results:s8_step_a:begin -->

**Guards and adoption verdict**

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

<!-- results:s8_step_a:end -->

<!-- results:s8_step_b:begin -->

**Guards and adoption verdict**

The guards of docs/decisions.md 1.32, 2RC-Ic against the incumbent 2RC-I, which is also the model S8 starts from, so the stage-budget check is the same comparison. Values are those of the results CSVs (4 decimals); a guard whose value lies within 0.0001 of its limit is recomputed from unrounded values, which decide (1.35).

| guard | value | result |
|---|---|---|
| 1. S1 gate | US06 at 25 degC: 29.9166 mV (limit 30) | pass |
| 2. rule of 1.22 | lower at 6 of 6; higher by more than 0.10 pp at none | pass |
| 3. run increase | largest +0.6196 pp; above the limit of +0.50: LA92 at -20 degC +0.6196, Mix 8 at -10 degC +0.6085, Mix 8 at -20 degC +0.5316 | FAIL |
| 4. largest cycle increase | +0.2479 pp (Mix 8, limit +0.25) | pass |
| 5. worst run | 6.6112 pp against 6.3441 pp | FAIL |
| 6. experiments 2 to 4 | largest exp4 increase -0.0209 pp (limit +0.10); fewer reached: exp2 at -20 degC, exp3_low at -20 degC | FAIL |

Guards recomputed from unrounded values: none.

**NOT ADOPTED.**

<!-- results:s8_step_b:end -->

<!-- results:s8_step_c:begin -->

**Experiment 1 / US06**

Experiment-1 SoC RMSE of the US06 run.

| T (degC) | 2RC (pp) | 2RC-I (pp) | 2RC-Il (pp) | change (pp) |
|---|---|---|---|---|
| 40 | 1.04 | 0.98 | 0.98 | +0.00 |
| 25 | 1.05 | 1.02 | 1.02 | -0.00 |
| 10 | 1.18 | 2.28 | 2.12 | -0.16 |
| 0 | 1.13 | 2.99 | 2.94 | -0.06 |
| -10 | 3.23 | 6.25 | 5.34 | -0.91 |
| -20 | 2.75 | 5.36 | 6.34 | +0.99 |

**Guards and adoption verdict**

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

<!-- results:s8_step_c:end -->

![2RC, 2RC-I and 2RC-Il against temperature](../results/plots/s8/model_compare_r1l.png)

2RC-I stays the adopted model. None of the three R1 changes recovers US06 in the cold without costing Mix 8 and the -20 degC runs beyond the guards. S8 is closed after these three steps (`decisions.md` 1.39); step D, noise settings that depend on conditions, was not run and is left as future work. The fits, the per-cycle tables and the open-loop error by current band are in `results/model_fit_r1c.md`, `results/model_fit_r1l.md`, `results/model_compare_r1c.md` and `results/model_compare_r1l.md`.

### S9: slow-branch resistances fitted on drive data

3RC-D adds a 45 s branch and scales the existing slow branch's resistance. Both tables are fitted jointly to the open-loop voltage of 40 Mix runs, including the tuning cycle. The 23 standard-cycle runs were held out of the final parameter fit. Prior diagnostics and the low-SoC boundary choice used those runs, and they share segments with the Mix runs.

3RC-D passed the 25 degC US06 voltage gate. Mean experiment-1 SoC error fell at all six temperatures on the standard runs. The worst-run guard rejected 3RC-D because US06 at -10 degC rose from 6.25 to 6.40 pp. See [decision 1.43](decisions.md#143-s9-outcome-the-worst-run-guard-rejects-3rc-d).

<!-- results:s9_results:begin -->

**US06 gate**

**PASS.** 3RC-D scores 23.1312 mV over all rows at 25 degC (limit 30 mV).

The window and tail columns separate the in-window and subsequent rows. All columns are in mV.

| T (degC) | 2RC-I all | 3RC-D all | 2RC-I window | 3RC-D window | 2RC-I tail | 3RC-D tail |
|---|---|---|---|---|---|---|
| 40 | 20.56 | 17.29 | 17.85 | 12.40 | 31.55 | 33.10 |
| 25 | 29.75 | 23.13 | 22.14 | 15.96 | 53.81 | 44.29 |
| 10 | 40.87 | 21.32 | 40.87 | 21.32 | n/a | n/a |
| 0 | 60.31 | 35.04 | 60.31 | 35.04 | n/a | n/a |
| -10 | 77.75 | 63.59 | 77.75 | 63.59 | n/a | n/a |
| -20 | 104.85 | 76.74 | 104.85 | 76.74 | n/a | n/a |

**Standard cycles**

Open-loop RMSE is pooled over window rows in mV. SoC RMSE is in pp. The lower count compares 3RC-D with 2RC-I.

| T (degC) | runs | 2RC voltage | 2RC-I voltage | 3RC-D voltage | 2RC exp1 mean | 2RC-I exp1 mean | 3RC-D exp1 mean | 2RC exp1 median | 2RC-I exp1 median | 3RC-D exp1 median | runs lower |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 | 4 | 13.48 | 13.41 | 9.69 | 0.84 | 0.79 | 0.42 | 0.80 | 0.77 | 0.40 | 4 |
| 25 | 3 | 13.75 | 13.68 | 10.27 | 0.87 | 0.86 | 0.58 | 0.88 | 0.87 | 0.70 | 3 |
| 10 | 4 | 23.04 | 22.28 | 15.53 | 1.20 | 1.44 | 1.09 | 1.11 | 1.26 | 1.13 | 4 |
| 0 | 4 | 35.48 | 33.61 | 19.92 | 1.66 | 1.90 | 1.69 | 1.42 | 1.69 | 1.32 | 3 |
| -10 | 4 | 55.38 | 49.62 | 32.07 | 3.04 | 3.64 | 2.69 | 3.03 | 3.06 | 1.62 | 3 |
| -20 | 4 | 83.20 | 76.31 | 47.11 | 2.88 | 3.07 | 2.88 | 2.92 | 2.56 | 2.08 | 3 |

Reached counts are in the order 2RC / 2RC-I / 3RC-D.

| T (degC) | 2RC exp4 mean | 2RC-I exp4 mean | 3RC-D exp4 mean | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|---|
| 40 | 1.19 | 1.15 | 0.76 | 3 / 3 / 4 | 3 / 3 / 4 | 3 / 3 / 4 |
| 25 | 1.25 | 1.25 | 0.81 | 3 / 3 / 3 | 3 / 3 / 3 | 3 / 3 / 3 |
| 10 | 1.33 | 1.46 | 1.34 | 4 / 4 / 4 | 4 / 4 / 4 | 4 / 4 / 4 |
| 0 | 1.91 | 1.83 | 1.81 | 4 / 4 / 4 | 4 / 4 / 4 | 4 / 4 / 4 |
| -10 | 3.11 | 3.40 | 2.44 | 3 / 3 / 3 | 2 / 2 / 3 | 2 / 2 / 3 |
| -20 | 3.44 | 3.32 | 2.74 | 2 / 2 / 4 | 0 / 1 / 3 | 2 / 1 / 4 |

**Experiment 1 by standard cycle**

| Cycle | 2RC (pp) | 2RC-I (pp) | 3RC-D (pp) |
|---|---|---|---|
| HWFET | 2.2604 | 1.7695 | 1.0105 |
| LA92 | 1.5225 | 1.4045 | 1.0898 |
| UDDS | 1.7213 | 1.6296 | 1.2762 |
| US06 | 1.7290 | 3.1468 | 2.9328 |

**Experiment 1 by run**

| Folder | Cycle | 2RC (pp) | 2RC-I (pp) | 3RC-D (pp) |
|---|---|---|---|---|
| 40degC | UDDS | 0.8086 | 0.8116 | 0.6077 |
| 40degC | HWFET | 0.7961 | 0.6532 | 0.2868 |
| 40degC | LA92 | 0.7285 | 0.7276 | 0.3831 |
| 40degC | US06 | 1.0405 | 0.9777 | 0.4169 |
| 25degC | UDDS | 0.8801 | 0.8656 | 0.6978 |
| 25degC | LA92 | 0.6802 | 0.6939 | 0.3157 |
| 25degC | US06 | 1.0462 | 1.0183 | 0.7399 |
| 10degC | UDDS | 1.0422 | 0.9488 | 0.8405 |
| 10degC | HWFET | 0.9618 | 0.9371 | 0.6377 |
| 10degC | LA92 | 1.6314 | 1.5809 | 1.4621 |
| 10degC | US06 | 1.1828 | 2.2807 | 1.4134 |
| 0degC | UDDS | 1.4977 | 1.3104 | 1.1899 |
| 0degC | HWFET | 2.6663 | 2.0790 | 1.3523 |
| 0degC | LA92 | 1.3513 | 1.2369 | 1.2945 |
| 0degC | US06 | 1.1304 | 2.9916 | 2.9079 |
| n10degC | UDDS | 2.8252 | 2.7224 | 1.9179 |
| n10degC | HWFET | 3.7917 | 3.3888 | 1.1354 |
| n10degC | LA92 | 2.3299 | 2.1916 | 1.3239 |
| n10degC | US06 | 3.2252 | 6.2547 | 6.3977 |
| n20degC | UDDS | 3.2740 | 3.1185 | 2.4031 |
| n20degC | HWFET | 3.0863 | 1.7893 | 1.6404 |
| n20degC | LA92 | 2.4139 | 1.9963 | 1.7594 |
| n20degC | US06 | 2.7491 | 5.3576 | 5.7209 |

**Guards and adoption verdict**

The guards of decisions 1.40 use the results CSVs, with comparisons near a limit recomputed from the unrounded traces under decisions 1.35. The S1 gate always uses the full-precision open-loop RMSE.

| guard | value | result |
|---|---|---|
| 1. S1 gate | US06 at 25 degC: 23.1312 mV (limit 30) | pass |
| 2. rule of 1.22 | lower at 6 of 6; higher by more than 0.10 pp at none | pass |
| 3. run increase | largest +0.3633 pp; above the limit of +0.50: none | pass |
| 4. largest cycle increase | -0.2140 pp (US06, limit +0.25) | pass |
| 5. worst run | 6.3977 pp against 6.2547 pp | FAIL |
| 6. experiments 2 to 4 | largest exp4 increase -0.0231 pp (limit +0.10); fewer reached: none | pass |

Guard inputs from unrounded traces. SoC changes are in pp and temperatures follow the table order above.

| guard | unrounded values |
|---|---|
| 1 | 23.1311726867 mV |
| 2 | -0.368887963988 / -0.274791007635 / -0.348463181403 / -0.218290291317 / -0.945664213542 / -0.184481834437 |
| 3 | Largest run increase +0.363345204516 |
| 4 | HWFET -0.75897260076, LA92 -0.314749266258, UDDS -0.353382739644, US06 -0.213977987074 |
| 5 | Worst run 6.25470078654 to 6.39769391382 |
| 6 | Experiment 4 changes -0.39122867284 / -0.440535446313 / -0.125721508815 / -0.0231267648174 / -0.957504088039 / -0.579297591924 |

**NOT ADOPTED.**

<!-- results:s9_results:end -->

![Open-loop voltage and SoC RMSE on the standard and Mix runs](../results/plots/s9/model_compare_3rcd.png)

The [fit report](../results/model_fit_3rcd.md) gives the fitted nodes, solver checks and leave-one-Mix-run-out voltage errors. The [comparison report](../results/model_compare_3rcd.md) includes the in-sample Mix results. See also the [fitted node plot](../results/plots/s9/params_3rcd.png).

### S10 · Drive-fitted third branch with v1.0 R1

S10 tests the interaction between current-dependent R1 and the drive-fitted slow
branches under decision 1.44. The 40 Mix runs calibrate the new coefficients.
The 23 standard runs are a previously inspected regression suite and share
segments with the Mix runs. The adoption comparator is 2RC-I.

<!-- results:s10_results:begin -->

**US06 voltage gate**

**PASS.** 3RC-D0 full-run RMSE at 25 degC is 23.2362515344 mV (limit 30 mV).

US06 voltage RMSE in mV. Scores use the reloaded tables.

| T (degC) | Scope | 2RC | 2RC-I | 3RC-D | 3RC-D0 | S9 R1 substitution |
|---|---|---|---|---|---|---|
| 40 | Full | 20.8982 | 20.5608 | 17.2904 | 17.9720 | 17.6607 |
| 40 | Window | 18.3128 | 17.8452 | 12.4010 | 12.4723 | 12.9899 |
| 40 | Tail | 31.5136 | 31.5453 | 33.1011 | 35.2404 | 33.1298 |
| 25 | Full | 29.7883 | 29.7533 | 23.1312 | 23.2363 | 23.2488 |
| 25 | Window | 22.1998 | 22.1409 | 15.9554 | 15.7318 | 16.1292 |
| 25 | Tail | 53.8003 | 53.8058 | 44.2946 | 45.0301 | 44.3490 |
| 10 | Full | 40.6783 | 40.8732 | 21.3203 | 20.8989 | 19.9090 |
| 10 | Window | 40.6783 | 40.8732 | 21.3203 | 20.8989 | 19.9090 |
| 10 | Tail | n/a | n/a | n/a | n/a | n/a |
| 0 | Full | 59.4654 | 60.3110 | 35.0350 | 34.5890 | 31.6125 |
| 0 | Window | 59.4654 | 60.3110 | 35.0350 | 34.5890 | 31.6125 |
| 0 | Tail | n/a | n/a | n/a | n/a | n/a |
| -10 | Full | 73.7450 | 77.7488 | 63.5928 | 65.4448 | 55.5902 |
| -10 | Window | 73.7450 | 77.7488 | 63.5928 | 65.4448 | 55.5902 |
| -10 | Tail | n/a | n/a | n/a | n/a | n/a |
| -20 | Full | 104.5780 | 104.8528 | 76.7435 | 85.8563 | 68.2001 |
| -20 | Window | 104.5780 | 104.8528 | 76.7435 | 85.8563 | 68.2001 |
| -20 | Tail | n/a | n/a | n/a | n/a | n/a |

**Standard regression runs**

Experiment-1 SoC RMSE in pp. The S9 R1 substitution is an experiment-1 diagnostic.

| T (degC) | runs | 2RC mean | 2RC-I mean | 3RC-D mean | 3RC-D0 mean | S9 R1 substitution mean | 2RC median | 2RC-I median | 3RC-D median | 3RC-D0 median | S9 R1 substitution median |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 40 | 4 | 0.843 | 0.793 | 0.424 | 0.465 | 0.484 | 0.802 | 0.770 | 0.400 | 0.452 | 0.455 |
| 25 | 3 | 0.869 | 0.859 | 0.584 | 0.608 | 0.598 | 0.880 | 0.866 | 0.698 | 0.707 | 0.675 |
| 10 | 4 | 1.205 | 1.437 | 1.088 | 0.861 | 0.880 | 1.113 | 1.265 | 1.127 | 0.788 | 0.835 |
| 0 | 4 | 1.661 | 1.904 | 1.686 | 1.229 | 1.305 | 1.425 | 1.695 | 1.323 | 1.188 | 1.283 |
| -10 | 4 | 3.043 | 3.639 | 2.694 | 1.418 | 1.572 | 3.025 | 3.056 | 1.621 | 1.334 | 1.619 |
| -20 | 4 | 2.881 | 3.065 | 2.881 | 1.216 | 1.674 | 2.918 | 2.557 | 2.081 | 1.140 | 1.687 |

Experiment-4 mean SoC RMSE in pp. Reached counts follow 2RC / 2RC-I / 3RC-D / 3RC-D0.

| T (degC) | 2RC exp4 | 2RC-I exp4 | 3RC-D exp4 | 3RC-D0 exp4 | exp2 reached | exp3 low reached | exp3 high reached |
|---|---|---|---|---|---|---|---|
| 40 | 1.190 | 1.152 | 0.761 | 0.795 | 3 / 3 / 4 / 4 | 3 / 3 / 4 / 4 | 3 / 3 / 4 / 4 |
| 25 | 1.252 | 1.250 | 0.809 | 0.844 | 3 / 3 / 3 / 3 | 3 / 3 / 3 / 3 | 3 / 3 / 3 / 3 |
| 10 | 1.334 | 1.464 | 1.339 | 1.074 | 4 / 4 / 4 / 4 | 4 / 4 / 4 / 4 | 4 / 4 / 4 / 4 |
| 0 | 1.913 | 1.831 | 1.808 | 1.719 | 4 / 4 / 4 / 4 | 4 / 4 / 4 / 4 | 4 / 4 / 4 / 4 |
| -10 | 3.105 | 3.400 | 2.442 | 2.032 | 3 / 3 / 3 / 3 | 2 / 2 / 3 / 3 | 2 / 2 / 3 / 3 |
| -20 | 3.436 | 3.321 | 2.742 | 1.958 | 2 / 2 / 4 / 4 | 0 / 1 / 3 / 3 | 2 / 1 / 4 / 3 |

**Experiment 1 by standard cycle**

| Cycle | 2RC (pp) | 2RC-I (pp) | 3RC-D (pp) | 3RC-D0 (pp) | S9 R1 substitution (pp) |
|---|---|---|---|---|---|
| HWFET | 2.2604 | 1.7695 | 1.0105 | 0.7570 | 1.2856 |
| LA92 | 1.5225 | 1.4045 | 1.0898 | 0.7533 | 0.8932 |
| UDDS | 1.7213 | 1.6296 | 1.2762 | 1.1498 | 1.2855 |
| US06 | 1.7290 | 3.1468 | 2.9328 | 1.2292 | 0.9930 |

**US06 experiment 1**

| Folder | Cycle | 2RC (pp) | 2RC-I (pp) | 3RC-D (pp) | 3RC-D0 (pp) | S9 R1 substitution (pp) |
|---|---|---|---|---|---|---|
| 40degC | US06 | 1.0405 | 0.9777 | 0.4169 | 0.5082 | 0.4684 |
| 25degC | US06 | 1.0462 | 1.0183 | 0.7399 | 0.7871 | 0.6753 |
| 10degC | US06 | 1.1828 | 2.2807 | 1.4134 | 0.7265 | 0.4874 |
| 0degC | US06 | 1.1304 | 2.9916 | 2.9079 | 1.5259 | 1.1634 |
| n10degC | US06 | 3.2252 | 6.2547 | 6.3977 | 2.3883 | 2.0288 |
| n20degC | US06 | 2.7491 | 5.3576 | 5.7209 | 1.4393 | 1.1349 |

**Experiment 1 by run**

| Folder | Cycle | 2RC (pp) | 2RC-I (pp) | 3RC-D (pp) | 3RC-D0 (pp) | S9 R1 substitution (pp) |
|---|---|---|---|---|---|---|
| 40degC | UDDS | 0.8086 | 0.8116 | 0.6077 | 0.6093 | 0.6083 |
| 40degC | HWFET | 0.7961 | 0.6532 | 0.2868 | 0.3467 | 0.4407 |
| 40degC | LA92 | 0.7285 | 0.7276 | 0.3831 | 0.3958 | 0.4190 |
| 40degC | US06 | 1.0405 | 0.9777 | 0.4169 | 0.5082 | 0.4684 |
| 25degC | UDDS | 0.8801 | 0.8656 | 0.6978 | 0.7070 | 0.7341 |
| 25degC | LA92 | 0.6802 | 0.6939 | 0.3157 | 0.3294 | 0.3857 |
| 25degC | US06 | 1.0462 | 1.0183 | 0.7399 | 0.7871 | 0.6753 |
| 10degC | UDDS | 1.0422 | 0.9488 | 0.8405 | 0.8486 | 0.9209 |
| 10degC | HWFET | 0.9618 | 0.9371 | 0.6377 | 0.5446 | 0.7487 |
| 10degC | LA92 | 1.6314 | 1.5809 | 1.4621 | 1.3235 | 1.3636 |
| 10degC | US06 | 1.1828 | 2.2807 | 1.4134 | 0.7265 | 0.4874 |
| 0degC | UDDS | 1.4977 | 1.3104 | 1.1899 | 1.2453 | 1.3804 |
| 0degC | HWFET | 2.6663 | 2.0790 | 1.3523 | 1.1307 | 1.4927 |
| 0degC | LA92 | 1.3513 | 1.2369 | 1.2945 | 1.0143 | 1.1854 |
| 0degC | US06 | 1.1304 | 2.9916 | 2.9079 | 1.5259 | 1.1634 |
| n10degC | UDDS | 2.8252 | 2.7224 | 1.9179 | 1.6355 | 1.8305 |
| n10degC | HWFET | 3.7917 | 3.3888 | 1.1354 | 1.0324 | 1.4082 |
| n10degC | LA92 | 2.3299 | 2.1916 | 1.3239 | 0.6156 | 1.0199 |
| n10degC | US06 | 3.2252 | 6.2547 | 6.3977 | 2.3883 | 2.0288 |
| n20degC | UDDS | 3.2740 | 3.1185 | 2.4031 | 1.8533 | 2.2389 |
| n20degC | HWFET | 3.0863 | 1.7893 | 1.6404 | 0.7307 | 2.3380 |
| n20degC | LA92 | 2.4139 | 1.9963 | 1.7594 | 0.8413 | 0.9854 |
| n20degC | US06 | 2.7491 | 5.3576 | 5.7209 | 1.4393 | 1.1349 |

**Guards and adoption verdict**

The S1 gate uses the full-precision full-run voltage RMSE. The SoC guards use CSV precision except near a limit, where they are recomputed from unrounded traces under decision 1.35. Guard 5 compares the maximum over all 23 standard runs for each model.

| guard | value | result |
|---|---|---|
| 1. S1 gate | US06 at 25 degC: 23.2363 mV (limit 30) | pass |
| 2. rule of 1.22 | lower at 6 of 6; higher by more than 0.10 pp at none | pass |
| 3. run increase | largest -0.0651 pp; above the limit of +0.50: none | pass |
| 4. largest cycle increase | -0.4797 pp (UDDS, limit +0.25) | pass |
| 5. worst run | 2.3883 pp against 6.2547 pp | pass |
| 6. experiments 2 to 4 | largest exp4 increase -0.1121 pp (limit +0.10); fewer reached: none | pass |

Guard inputs from unrounded traces. SoC changes are in pp and temperatures follow the table order above.

| guard | unrounded values |
|---|---|
| 1 | 23.2362515344 mV |
| 2 | -0.327501570361 / -0.251425519076 / -0.576091974792 / -0.675415197033 / -2.22146847568 / -1.84927112782 |
| 3 | Largest run increase -0.0650712095378 |
| 4 | HWFET -1.01245621114, LA92 -0.651240561222, UDDS -0.479702599956, US06 -1.9175549862 |
| 5 | Worst run 6.25470078654 to 2.38825302507 |
| 6 | Experiment 4 changes -0.357455309378 / -0.405803147574 / -0.389876157603 / -0.112115130874 / -1.3677909331 / -1.36305181382 |

**ADOPTED.**

<!-- results:s10_results:end -->

The [residual diagnosis](../results/accuracy_diagnostics.md) records run
membership, input hashes, timing and Jacobian measurements for all 63 incumbent
experiment-1 runs.
The [fit report](../results/model_fit_3rcd0.md) gives solver checks, fitted nodes,
both splits' voltage scores and the 40 diagnostic Mix folds. The
[comparison report](../results/model_compare_3rcd0.md) also gives the Mix
in-sample scores and the standard-run peak error, convergence and sensitivity
diagnostics.

The 3RC-D0 model recovered the cold non-US06 gains that were at risk when
removing current-dependent R1. It improved every standard run versus 2RC-I.
The unfitted R1 substitution had lower US06 SoC RMSE at all six temperatures,
with a higher mean across the full standard suite. The substitution was scored
in experiment 1 for diagnosis. [Decision 1.47](decisions.md#147-s10-review-expands-the-diagnosis-and-defers-deployment)

![S10 comparison](../results/plots/s10/model_compare_3rcd0.png)

### S11 A · Noise and initial branch covariance

This experiment tunes the three noise settings and shared initial branch-voltage
uncertainty for 3RC-D0 using all 40 Mix runs. The objective balances wrong-start
and sensor-offset RMSE equally across six temperatures. The 23 standard runs stay
outside the objective; all 63 runs enter the regression guards. The model tables
and filter equations are unchanged. The C search accelerator is an offline tool;
the evaluation and adoption verdict use the Python reference.

<!-- results:s11_settings:begin -->

**Summary**

Experiment-1 SoC RMSE in percentage points. Each run has equal weight here; the calibration objective instead gives each temperature equal weight.

| Split | Incumbent mean | Incumbent worst | Candidate mean | Candidate worst |
|---|---|---|---|---|
| Standard (23) | 0.9817 | 2.3883 | 1.2275 | 4.2586 |
| Mix (40, calibration) | 1.2736 | 6.7681 | 1.0852 | 4.9228 |
| All (63) | 1.1670 | 6.7681 | 1.1372 | 4.9228 |

**Guards and adoption verdict**

Guard 2 uses the 23 standard runs; guards 3–7 use all 63; guard 8 uses the 40 Mix runs. The current incumbent and stage baseline are identical for step A, so both comparisons coincide. CSV values decide except within 1e-4 of a threshold or equality, where unrounded trace values decide. The 25 pp count threshold is included in that check. Original S10 files are unchanged.

| guard | value | result |
|---|---|---|
| 1. S1 gate | US06 at 25 degC: 23.2363 mV (limit 30) | pass |
| 2. Standard-run improvement | lower at 2 of 6; higher by more than 0.10 pp at -10 degC, -20 degC | FAIL |
| 3. run increase | largest +3.2588 pp; above the limit of +0.50: Mix 8 at -20 degC +3.2588, US06 at -20 degC +2.8193, UDDS at -20 degC +1.0158, Mix 4 at -20 degC +0.5792, HWFET at -10 degC +0.5461, LA92 at -10 degC +0.5062 | FAIL |
| 4. largest cycle increase | +0.3129 pp (US06, limit +0.25) | FAIL |
| 5. worst run | 4.9228 pp against 6.7681 pp | pass |
| 6. experiments 2 to 4 | largest exp4 increase +0.3890 pp (limit +0.10); fewer reached: exp3_high at -20 degC | FAIL |
| 7. Wrong-start peaks | above 25 pp: 45 vs 30; maximum 70.0000 vs 46.7341 pp | FAIL |
| 8. Mix-run means | largest increase +0.1567 pp (limit +0.10) | FAIL |

**NOT ADOPTED.** The S2 settings remain the incumbent; the candidate JSON is experimental.

See [the complete search](../results/tuning_3rcd0.md) and [per-run results](../results/ekf_results_3rcd0n.csv).

<!-- results:s11_settings:end -->

The [search report](../results/tuning_3rcd0.md) lists all 945 objectives, the
grid winner at each p0_v_std value and the input hashes, and states that the native
evaluator passed its checks against the Python filter (decision 1.50). The
[comparison report](../results/model_compare_3rcd0n.md) holds every experiment, the
guard-7 counts of the three grid winners and the state replays of the wrong-start
cases. `results/ekf_config_3rcd0.json` keeps the candidate for reproduction;
`results/ekf_config.json` stays the frozen S2 configuration.

What the candidate shows (decision 1.51): the objective pushed the initial branch
standard deviation to the end of the searched range, 5 mV. At a rested start
(experiment 2) the branches really are near zero, so the filter puts the whole first
innovation into SoC and forgets a 20 pp wrong start within a second; no experiment-2
case peaks above 25 pp against 19 for the incumbent. At a start under load
(experiment 3) the branches hold tens of millivolts, the same prior forbids the
filter to put it there, and in the cold the SoC estimate runs onto the 0 bound: 34
experiment-3-high cases peak above 25 pp, six of them at 70 pp. The objective
contains experiment 2 and not experiment 3, so one set of settings cannot serve both
start conditions. The smaller r and q_v also turn cold model error into SoC error:
Mix 8 and US06 at -20 degC rise by 3.3 and 2.8 pp, while Mix 8 at -10 degC, the
full-charge regen event, falls from 6.77 to 1.07 pp.

![S11 settings comparison](../results/plots/s11/model_compare_3rcd0n.png)

### S11 B · Regen rows at the 4.2 V limit

Every run starts at full charge and meets regen rows that the cycler holds at its
4.2 V limit in its first minutes. No fitted table covers that regime. The diagnostic
reads each model's stored experiment-1 trace and measures how far the SoC error moves
across those rows. In the cold the adopted 3RC-D0 moves several pp per run, in both
directions; the models that read R1 over current move less.

<!-- results:s11_regen:begin -->

**Limit rows per temperature**

| T (degC) | runs | intervals | limit rows | end of last interval (s) | lowest reference SoC | most negative current (A) |
|---|---|---|---|---|---|---|
| 40 | 7 | 34 | 920 | 1116.9 | 0.9220 | -5.956 |
| 25 | 11 | 78 | 2168 | 1116.9 | 0.9071 | -5.995 |
| 10 | 11 | 157 | 3599 | 2047.9 | 0.8451 | -5.995 |
| 0 | 11 | 153 | 4320 | 1658.9 | 0.8895 | -2.999 |
| -10 | 11 | 204 | 6320 | 1984.9 | 0.8596 | -2.999 |
| -20 | 12 | 172 | 6592 | 1637.9 | 0.8730 | -1.497 |

**Mean over runs of the summed change in size (pp)**

| Model | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| 2RC | 0.190 | 0.389 | 1.241 | 3.022 | 4.844 | 5.365 |
| 2RC-I | 0.107 | 0.147 | 0.420 | 0.860 | 1.672 | 1.887 |
| 2RC-Id | 0.149 | 0.256 | 0.673 | 1.979 | 2.771 | 2.889 |
| 2RC-Ic | 0.149 | 0.226 | 0.436 | 1.223 | 1.995 | 2.424 |
| 2RC-Il | 0.107 | 0.153 | 0.385 | 1.023 | 1.792 | 2.118 |
| 3RC-D | 0.092 | 0.153 | 0.535 | 0.967 | 1.606 | 1.835 |
| 3RC-D0 | 0.158 | 0.365 | 1.293 | 2.960 | 4.745 | 3.331 |
| 3RC-D0-N | 0.047 | 0.084 | 0.422 | 0.972 | 1.598 | 1.549 |

<!-- results:s11_regen:end -->

Two candidates were set aside before any run ([decision 1.52](decisions.md#152-s11-step-b-first-candidate-the-voltage-update-skipped-on-the-limit-rows-3rc-d0-g-not-run),
[decision 1.53](decisions.md#153-s11-step-b-closed-without-a-run-no-s11-change-is-adopted)). Skipping the voltage update on these rows
would slow the recovery from a wrong start at -20 degC and fail a fixed adoption guard.
A regen resistance term near full charge corrects part of the model voltage there but
leaves the SoC estimate unchanged, because part of the error is tied to the voltage limit
itself. S11 adopts nothing; 3RC-D0 with the S2 settings stays.

![S11 regen rows at the limit](../results/plots/s11/regen_limit.png)

## C port

**API** (`c/include/ekf.h`). The caller owns one `ekf_t` per cell and one `ekf_cfg_t` with the noise settings and a pointer to the parameter tables. The library allocates nothing and keeps no state of its own.

```c
ekf_status_t ekf_init(ekf_t *e, const ekf_cfg_t *cfg, ekf_real_t soc0);
ekf_status_t ekf_step(ekf_t *e, ekf_real_t i_a, ekf_real_t v_v, ekf_real_t t_degc, ekf_real_t dt_s);
ekf_real_t   ekf_get_soc(const ekf_t *e);
```

`ekf_step` predicts over `dt_s` with the held current, updates with the new sample, then holds its current. `dt_s = 0` means update only, as on the first sample of a run; a negative `dt_s` or a non-finite input (NaN or an infinity) is rejected and leaves the state unchanged. A temperature outside the table range is clamped and returns a warning status (`docs/decisions.md` 1.17). The parameter tables in `c/src/ekf_params.c` are generated from `results/params.csv` by `python/export_params.py`. The 3RC-D0 tables in `c/src/ekf_params_3rcd0.c` are generated from `results/params_3rcd0.csv` by `python/export_3rcd0.py`, which refuses a third-branch time constant other than 45 s.

**Builds.** `ekf_real_t` is `float` by default; `-DEKF_USE_DOUBLE=ON` makes it `double`. `-DEKF_SANITIZE=ON` adds AddressSanitizer and UndefinedBehaviorSanitizer to the host build. ctest runs the Unity unit tests (`c/tests/test_ekf.c`) and the three committed US06 fixtures in `c/tests/fixtures/`, where the C SoC must match the Python SoC within the same thresholds as the full equivalence run. `-DEKF_USE_3RCD0=ON` builds the four-state 3RC-D0 filter, the deployment model (`docs/decisions.md` 1.46, 1.54); ctest then runs the unit tests on four-state vectors, and the 2RC fixtures are not built.

**Footprint.** The library is cross-compiled for a Cortex-M4 with a single-precision FPU. It is not linked or run on a target.

<!-- results:footprint:begin -->

**C library footprint (Cortex-M4, float build)**

Generated by python/arm_footprint.py (make arm), do not edit. The library is cross-compiled only; nothing
is linked or run on a target.

- Compiler: `arm-none-eabi-gcc (Arm GNU Toolchain 15.3.Rel1 (Build arm-15.149)) 15.3.1 20260627`
- Flags of the library objects: `-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -O2 -std=c99 -Wall -Wextra -Wpedantic -Werror -Wdouble-promotion`

Sections of the library objects in bytes, from arm-none-eabi-size. The parameter tables are const, so they
count in .text (flash), not in .data (RAM). The size marker object and the host tools are not counted.

| object | .text | .data | .bss | total |
|---|---:|---:|---:|---:|
| ekf.c.obj | 1956 | 0 | 0 | 1956 |
| ekf_params.c.obj | 17432 | 0 | 0 | 17432 |
| total | 19388 | 0 | 0 | 19388 |

sizeof(ekf_t) = 60 bytes: the state of one filter, which the caller owns (one per cell). Read
with arm-none-eabi-nm -S from the object ekf_t_size_marker[sizeof(ekf_t)] (c/src/ekf_size_marker.c).

**Double-precision helper check**

Undefined symbols of libekf.a (arm-none-eabi-nm -u): `expf`.

Double-precision helpers searched for: `__aeabi_d*`, `__aeabi_f2d`, `__aeabi_i2d`, `__aeabi_ui2d`, `__aeabi_l2d`, `__aeabi_ul2d`.

Result: PASS, none found.

<!-- results:footprint:end -->

**3RC-D0, the deployment model.** S11 adopted no change, so 3RC-D0 with the S2 settings is the model the C port deploys (`docs/decisions.md` 1.54). Its equivalence covers all six experiment cases of every run, each from its own start row, tails included.

<!-- results:equivalence_3rcd0:begin -->

**Result**

| build | threshold (pp) | max \|delta SoC\| (pp) | worst run | largest RMS (pp) | result |
|---|---|---|---|---|---|
| float | 0.1 | 1.94e-02 | Mix 4, exp2 at 0 degC (590) | 3.65e-03 | PASS |
| double | 0.001 | 5.05e-09 | Mix 1, exp3_ref at -10 degC (601) | 2.91e-09 | PASS |

**Per experiment**

| experiment | cases | float max (pp) | float largest RMS (pp) | double max (pp) | double largest RMS (pp) |
|---|---|---|---|---|---|
| exp1 | 63 | 5.91e-03 | 1.48e-03 | 5.00e-09 | 2.90e-09 |
| exp2 | 63 | 1.94e-02 | 1.59e-03 | 5.00e-09 | 2.91e-09 |
| exp3_low | 63 | 1.36e-02 | 2.42e-03 | 5.00e-09 | 2.90e-09 |
| exp3_high | 63 | 2.53e-03 | 4.66e-04 | 5.00e-09 | 2.90e-09 |
| exp3_ref | 63 | 1.73e-02 | 3.65e-03 | 5.05e-09 | 2.91e-09 |
| exp4 | 63 | 6.51e-03 | 2.52e-03 | 5.00e-09 | 2.89e-09 |

<!-- results:equivalence_3rcd0:end -->

<!-- results:footprint_3rcd0:begin -->

**C library footprint, 3RC-D0 (Cortex-M4, float build)**

Generated by python/arm_footprint.py (make arm-3rcd0), do not edit. The library is cross-compiled only; nothing
is linked or run on a target.

- Compiler: `arm-none-eabi-gcc (Arm GNU Toolchain 15.3.Rel1 (Build arm-15.149)) 15.3.1 20260627`
- Flags of the library objects: `-DEKF_USE_3RCD0 -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -O2 -std=c99 -fstack-usage -Wall -Wextra -Wpedantic -Werror -Wdouble-promotion`

Sections of the library objects in bytes, from arm-none-eabi-size. The parameter tables are const, so they
count in .text (flash), not in .data (RAM). The size marker object and the host tools are not counted.

| object | .text | .data | .bss | total |
|---|---:|---:|---:|---:|
| ekf.c.obj | 2028 | 0 | 0 | 2028 |
| ekf_params_3rcd0.c.obj | 19860 | 0 | 0 | 19860 |
| total | 21888 | 0 | 0 | 21888 |

sizeof(ekf_t) = 92 bytes: the state of one filter, which the caller owns (one per cell). Read
with arm-none-eabi-nm -S from the object ekf_t_size_marker[sizeof(ekf_t)] (c/src/ekf_size_marker.c).

**Double-precision helper check**

Undefined symbols of libekf.a (arm-none-eabi-nm -u): `expf`, `memset`.

Double-precision helpers searched for: `__aeabi_d*`, `__aeabi_f2d`, `__aeabi_i2d`, `__aeabi_ui2d`, `__aeabi_l2d`, `__aeabi_ul2d`.

Result: PASS, none found.

**Static stack frames**

From `-fstack-usage` (`ekf.c.su`): the frame of each function of `ekf.c` in bytes, as the compiler
reports it. A call nests the frames of the functions it calls; nothing here is measured on a target.

| function | bytes | kind |
|---|---:|---|
| find_cell | 8 | static |
| mat_mul | 24 | static |
| mat_mul_transposed | 16 | static |
| ekf_interp2 | 32 | static |
| ekf_init | 0 | static |
| ekf_predict | 376 | static |
| ekf_limit_soc | 0 | static |
| ekf_update | 376 | static |
| ekf_step | 32 | static |
| ekf_get_soc | 0 | static |

<!-- results:footprint_3rcd0:end -->

The largest frames belong to `ekf_predict` and `ekf_update`, each of which holds several 4 x 4 matrices; one `ekf_step` nests at most about 450 B of frames (its own 32 B, one of those two, then the interpolation and cell search).

**CI** (`.github/workflows/ci.yml`) has four jobs. None of them downloads the raw data.

- `python`: the unit tests; the generated C tables must match `results/params.csv`; `README.md` and this file must be in sync with `results/` (`python python/update_readme.py --check`).
- `c-host`: the float build with ASan and UBSan and the double build, each with its unit tests and fixture equivalence; the same two builds of 3RC-D0 with their unit tests.
- `c-arm`: installs the pinned Arm GNU Toolchain (checked by sha256), cross-compiles, runs the double-precision helper check for both models, and requires the committed `results/c_footprint.md` and `results/c_footprint_3rcd0.md` to match byte for byte.
- `octave`: installs Ubuntu's GNU Octave and runs the Octave filter in `octave/` on the three committed fixtures against their expected SoC (`python python/compare_octave.py --fixtures`).

CI runs on every push to GitHub.

## Limitations in full

- In the cold the SoC estimate of 3RC-D0 moves by about 3 to 5 pp per run across the regen rows that the cycler holds at its 4.2 V limit near full charge ([`results/regen_limit.md`](../results/regen_limit.md)). S11 found no model or settings change that removes this within the adoption guards.
- S9 used one cell and shared drive segments across the two splits. The standard runs also informed prior diagnostics and the low-SoC boundary choice.
- This is a personal project. It validates offline on public data from one new cell.
- Not run on target hardware: the C library is cross-compiled only. It is not checked against MISRA C or ISO 26262.
- No SOH or SOP estimation, and no Simulink model.
- The 2RC-I model of S7 reads R1 at the current but holds it below the smallest HPPC pulse current, about 3 A at 40 to 0 degC, where drive cycles run often. Its smallest pulse is always the first after a 1 h rest, so a current effect and a history effect cannot be told apart there (`docs/decisions.md` 1.28). It lowers the mean SoC error in the cold but makes US06, the cycle with the highest currents, worse from 10 degC down (1.31). It runs in the Python reference only; the C library runs the 2RC model.
- The model has no hysteresis and no ageing or capacity fade, and it takes coulombic efficiency as 1. The C/20 charge put back more Ah than the discharge removed at every temperature except -20 degC, where it put back less (the charge / discharge column of the capacity table). The cause is unexplained.
- The cell aged over the campaign, which ran 25, 40, 10, 0, -10 and -20 degC in that order. It also lost capacity inside the 25 degC block (the two 25 degC 1C runs in the capacity table). One Q_ref, from the freshest cell, is used at every temperature. Missing and off-temperature 1C tests are marked in `results/capacity.md`.
- The reference SoC is itself coulomb counting, on the cycler's Ah counter. The baseline counts the logged current; the two agree closely (the coulomb-counting table of experiment 1, `docs/model.md` C13). The cycler's stated accuracy is 0.1 % of full scale, so a real sensor offset in the data would be invisible to this comparison.
- The OCV table is the C/20 discharge branch, corrected onto the HPPC 1 h rest voltages. The correction rests on the few rest points of each temperature and is held flat beyond the first and last of them. The cold rests have not fully relaxed after 1 h, which leaves a small bias in those points (`docs/decisions.md` 1.1, 1.12). The charge half of the C/20 test is not used, because the two halves do not share an Ah axis.
- The 2RC fit assumes two separable branches: R0, R1 and tau1 from the discharge pulses, R2 and tau2 from the 1 h rests, with V2 = 0 at the start of each move. A third branch fitted from the same pulses made the US06 voltage worse at most temperatures (S6), so the model keeps no time constant between the fast and the slow branch, although the drive cycles ask for one of 20 to 50 s (`docs/decisions.md` 1.25). A second fit of the middle branch alone, on the HPPC pulse trains, failed the US06 gate too (1.27). Charge pulses are fitted only for the 2RC-Ic model of S8, which is not adopted, so regen uses discharge parameters in the adopted model too; the low-current R1 of the 2RC-Il model of S8, fitted on the PausCycl files, is not adopted either. The EKF Jacobians leave out dR0/dSoC and the SoC dependence of the RC parameters (`docs/decisions.md` 1.12, `docs/model.md` Eq. 7, Eq. 8).
- The 25 degC open-loop voltage error passes the sanity limit by a thin margin (the gate line under the model-fit table).
- The noise settings were tuned on one cycle at one temperature. The eight mixes are built from segments of the four standard cycles, so the tuning cycle and the evaluation runs share segments (`docs/decisions.md` 1.11).
- Errors grow in the cold. Experiment 1 errors are clearly larger at 0, -10 and -20 degC than at 40, 25 and 10 degC, and at -10 and -20 degC many runs of experiments 2 and 3 never settle inside the +-2 pp band.
- The largest cold outliers are Mix 8 (and Mix 4 at -20 degC). These runs open under load (`docs/model.md` C13), while the filter starts with V1 = V2 = 0.
- In experiment 4 some cold runs at -10 and -20 degC have a larger SoC RMSE with the EKF than with coulomb counting; `results/ekf_results.csv` lists both per run (`rmse_pp` and `cc_rmse_pp`, experiment `exp4`). US06 at -10 degC also ends with a slightly larger EKF error than coulomb counting.
- The cycler caps the cold currents: discharge and regen are much lower at -10 and -20 degC than at the warm temperatures, and regen is already reduced at 0 degC (`results/data_inventory.md`, summary per folder). The cold drive cycles are therefore not the same loads as the warm ones.
- The evaluation set is 62 runs. Where no run exists (HWFET at 25 degC, Mix 4 to 8 at 40 degC, Mix 4 at -10 degC, Mix 3 at 10 and 0 degC) the tables show `n/a`.
- The C and Octave equivalence checks cover experiment 1 only. The other experiments run the same filter with other start values and inputs, but they are not compared run by run.
- The capacity sensitivity scales only the filter's capacity. Real ageing also changes the resistances and the OCV, while the model's tables stay as fitted.
- Valid only within the tested temperature range.
