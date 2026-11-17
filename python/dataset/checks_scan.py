"""One pass over every raw file for results/s0/data_checks.md: the facts that need every file, drive and Charge files
in detail."""

import math

import numpy as np

from dataset.checks_rules import CC_CURRENT_A, CV_PHASE_V, NUMERIC_FIELDS, WINDOW_SOC, counter_resets, rows_used
from dataset.common import DRIVE_TYPES, FLOW_CURRENT_A, longest_run, runs_of
from ekfsoc import rawio
from ekfsoc.hppc import LOW_LIMIT_V
from ekfsoc.loader import GAP_S


def scan_file(record, data, q_ref):
    """Fill record with the facts that sections 1-9, 14 and 16-17 need from this file.

    Generic facts for every file (duplicates, NaN and 0 V rows, TimeStamps,
    counter), plus drive-file facts (steps, run length, reference SoC,
    coulomb counter, first row, temperatures) and Charge-file facts.
    Only small arrays are kept, so all 206 files fit in memory.
    """
    time_s = data["Time"]
    voltage = data["Voltage"]
    current = data["Current"]
    ah = data["Ah"]
    temp = data["Battery_Temp_degC"]
    n_rows = len(time_s)
    steps = np.diff(time_s)

    record["n_rows"] = n_rows
    record["start"] = rawio.parse_timestamp(data["TimeStamp"][0])
    record["end"] = rawio.parse_timestamp(data["TimeStamp"][-1])
    record["first_v"] = float(voltage[0])
    record["first_i"] = float(current[0])
    valid = np.where((voltage > 0.0) & ~np.isnan(voltage) & ~np.isnan(current))[0]
    record["last_valid_v"] = float(voltage[valid[-1]]) if len(valid) else float("nan")
    record["last_valid_i"] = float(current[valid[-1]]) if len(valid) else float("nan")
    record["has_current"] = bool(np.nanmax(np.abs(current)) > FLOW_CURRENT_A)

    # Duplicate Time rows: row k repeats the Time of row k-1.
    duplicate_rows = np.where(steps == 0.0)[0] + 1
    record["n_duplicates"] = len(duplicate_rows)
    pairs = []   # (row, |dI|, |dV|, at a step end) for duplicate pairs whose Current or Voltage differ
    n_nan_pairs = 0
    for k in duplicate_rows:
        values = (current[k], current[k - 1], voltage[k], voltage[k - 1])
        if any(math.isnan(v) for v in values):
            n_nan_pairs += 1
            continue
        if current[k] != current[k - 1] or voltage[k] != voltage[k - 1]:
            next_i = current[k + 1] if k + 1 < n_rows else float("nan")
            at_step_end = abs(current[k]) >= FLOW_CURRENT_A and abs(next_i) < FLOW_CURRENT_A
            pairs.append((int(k), abs(current[k] - current[k - 1]), abs(voltage[k] - voltage[k - 1]), at_step_end))
    record["differing_pairs"] = pairs
    record["n_nan_pairs"] = n_nan_pairs
    same_time = np.concatenate(([False], steps == 0.0))
    longest = longest_run(same_time)
    record["longest_same_time_rows"] = (longest[1] - longest[0] + 2) if longest else 1   # rows sharing one Time
    record["ends_on_duplicate"] = n_rows >= 2 and time_s[-1] == time_s[-2]
    record["ends_on_duplicate_zero"] = record["ends_on_duplicate"] and current[-1] == 0.0 and current[-2] == 0.0

    # Rows with Voltage <= 0 and rows with NaN in any numeric field.
    record["zero_voltage_rows"] = [(int(k), float(voltage[k])) for k in np.where(voltage <= 0.0)[0]]
    any_nan = np.zeros(n_rows, dtype=bool)
    for name in NUMERIC_FIELDS:
        any_nan |= np.isnan(data[name])
    record["nan_rows"] = [(int(k), [name for name in NUMERIC_FIELDS if math.isnan(data[name][k])])
                          for k in np.where(any_nan)[0]]

    # Ah counter: first row and resets to 0 inside the file.
    record["ah_first"] = float(ah[0])
    record["ah_last"] = float(ah[-1])
    record["reset_rows"] = counter_resets(time_s, current, ah)
    discharging = current < -FLOW_CURRENT_A
    record["median_current_discharge"] = float(np.median(current[discharging])) if np.any(discharging) else float("nan")

    if record["test_type"] in DRIVE_TYPES:
        scan_drive_file(record, data, steps, q_ref)
        record["temp_all"] = temp[~np.isnan(temp)]
    if record["test_type"] == "pauscycl":
        rows = rows_used(record, data)
        record["used_duration_s"] = float(time_s[rows[-1]] - time_s[rows[0]])
    if record["test_type"] == "charge":
        scan_charge_file(record, data)


