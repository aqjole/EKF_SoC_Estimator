"""One raw file described for the inventory: time base, ranges, flags and, for a capacity test, its main discharge."""

import datetime

import numpy as np

from dataset.common import DRIVE_TYPES, FLOW_CURRENT_A, FOLDER_TEMPS_DEGC, is_number, longest_run
from dataset.inventory_rules import (AH_FLAG_AH, CAPACITY_TYPES, GAP_REPORT_S, NAME_FLAG_S, PAUSE_FLAG_S, REGEN_TYPES,
                                     REPEAT_FLAG_ROWS, REST_CURRENT_A, TEMP_FLAG_DEGC, first_finite,
                                     hppc_discharge_levels, integral_of_current_ah, last_finite,
                                     longest_repeated_time_run, nan_max, nan_median, nan_min, seconds_since_zero)
from ekfsoc import rawio


def capacity_from_discharge(time_s, voltage, current, ah, temp):
    """Measure the main constant-current discharge of a capacity test.

    The discharge is the longest run of samples with current below
    -FLOW_CURRENT_A. Ah removed = Ah counter at the start of that discharge
    minus Ah counter at its last sample (cycler sign, so the result is
    positive).

    The counter value at the start is taken from the rest sample just before
    the discharge when there is one. Otherwise the file opens mid-discharge:
    its first sample is one logging interval into the step (the C/20 and 2C
    files show this: going back one interval from the first sample lands on
    0.0000 Ah). The start is then extrapolated back by that one interval at
    the first sample's current.

    Also returns the C/20-style charge that may follow in the same file:
    the highest Ah counter after the discharge minus the counter at its end.
    """
    discharging = current < -FLOW_CURRENT_A
    run = longest_run(discharging)
    if run is None:
        return None
    first, last = run

    if first > 0 and abs(current[first - 1]) < REST_CURRENT_A:
        ah_start = float(ah[first - 1])
        start_note = "counter read at the rest sample before the discharge"
    else:
        interval_s = float(time_s[first + 1] - time_s[first]) if first + 1 < len(time_s) else 0.0
        first_step_ah = -current[first] * interval_s / 3600.0      # positive: charge removed before the first sample
        ah_start = float(ah[first] + first_step_ah)
        start_note = (f"file opens mid-discharge; start extrapolated back one {interval_s:.0f} s "
                      f"interval (+{first_step_ah:.4f} Ah)")

    ah_end = float(ah[last])
    later_ah = ah[last + 1:]
    later_finite = later_ah[~np.isnan(later_ah)]
    charge_after_ah = float(np.max(later_finite) - ah_end) if len(later_finite) else float("nan")

    return {
        "ah_start": ah_start,
        "ah_removed": ah_start - ah_end,
        "final_voltage": float(voltage[last]),
        "mean_current_a": float(-np.mean(current[first:last + 1])),   # positive = discharge
        "median_current_a": float(-np.median(current[first:last + 1])),
        "temp_start": float(temp[first]),
        "temp_min": nan_min(temp[first:last + 1]),
        "temp_max": nan_max(temp[first:last + 1]),
        "start_note": start_note,
        "charge_after_ah": charge_after_ah,
    }


