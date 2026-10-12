"""Project-wide constants: the reference capacity, the two table axes and the data folders.

Every stage imports these instead of retyping them, so the loader, the OCV and 2RC fit, the EKF
and the C export all use one Q_ref and the same grids.
"""

from pathlib import Path

import numpy as np


# Repository root, found from this file (python/ekfsoc/constants.py), so a script
# gives the same answer whatever directory it is started from.
REPO_DIR = Path(__file__).resolve().parents[2]

# Raw .mat files, one sub-folder per set temperature (data/raw/<folder>/*.mat).
# Absolute, because it is built from the repo root.
RAW_DIR = REPO_DIR / "data" / "raw"

# Q_ref in Ah: the C/20 discharge capacity at 25 degC, counted from the counter's zero at the
# step start in 25degC/549_C20DisCh (results/capacity.md; docs/model.md C4). One value at every temperature.
Q_REF_AH = 2.7807

# SoC axis of every table: 0 to 1 in 1 % steps, 101 points (docs/model.md C15).
SOC_GRID = np.linspace(0.0, 1.0, 101)

# Temperature axis of every table in degC, in table row order (docs/model.md C15).
T_GRID_DEGC = [40, 25, 10, 0, -10, -20]

# Raw data folder name -> nominal (set) temperature in degC, the T_GRID_DEGC nodes.
FOLDER_TEMP = {
    "40degC": 40,
    "25degC": 25,
    "10degC": 10,
    "0degC": 0,
    "n10degC": -10,
    "n20degC": -20,
}