def scan_drive_file(record, data, steps, q_ref):
    """Drive-file facts: steps, long steps, run length, reference SoC, coulomb counter, temperatures.

    Reference SoC (docs/decisions.md): SoC_ref = SoC0 - Ah_removed / Q_ref,
    with Ah_removed = -(Ah - Ah at the first row used) on the cycler's
    counter, and SoC0 = 1 - (charge the counter removed between row 0 and the
    first row used) / Q_ref.
    Coulomb-counting baseline (docs/decisions.md): the project-sign current
    of the previous kept row held over the actual dt (the exact zero-order
    hold of the process model), with no special code for long steps.
    """
    time_s = data["Time"]
    current = data["Current"]
    ah = data["Ah"]
    voltage = data["Voltage"]
    temp = data["Battery_Temp_degC"]

    record["steps"] = steps
    record["stored_duration_s"] = float(time_s[-1] - time_s[0])
    long_rows = np.where(steps > GAP_S)[0] + 1        # row k ends a step longer than 1 s
    record["long_steps"] = [(int(k), float(steps[k - 1])) for k in long_rows]

    rows = rows_used(record, data)
    t = time_s[rows]
    i_project = -current[rows]                       # positive = discharge
    dt = np.diff(t)

    removed_before = -(ah[rows[0]] - ah[0])
    soc0 = 1.0 - removed_before / q_ref
    ah_removed = -(ah[rows] - ah[rows[0]])
    soc_ref = soc0 - ah_removed / q_ref
    ah_cc = np.concatenate(([0.0], np.cumsum(i_project[:-1] * dt))) / 3600.0
    soc_cc = soc0 - ah_cc / q_ref
    cc_minus_ref_pp = 100.0 * (soc_cc - soc_ref)
    in_window = np.where(soc_ref >= WINDOW_SOC)[0]

    record["rows_used"] = len(rows)
    record["used_duration_s"] = float(t[-1] - t[0])
    record["first_row_used"] = int(rows[0])
    record["first_used_v"] = float(voltage[rows[0]])
    record["first_used_i"] = float(current[rows[0]])
    record["first_used_ah"] = float(ah[rows[0]])
    record["soc0"] = soc0
    record["soc_end"] = float(soc_ref[-1])
    record["soc_min"] = float(np.min(soc_ref))
    record["window_s"] = float(t[in_window[-1]] - t[0]) if len(in_window) else 0.0
    record["cc_minus_ref_end_pp"] = float(cc_minus_ref_pp[-1])
    record["cc_minus_ref_max_pp"] = float(np.max(np.abs(cc_minus_ref_pp)))
    record["used_i_max"] = float(np.max(current[rows]))      # largest charging (regen) current, cycler sign
    record["used_i_min"] = float(np.min(current[rows]))      # largest discharge current, cycler sign
    record["temp_used"] = temp[rows]

    # Steps longer than 1 s between kept rows, with the charge the held current carries across them.
    used_long = []
    for j in np.where(dt > GAP_S)[0]:
        before, after = rows[j], rows[j + 1]
        held_ah = i_project[j] * dt[j] / 3600.0                     # zero-order hold, removed charge
        counter_ah = -(ah[after] - ah[before])                       # what the counter removed
        used_long.append({
            "row": int(after), "time_before": float(t[j]), "dt": float(dt[j]),
            "i_before": float(current[before]), "i_after": float(current[after]),
            "held_mah": 1000.0 * held_ah, "counter_mah": 1000.0 * counter_ah,
            "error_pp": 100.0 * (held_ah - counter_ah) / q_ref,
        })
    record["used_long_steps"] = used_long

    # Samples at the 2.8 V cutoff (extra check 17).
    at_limit = np.where((voltage > 0.0) & (voltage <= LOW_LIMIT_V))[0]
    record["low_limit_rows"] = len(at_limit)
    record["low_limit_first_s"] = float(time_s[at_limit[0]]) if len(at_limit) else float("nan")


def scan_charge_file(record, data):
    """Charge-file facts: CC phase, CV voltage, cutoff current, rests, temperatures (section 9)."""
    time_s = data["Time"]
    current = data["Current"]
    voltage = data["Voltage"]
    ah = data["Ah"]
    temp = data["Battery_Temp_degC"]

    charging = np.where(current > FLOW_CURRENT_A)[0]
    record["charge_runs"] = len(runs_of(current > FLOW_CURRENT_A))
    if len(charging) == 0:
        record["charge"] = None
        return
    first = charging[0]
    last_positive = np.where(current > 0.0)[0][-1]
    valid = np.where(voltage > 0.0)[0]
    cc = current > CC_CURRENT_A
    cv = (current > 0.0) & (voltage >= CV_PHASE_V)
    record["charge"] = {
        "peak_a": float(np.max(current)),
        "has_cc": bool(np.any(cc)),
        "cc_median_a": float(np.median(current[cc])) if np.any(cc) else float("nan"),
        "cv_median_v": float(np.median(voltage[cv])) if np.any(cv) else float("nan"),
        "v_max": float(np.max(voltage)),
        "last_current_a": float(current[last_positive]),
        "rest_before_s": float(time_s[first] - time_s[0]),
        "rest_after_s": float(time_s[valid[-1]] - time_s[last_positive]),
        "temp_at_start": float(temp[first]),
        "temp_min": float(np.min(temp[charging])),
        "temp_max": float(np.max(temp[charging])),
        "ah_charged": float(np.max(ah[first:]) - ah[first - 1]) if first > 0 else float(np.max(ah) - ah[0]),
        "charge_s": float(time_s[last_positive] - time_s[first]),
    }
