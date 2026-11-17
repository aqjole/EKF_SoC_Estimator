# Results

Every committed result file, by the stage that wrote it (`docs/decisions.md` 1.59). Each file is written by a script in `python/` through a `make` target; `make all` rewrites all of them from the raw data except the four whose rows say otherwise. Printed paths were edited by hand where a target could not rerun: in `s11/tuning_3rcd0.md` and `s5/equivalence_octave.md` during the move of 1.59, and in `s2/tuning.md` and `s5/equivalence_octave.md` during the move of 1.60, as those entries record. The rules behind each result are in [`docs/decisions.md`](../docs/decisions.md), the tables and plots per stage in [`docs/results.md`](../docs/results.md), and every filter model side by side in [`summary.md`](summary.md). Entries of `docs/decisions.md` older than 1.59 name these files by their old flat path, `results/<file>`.

## s0: data inventory

S0 listed every raw file, measured the capacity tests and checked the dataset properties the later stages rely on. Governed by the dataset facts and anomalies of `docs/decisions.md` sections 2 and 3, and by 1.5 (evaluation set) and 1.6 (Q_ref).

| File | Written by | Holds |
|---|---|---|
| [`s0/data_inventory.md`](s0/data_inventory.md) | `python/dataset/inventory.py` (`make inventory`) | every raw file per folder with its test type, size and flags, and the sign convention |
| [`s0/capacity.md`](s0/capacity.md) | `python/dataset/inventory.py` (`make inventory`) | the capacity tests in campaign order and the C/20 and 1C capacities per folder |
| [`s0/data_checks.md`](s0/data_checks.md) | `python/dataset/data_checks.py` (`make checks`) | the measured dataset properties the docs cite: sampling steps, damaged files, temperatures, the full-charge start of the drive files, HPPC structure, counters and campaign chronology |

## s1: 2RC model fit

S1 fitted the OCV and the 2RC tables from the C/20 and HPPC files and ran the model open loop on US06; the model passes the S1 gate. Governed by 1.1, 1.2, 1.4, 1.8 and 1.12.

| File | Written by | Holds |
|---|---|---|
| [`s1/params.csv`](s1/params.csv) | `python/fit/fit_all.py` (`make fit`) | the v1.0 2RC tables: OCV, its slope, R0, R1, tau1, R2 and tau2 over temperature and SoC |
| [`s1/params.md`](s1/params.md) | `python/fit/export_params.py`, called by `python/fit/fit_all.py` (`make fit`) | the OCV valid range per temperature, the OCV correction at every HPPC rest point and the fast and slow branch fit of every HPPC level, to read |
| [`s1/fit_levels.csv`](s1/fit_levels.csv) | `python/fit/fit_all.py` (`make fit`) | the fast and slow branch fit of every HPPC level |
| [`s1/ocv_correction.csv`](s1/ocv_correction.csv) | `python/fit/fit_all.py` (`make fit`) | the OCV correction at every HPPC rest point |
| [`s1/model_fit.md`](s1/model_fit.md) | `python/fit/fit_all.py` (`make fit`) | the US06 open-loop error per temperature with the S1 gate, the HPPC pulses left out and the OCV checks |

## s2: EKF experiments

S2 froze the noise settings on the tuning cycle and ran the four experiments on every run with the 2RC filter, the v1.0 baseline. Governed by 1.3, 1.5, 1.7, 1.9, 1.13, 1.15 and 1.16.

| File | Written by | Holds |
|---|---|---|
| [`s2/ekf_config.json`](s2/ekf_config.json) | `python/evaluate/tune.py` (`make tune`, not part of `make all`) | the frozen noise settings every later filter uses unless its stage says otherwise |
| [`s2/tuning.md`](s2/tuning.md) | `python/evaluate/tune.py` (`make tune`, not part of `make all`) | the grid and refinement search on the tuning cycle |
| [`s2/ekf_results.csv`](s2/ekf_results.csv) | `python/evaluate/run_all.py` (`make ekf`) | one row per run and experiment: SoC RMSE, peak error, convergence, voltage RMSE and the coulomb-counting columns |
| [`s2/ekf_summary.md`](s2/ekf_summary.md) | `python/evaluate/run_all.py` (`make ekf`) | the tables of the four experiments per temperature |

