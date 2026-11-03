# Reproduce the results from the raw data. Stages and targets are described in the spec.

PYTHON := .venv/bin/python

.PHONY: all data inventory checks fit fit-3rc fit-3rc-rest fit-r1i ekf-r1i ekf-r1d tune ekf c equiv arm sensitivity octave readme readme-check

all: data inventory checks fit ekf c equiv arm sensitivity octave fit-3rc fit-3rc-rest fit-r1i ekf-r1i ekf-r1d readme

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

# S4: copy the results tables from results/*.md into README.md between its marker comments.
readme:
	$(PYTHON) python/update_readme.py

# S4: fail if README.md is out of sync with results/*.md (the check CI runs).
readme-check:
	$(PYTHON) python/update_readme.py --check
