"""The test types, thresholds and small helpers of results/s0/data_inventory.md and results/s0/capacity.md."""

import datetime
import math

import numpy as np

from dataset.common import DRIVE_TYPES, fmt


REGEN_TYPES = DRIVE_TYPES + ("pauscycl",)          # files where charging current means regen
CAPACITY_TYPES = ("c20", "dis_0p5c", "dis_2c", "cap_1c")


# Tests the readme lists for every temperature, with how many files of each to expect.
EXPECTED_TESTS = {"hppc": 1, "c20": 1, "dis_0p5c": 1, "dis_2c": 1, "cap_1c": 2}
EXPECTED_TESTS.update({drive_type: 1 for drive_type in DRIVE_TYPES})


# Thresholds. Each one is stated in the legend of the file it affects.
LINK_GAP_S = 300.0           # a rest in an earlier file counts only if it ends this close to the start
REST_CURRENT_A = 0.05        # |I| below this is a rest (50 mA, the charge cutoff current)
CV_REACHED_V = 4.19          # the charge before that rest must have reached the 4.2 V CV phase
GAP_REPORT_S = 1.0           # the spec: the S1 loader records time gaps longer than 1 s
TEMP_FLAG_DEGC = 5.0         # flag a file whose cell temperature when discharge starts is this far off the folder
PAUSE_FLAG_S = 60.0          # flag a file whose TimeStamp span exceeds its Time span by more than this
NAME_FLAG_S = 300.0          # flag a file whose name start differs from its first TimeStamp by more than this
REPEAT_FLAG_ROWS = 100       # flag a run of more than this many rows with the same Time value
AH_FLAG_AH = 0.01            # flag a drive cycle whose integral of I dt differs from its Ah counter by this much
OVERLAP_FLAG_S = 2.0         # flag a file that starts this long before the previous file ends (TimeStamp: ~1 s)
UNLOGGED_DROP_V = 0.3        # flag a file that opens at rest this far below the voltage the previous file ended at
PULSE_MIN_A = 2.0            # HPPC discharge pulses draw more than this (the moves between SoC levels draw less)
PULSE_MIN_SAMPLES = 100      # an HPPC pulse level must hold at least this many samples (10 s at 0.1 s logging)
RATE_FLAG = 0.02             # flag a folder whose C/20, 0.5C or 2C current differs from the other folders by 2 %
NOMINAL_1C_A = 3.0           # 1C current of the 3 Ah cell; used only to name C-rates
STOP_RULE_FRACTION = 0.95    # readme: drive cycles stop at 95 % of the 1C capacity
STOP_RULE_TOLERANCE = 0.001  # a drive cycle meets the stop rule if Ah removed / 1C is within 0.1 pp of 95 %
CAMPAIGN_ZERO = datetime.datetime(2018, 1, 1)   # origin for absolute times inside one folder


def fmt_pair(low, high, digits):
    """Format 'min / max' for a table cell."""
    return f"{fmt(low, digits)} / {fmt(high, digits)}"


def seconds_since_zero(moment):
    """Seconds from CAMPAIGN_ZERO to a datetime; used to put files of one folder on one time axis."""
    return (moment - CAMPAIGN_ZERO).total_seconds()


def last_finite(values):
    """Last value that is not NaN, or NaN if there is none."""
    for k in range(len(values) - 1, -1, -1):
        if not math.isnan(values[k]):
            return float(values[k])
    return float("nan")


def first_finite(values):
    """First value that is not NaN, or NaN if there is none."""
    for k in range(len(values)):
        if not math.isnan(values[k]):
            return float(values[k])
    return float("nan")


def nan_min(values):
    """Minimum ignoring NaN; NaN for an empty or all-NaN array."""
    finite = values[~np.isnan(values)]
    return float(np.min(finite)) if len(finite) else float("nan")


def nan_max(values):
    """Maximum ignoring NaN; NaN for an empty or all-NaN array."""
    finite = values[~np.isnan(values)]
    return float(np.max(finite)) if len(finite) else float("nan")


def nan_median(values):
    """Median ignoring NaN; NaN for an empty or all-NaN array."""
    finite = values[~np.isnan(values)]
    return float(np.median(finite)) if len(finite) else float("nan")


def integral_of_current_ah(time_s, current_a):
    """Trapezoid integral of current over time, in Ah (cycler sign).

    Steps with dt <= 0 or a NaN at either end are skipped, so duplicate rows
    and backward jumps add nothing. The result is an independent check of the
    cycler's Ah counter: same sign and size means current is in A, time in s,
    and Ah counts with the same sign as current.
    """
    total_as = 0.0
    for k in range(len(time_s) - 1):
        dt = time_s[k + 1] - time_s[k]
        i_left = current_a[k]
        i_right = current_a[k + 1]
        if dt > 0 and not math.isnan(i_left) and not math.isnan(i_right):
            total_as += 0.5 * (i_left + i_right) * dt
    return total_as / 3600.0


def longest_repeated_time_run(time_s):
    """Length of the longest run of consecutive rows that share one Time value (1 = no repeats)."""
    longest = 1
    run = 1
    for k in range(1, len(time_s)):
        if time_s[k] == time_s[k - 1]:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    return longest


def hppc_discharge_levels(current):
    """Discharge pulse levels of an HPPC file in A (cycler sign, so negative), smallest pulse first.

    Samples below -PULSE_MIN_A are rounded to 0.1 A. A level counts only if it
    holds at least PULSE_MIN_SAMPLES samples, so pulses cut short by the
    voltage limit do not add levels.
    """
    pulse_samples = np.round(current[current < -PULSE_MIN_A], 1)
    levels, counts = np.unique(pulse_samples, return_counts=True)
    kept = [float(level) for level, count in zip(levels, counts) if count >= PULSE_MIN_SAMPLES]
    return sorted(kept, reverse=True)   # e.g. -3.0, -6.0, -12.0, -18.0