## s3: C port

S3 ported the 2RC filter to C99; the float and double builds match the Python filter within their thresholds, and the library builds for a Cortex-M4 without double-precision helpers. Governed by 1.17.

| File | Written by | Holds |
|---|---|---|
| [`s3/equivalence.md`](s3/equivalence.md) | `python/port/compare_c.py` (`make equiv`) | the C filter against the Python filter on every run, in both builds |
| [`s3/c_footprint.md`](s3/c_footprint.md) | `python/port/arm_footprint.py` (`make arm`) | the Cortex-M4 sections, the filter state size and the double-precision helper check |

## s5: sensitivity and Octave port

S5 ran the 2RC filter with a capacity error and at 1 Hz, and checked an Octave port against the Python filter, which it matches. Governed by 1.18, 1.19 and 1.20.

| File | Written by | Holds |
|---|---|---|
| [`s5/sensitivity.csv`](s5/sensitivity.csv) | `python/evaluate/sensitivity.py` (`make sensitivity`) | experiment 1 per run with the filter capacity at -5 % and +5 % and at 1 Hz, EKF and coulomb counting |
| [`s5/sensitivity.md`](s5/sensitivity.md) | `python/evaluate/sensitivity.py` (`make sensitivity`) | the same per temperature |
| [`s5/equivalence_octave.md`](s5/equivalence_octave.md) | `python/port/compare_octave.py` (`make octave`) | the Octave filter against the Python filter on every run |

## s6: a third RC branch (negative result)

S6 fitted a 3RC model twice from the HPPC files; both fits fail the S1 gate, so neither was evaluated in the filter. Governed by 1.21 to 1.27.

| File | Written by | Holds |
|---|---|---|
| [`s6/fit_levels_3rc.csv`](s6/fit_levels_3rc.csv) | `python/fit/fit_3rc.py` (`make fit-3rc`) | the first 3RC fit of every HPPC level |
| [`s6/params_3rc.csv`](s6/params_3rc.csv) | `python/fit/fit_3rc.py` (`make fit-3rc`) | the first 3RC tables |
| [`s6/model_fit_3rc.md`](s6/model_fit_3rc.md) | `python/fit/fit_3rc.py` (`make fit-3rc`) | the US06 open-loop check of 2RC and 3RC, the level fits and the third-branch ceiling on every drive run |
| [`s6/fit_levels_3rc_rest.csv`](s6/fit_levels_3rc_rest.csv) | `python/fit/fit_3rc_rest.py` (`make fit-3rc-rest`) | the second fit, the middle branch alone on the whole HPPC pulse train of every level |
| [`s6/params_3rc_rest.csv`](s6/params_3rc_rest.csv) | `python/fit/fit_3rc_rest.py` (`make fit-3rc-rest`) | the second 3RC tables |
| [`s6/model_fit_3rc_rest.md`](s6/model_fit_3rc_rest.md) | `python/fit/fit_3rc_rest.py` (`make fit-3rc-rest`) | the level fits and the open-loop check of the second fit on US06 and every drive run |

## s7: R1 that depends on current (adopted)

S7 made R1 depend on the current (2RC-I), fitted per HPPC discharge pulse; it passes the S1 gate and the adoption rule, and was the adopted model until S10. Governed by 1.28 to 1.31.

| File | Written by | Holds |
|---|---|---|
| [`s7/fit_pulses_r1i.csv`](s7/fit_pulses_r1i.csv) | `python/fit/fit_r1_current.py` (`make fit-r1i`) | R1 of every HPPC discharge pulse |
| [`s7/r1_current.csv`](s7/r1_current.csv) | `python/fit/fit_r1_current.py` (`make fit-r1i`) | the R1 table over temperature, current and SoC |
| [`s7/model_fit_r1i.md`](s7/model_fit_r1i.md) | `python/fit/fit_r1_current.py` (`make fit-r1i`) | R1 per pulse and the open-loop check of 2RC-I on US06 and every drive run |
| [`s7/ekf_results_r1i.csv`](s7/ekf_results_r1i.csv) | `python/evaluate/compare_r1i.py` (`make ekf-r1i`) | the four experiments on 2RC-I, in the columns of `s2/ekf_results.csv` |
| [`s7/model_compare_r1i.md`](s7/model_compare_r1i.md) | `python/evaluate/compare_r1i.py` (`make ekf-r1i`) | 2RC against 2RC-I per temperature and the adoption verdict |

