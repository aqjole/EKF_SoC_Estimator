# Reproduce the results from the raw data. Stages and targets are described in the spec.

PYTHON := .venv/bin/python

.PHONY: all data inventory checks fit fit-3rc fit-3rc-rest fit-r1i ekf-r1i ekf-r1d fit-r1c ekf-r1c fit-r1l ekf-r1l fit-3rcd ekf-3rcd accuracy diagnose-accuracy fit-3rcd0 ekf-3rcd0 tune-3rcd0 ekf-3rcd0n diagnose-regen diagnose-starts diagnose-jacobian c-3rcd0 equiv-3rcd0 arm-3rcd0 tune ekf c equiv arm sensitivity octave readme readme-check

all: data inventory checks fit ekf c equiv arm sensitivity octave fit-3rc fit-3rc-rest fit-r1i ekf-r1i ekf-r1d fit-r1c ekf-r1c fit-r1l ekf-r1l fit-3rcd ekf-3rcd
	$(MAKE) accuracy
	$(MAKE) ekf-3rcd0n
	$(MAKE) diagnose-regen
	$(MAKE) diagnose-starts
	$(MAKE) diagnose-jacobian
	$(MAKE) c-3rcd0
	$(MAKE) equiv-3rcd0
	$(MAKE) arm-3rcd0
	$(MAKE) readme

# Fetch the LG 18650HG2 .mat files into data/raw/ and verify their sha256.
data:
	bash data/download.sh

# S0: write results/data_inventory.md and results/capacity.md.
inventory:
	$(PYTHON) python/inventory.py

# S0: write results/data_checks.md (measured dataset properties the docs cite).
checks:
	$(PYTHON) python/data_checks.py

# S1: OCV and 2RC tables from the C/20 and HPPC files, then the US06 open-loop check.
# Writes results/params.csv, fit_levels.csv, ocv_correction.csv, params.md, model_fit.md, plots/s1/ and the C tables in c/.
fit:
	$(PYTHON) python/fit_all.py

# S6: the 3RC fit on the same HPPC files and OCV, and the open-loop check of both models on US06 (needs make fit).
# Writes results/fit_levels_3rc.csv, params_3rc.csv, model_fit_3rc.md and plots/s6/params_3rc.png.
fit-3rc:
	$(PYTHON) python/fit_3rc.py

# S6: the second 3RC fit, the middle branch alone on the whole HPPC pulse train (docs/decisions.md 1.26; needs make fit).
# Writes results/fit_levels_3rc_rest.csv, params_3rc_rest.csv, model_fit_3rc_rest.md and plots/s6/params_3rc_rest.png.
fit-3rc-rest:
	$(PYTHON) python/fit_3rc_rest.py

# S7: R1 over current, the 2RC-I model (docs/decisions.md 1.28; needs make fit).
# Writes results/fit_pulses_r1i.csv, r1_current.csv, model_fit_r1i.md and plots/s7/r1_current.png.
fit-r1i:
	$(PYTHON) python/fit_r1_current.py

# S7: experiments 1 to 4 on the 2RC-I model and the adoption verdict (docs/decisions.md 1.29; needs ekf and fit-r1i).
# Writes results/ekf_results_r1i.csv, model_compare_r1i.md and plots/s7/model_compare_r1i.png; traces in results/runs/r1i/.
ekf-r1i:
	$(PYTHON) python/compare_r1i.py

# S8 step A: experiments 1 to 4 on the 2RC-Id model, the guards and the test for step B (docs/decisions.md 1.32, 1.33;
# needs ekf and ekf-r1i). Writes results/ekf_results_r1d.csv, model_compare_r1d.md and plots/s8/model_compare_r1d.png;
# traces in results/runs/r1d/.
ekf-r1d:
	$(PYTHON) python/compare_r1d.py

