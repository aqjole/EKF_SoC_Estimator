"""What the two S0 scripts share: the folder temperatures, the drive-cycle types, three thresholds and the number
formatting and run helpers of their reports."""

import math

import numpy as np

from ekfsoc.constants import FOLDER_TEMP


# Folder name -> chamber temperature it stands for (degC); the temperature grid nodes.
FOLDER_TEMPS_DEGC = {folder: float(temp) for folder, temp in FOLDER_TEMP.items()}
DRIVE_TYPES = ("udds", "hwfet", "la92", "us06",
               "mixed1", "mixed2", "mixed3", "mixed4", "mixed5", "mixed6", "mixed7", "mixed8")


# Thresholds both reports use; each report's text states the ones that shape a result.
FLOW_CURRENT_A = 0.05        # |I| above this is a discharge (I < 0) or a charge (I > 0); below it is a rest
FULL_VOLTAGE_V = 4.15        # full-charge rule: a rest above this voltage is a full charge


def is_number(value):
    """True for a finite float or int (False for None and NaN)."""
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def fmt(value, digits):
    """Format a number with a fixed number of decimals, or 'n/a' for None and NaN."""
    if not is_number(value):
        return "n/a"
    text = f"{value:.{digits}f}"
    if text.startswith("-") and float(text) == 0.0:
        text = text[1:]          # show 0.000, not -0.000
    return text


def runs_of(mask):
    """(first, last) row pairs of every run of True values in a boolean array, in order."""
    padded = np.concatenate(([False], mask, [False])).astype(int)
    edges = np.diff(padded)
    return list(zip(np.where(edges == 1)[0], np.where(edges == -1)[0] - 1))


def longest_run(mask):
    """(first, last) rows of the longest run of True values, or None."""
    runs = runs_of(mask)
    if not runs:
        return None
    return max(runs, key=lambda run: run[1] - run[0])
