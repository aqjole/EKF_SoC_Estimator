# Reproduce the results from the raw data. Stages and targets are described in the spec.
# Later stages add c, equiv and readme targets and extend "all".

PYTHON := .venv/bin/python

.PHONY: all data inventory checks fit tune ekf

all: data inventory checks fit ekf

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

# S2: tune the EKF noise settings on the tuning cycle and freeze them (not part of "all": the frozen values are committed).
# Writes results/tuning.md, results/ekf_config.json and section 1.15 of docs/decisions.md.
tune:
	$(PYTHON) python/tune.py

# S2: the four experiments on the 62 evaluation runs and the tuning cycle, with the frozen noise settings (results/ekf_config.json).
# Writes results/ekf_results.csv, ekf_summary.md, plots/s2/ and, git-ignored, results/runs/ (per-run traces, reused when still newer than the code).
ekf:
	$(PYTHON) python/run_all.py