# S8 step B: the charge-side R1 of the 2RC-Ic model on the HPPC charge pulses (docs/decisions.md 1.35; needs fit and
# fit-r1i). Writes results/fit_pulses_r1c.csv, r1_charge.csv, model_fit_r1c.md and plots/s8/r1_charge.png.
fit-r1c:
	$(PYTHON) python/fit_r1_charge.py

# S8 step B: experiments 1 to 4 on the 2RC-Ic model and the guards of 1.32 (docs/decisions.md 1.35; needs ekf, ekf-r1i,
# ekf-r1d and fit-r1c). Writes results/ekf_results_r1c.csv, model_compare_r1c.md and plots/s8/model_compare_r1c.png;
# traces in results/runs/r1c/.
ekf-r1c:
	$(PYTHON) python/compare_r1c.py

# S8 step C: the low-current R1 of the 2RC-Il model, scaled by factors fitted on the PausCycl files (docs/decisions.md
# 1.37; needs fit and fit-r1i). Writes results/r1_low.csv and model_fit_r1l.md.
fit-r1l:
	$(PYTHON) python/fit_r1_low.py

# S8 step C: experiments 1 to 4 on the 2RC-Il model and the guards of 1.32 (docs/decisions.md 1.37; needs ekf, ekf-r1i
# and fit-r1l). Writes results/ekf_results_r1l.csv, model_compare_r1l.md and plots/s8/model_compare_r1l.png; traces in
# results/runs/r1l/.
ekf-r1l:
	$(PYTHON) python/compare_r1l.py

# S9: fit 3RC-D on the Mix runs and score open loop (needs fit and fit-r1i).
fit-3rcd:
	$(PYTHON) python/fit_3rcd.py

# S9: compare the frozen EKF on the two splits after the S1 gate (needs ekf, ekf-r1i and fit-3rcd).
ekf-3rcd:
	$(PYTHON) python/compare_3rcd.py

# S10: fit and evaluate against frozen 2RC-I. Diagnosis is separate (decisions 1.44 and 1.47).
accuracy:
	$(MAKE) fit-3rcd0
	$(MAKE) ekf-3rcd0
	$(MAKE) diagnose-accuracy

diagnose-accuracy:
	$(PYTHON) python/diagnose_accuracy.py

fit-3rcd0:
	$(PYTHON) python/fit_3rcd0.py

ekf-3rcd0:
	$(PYTHON) python/compare_3rcd0.py

# S11 A: calibrate once on 40 Mix runs; search is outside all, chosen config is committed.
tune-3rcd0:
	$(PYTHON) python/tune_3rcd0.py

# S11 A: Python reference experiments, eight guards and wrong-start diagnostics.
ekf-3rcd0n:
	$(PYTHON) python/compare_3rcd0n.py

# S11 B: the regen rows at the 4.2 V limit, read from the stored traces of every model (decision 1.48).
diagnose-regen:
	$(PYTHON) python/diagnose_regen.py

# S12 step A: history before each run, the 189 wrong-start cases and the branch prior alone on the Mix runs
# (decision 1.56). Needs ekf-3rcd0 (results/runs/3rcd0/ and ekf_results_3rcd0.csv); builds the native evaluator of
# decision 1.50 (c/tools/ekf_tuning.c, with cc) and runs the prior values through it. Writes results/start_cases.md,
# start_cases.csv and plots/s12/start_cases.png.
diagnose-starts:
	$(PYTHON) python/diagnose_starts.py

# S12 step B: the omitted Jacobian terms of the 3RC-D0 filter and the three variants on the Mix runs (decision 1.56).
# Needs the ekf-3rcd0 traces (results/runs/3rcd0/) and results/accuracy_jacobian.csv of diagnose-accuracy. Writes
# results/jacobian_3rcd0.md, jacobian_3rcd0.csv and plots/s12/jacobian_3rcd0.png.
diagnose-jacobian:
	$(PYTHON) python/diagnose_jacobian.py