## s8: R1 by the sign of the current and at low current (three negative results)

S8 tried three changes to the 2RC-I resistance: the v1.0 R1 under regen (2RC-Id), a charge-side R1 (2RC-Ic) and a low-current R1 (2RC-Il); none passes the guards, and 2RC-I stayed the adopted model. Governed by 1.32 to 1.39.

| File | Written by | Holds |
|---|---|---|
| [`s8/ekf_results_r1d.csv`](s8/ekf_results_r1d.csv) | `python/evaluate/compare_r1d.py` (`make ekf-r1d`) | the four experiments on 2RC-Id |
| [`s8/model_compare_r1d.md`](s8/model_compare_r1d.md) | `python/evaluate/compare_r1d.py` (`make ekf-r1d`) | step A: 2RC, 2RC-I and 2RC-Id side by side, the guards and the test for step B |
| [`s8/fit_pulses_r1c.csv`](s8/fit_pulses_r1c.csv) | `python/fit/fit_r1_charge.py` (`make fit-r1c`) | the charge-side R1 of every HPPC charge pulse |
| [`s8/r1_charge.csv`](s8/r1_charge.csv) | `python/fit/fit_r1_charge.py` (`make fit-r1c`) | the charge-side R1 table over temperature, current and SoC |
| [`s8/model_fit_r1c.md`](s8/model_fit_r1c.md) | `python/fit/fit_r1_charge.py` (`make fit-r1c`) | the charge pulses in the fit and the open-loop check of 2RC-Ic on US06 |
| [`s8/ekf_results_r1c.csv`](s8/ekf_results_r1c.csv) | `python/evaluate/compare_r1c.py` (`make ekf-r1c`) | the four experiments on 2RC-Ic |
| [`s8/model_compare_r1c.md`](s8/model_compare_r1c.md) | `python/evaluate/compare_r1c.py` (`make ekf-r1c`) | step B: the four models side by side, the guards and the verdict |
| [`s8/r1_low.csv`](s8/r1_low.csv) | `python/fit/fit_r1_low.py` (`make fit-r1l`) | the 2RC-Il R1 table, scaled at low current |
| [`s8/model_fit_r1l.md`](s8/model_fit_r1l.md) | `python/fit/fit_r1_low.py` (`make fit-r1l`) | the low-current factors fitted on the PausCycl files and the open-loop check on US06 and every drive run |
| [`s8/ekf_results_r1l.csv`](s8/ekf_results_r1l.csv) | `python/evaluate/compare_r1l.py` (`make ekf-r1l`) | the four experiments on 2RC-Il |
| [`s8/model_compare_r1l.md`](s8/model_compare_r1l.md) | `python/evaluate/compare_r1l.py` (`make ekf-r1l`) | step C: 2RC, 2RC-I and 2RC-Il side by side, the guards and the verdict |

## s9: slow-branch resistances fitted on drive data

S9 added a third branch and scaled R2 on the 2RC-I model, fitted on the Mix runs and judged on the standard runs (3RC-D); the worst-run guard rejects it. Governed by 1.40 to 1.43.

| File | Written by | Holds |
|---|---|---|
| [`s9/fit_nodes_3rcd.csv`](s9/fit_nodes_3rcd.csv) | `python/fit/fit_3rcd.py` (`make fit-3rcd`) | R3 and the R2 scale at every fitted node, with support and bounds |
| [`s9/params_3rcd.csv`](s9/params_3rcd.csv) | `python/fit/fit_3rcd.py` (`make fit-3rcd`) | the 3RC-D tables |
| [`s9/model_fit_3rcd.md`](s9/model_fit_3rcd.md) | `python/fit/fit_3rcd.py` (`make fit-3rcd`) | the fit checks, the open-loop error on both splits, the US06 gate and the leave-one-run-out check |
| [`s9/ekf_results_3rcd.csv`](s9/ekf_results_3rcd.csv) | `python/evaluate/compare_3rcd.py` (`make ekf-3rcd`) | the four experiments on 3RC-D |
| [`s9/model_compare_3rcd.md`](s9/model_compare_3rcd.md) | `python/evaluate/compare_3rcd.py` (`make ekf-3rcd`) | 2RC, 2RC-I and 3RC-D on the standard and the Mix runs, the guards and the verdict |

