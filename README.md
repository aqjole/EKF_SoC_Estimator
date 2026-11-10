# EKF SoC Estimator

[![ci](https://github.com/aqjole/EKF_SoC_Estimator/actions/workflows/ci.yml/badge.svg)](https://github.com/aqjole/EKF_SoC_Estimator/actions/workflows/ci.yml)

State-of-charge (SoC) estimation for a Li-ion cell with an equivalent-circuit model and an Extended Kalman Filter (EKF). The Python reference was evaluated offline on the public LG 18650HG2 dataset at six temperatures, from 40 to -20 degC. Its S10 model is 3RC-D0, with a drive-fitted middle branch and v1.0 R1. The embedded C99 library reproduces the v1.0 2RC model.

## Results at a glance

Every filter model run in all four experiments, scored the same way on all 63 runs (the 62 evaluation runs plus the tuning run, Mix 1 at 25 degC); diagnostic variants run on fewer cases stay in their stage reports. 3RC-D0 is the deployment model; the rows marked not adopted are negative results kept on purpose, as are the two S6 fits, which failed the open-loop gate and never reached the filter ([`results/summary.md`](results/summary.md)). [`results/README.md`](results/README.md) indexes every result file, [`docs/results.md`](docs/results.md) every table.

The filter runs four experiments on every drive-cycle run: (1) the correct initial SoC, (2) an initial SoC 20 pp too low, (3) a restart mid-run at 50 % or 90 % SoC when the reference is 70 %, and (4) a +0.2 A current-sensor offset. Errors are SoC RMSE in percentage points (pp) of SoC. Experiments 2, 3 low and 3 high are the wrong starts; the last column counts those whose largest SoC error exceeds 25 pp.

<!-- results:scoreboard:begin -->

**Filter models**

Mean SoC RMSE in pp over the 63 runs of each model's experiments CSV. The Mix and 63-run columns are not validation: 3RC-D and 3RC-D0 are fitted on the Mix runs (decisions 1.41, 1.44), 3RC-D0-N is tuned (1.49) and 3RC-D0-P screened (1.57) on them, and every filter but 3RC-D0-N runs the noise settings of 1.15, tuned on Mix 1 at 25 degC (3RC-D0-P with a 10 mV branch prior at a start below 0.5 A). The standard runs are a repeatedly inspected regression set (1.32, 1.44). A status follows its stage's adoption rule, not these means; from S9 on that rule is judged on the standard runs, with guards on all runs and the Mix runs added in S11 and S12 (1.48).

| Model | Stage | Status | Decision | Exp 1, 63 runs | Exp 1, 23 standard | Exp 1, 40 Mix | Exp 1, worst run | Exp 2 | Exp 4 | Wrong starts above 25 pp (of 189) |
|---|---|---|---|---|---|---|---|---|---|---|
| 2RC | S2 | v1.0 baseline, the default C build | 1.15, 1.55 | 2.10 | 1.79 | 2.28 | 9.12 (Mix 8, -20 degC) | 2.84 | 2.31 | 19 |
| 2RC-I | S7 | adopted, replaced in S10 | 1.31, 1.45 | 1.92 | 2.00 | 1.88 | 6.34 (Mix 6, -20 degC) | 2.49 | 2.17 | 17 |
| 2RC-Id | S8 | not adopted | 1.34 | 1.77 | 1.60 | 1.88 | 6.98 (Mix 6, -20 degC) | 2.27 | 1.84 | 15 |
| 2RC-Ic | S8 | not adopted | 1.36 | 1.86 | 1.85 | 1.87 | 6.61 (Mix 6, -20 degC) | 2.41 | 2.08 | 16 |
| 2RC-Il | S8 | not adopted | 1.38 | 1.99 | 2.06 | 1.94 | 6.47 (Mix 6, -20 degC) | 2.61 | 2.06 | 17 |
| 3RC-D | S9 | not adopted | 1.43 | 1.16 | 1.60 | 0.91 | 6.40 (US06, -10 degC) | 3.94 | 1.44 | 30 |
| 3RC-D0 | S10 | deployment model | 1.45, 1.54, 1.55 | 1.17 | 0.98 | 1.27 | 6.77 (Mix 8, -10 degC) | 4.69 | 1.50 | 30 |
| 3RC-D0-N | S11 | not adopted | 1.51 | 1.14 | 1.23 | 1.09 | 4.92 (Mix 8, -20 degC) | 1.22 | 1.38 | 45 |
| 3RC-D0-P | S12 | not adopted | 1.58 | 1.10 | 1.03 | 1.14 | 6.77 (Mix 8, -10 degC) | 1.38 | 1.43 | 13 |

<!-- results:scoreboard:end -->

3RC-D0 passed all six S10 guards against the incumbent 2RC-I: it lowered the experiment-1 mean SoC RMSE over the 23 standard runs from 2.00 to 0.98 pp and the worst standard run from 6.25 to 2.39 pp. The 40 Mix runs supplied the calibration data and share drive segments with the standard suite. [S10 results](docs/results.md#s10--drive-fitted-third-branch-with-v10-r1)

The reference SoC is itself coulomb counting, so with a correct start and an exact current sensor plain coulomb counting is near-perfect here (0.03 to 0.06 pp). The EKF earns its place when that fails: in experiments 2 to 4, and under a 5 % capacity error, where from 40 to 10 degC the EKF stays at 0.6 to 1.4 pp while coulomb counting rises to 2.3 to 2.8 pp (`results/s5/sensitivity.md`).

The C port (v1.0 2RC model) against the Python reference, experiment 1 on all 63 runs:

<!-- results:summary_equivalence:begin -->

**Result**

| build | threshold (pp) | max \|delta SoC\| (pp) | worst run | largest RMS (pp) | result |
|---|---|---|---|---|---|
| float | 0.1 | 1.85e-02 | HWFET at -20 degC (610) | 6.00e-03 | PASS |
| double | 0.001 | 5.00e-09 | HWFET at -20 degC (610) | 2.89e-09 | PASS |

<!-- results:summary_equivalence:end -->

The C port of the deployment model, 3RC-D0 with the S2 settings, against the Python reference in all six experiment cases (1, 2, 3 low, 3 high, 3 reference, 4) on all 63 runs:

<!-- results:summary_equivalence_3rcd0:begin -->

**Result**

| build | threshold (pp) | max \|delta SoC\| (pp) | worst run | largest RMS (pp) | result |
|---|---|---|---|---|---|
| float | 0.1 | 1.94e-02 | Mix 4, exp2 at 0 degC (590) | 3.65e-03 | PASS |
| double | 0.001 | 5.05e-09 | Mix 1, exp3_ref at -10 degC (601) | 2.91e-09 | PASS |

<!-- results:summary_equivalence_3rcd0:end -->

![SoC RMSE per experiment and temperature](results/plots/s2/summary_rmse.png)

*Per-run SoC RMSE of the v1.0 2RC filter in all four experiments (experiment 3 split into its low and high start).*

On a Cortex-M4F in float32 the library takes 19,388 B of flash, 17,432 B of it the const parameter tables, no .data or .bss, and 60 B of state per filter, owned by the caller; it needs no double-precision helpers (`results/s3/c_footprint.md`). The 3RC-D0 build, the deployment model since S11, takes 21,888 B of flash, 19,860 B of it the tables, and 92 B of state per filter; its largest static stack frame is 376 B and it also needs no double-precision helpers (`results/s11/c_footprint_3rcd0.md`).

## Claims

1. **The EKF recovers from a wrong initial SoC and keeps a current-sensor offset bounded, where plain coulomb counting does not.** This holds in nearly every run at 40, 25, 10 and 0 degC. At -10 and -20 degC it holds only in part: in many cold runs the error does not settle inside the +-2 pp band before the end of the run ("not reached"), and some cold runs end several pp off.
   Evidence: the convergence tables of experiments 2 and 3 (their `reached` rows count the runs per temperature) and the end-of-window errors of experiment 4, where coulomb counting drifts with the offset and the EKF does not ([S2 results](docs/results.md#s2-ekf-experiments)).
2. **The float32 C port reproduces the Python reference to within 0.1 pp of SoC.**
   Evidence: `results/s3/equivalence.md` (v1.0 2RC, experiment 1) and `results/s11/equivalence_3rcd0.md` (3RC-D0, all six experiment cases) run the C filter and the Python filter on every evaluation run and the tuning cycle and compare the SoC row by row; the worst case is in the [C port equivalence](docs/results.md#s3-c-port-equivalence) table.

## Overview

<p align="center"><img src="docs/model.svg" alt="2RC equivalent circuit: OCV source, R0, R1 parallel C1, R2 parallel C2, terminal voltage V" width="620"></p>

**Model.** In v1.0, the cell is an open-circuit voltage OCV(SoC, T) in series with an ohmic resistance R0 and two RC branches, a fast one (R1, C1) and a slow one (R2, C2). The current I is positive on discharge. Every parameter is a table over temperature and SoC, read with clamped bilinear interpolation. The OCV comes from the C/20 discharge, corrected onto the HPPC rest voltages; R0 and the RC branches come from the HPPC pulses and rests (`docs/decisions.md` 1.1, 1.2, 1.12). The 3RC-D0 model adds a 45 s middle branch and fits R3 and a scale on R2 on the 40 Mix runs.

**Filter.** The 2RC state is x = [SoC, V1, V2]. The 3RC-D0 state adds V3. The input is the measured current, the measurement is the terminal voltage, and the measured cell temperature selects the table values. Each sample runs a predict step and an update step. The noise settings were tuned once, on one drive cycle (Mix 1 at 25 degC), and frozen (`docs/decisions.md` 1.3, 1.15). When an update pushes SoC outside [0, 1], the whole state is projected onto the bound along the covariance, not truncated (`docs/decisions.md` 1.16).

**Reference SoC.** The reference is coulomb counting on the cycler's own Ah counter from the full charge at the start of each test. Q_ref is the 25 degC C/20 discharge capacity, one value for every temperature (`docs/decisions.md` 1.6, `docs/model.md` C13). The plain coulomb-counting baseline integrates the logged current instead, as a BMS would.

**C port.** `c/` holds a C99 library with the same equations in the same operation order. It uses no dynamic allocation, no mutable globals and no file I/O. `ekf_real_t` is `float` by default and `double` on request. The default build is the v1.0 2RC filter; `-DEKF_USE_3RCD0=ON` builds the four-state 3RC-D0 filter, the model selected for deployment (`docs/decisions.md` 1.54).

The two model equations, with `a_i = exp(-dt / tau_i)` and the current held over each step:

- RC branches: `V_i(k) = a_i V_i(k-1) + R_i (1 - a_i) I(k-1)`
- terminal voltage: subtract the branch voltages and `R0(SoC, T) I` from `OCV(SoC, T)`

The full equations and conventions are in [`docs/model.md`](docs/model.md). Experiment protocols and outcomes are in [`docs/decisions.md`](docs/decisions.md).

## What was tried after v1.0

- **S5, sensitivity and an Octave port.** A 5 % error in the filter's capacity, a 1 Hz sample rate, and a GNU Octave port checked against Python like the C port. From 40 to 10 degC the EKF tolerates the capacity error far better than coulomb counting, but not in the cold; the Octave port matches Python to within 1e-11 pp. [Results](docs/results.md#s5-sensitivity)
- **S6, a third RC branch: negative result.** Fitted twice, each time under rules fixed before the fit; both fits made the voltage error on US06 (the most aggressive standard drive cycle) worse at most temperatures, so the 2RC model stays. [Results](docs/results.md#s6-a-third-rc-branch-negative-result)
- **S7, R1 that depends on the current: adopted.** The 2RC-I model lowers the SoC error in the cold and is adopted in the Python reference; it makes US06, the cycle with the highest currents, worse from 10 degC down. [Results](docs/results.md#s7-r1-that-depends-on-current-adopted)
- **S8, R1 by the sign of the current and at low current: three negative results.** Two ways to read R1 under regen (the charging current of regenerative braking) and one low-current R1 fitted on data outside the evaluation set, to undo that US06 regression; each fixed US06 in part but broke guards on other cycles (limits, fixed in advance, on how much any run or cycle may get worse), so 2RC-I stays and the stage is closed. [Results](docs/results.md#s8-r1-by-the-sign-of-the-current-and-at-low-current-three-negative-results)
- **S9, slow-branch resistances fitted on drive data.** 3RC-D lowered open-loop voltage RMSE and experiment-1 mean SoC RMSE at all six temperatures on the standard cycles. The worst-run guard rejected it after US06 at -10 degC rose from 6.25 to 6.40 pp. [Results](docs/results.md#s9-slow-branch-resistances-fitted-on-drive-data)
- **S10, drive-fitted third branch with v1.0 R1.** 3RC-D0 improved experiment-1 SoC RMSE on every standard run versus 2RC-I. The unfitted S9 R1 substitution scored better on US06 and had a higher overall mean. [Comparison](results/s10/model_compare_3rcd0.md)
- **S11 step A, noise settings and initial branch covariance.** A 945-point search on the 40 Mix runs cut its calibration objective from 2.92 to 1.10 pp, but the chosen settings failed six of eight adoption guards: a 5 mV prior on the branch voltages forgets a rested wrong start within a second and collapses a start under load, and the -20 degC runs get worse. The S2 settings stay. [Comparison](results/s11/model_compare_3rcd0n.md) · [Search](results/s11/tuning_3rcd0.md)
- **S11 step B, regen rows at the 4.2 V limit.** Every run meets regen rows held at the cycler's 4.2 V limit near full charge, and the adopted model's cold SoC error moves 3 to 5 pp per run across them. Skipping the update there fails a fixed guard, and a regen resistance term does not move the SoC, so S11 adopts nothing. [Diagnostic](results/s11/regen_limit.md)
- **S11 close, C port of 3RC-D0.** With nothing adopted in S11, 3RC-D0 with the S2 settings is the deployment model. Its four-state C build matches Python in every experiment case of all 63 runs (float within 0.02 pp) and fits in 21,888 B of Cortex-M4 flash with 92 B of state. [Equivalence](results/s11/equivalence_3rcd0.md) · [Footprint](results/s11/c_footprint_3rcd0.md)
- **S12 step A, the starts.** 30 of the 189 wrong-start cases peak above 25 pp; no measured start quantity separates them. On the Mix runs a smaller branch prior for a start below 0.5 A halves the Mix cases above 25 pp (20 to 10). [Diagnostic](results/s12/start_cases.md)
- **S12 step B, the omitted Jacobian terms.** They matter mainly in the cold; none of three variants that put them back passes the Mix pre-screen. [Diagnostic](results/s12/jacobian_3rcd0.md)
- **S12 step C, a rested-start branch prior: not adopted.** A 10 mV prior cuts the -20 degC experiment-2 mean from 12.45 to 2.61 pp but fails guards 2 and 3 on the cold standard runs. Accuracy work on this dataset ends here; next is the filter on target hardware. [Comparison](results/s12/model_compare_3rcd0p.md)

## Dataset

LG 18650HG2 Li-ion Battery Data (P. Kollmeyer, M. Naguib and M. Skells, McMaster University, Mendeley Data, DOI [10.17632/b5mj79w5w9.2](https://doi.org/10.17632/b5mj79w5w9.2)): one new 18650 cell tested at six temperatures. The C/20 discharge gives the OCV, the HPPC test gives the resistances and time constants, and 62 drive-cycle runs (UDDS, HWFET, LA92, US06 and eight mixes of them) are the evaluation set. Run selection and the measured capacities are in [`docs/results.md`](docs/results.md#dataset).

## How to run

Requirements: Python 3.12, CMake and a C99 compiler. `make all` also runs `make arm`, which needs the Arm GNU Toolchain, and `make octave`, which needs GNU Octave and is slow.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
make data        # download the raw .mat files into data/raw/ and verify their sha256
make all         # every stage, in order, then refresh the copied tables
make readme-check  # fail if README.md or docs/results.md is out of sync with results/
.venv/bin/python -m pytest python/tests -q   # unit tests; those needing the raw data skip without it
```

Every target, what it writes and the extra tools some need (the Arm toolchain, Octave) are listed in [`docs/results.md`](docs/results.md#how-to-run-every-target). To reproduce S9 using the earlier outputs, run `make fit-3rcd` and then `make ekf-3rcd`. Run `make accuracy` for the S10 fit, evaluation and separate diagnosis.

Run `make ekf-3rcd0n` to reproduce the S11 step A comparison from the saved candidate settings; `make tune-3rcd0` repeats the search itself (outside `make all`, needs a host C compiler).

Run `make diagnose-starts`, `make diagnose-jacobian` and `make ekf-3rcd0p` for the S12 diagnostics and comparison.

## Limitations

- A personal project, validated offline on public data from one new cell, and only within the tested temperature range.
- Not run on target hardware: the C library is cross-compiled only and not checked against MISRA C or ISO 26262. No SOH or SOP estimation, no Simulink model.
- The model has no hysteresis, no ageing or capacity fade, and takes coulombic efficiency as 1, although the C/20 charge put back 0.98 to 1.07 times the discharge Ah (unexplained). The OCV is the C/20 discharge branch.
- The cell aged over the campaign, which ran 25, 40, 10, 0, -10 and -20 degC in that order, and lost capacity inside the 25 degC block too; one Q_ref is used at every temperature (`results/s0/capacity.md`).
- The reference SoC is itself coulomb counting, on the cycler's Ah counter, so the coulomb-counting baseline on the logged current agrees with it closely by construction. With the cycler's stated accuracy of 0.1 % of full scale, a real current-sensor offset in the data would not show.
- The noise settings were tuned on one cycle at one temperature, and the evaluation runs share segments with it, because the mixes are built from segments of the standard cycles (`docs/decisions.md` 1.11). S7 and S8 compared models on the same 62 runs that every stage since S2 has looked at, so those comparisons are on a repeatedly inspected set (1.32).
- S9 and S10 used 23 previously inspected standard runs for regression checks. They share segments with the 40 Mix runs used for calibration.
- Errors grow in the cold: at -10 and -20 degC many runs of experiments 2 and 3 never settle inside the 2 pp band. The cycler also caps the cold currents, so the cold drive cycles are lighter loads than the warm ones. With the current offset of experiment 4, four cold runs (Mix 8 at -10 and -20 degC, HWFET and Mix 4 at -20 degC) have a larger SoC RMSE than coulomb counting, and US06 at -10 degC ends with a slightly larger error (`results/s2/ekf_results.csv`).
- In the cold the SoC estimate moves by about 3 to 5 pp per run across the regen rows the cycler holds at 4.2 V near full charge; S11 found no change that removes this within the adoption guards.
- Under the deployment filter, 30 of the 189 wrong-start cases overshoot above 25 pp. S12 measured this and adopted nothing: a 10 mV rested-start prior cuts the experiment-2 error but fails two guards.
- The S7 2RC-I model held R1 flat below its smallest pulse current and made US06 worse from 10 degC down. The S10 experiment replaces its current-axis lookup with v1.0 R1 and refits the slow branches.

The full list, with the fit and OCV assumptions, is in [`docs/results.md`](docs/results.md#limitations-in-full).

## Reproducibility

Every result table in this README and in `docs/results.md` sits between `<!-- results:<key>:begin -->` and `<!-- results:<key>:end -->` markers and is copied from a file in `results/` by `python/update_readme.py`. Each of those files is written by a script in this repository. `make all` reproduces them from the raw data, and `make readme-check` and CI fail when the documents and `results/` disagree.

## Citation and licence

The code is under the MIT licence (`LICENSE`).

The dataset is under CC BY 4.0. The excerpts committed as test fixtures, in `python/tests/fixtures/` and `c/tests/fixtures/`, are data from it: they carry the dataset's licence and attribution, not the MIT licence. Each fixtures folder has a README with its source.

Dataset citation: P. Kollmeyer, M. Naguib, M. Skells, "LG 18650HG2 Li-ion Battery Data", McMaster University, Mendeley Data, version 2, 2020. DOI [10.17632/b5mj79w5w9.2](https://doi.org/10.17632/b5mj79w5w9.2).