# S11 close (decision 1.54): regenerate the 3RC-D0 C tables and test vectors, build the float and the double
# library with -DEKF_USE_3RCD0=ON and run the unit tests in both.
c-3rcd0:
	$(PYTHON) python/export_3rcd0.py
	cmake -S c -B c/build/3rcd0-float -DEKF_USE_3RCD0=ON -DEKF_USE_DOUBLE=OFF
	cmake --build c/build/3rcd0-float
	ctest --test-dir c/build/3rcd0-float --output-on-failure
	cmake -S c -B c/build/3rcd0-double -DEKF_USE_3RCD0=ON -DEKF_USE_DOUBLE=ON
	cmake --build c/build/3rcd0-double
	ctest --test-dir c/build/3rcd0-double --output-on-failure

# S11 close: the 3RC-D0 C build against the Python traces, six experiments on all 63 runs (needs make ekf-3rcd0).
# Writes results/equivalence_3rcd0.md and .csv; exits 1 when a build reaches its threshold.
equiv-3rcd0:
	$(PYTHON) python/compare_c_3rcd0.py

# S11 close: Cortex-M4 sections, sizeof(ekf_t) and static stack frames of the 3RC-D0 build (needs arm-none-eabi-gcc).
arm-3rcd0:
	$(PYTHON) python/arm_footprint.py --model 3rcd0

# S2: tune the EKF noise settings on the tuning cycle and freeze them (not part of "all": the frozen values are committed).
# Writes results/tuning.md, results/ekf_config.json and section 1.15 of docs/decisions.md.
tune:
	$(PYTHON) python/tune.py

# S2: the four experiments on the 62 evaluation runs and the tuning cycle, with the frozen noise settings (results/ekf_config.json).
# Writes results/ekf_results.csv, ekf_summary.md, plots/s2/ and, git-ignored, results/runs/ (per-run traces, reused when still newer than the code).
ekf:
	$(PYTHON) python/run_all.py

# S3: configure, build and test the C library, its unit tests and the fixture equivalence in the float and double builds.
c:
	cmake -S c -B c/build/float -DEKF_USE_DOUBLE=OFF
	cmake --build c/build/float
	ctest --test-dir c/build/float --output-on-failure
	cmake -S c -B c/build/double -DEKF_USE_DOUBLE=ON
	cmake --build c/build/double
	ctest --test-dir c/build/double --output-on-failure

# S3: the C filter against the Python one on every evaluation run, in both builds (needs data/raw/ and make ekf).
# Writes results/equivalence.md and results/plots/s3/; the C inputs go to results/runs/c_inputs/ (git-ignored).
equiv:
	$(PYTHON) python/compare_c.py

# S3: cross-compile the library for a Cortex-M4 (c/cmake/arm-none-eabi.cmake) and check it uses no double-precision helper.
# Writes results/c_footprint.md (.text/.data/.bss per library object, sizeof(ekf_t), the symbol check); fails on a helper.
arm:
	$(PYTHON) python/arm_footprint.py

# S5: experiment 1 with the capacity at 0.95 and 1.05 Q_ref, and at 1 Hz (every 10th row), on every evaluation run (needs make ekf).
# Writes results/sensitivity.csv, results/sensitivity.md and results/plots/s5/sensitivity_*.png.
sensitivity:
	$(PYTHON) python/sensitivity.py

# S5: the Octave filter (octave/) against the Python one on every evaluation run (needs GNU Octave on PATH and make ekf).
# Writes results/equivalence_octave.md and results/plots/s5/equivalence_octave_25degC.png.
octave:
	$(PYTHON) python/compare_octave.py

# S4: copy the results tables from results/*.md into README.md and docs/results.md between their marker comments.
readme:
	$(PYTHON) python/update_readme.py

# S4: fail if README.md or docs/results.md is out of sync with results/*.md (the check CI runs).
readme-check:
	$(PYTHON) python/update_readme.py --check