## s10: drive-fitted third branch with the v1.0 R1 (adopted, the deployment model)

S10 refitted the S9 branches with the v1.0 R1 (3RC-D0); it passes all six guards and is the deployment model. A separate diagnosis looks at the residuals and the omitted Jacobian terms. Governed by 1.44 to 1.47; deployment by 1.54.

| File | Written by | Holds |
|---|---|---|
| [`s10/fit_nodes_3rcd0.csv`](s10/fit_nodes_3rcd0.csv) | `python/fit/fit_3rcd0.py` (`make fit-3rcd0`, in `make accuracy`) | R3 and the R2 scale at every fitted node, with support and bounds |
| [`s10/params_3rcd0.csv`](s10/params_3rcd0.csv) | `python/fit/fit_3rcd0.py` (`make fit-3rcd0`, in `make accuracy`) | the 3RC-D0 tables, which the deployment model and its C build use |
| [`s10/model_fit_3rcd0.md`](s10/model_fit_3rcd0.md) | `python/fit/fit_3rcd0.py` (`make fit-3rcd0`, in `make accuracy`) | the fit checks, the US06 gate, the open-loop error on both splits and the leave-one-run-out check |
| [`s10/ekf_results_3rcd0.csv`](s10/ekf_results_3rcd0.csv) | `python/evaluate/compare_3rcd0.py` (`make ekf-3rcd0`, in `make accuracy`) | the four experiments on 3RC-D0 |
| [`s10/model_compare_3rcd0.md`](s10/model_compare_3rcd0.md) | `python/evaluate/compare_3rcd0.py` (`make ekf-3rcd0`, in `make accuracy`) | 3RC-D0 against 2RC-I and earlier models on both splits, the guards and the verdict |
| [`s10/sensitivity_3rcd0.csv`](s10/sensitivity_3rcd0.csv) | `python/evaluate/compare_3rcd0.py` (`make ekf-3rcd0`, in `make accuracy`) | experiment 1 on the standard runs with the capacity error and at 1 Hz, for 2RC-I and 3RC-D0 |
| [`s10/accuracy_diagnostics.md`](s10/accuracy_diagnostics.md) | `python/diagnose/diagnose_accuracy.py` (`make diagnose-accuracy`, in `make accuracy`) | the residual diagnosis of 2RC-I: residuals by split and window, timing, omitted Jacobian terms, frozen inputs |
| [`s10/accuracy_jacobian.csv`](s10/accuracy_jacobian.csv) | `python/diagnose/diagnose_accuracy.py` (`make diagnose-accuracy`, in `make accuracy`) | the omitted Jacobian terms per run and window |
| [`s10/accuracy_residual_bins.csv`](s10/accuracy_residual_bins.csv) | `python/diagnose/diagnose_accuracy.py` (`make diagnose-accuracy`, in `make accuracy`) | voltage, innovation and SoC errors binned by feature, split and temperature |

## s11: filter settings, the regen limit and the 3RC-D0 C port

S11 searched new noise settings for 3RC-D0 (3RC-D0-N, not adopted), measured the regen rows at the 4.2 V limit (step B closed without a run) and ported 3RC-D0 to C, which meets its limits. Governed by 1.48 to 1.55.