def summarize_file(folder, path):
    """Load one file and compute everything the inventory reports about it.

    Returns a dict. The keys "abs_time_s", "voltage" and "current" hold the
    per-sample arrays that full_charge_start(), check_previous_file() and
    check_inside_earlier() need; main() drops them when the folder is done.
    """
    name_info = rawio.parse_filename(path.name)
    data, details = rawio.load_mat_details(path)

    time_s = data["Time"]
    voltage = data["Voltage"]
    current = data["Current"]          # cycler sign: negative = discharge
    ah = data["Ah"]                    # cycler sign: decreases while discharging
    temp = data["Battery_Temp_degC"]
    stamps = data["TimeStamp"]
    n_samples = len(time_s)

    start = rawio.parse_timestamp(stamps[0])
    end = rawio.parse_timestamp(stamps[-1])

    if name_info is None:
        test_type = "other"
        test_number = None
        descriptor_temp = None
        name_start = None
        separator_ok = True
    else:
        test_type = name_info["test_type"]
        test_number = name_info["test_number"]
        descriptor_temp = name_info["descriptor_temp_degc"]
        separator_ok = name_info["separator_ok"]
        name_start = None
        if name_info["date"] is not None:
            name_start = datetime.datetime.combine(name_info["date"], name_info["time"])

    # Time base.
    steps = np.diff(time_s)
    time_span_s = nan_max(time_s) - nan_min(time_s)
    stamp_span_s = (end - start).total_seconds()
    median_dt = nan_median(steps)
    max_gap = nan_max(steps)
    n_gaps_over_limit = int(np.sum(steps > GAP_REPORT_S))
    n_duplicates = int(np.sum(steps == 0))
    n_backward = int(np.sum(steps < 0))
    longest_repeat = longest_repeated_time_run(time_s)

    # Rows with a NaN in any numeric field.
    nan_row = np.zeros(n_samples, dtype=bool)
    for name, values in data.items():
        if name != "TimeStamp":
            nan_row |= np.isnan(values)
    n_nan_rows = int(np.sum(nan_row))

    # Rows with Voltage <= 0: the cycler writes 0 V on the last row of some files (end-of-test sentinel).
    zero_voltage_rows = np.where(voltage <= 0.0)[0]
    zero_voltage_last_row_only = len(zero_voltage_rows) == 1 and zero_voltage_rows[0] == n_samples - 1

    # Field names against the expected eight.
    field_names = list(data.keys())
    missing_fields = [name for name in rawio.EXPECTED_FIELDS if name not in field_names]
    extra_fields = [name for name in field_names if name not in rawio.EXPECTED_FIELDS]
    if not missing_fields and not extra_fields:
        fields_text = "8 expected"
        if tuple(field_names) != rawio.EXPECTED_FIELDS:
            fields_text = "8 expected, other order"
    else:
        parts = []
        if missing_fields:
            parts.append("missing " + ", ".join(missing_fields))
        if extra_fields:
            parts.append("extra " + ", ".join(extra_fields))
        fields_text = "; ".join(parts)

    # Current flow.
    discharging = current < -FLOW_CURRENT_A
    charging = current > FLOW_CURRENT_A
    regen = None
    if test_type in REGEN_TYPES:
        regen = {
            "present": bool(np.any(charging)),
            "percent": 100.0 * float(np.sum(charging)) / n_samples,
            "max_a": nan_max(current),
        }
    # Cell temperature at the first discharging sample: the soak temperature before any self-heating.
    discharge_start_temp = float(temp[np.argmax(discharging)]) if np.any(discharging) else float("nan")

    # Charge files: battery temperature when the charge current starts (readme: 22 degC or more).
    charge_start_temp = float("nan")
    if test_type == "charge" and np.any(charging):
        charge_start_temp = float(temp[np.argmax(charging)])

    ah_first = first_finite(ah)
    ah_end = last_finite(ah)
    ah_integral = integral_of_current_ah(time_s, current)
    reset_on_last_row = n_samples > 1 and ah[-1] == 0.0 and ah[-2] != 0.0

    capacity = None
    if test_type in CAPACITY_TYPES:
        capacity = capacity_from_discharge(time_s, voltage, current, ah, temp)

    pulse_levels = None
    if test_type == "hppc":
        pulse_levels = hppc_discharge_levels(current)

    # Flags: anything a later stage must know about this file.
    flags = []
    if name_info is None:
        flags.append("file name does not follow the readme pattern")
    if not separator_ok:
        flags.append("no '_' between date and time in the name")
    if name_start is None and name_info is not None:
        flags.append("date in the name is not a valid MM-DD-YY date")
    if name_start is not None and abs((start - name_start).total_seconds()) > NAME_FLAG_S:
        flags.append(f"name gives {name_start:%Y-%m-%d %H:%M} but first TimeStamp is {start:%Y-%m-%d %H:%M:%S}")
    folder_temp = FOLDER_TEMPS_DEGC.get(folder)
    if descriptor_temp is not None and folder_temp is not None and descriptor_temp != folder_temp:
        flags.append(f"descriptor says {descriptor_temp:.0f} degC, folder is {folder_temp:.0f} degC")
    if descriptor_temp is None and test_type != "charge":
        flags.append("descriptor has no temperature")
    odd_types = [f"{name} {dtype}" for name, dtype in details["dtypes"].items()
                 if name not in ("TimeStamp", "Wh") and dtype != "float64"]
    if odd_types:
        flags.append("stored as " + ", ".join(odd_types))
    no_current = nan_max(np.abs(current)) == 0.0
    if no_current:
        flags.append("no current: every Current sample is 0 A")
    if n_nan_rows:
        flags.append(f"{n_nan_rows} rows with NaN")
    if zero_voltage_last_row_only:
        flags.append("Voltage <= 0 V on the last row (end-of-test sentinel; drop it)")
    elif len(zero_voltage_rows):
        flags.append(f"Voltage <= 0 V on {len(zero_voltage_rows)} rows")
    if n_backward:
        flags.append(f"{n_backward} backward Time steps")
    if longest_repeat > REPEAT_FLAG_ROWS:
        flags.append(f"{longest_repeat} consecutive rows share one Time value (logger stall)")
    if stamp_span_s - time_span_s > PAUSE_FLAG_S:
        flags.append(f"TimeStamp span is {(stamp_span_s - time_span_s) / 3600:.2f} h longer than Time span "
                     f"(pause that Time does not show)")
    if folder_temp is not None and is_number(discharge_start_temp) \
            and abs(discharge_start_temp - folder_temp) > TEMP_FLAG_DEGC:
        flags.append(f"cell at {discharge_start_temp:.1f} degC when the discharge starts, "
                     f"folder is {folder_temp:.0f} degC")
    if reset_on_last_row:
        flags.append(f"Ah reset to 0 on the last row (max before: {nan_max(ah):.4f} Ah)")
    if test_type in DRIVE_TYPES and is_number(ah_end) \
            and abs(ah_integral - (ah_end - ah_first)) > AH_FLAG_AH:
        flags.append(f"integral of I dt ({ah_integral:.4f} Ah) differs from the Ah counter "
                     f"({ah_end - ah_first:.4f} Ah)")

    return {
        "folder": folder,
        "file": path.name,
        "reader": details["reader"],
        "dtypes": details["dtypes"],
        "test_type": test_type,
        "test_number": test_number,
        "no_current": no_current,
        "descriptor_temp": descriptor_temp,
        "name_start": name_start,
        "start": start,
        "end": end,
        "duration_h": time_span_s / 3600.0,
        "n_samples": n_samples,
        "median_dt": median_dt,
        "max_gap": max_gap,
        "n_gaps_over_limit": n_gaps_over_limit,
        "n_duplicates": n_duplicates,
        "fields_text": fields_text,
        "v_min": nan_min(voltage), "v_max": nan_max(voltage),
        "i_min": nan_min(current), "i_max": nan_max(current),
        "t_min": nan_min(temp), "t_max": nan_max(temp),
        "ah_first": ah_first,
        "ah_end": ah_end,
        "ah_integral": ah_integral,
        "regen": regen,
        "discharge_start_temp": discharge_start_temp,
        "charge_start_temp": charge_start_temp,
        "wh_values": [float(x) for x in np.unique(data["Wh"][~np.isnan(data["Wh"])])],
        "capacity": capacity,
        "pulse_levels": pulse_levels,
        "n_zero_voltage_rows": len(zero_voltage_rows),
        "zero_voltage_last_row_only": zero_voltage_last_row_only,
        "flags": flags,
        "steps_s": steps if test_type in DRIVE_TYPES else None,
        # Filled by check_previous_file() and check_inside_earlier().
        "overlap": None,              # (previous file, minutes) when this file overlaps the previous one
        "inside_earlier": None,       # (earlier file, its samples inside this file's span) if this file lies inside it
        "unlogged_discharge": None,   # text, when the cell lost charge between the previous file and this one
        # Per-sample arrays for full_charge_start(), check_previous_file() and check_inside_earlier();
        # dropped after the folder is done.
        "abs_time_s": seconds_since_zero(start) + (time_s - time_s[0]),
        "voltage": voltage,
        "current": current,
    }
