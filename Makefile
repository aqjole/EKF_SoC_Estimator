# Reproduce the results from the raw data. Stages and targets are described in the spec.
# Later stages add fit, ekf, c, equiv and readme targets and extend "all".

PYTHON := .venv/bin/python

.PHONY: all data inventory checks

all: data inventory checks

# Fetch the LG 18650HG2 .mat files into data/raw/ and verify their sha256.
data:
	bash data/download.sh

# S0: write results/data_inventory.md and results/capacity.md.
inventory:
	$(PYTHON) python/inventory.py

# S0: write results/data_checks.md (measured dataset properties the docs cite).
checks:
	$(PYTHON) python/data_checks.py