| File | Written by | Holds |
|---|---|---|
| [`s11/tuning_3rcd0.md`](s11/tuning_3rcd0.md) | `python/evaluate/tune_3rcd0.py` (`make tune-3rcd0`, not part of `make all`) | the settings search on the Mix runs: method, grid, refinement and input hashes |
| [`s11/ekf_config_3rcd0.json`](s11/ekf_config_3rcd0.json) | `python/evaluate/tune_3rcd0.py` (`make tune-3rcd0`, not part of `make all`) | the settings candidate, kept for reproduction only |
| [`s11/ekf_results_3rcd0n.csv`](s11/ekf_results_3rcd0n.csv) | `python/evaluate/compare_3rcd0n.py` (`make ekf-3rcd0n`) | the four experiments on 3RC-D0 under the candidate settings (3RC-D0-N) |
| [`s11/model_compare_3rcd0n.md`](s11/model_compare_3rcd0n.md) | `python/evaluate/compare_3rcd0n.py` (`make ekf-3rcd0n`) | the candidate against 3RC-D0 under the S2 settings, the eight guards and the wrong-start diagnostics |
| [`s11/regen_limit.csv`](s11/regen_limit.csv) | `python/diagnose/diagnose_regen.py` (`make diagnose-regen`) | every interval of regen rows at the 4.2 V limit and each model's SoC error before and after it |
| [`s11/regen_limit.md`](s11/regen_limit.md) | `python/diagnose/diagnose_regen.py` (`make diagnose-regen`) | the same per temperature and per run |
| [`s11/equivalence_3rcd0.csv`](s11/equivalence_3rcd0.csv) | `python/port/compare_c_3rcd0.py` (`make equiv-3rcd0`) | the 3RC-D0 C build against the Python filter per run and experiment, in both builds |
| [`s11/equivalence_3rcd0.md`](s11/equivalence_3rcd0.md) | `python/port/compare_c_3rcd0.py` (`make equiv-3rcd0`) | the same per experiment and temperature, with the verdict |
| [`s11/c_footprint_3rcd0.md`](s11/c_footprint_3rcd0.md) | `python/port/arm_footprint.py --model 3rcd0` (`make arm-3rcd0`) | the Cortex-M4 sections, state size, helper check and static stack frames of the 3RC-D0 build |

## s12: starts and Jacobian of the 3RC-D0 filter

S12 diagnosed the wrong starts and the omitted Jacobian terms of the 3RC-D0 filter, then tried a branch prior for a start at low current (3RC-D0-P), which fails two guards and is not adopted; accuracy work on this dataset ends here. Governed by 1.56 to 1.58.

| File | Written by | Holds |
|---|---|---|
| [`s12/start_cases.csv`](s12/start_cases.csv) | `python/diagnose/diagnose_starts.py` (`make diagnose-starts`) | the history before each run and every wrong-start case with its start measures |
| [`s12/start_cases.md`](s12/start_cases.md) | `python/diagnose/diagnose_starts.py` (`make diagnose-starts`) | the same as tables, and the branch prior values screened on the Mix runs |
| [`s12/jacobian_3rcd0.csv`](s12/jacobian_3rcd0.csv) | `python/diagnose/diagnose_jacobian.py` (`make diagnose-jacobian`) | the omitted Jacobian terms of the 3RC-D0 filter per run, experiment and window |
| [`s12/jacobian_3rcd0.md`](s12/jacobian_3rcd0.md) | `python/diagnose/diagnose_jacobian.py` (`make diagnose-jacobian`) | the same as tables, and the three Jacobian variants screened on the Mix runs |
| [`s12/ekf_config_3rcd0p.json`](s12/ekf_config_3rcd0p.json) | `python/evaluate/compare_3rcd0p.py` (`make ekf-3rcd0p`) | the S2 settings plus the branch prior for a rested start |
| [`s12/ekf_results_3rcd0p.csv`](s12/ekf_results_3rcd0p.csv) | `python/evaluate/compare_3rcd0p.py` (`make ekf-3rcd0p`) | the four experiments on 3RC-D0-P |
| [`s12/model_compare_3rcd0p.md`](s12/model_compare_3rcd0p.md) | `python/evaluate/compare_3rcd0p.py` (`make ekf-3rcd0p`) | 3RC-D0-P against 3RC-D0, the eight guards and the verdict |

There is no `s4/`: S4 wrote the README, not a result file.

## summary.md

