# Reproduce the results from the raw data. Stages and targets are described in the spec.
# Later stages add ekf, c, equiv and readme targets and extend "all".

PYTHON := .venv/bin/python

.PHONY: all data inventory checks fit

all: data inventory checks fit

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
# Writes results/params.csv, fit_levels.csv, params.md, model_fit.md, plots/s1/ and the C tables in c/.
fit:
	$(PYTHON) python/fit_all.py