[`summary.md`](summary.md) is written by `python/report/summarize.py` (`make summary`) from the files above: coulomb counting, the baseline and the deployment model in every experiment and per temperature (the two tables the README leads with), one row per filter model with its status, the experiment means, the US06 open-loop check of every model's tables and the two C builds.

## plots/

Every figure in `plots/` is written by a repo script; none is saved by hand. The fixed list and the reasons are in `docs/decisions.md` 1.14 (S5: 1.18 to 1.20; S6 to S11 follow 1.21 to 1.49).

| Folder | Written by | Files |
|---|---|---|
| `plots/s1/` | `python/fit/fit_all.py` (`make fit`) | `ocv.png`, `docv.png`, `params.png`, `model_fit_<T>degC.png` x 6 |
| `plots/s2/` | `python/evaluate/run_all.py` (`make ekf`) | `summary_rmse.png`, `summary_convergence.png`, `trace_<experiment>_<cycle>_<T>degC.png` x 16, `synthetic.png` |
| `plots/s3/` | `python/port/compare_c.py` (`make equiv`) | `equivalence_<T>degC.png` x 6 |
| `plots/s5/` | `python/evaluate/sensitivity.py` (`make sensitivity`), `python/port/compare_octave.py` (`make octave`) | `sensitivity_capacity.png`, `sensitivity_rate.png`, `equivalence_octave_25degC.png` |
| `plots/s6/` | `python/fit/fit_3rc.py` (`make fit-3rc`), `python/fit/fit_3rc_rest.py` (`make fit-3rc-rest`) | `params_3rc.png`, `params_3rc_rest.png` |
| `plots/s7/` | `python/fit/fit_r1_current.py` (`make fit-r1i`), `python/evaluate/compare_r1i.py` (`make ekf-r1i`) | `r1_current.png`, `model_compare_r1i.png` |
| `plots/s8/` | `python/evaluate/compare_r1d.py` (`make ekf-r1d`), `python/fit/fit_r1_charge.py` (`make fit-r1c`), `python/evaluate/compare_r1c.py` (`make ekf-r1c`), `python/evaluate/compare_r1l.py` (`make ekf-r1l`) | `model_compare_r1d.png`, `r1_charge.png`, `model_compare_r1c.png`, `model_compare_r1l.png` |
| `plots/s9/` | `python/fit/fit_3rcd.py` (`make fit-3rcd`), `python/evaluate/compare_3rcd.py` (`make ekf-3rcd`) | `params_3rcd.png`, `model_compare_3rcd.png` |
| `plots/s10/` | `python/diagnose/diagnose_accuracy.py`, `python/fit/fit_3rcd0.py`, `python/evaluate/compare_3rcd0.py` | `accuracy_residuals.png`, `params_3rcd0.png`, `model_compare_3rcd0.png` |
| `plots/s11/` | `python/evaluate/tune_3rcd0.py` (`make tune-3rcd0`), `python/evaluate/compare_3rcd0n.py` (`make ekf-3rcd0n`), `python/diagnose/diagnose_regen.py` (`make diagnose-regen`) | `tuning_3rcd0.png`, `model_compare_3rcd0n.png`, `regen_limit.png` |
| `plots/s12/` | `python/diagnose/diagnose_starts.py` (`make diagnose-starts`), `python/diagnose/diagnose_jacobian.py` (`make diagnose-jacobian`), `python/evaluate/compare_3rcd0p.py` (`make ekf-3rcd0p`) | `start_cases.png`, `jacobian_3rcd0.png`, `model_compare_3rcd0p.png` |

Per-run traces for every evaluation run are not committed; `run_all.py` writes them to `results/runs/plots/` (gitignored).

## runs/

Git-ignored. The per-run traces of every model's filter (`runs/*.npz` for 2RC, `runs/r1i/`, `runs/r1d/`, `runs/r1c/`, `runs/r1l/`, `runs/3rcd/`, `runs/3rcd0/`, `runs/3rcd0n/`, `runs/3rcd0p/`), the C filter inputs (`runs/c_inputs/`, `runs/c_inputs_3rcd0/`), the per-run trace plots (`runs/plots/`) and the checkpoint of the S11 search (`runs/s11_tuning/`). The targets above write them and reuse a trace while it is newer than its inputs and code.
