"""S0 data inventory: walk data/raw/ and describe every file.

Writes two files:
- results/s0/data_inventory.md: one row per .mat file (time base, ranges, flags)
  plus a summary per temperature folder.
- results/s0/capacity.md: every capacity test in campaign order, the C/20 and 1C
  capacities per folder, and a check of the drive-cycle stop rule.

Run from the repo root:  .venv/bin/python python/inventory.py   (or: make inventory)

All values keep the cycler's sign (discharge current and discharged Ah are
negative), except where a column says "removed", which is positive. Every
number is measured from the files; nothing is copied from the readme.
"""

import datetime
import math
from pathlib import Path

import numpy as np

from ekfsoc import rawio


REPO_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_DIR / "data" / "raw"
RESULTS_DIR = REPO_DIR / "results"

# Folder name -> chamber temperature it stands for (degC).
FOLDER_TEMPS_DEGC = {
    "40degC": 40.0,
    "25degC": 25.0,
    "10degC": 10.0,
    "0degC": 0.0,
    "n10degC": -10.0,
    "n20degC": -20.0,
}

DRIVE_TYPES = ("udds", "hwfet", "la92", "us06",
               "mixed1", "mixed2", "mixed3", "mixed4", "mixed5", "mixed6", "mixed7", "mixed8")
REGEN_TYPES = DRIVE_TYPES + ("pauscycl",)          # files where charging current means regen
CAPACITY_TYPES = ("c20", "dis_0p5c", "dis_2c", "cap_1c")
# Tests the readme lists for every temperature, with how many files of each to expect.
EXPECTED_TESTS = {"hppc": 1, "c20": 1, "dis_0p5c": 1, "dis_2c": 1, "cap_1c": 2}
EXPECTED_TESTS.update({drive_type: 1 for drive_type in DRIVE_TYPES})

# Thresholds. Each one is stated in the legend of the file it affects.
REST_CURRENT_A = 0.05        # |I| below this is a rest (50 mA, the charge cutoff current)
FULL_VOLTAGE_V = 4.15        # a rest above this voltage counts as a full charge
CV_VOLTAGE_V = 4.19          # the charge before that rest must have reached the 4.2 V CV phase
LINK_GAP_S = 300.0           # a rest in an earlier file counts only if it ends this close to the start
FLOW_CURRENT_A = 0.05        # |I| above this is a discharge (I < 0) or a charge/regen (I > 0)
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


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def is_number(value):
    """True for a finite float or int (False for None and NaN)."""
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def fmt(value, digits):
    """Format a number with a fixed number of decimals, or 'n/a'."""
    if not is_number(value):
        return "n/a"
    text = f"{value:.{digits}f}"
    if text.startswith("-") and float(text) == 0.0:
        text = text[1:]          # show 0.0000, not -0.0000
    return text


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


def longest_run(mask):
    """(first, last) indices of the longest run of True values in a boolean array, or None."""
    best = None
    run_start = None
    for k in range(len(mask)):
        if mask[k]:
            if run_start is None:
                run_start = k
            if best is None or (k - run_start) > (best[1] - best[0]):
                best = (run_start, k)
        else:
            run_start = None
    return best


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


# ----------------------------------------------------------------------------
# Per-file analysis
# ----------------------------------------------------------------------------

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


def full_charge_start(record, folder_records):
    """Say whether a file starts from a full charge, and on what evidence.

    1. The first sample is above 4.15 V with |I| < 50 mA: the cell sits at its
       full-charge rest voltage when the file starts.
    2. Otherwise: the last sample logged before this file starts, in any other
       file of the same folder, is a rest above 4.15 V that ends at most 300 s
       before the start, and that file reached the 4.2 V CV phase (>= 4.19 V)
       before it. This covers files that open with current already flowing
       straight after a full charge (e.g. the C/20 test, Mixed4 and Mixed8).
    Absolute sample times are the first TimeStamp plus Time, which is right
    for every file except the two whose Time stops during a pause (flagged).
    Rows with Voltage <= 0 (end-of-test sentinel) are not used as evidence.
    """
    v0 = record["voltage"][0]
    i0 = record["current"][0]
    if v0 > FULL_VOLTAGE_V and abs(i0) < REST_CURRENT_A:
        return f"yes: first sample {v0:.3f} V at {fmt(i0, 3)} A"

    start_s = record["abs_time_s"][0]
    best = None   # (time, record, index) of the latest earlier sample in the folder
    for other in folder_records:
        if other is record:
            continue
        times = other["abs_time_s"]
        earlier = np.where((times <= start_s) & (other["voltage"] > 0.0))[0]
        if len(earlier) == 0:
            continue
        k = earlier[np.argmax(times[earlier])]
        if best is None or times[k] > best[0]:
            best = (times[k], other, k)

    earlier_text = "no earlier sample in the folder"
    if best is not None:
        when, other, k = best
        gap_s = start_s - when
        v_rest = other["voltage"][k]
        i_rest = other["current"][k]
        reached_cv = nan_max(other["voltage"][:k + 1]) >= CV_VOLTAGE_V
        if gap_s <= LINK_GAP_S and abs(i_rest) < REST_CURRENT_A and v_rest > FULL_VOLTAGE_V and reached_cv:
            return f"yes: rest at {v_rest:.3f} V ends {gap_s:.0f} s before start ({short_file(other['file'])})"
        earlier_text = (f"last earlier sample: {v_rest:.3f} V at {fmt(i_rest, 3)} A, {gap_s:.0f} s before "
                        f"({short_file(other['file'])})")

    if abs(i0) < REST_CURRENT_A and v0 <= FULL_VOLTAGE_V:
        return f"no: opens at rest at {v0:.3f} V"
    state = "under load" if i0 < 0 else "charging"
    return f"unclear: opens {state} at {v0:.3f} V, {fmt(i0, 3)} A; {earlier_text}"


def check_previous_file(record, previous):
    """Compare a file with the file logged just before it in the same folder.

    Only neighbouring files are compared here.
    - Overlap: the file starts before the previous file ends (by TimeStamp)
      and ends after it, so the two files claim the same wall-clock minutes.
      A file that lies wholly inside an earlier file's span is not an overlap;
      check_inside_earlier() looks for those against every earlier file.
    - Unlogged discharge: the file opens at rest more than UNLOGGED_DROP_V
      below the last voltage of the previous file, so the cell lost charge
      in between without a log.
    Adds flags to record and fills record["overlap"] and ["unlogged_discharge"].
    """
    overlap_s = (previous["end"] - record["start"]).total_seconds()
    if overlap_s > OVERLAP_FLAG_S and record["end"] > previous["end"]:
        record["overlap"] = (previous["file"], overlap_s / 60.0)
        record["flags"].append(f"starts {overlap_s / 60:.1f} min before the previous file "
                               f"({short_file(previous['file'])}) ends, by TimeStamp: the two clocks disagree "
                               "(e.g. a daylight-saving change), so wall-clock gaps across the pair are wrong")

    previous_voltage = previous["voltage"][previous["voltage"] > 0.0]   # drops NaN and the 0 V sentinel
    if len(previous_voltage) == 0:
        return
    v_end = float(previous_voltage[-1])
    v0 = float(record["voltage"][0])
    gap_min = (record["start"] - previous["end"]).total_seconds() / 60.0
    if abs(record["current"][0]) < REST_CURRENT_A and v_end - v0 > UNLOGGED_DROP_V:
        text = (f"opens at rest at {v0:.3f} V, {gap_min:.0f} min after {short_file(previous['file'])} "
                f"ended at {v_end:.3f} V")
        record["unlogged_discharge"] = text
        record["flags"].append(text + ": unlogged discharge in between")


def check_inside_earlier(record, folder_records):
    """Note a file whose [first, last TimeStamp] span lies wholly inside the span of an earlier file.

    Every earlier file of the folder is checked, not only the neighbour,
    because a long Charge file (549_Charge holds four charges) can span
    several tests logged in between. Such a file is not an overlap and is not
    flagged; the legend lists it with the number of samples the earlier file
    logs inside its span (0 means the two files never log at the same time).
    Fills record["inside_earlier"] with the first such earlier file.
    """
    for other in folder_records:
        if other is record or other["start"] >= record["start"]:
            continue
        reaches_into = (other["end"] - record["start"]).total_seconds() > OVERLAP_FLAG_S
        if reaches_into and record["end"] <= other["end"]:
            times = other["abs_time_s"]
            n_inside = int(np.sum((times > record["abs_time_s"][0]) & (times < record["abs_time_s"][-1])))
            record["inside_earlier"] = (other["file"], n_inside)
            return


# ----------------------------------------------------------------------------
# Markdown output
# ----------------------------------------------------------------------------

def regen_text(regen):
    """Table cell for the regen column."""
    if regen is None:
        return "n/a"
    if not regen["present"]:
        return "no"
    return f"yes: {regen['percent']:.1f} % of samples, max +{regen['max_a']:.2f} A"


def short_file(file_name):
    """File name without the date/time prefix and extension, e.g. '551_Cap_1C_25degC_LGHG2'."""
    return file_name.split(" ", 1)[1].replace(".mat", "") if " " in file_name else file_name


def folder_summary_row(folder, records):
    """One row of the per-folder summary table."""
    starts = [r["start"] for r in records]
    ends = [r["end"] for r in records]
    numbers = sorted(set(r["test_number"] for r in records if r["test_number"] is not None))

    counts = {}
    for r in records:
        if not r["no_current"]:
            counts[r["test_type"]] = counts.get(r["test_type"], 0) + 1
    missing = []
    for test_type, expected in EXPECTED_TESTS.items():
        found = counts.get(test_type, 0)
        if found < expected:
            text = test_type if expected == 1 else f"{test_type} ({found} of {expected})"
            if any(r["no_current"] and r["test_type"] == test_type for r in records):
                text += " (its file has no current)"
            missing.append(text)

    drives = [r for r in records if r["test_type"] in DRIVE_TYPES]
    drive_i_min = min(r["i_min"] for r in drives) if drives else float("nan")
    drive_i_max = max(r["i_max"] for r in drives) if drives else float("nan")
    drive_t_min = min(r["t_min"] for r in drives) if drives else float("nan")
    drive_t_max = max(r["t_max"] for r in drives) if drives else float("nan")

    steps = [r["steps_s"] for r in drives if r["steps_s"] is not None]
    if steps:
        all_steps = np.concatenate(steps)
        positive = all_steps[all_steps > 0]
        dt_text = (f"{np.median(positive):.3f} ({np.percentile(positive, 1):.3f} to "
                   f"{np.percentile(positive, 99):.3f})")
    else:
        dt_text = "n/a"

    charge_temps = [r["charge_start_temp"] for r in records if is_number(r["charge_start_temp"])]
    charge_text = fmt_pair(min(charge_temps), max(charge_temps), 1) if charge_temps else "n/a"

    return (f"| {folder} | {len(records)} | {min(starts):%Y-%m-%d %H:%M} | {max(ends):%Y-%m-%d %H:%M} "
            f"| {', '.join(str(n) for n in numbers)} | {', '.join(missing) if missing else 'none'} "
            f"| {dt_text} | {fmt(drive_i_min, 2)} | {fmt(drive_i_max, 2)} | {fmt_pair(drive_t_min, drive_t_max, 1)} "
            f"| {charge_text} |")


def file_row(r):
    """One row of a per-folder file table."""
    name_start = f"{r['name_start']:%Y-%m-%d %H:%M}" if r["name_start"] is not None else "n/a"
    descriptor_temp = fmt(r["descriptor_temp"], 0) if r["descriptor_temp"] is not None else "none"
    gap_text = fmt(r["max_gap"], 2)
    if r["n_gaps_over_limit"]:
        gap_text += f" ({r['n_gaps_over_limit']} > {GAP_REPORT_S:.0f} s)"
    flags = "; ".join(r["flags"]) if r["flags"] else ""
    return (f"| {r['folder']} | `{r['file']}` | {name_start} | {r['test_type']} | {descriptor_temp} "
            f"| {fmt(r['duration_h'], 2)} | {r['n_samples']} | {fmt(r['median_dt'], 3)} | {gap_text} "
            f"| {r['n_duplicates']} | {r['fields_text']} | {fmt_pair(r['v_min'], r['v_max'], 3)} "
            f"| {fmt_pair(r['i_min'], r['i_max'], 3)} | {fmt_pair(r['t_min'], r['t_max'], 1)} "
            f"| {fmt(r['ah_end'], 4)} | {fmt(r['ah_integral'], 4)} | {regen_text(r['regen'])} "
            f"| {r['full_charge']} | {flags} |")


def write_inventory(folders, records_by_folder, failures, out_path):
    """Write results/s0/data_inventory.md."""
    all_records = [r for folder in folders for r in records_by_folder[folder]]
    lines = []
    lines.append("# Data inventory (S0)")
    lines.append("")
    lines.append("Generated by `python/inventory.py` (`make inventory`) from `data/raw/`: LG 18650HG2 Li-ion "
                 "Battery Data, Kollmeyer et al., McMaster University, Mendeley Data v2, "
                 "DOI 10.17632/b5mj79w5w9.2, CC BY 4.0. Do not edit by hand. Every number is measured "
                 "from the `.mat` files.")
    lines.append("")
    lines.append(f"Files read: {len(all_records)} "
                 f"({sum(1 for r in all_records if r['reader'] == 'scipy')} with scipy as MATLAB v5/v7, "
                 f"{sum(1 for r in all_records if r['reader'] == 'h5py')} with h5py as v7.3). "
                 f"Files that failed to load: {len(failures)}.")
    for path, error in failures:
        lines.append(f"- failed: `{path}`: {error}")
    lines.append("")

    lines.append("## Sign convention")
    lines.append("")
    lines.append("Current and Ah are shown **as the cycler wrote them: discharge current is negative, and the Ah "
                 "counter decreases while discharging** (it is reset to 0 at the start of most tests). The S1 "
                 "loader converts to the project convention (positive = discharge). Units: V, A, s, h, Ah, degC.")
    lines.append("")

    lines.append("## Summary per folder")
    lines.append("")
    lines.append("Folders are in campaign order, i.e. sorted by the first TimeStamp in each folder.")
    lines.append("")
    lines.append("| folder | files | first start | last end | cycler test numbers | readme tests missing "
                 "| drive-cycle dt (s): median (1st to 99th percentile) | drive-cycle min current (A) "
                 "| drive-cycle max current (A, regen) | drive-cycle cell T min / max (degC) "
                 "| cell T when charge current starts, min / max (degC) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for folder in folders:
        lines.append(folder_summary_row(folder, records_by_folder[folder]))
    lines.append("")
    lines.append("- *readme tests missing*: the readme lists, per temperature, one HPPC, one C/20, one 0.5C, one 2C, "
                 "two 1C tests, UDDS, HWFET, LA92, US06 and Mix 1 to 8. Charge and PausCycl files are not counted, "
                 "and a file whose current is 0 A throughout does not count as present.")
    lines.append("- *drive-cycle* columns pool UDDS, HWFET, LA92, US06 and Mixed1 to 8 of the folder.")
    lines.append(f"- *cell T when charge current starts*: Battery_Temp_degC at the first sample with current above "
                 f"+{FLOW_CURRENT_A * 1000:.0f} mA in each Charge file (the readme says charging happens at 22 degC or more).")
    lines.append("")

    lines.append("## Field storage")
    lines.append("")
    lines.append("How each field is stored across all files (number of files per type).")
    lines.append("")
    lines.append("| field | stored as | files not stored as the usual type |")
    lines.append("|---|---|---|")
    field_names = []
    for r in all_records:
        for name in r["dtypes"]:
            if name not in field_names:
                field_names.append(name)
    for name in field_names:
        counts = {}
        for r in all_records:
            dtype = r["dtypes"].get(name, "missing")
            counts[dtype] = counts.get(dtype, 0) + 1
        usual = max(counts, key=counts.get)
        odd = [f"`{r['folder']}/{r['file']}` ({r['dtypes'].get(name, 'missing')})"
               for r in all_records if r["dtypes"].get(name, "missing") != usual]
        counts_text = ", ".join(f"{dtype}: {count}" for dtype, count in sorted(counts.items()))
        lines.append(f"| {name} | {counts_text} | {'; '.join(odd) if odd else 'none'} |")
    wh_values = sorted(set(value for r in all_records for value in r["wh_values"]))
    most_wh = max(all_records, key=lambda r: len(r["wh_values"]))
    n_few_wh = sum(1 for r in all_records if len(r["wh_values"]) <= 3)
    lines.append("")
    lines.append(f"Values found in the Wh field across all files: {', '.join(fmt(v, 0) for v in wh_values)}. "
                 f"{n_few_wh} of {len(all_records)} files hold at most 3 distinct Wh values; the most is "
                 f"{len(most_wh['wh_values'])} in `{most_wh['folder']}/{most_wh['file']}`. Wh is not a "
                 "watt-hour counter and is not used.")
    lines.append("")

    lines.append("## Legend for the file tables")
    lines.append("")
    lines.append("- Rows are sorted by the first TimeStamp of each file (not by the name, which is wrong for some "
                 "files; see *flags*).")
    lines.append("- *start (name)*: date and time from the file name, read as `MM-DD-YY_hh.mm` as the readme "
                 "says. *flags* says when this disagrees with the first TimeStamp by more than "
                 f"{NAME_FLAG_S / 60:.0f} min.")
    lines.append("- *TimeStamp format*: month first with whole seconds in 25degC (`10/28/2018 5:44:00 PM`, "
                 "midnight written as the date alone); day first with milliseconds in every other folder "
                 "(`02/11/2018  6:30:13.000 PM`). The whole second sometimes lags the milliseconds by up to 1 s, "
                 "so Time, not TimeStamp, is the sample clock.")
    lines.append("- *type*: test type from the descriptor (`ekfsoc.rawio.classify_test`). *desc T*: temperature "
                 "written in the descriptor (degC), `none` if absent.")
    lines.append("- *duration*: (max Time - min Time) / 3600. *n*: number of rows. *median dt*, *max gap*: median "
                 "and largest step of Time (s); in brackets, the number of steps longer than "
                 f"{GAP_REPORT_S:.0f} s. *dup*: number of steps where Time does not advance (duplicate rows).")
    lines.append("- *fields*: `8 expected` means exactly Time, TimeStamp, Voltage, Current, Ah, Wh, Power, "
                 "Battery_Temp_degC. No file has a chamber temperature field.")
    lines.append("- *V*, *I*, *T*: min / max of Voltage (V), Current (A, cycler sign) and Battery_Temp_degC "
                 "(degC), NaN ignored.")
    lines.append("- *Ah end*: last Ah value in the file (cycler sign). *integral I dt*: trapezoid integral of "
                 "Current over Time in Ah (steps with dt <= 0 or NaN skipped); for a file whose counter starts at "
                 "0 it should match *Ah end*, which confirms units (A, s) and that Ah has the same sign as current.")
    lines.append(f"- *regen*: drive cycles and PausCycl only; samples with current above +{FLOW_CURRENT_A * 1000:.0f} mA "
                 "(charging) and the largest charging current.")
    lines.append(f"- *full charge at start*: `yes` when the first sample is above {FULL_VOLTAGE_V} V with "
                 f"|I| < {REST_CURRENT_A * 1000:.0f} mA, i.e. the cell sits at its full-charge rest voltage when the "
                 "file starts (`yes: first sample ...`). A file that opens with current already flowing also counts "
                 "as `yes` when the last sample logged before it in the same folder is such a rest, at most "
                 f"{LINK_GAP_S:.0f} s earlier, in a file that reached {CV_VOLTAGE_V} V (CV phase) before it "
                 "(`yes: rest at ...`); this covers e.g. the C/20, 0.5C and 2C tests and the Mixed4 and Mixed8 runs, "
                 f"which start straight after their Charge file. `no` means the file opens at rest at or below "
                 f"{FULL_VOLTAGE_V} V. `unclear` means the file opens under load and no such rest is logged before "
                 "it; the cell gives the first sample and the last earlier sample in the folder. Rows with "
                 "Voltage <= 0 are not used as evidence.")
    unclear_drives = [r for r in all_records
                      if r["test_type"] in DRIVE_TYPES and r["full_charge"].startswith("unclear")]
    if unclear_drives:
        lines.append("- Drive cycles whose full-charge start is not confirmed: " +
                     "; ".join(f"`{r['folder']}/{short_file(r['file'])}` ({r['full_charge'][len('unclear: '):]})"
                               for r in unclear_drives) + ".")
    zero_voltage_parts = []
    for r in all_records:
        if r["zero_voltage_last_row_only"]:
            zero_voltage_parts.append(f"`{r['folder']}/{short_file(r['file'])}` (last row only)")
        elif r["n_zero_voltage_rows"]:
            zero_voltage_parts.append(f"`{r['folder']}/{short_file(r['file'])}` ({r['n_zero_voltage_rows']} rows)")
    lines.append("- *Voltage <= 0* (flag): rows where the cycler logged 0 V, an end-of-test sentinel that the S1 "
                 "loader drops. Found in: " + (", ".join(zero_voltage_parts) if zero_voltage_parts else "none") + ".")
    overlaps = [r for r in all_records if r["overlap"] is not None]
    inside = [r for r in all_records if r["inside_earlier"] is not None]
    overlap_text = "; ".join(f"`{r['folder']}/{short_file(r['file'])}` starts {r['overlap'][1]:.1f} min before "
                             f"`{short_file(r['overlap'][0])}` ends" for r in overlaps)
    inside_text = "; ".join(f"`{r['folder']}/{short_file(r['file'])}` inside `{short_file(r['inside_earlier'][0])}`, "
                            f"which logs {r['inside_earlier'][1]} samples within it" for r in inside)
    lines.append(f"- *overlap* (flag): the file's [first, last TimeStamp] span starts more than {OVERLAP_FLAG_S:.0f} s "
                 "before the previous file of the folder ends and ends after it, so both files claim the same "
                 "wall-clock minutes and any rest time computed across the pair is wrong by that much. Only "
                 "neighbouring files are compared (each file with the file logged just before it). Found: "
                 f"{overlap_text if overlaps else 'none'}. A file whose span lies wholly inside the span of an earlier "
                 "file of the folder is not an overlap and is not flagged; this is checked against every earlier "
                 f"file, not only the neighbour ({inside_text if inside else 'none found'}).")
    lines.append(f"- *flags*: anything a later stage must handle: name problems, integer storage, NaN rows, "
                 f"Voltage <= 0 rows, backward or stalled Time, pauses that only TimeStamp shows, an overlap with "
                 f"the previous file, a file that opens at rest more than {UNLOGGED_DROP_V} V below the end of the "
                 f"previous file (unlogged discharge), a cell temperature more than "
                 f"{TEMP_FLAG_DEGC:.0f} degC from the folder temperature at the first discharging sample (before "
                 f"self-heating), an Ah counter reset on "
                 f"the last row, or a drive cycle whose integral of I dt is more than {AH_FLAG_AH} Ah off its Ah counter.")
    lines.append("")

    header = ("| folder | file | start (name) | type | desc T (degC) | duration (h) | n | median dt (s) "
              "| max gap (s) | dup | fields | V min / max (V) | I min / max (A) | T min / max (degC) "
              "| Ah end (Ah) | integral I dt (Ah) | regen | full charge at start | flags |")
    separator = "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    for folder in folders:
        records = records_by_folder[folder]
        lines.append(f"## {folder} ({len(records)} files)")
        lines.append("")
        lines.append(header)
        lines.append(separator)
        for r in records:
            lines.append(file_row(r))
        lines.append("")

    out_path.write_text("\n".join(lines))


def extrapolation_check(capacity_records):
    """Sentence that checks the one-interval extrapolation of the discharge start against the data.

    If the first logged sample really is one interval into the step, the
    extrapolated start is 0 where the cycler reset the counter (C/20, 2C) and
    equals the last Ah of the preceding C/20 file where it did not (0.5C).
    """
    reset_starts = [abs(r["capacity"]["ah_start"]) for r in capacity_records
                    if r["test_type"] in ("c20", "dis_2c") and r["capacity"]["start_note"].startswith("file opens")]
    carried = []
    for r in capacity_records:
        if r["test_type"] != "dis_0p5c" or not r["capacity"]["start_note"].startswith("file opens"):
            continue
        c20 = [x for x in capacity_records if x["folder"] == r["folder"] and x["test_type"] == "c20"]
        if c20:
            carried.append(r["capacity"]["ah_start"] - c20[0]["ah_end"])
    parts = []
    if reset_starts:
        parts.append(f"check: for the {len(reset_starts)} C/20 and 2C files this gives |Ah at start| <= "
                     f"{max(reset_starts):.5f} Ah (counter reset at the step start)")
    if carried:
        parts.append(f"for the {len(carried)} 0.5C files it gives the last Ah value of that folder's C20DisCh "
                     f"file to within {max(abs(x) for x in carried):.5f} Ah (counter not reset)")
    return "; ".join(parts) + "." if parts else "no file needed this."


def at_folder_temperature(r):
    """True if a capacity test's discharge started within TEMP_FLAG_DEGC of its folder temperature."""
    folder_temp = FOLDER_TEMPS_DEGC.get(r["folder"])
    if folder_temp is None:
        return True
    return abs(r["capacity"]["temp_start"] - folder_temp) <= TEMP_FLAG_DEGC


def one_c_runs(records):
    """Return (first run, second run) of a folder's 1C tests; None where the data has no file.

    records: the folder's records in time order. The readme puts the first 1C
    test before UDDS and the second before Mix 3. With two 1C files they are
    taken in the order they ran. With one, it is the first run if it started
    before the folder's UDDS file, otherwise the second.
    """
    one_c = [r for r in records if r["test_type"] == "cap_1c" and r["capacity"] is not None]
    if len(one_c) >= 2:
        return one_c[0], one_c[1]
    if len(one_c) == 0:
        return None, None
    udds = [r for r in records if r["test_type"] == "udds"]
    if udds and one_c[0]["start"] > udds[0]["start"]:
        return None, one_c[0]
    return one_c[0], None


def one_c_note(r):
    """Short note for a 1C test that ran off its folder temperature or whose name gives another one ('' if neither)."""
    folder_temp = FOLDER_TEMPS_DEGC.get(r["folder"])
    if folder_temp is None:
        return ""
    if not at_folder_temperature(r):
        return f"**off-temperature**, not a {folder_temp:.0f} degC capacity"
    if r["descriptor_temp"] is not None and r["descriptor_temp"] != folder_temp:
        return f"named {r['descriptor_temp']:.0f} degC, valid as {folder_temp:.0f} degC"
    return ""


def one_c_notes(folders, records_by_folder):
    """Bullets under the per-folder table: which 1C run is missing, and which 1C test to read with care."""
    notes = []
    for folder in folders:
        records = records_by_folder[folder]
        first, second = one_c_runs(records)
        udds = [r for r in records if r["test_type"] == "udds"]
        udds_text = f"`{short_file(udds[0]['file'])}`" if udds else "no UDDS file in the data"
        if first is None and second is None:
            notes.append(f"{folder}: no 1C file.")
        elif first is None:
            text = (f"{folder}: the only 1C file, `{short_file(second['file'])}`, started after the folder's UDDS "
                    f"({udds_text}), so it is the second run; the first run is missing.")
            before_udds = [r for r in records if r["unlogged_discharge"] and udds and r["start"] <= udds[0]["start"]]
            if before_udds:
                text += (" Before UDDS, where the readme puts the first 1C test, the data shows an unlogged discharge: "
                         + "; ".join(f"`{short_file(r['file'])}` {r['unlogged_discharge']}" for r in before_udds) + ".")
            notes.append(text)
        elif second is None:
            notes.append(f"{folder}: the only 1C file, `{short_file(first['file'])}`, started before the folder's UDDS "
                         f"({udds_text}), so it is the first run; the second run is missing.")

        for r in (first, second):
            if r is None or not one_c_note(r):
                continue
            c = r["capacity"]
            folder_temp = FOLDER_TEMPS_DEGC[folder]
            text = (f"`{folder}/{short_file(r['file'])}`: cell at {c['temp_start']:.1f} degC when the discharge "
                    f"starts, {fmt_pair(c['temp_min'], c['temp_max'], 1)} degC min / max over it; "
                    f"folder {folder_temp:.0f} degC.")
            if not at_folder_temperature(r):
                text += f" Not a {folder_temp:.0f} degC capacity."
            else:
                text += (f" The name says {r['descriptor_temp']:.0f} degC, but this is the {folder_temp:.0f} degC "
                         "1C test.")
            notes.append(text)
    return notes


def drive_groups(folders, records_by_folder):
    """Drive cycles grouped by folder and cycler test number, with the 1C tests to compare them with.

    Returns a list of dicts in campaign order with keys:
        folder, number
        cycles: drive-cycle records of the group that have current
        dead: test types of the group whose file has no current
        removed: Ah removed by each cycle (first Ah minus last Ah, positive)
        same_test: the 1C record with the same test number, or None
        reference: the first 1C record of the folder that ran at the folder temperature, or None
    """
    groups = []
    for folder in folders:
        records = records_by_folder[folder]
        at_temperature = [r for r in records if r["test_type"] == "cap_1c" and r["capacity"] is not None
                          and at_folder_temperature(r)]
        numbers = []
        for r in records:
            if r["test_type"] in DRIVE_TYPES and r["test_number"] not in numbers:
                numbers.append(r["test_number"])
        for number in numbers:
            cycles = [r for r in records if r["test_type"] in DRIVE_TYPES and r["test_number"] == number
                      and not r["no_current"]]
            dead = [r["test_type"] for r in records if r["test_type"] in DRIVE_TYPES
                    and r["test_number"] == number and r["no_current"]]
            if not cycles:
                continue
            same_test = [r for r in records if r["test_type"] == "cap_1c" and r["test_number"] == number
                         and r["capacity"] is not None]
            groups.append({
                "folder": folder,
                "number": number,
                "cycles": cycles,
                "dead": dead,
                "removed": [r["ah_first"] - r["ah_end"] for r in cycles],
                "same_test": same_test[0] if same_test else None,
                "reference": at_temperature[0] if at_temperature else None,
            })
    return groups


def percent_range(low, high):
    """'97.4 %' or '93.2 to 94.1 %' for two fractions."""
    if f"{low * 100:.1f}" == f"{high * 100:.1f}":
        return f"{low * 100:.1f} %"
    return f"{low * 100:.1f} to {high * 100:.1f} %"


def stop_rule_verdict(groups):
    """Anomaly bullet: does every drive cycle stop at 95 % of a 1C capacity?

    A group is compared with its same-number 1C test when the data has one,
    otherwise with the first 1C test that ran at the folder temperature. It
    fits when every cycle is within STOP_RULE_TOLERANCE of 95 %. A group that
    removed less than half of what the folder's largest group removed is a
    partial run.
    """
    matched_ratios = []
    off_temperature_matches = []
    fits_without_match = []
    misses = []
    unchecked = []
    partial = []
    for g in groups:
        folder_most = max(max(other["removed"]) for other in groups if other["folder"] == g["folder"])
        if max(g["removed"]) < 0.5 * folder_most:
            partial.append(f"{g['number']} ({g['folder']}: {', '.join(r['test_type'] for r in g['cycles'])}) "
                           f"removed only {max(g['removed']):.2f} Ah per cycle")
            continue
        one_c = g["same_test"] if g["same_test"] is not None else g["reference"]
        if one_c is None:
            unchecked.append(f"{g['number']} ({g['folder']})")
            continue
        capacity = one_c["capacity"]["ah_removed"]
        ratios = [x / capacity for x in g["removed"]]
        fits = all(abs(x - STOP_RULE_FRACTION) <= STOP_RULE_TOLERANCE for x in ratios)
        if g["same_test"] is not None:
            matched_ratios += ratios
            if not at_folder_temperature(g["same_test"]):
                off_temperature_matches.append(str(g["number"]))
        if fits and g["same_test"] is None:
            fits_without_match.append(f"{g['number']} ({g['folder']})")
        if not fits:
            misses.append(f"{g['number']} ({g['folder']}) removed {percent_range(min(ratios), max(ratios))} of "
                          f"{one_c['test_number']}'s 1C capacity")

    if not misses and not unchecked and not partial:
        verdict = "yes"
    elif matched_ratios or fits_without_match:
        verdict = "partly"
    else:
        verdict = "no"
    text = f"- **Drive-cycle stop rule ({STOP_RULE_FRACTION * 100:.0f} % of the 1C capacity): {verdict}.**"
    if matched_ratios:
        text += (f" In all {len(matched_ratios)} drive cycles that share a cycler test number with a 1C test, Ah "
                 f"removed / that 1C capacity is {min(matched_ratios):.4f} to {max(matched_ratios):.4f}")
        if off_temperature_matches:
            text += f", even where that 1C test ran off-temperature (tests {', '.join(off_temperature_matches)})"
        text += "."
    text += (" Groups without a same-number 1C test are compared with the first 1C test that ran at the folder "
             "temperature.")
    if fits_without_match:
        text += f" Fit: {', '.join(fits_without_match)}."
    if misses:
        text += f" Do not fit: {'; '.join(misses)}."
    if unchecked:
        text += f" Cannot be checked (no 1C test at the folder temperature): {', '.join(unchecked)}."
    if partial:
        text += f" Partial runs: {'; '.join(partial)}."
    return text


def current_scaling_notes(folders, records_by_folder):
    """Anomaly bullets for folders whose C/20, 0.5C or 2C current differs from the other folders by > RATE_FLAG."""
    test_names = {"c20": "C/20", "dis_0p5c": "0.5C", "dis_2c": "2C"}
    median_current = {}   # (folder, test type) -> median discharge current (A, positive)
    hppc_levels = {}      # folder -> HPPC discharge pulse levels (A, cycler sign)
    for folder in folders:
        for r in records_by_folder[folder]:
            if r["test_type"] in test_names and r["capacity"] is not None:
                median_current[(folder, r["test_type"])] = r["capacity"]["median_current_a"]
            if r["test_type"] == "hppc" and r["pulse_levels"]:
                hppc_levels[folder] = r["pulse_levels"]

    notes = []
    for folder in folders:
        parts = []
        ratios = []
        flagged = False
        for test_type, name in test_names.items():
            others = [median_current[(f, test_type)] for f in folders
                      if f != folder and (f, test_type) in median_current]
            if (folder, test_type) not in median_current or not others:
                continue
            value = median_current[(folder, test_type)]
            reference = float(np.median(others))
            ratio = value / reference
            ratios.append(ratio)
            if abs(ratio - 1.0) > RATE_FLAG:
                flagged = True
            parts.append(f"{name} {value:.3f} A (other folders {reference:.3f} A, ratio {ratio:.3f})")
        if not flagged:
            continue

        records = records_by_folder[folder]
        numbers = sorted(set(str(r["test_number"]) for r in records
                             if r["test_type"] in ("c20", "dis_0p5c", "dis_2c", "hppc")))
        test_word = "test" if len(numbers) == 1 else "tests"
        text = (f"- **{folder} {test_word} {', '.join(numbers)}: currents differ from the other folders.** "
                f"Median discharge current: {', '.join(parts)}.")
        if folder in hppc_levels and "25degC" in hppc_levels and folder != "25degC":
            levels = hppc_levels[folder]
            reference_levels = hppc_levels["25degC"]
            text += (f" HPPC discharge pulses: {' / '.join(fmt(x, 1) for x in levels)} A, against "
                     f"{' / '.join(fmt(x, 1) for x in reference_levels)} A at 25degC")
            if len(levels) == len(reference_levels):
                level_ratios = [a / b for a, b in zip(levels, reference_levels)]
                ratios += level_ratios
                if fmt(min(level_ratios), 3) == fmt(max(level_ratios), 3):
                    text += f" (ratio {fmt(min(level_ratios), 3)} for every level)"
                else:
                    text += f" (ratio {fmt(min(level_ratios), 3)} to {fmt(max(level_ratios), 3)})"
            text += "."
        text += f" Median of these ratios: {float(np.median(ratios)):.3f}."
        if (folder, "dis_0p5c") in median_current and (folder, "dis_2c") in median_current:
            text += (f" Against the {NOMINAL_1C_A:.1f} A 1C basis, the {folder} 0.5C and 2C capacities were therefore "
                     f"measured at {median_current[(folder, 'dis_0p5c')] / NOMINAL_1C_A:.2f}C and "
                     f"{median_current[(folder, 'dis_2c')] / NOMINAL_1C_A:.2f}C.")
        one_c = [r for r in records if r["test_type"] == "cap_1c" and r["capacity"] is not None]
        if one_c:
            text += (" The folder's 1C tests ran at the usual current (mean I: " +
                     ", ".join(f"{r['capacity']['mean_current_a']:.3f} A in {r['test_number']}" for r in one_c) + ").")
        notes.append(text)
    return notes


def c20_ratio_note(folders, records_by_folder):
    """Anomaly bullet: Ah put back by the C/20 charge divided by Ah removed by the C/20 discharge, per folder.

    The ratio is charge Ah over discharge Ah. A coulombic efficiency under 1
    means more charge must go in than came out, so it would put the ratio
    just above 1. The sentence compares the measured ratios with that.
    """
    parts = []
    ratios = []   # (folder, ratio) in campaign order
    for folder in folders:
        c20 = [r for r in records_by_folder[folder] if r["test_type"] == "c20" and r["capacity"] is not None]
        if c20:
            c = c20[0]["capacity"]
            ratio = c["charge_after_ah"] / c["ah_removed"]
            ratios.append((folder, ratio))
            parts.append(f"{fmt(ratio, 3)} ({folder})")
    above = [ratio for _, ratio in ratios if ratio > 1.0]
    below = [(folder, ratio) for folder, ratio in ratios if ratio < 1.0]
    comparison = []
    if above:
        comparison.append(f"the measured ratios above 1 ({fmt(min(above), 3)} to {fmt(max(above), 3)}) are far "
                          "larger than that")
    if below:
        comparison.append(", ".join(folder for folder, _ in below) + " is below 1 (" +
                          ", ".join(fmt(ratio, 3) for _, ratio in below) + ")")
    comparison_text = ""
    if comparison:
        sentence = ", and ".join(comparison)
        comparison_text = sentence[0].upper() + sentence[1:] + ". "
    return ("- **C/20 charge / discharge Ah ratio**, in campaign order: " + ", ".join(parts) + ". With no charge "
            "lost or created the ratio would be 1, or just above 1 for a coulombic efficiency under 1 (more charge "
            "goes in than comes out). " + comparison_text + "The data explains none of them, so all are recorded "
            "as unexplained, and the two halves of a C20DisCh file should not be assumed to share one Ah axis.")


def write_capacity(folders, records_by_folder, out_path):
    """Write results/s0/capacity.md."""
    all_records = [r for folder in folders for r in records_by_folder[folder]]
    capacity_records = sorted((r for r in all_records if r["capacity"] is not None), key=lambda r: r["start"])

    lines = []
    lines.append("# Capacity tests (S0)")
    lines.append("")
    lines.append("Generated by `python/inventory.py` (`make inventory`) from `data/raw/` (LG 18650HG2, "
                 "DOI 10.17632/b5mj79w5w9.2, CC BY 4.0). Do not edit by hand. Every number is measured from the files.")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(f"- The discharge of a test is the longest run of samples with current below -{FLOW_CURRENT_A * 1000:.0f} mA "
                 "(cycler sign). For C20DisCh this is the C/20 discharge part; its charge part is reported separately.")
    lines.append("- *Ah removed* = Ah counter at the start of the discharge minus Ah counter at its last sample. The "
                 "cycler counts discharge as negative Ah, so this is positive.")
    lines.append("- *Ah at start*: the counter at the rest sample just before the discharge. Files that open "
                 "mid-discharge (last column) are extrapolated back one logging interval at the first sample's "
                 "current; " + extrapolation_check(capacity_records))
    lines.append("- *final V*: voltage at the last discharge sample. *mean I*: mean of the logged current over the "
                 "discharge, sign flipped so discharge is positive (the *Anomalies* section uses the median instead). "
                 "*cell T*: Battery_Temp_degC min / max over the discharge.")
    lines.append("- Rows are in campaign order (first TimeStamp of each file), so ageing across the campaign shows "
                 f"down the table. Folder order by first TimeStamp: {', '.join(folders)}. The readme gives the order "
                 "40, 25, 10, 0, -10, -20 degC.")
    lines.append("")

    lines.append("## All capacity tests in campaign order")
    lines.append("")
    lines.append("| # | folder | start (TimeStamp) | file | test | Ah removed (Ah) | Ah at start (Ah) | final V (V) "
                 "| mean I (A) | cell T min / max (degC) | how the start was found |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, r in enumerate(capacity_records, start=1):
        c = r["capacity"]
        lines.append(f"| {k} | {r['folder']} | {r['start']:%Y-%m-%d %H:%M} | `{r['file']}` | {r['test_type']} "
                     f"| {fmt(c['ah_removed'], 4)} | {fmt(c['ah_start'], 4)} | {fmt(c['final_voltage'], 3)} "
                     f"| {fmt(c['mean_current_a'], 3)} | {fmt_pair(c['temp_min'], c['temp_max'], 1)} "
                     f"| {c['start_note']} |")
    lines.append("")

    # The 25 degC C/20 discharge capacity, named explicitly (Q_ref candidate, decided in docs/decisions.md).
    c20_25 = [r for r in capacity_records if r["folder"] == "25degC" and r["test_type"] == "c20"]
    lines.append("## 25 degC C/20 discharge capacity")
    lines.append("")
    if len(c20_25) == 1:
        r = c20_25[0]
        c = r["capacity"]
        lines.append(f"The C/20 discharge capacity at 25 degC is **{c['ah_removed']:.4f} Ah**, measured on the discharge "
                     f"part of `data/raw/25degC/{r['file']}` (started {r['start']:%Y-%m-%d %H:%M}, mean current "
                     f"{c['mean_current_a']:.4f} A, ended at {c['final_voltage']:.3f} V, cell at "
                     f"{c['temp_min']:.1f} to {c['temp_max']:.1f} degC). The spec makes this number `Q_ref`; the "
                     "decision itself belongs in `docs/decisions.md`.")
    else:
        lines.append(f"Expected exactly one C/20 test in 25degC, found {len(c20_25)}.")
    lines.append("")

    lines.append("## C/20 and 1C capacities per folder")
    lines.append("")
    lines.append("The two 1C columns are the folder's first and second 1C run in the order they ran (the readme puts "
                 "the first before UDDS and the second before Mix 3). A folder with only one 1C file has it in the "
                 "first-run column if it started before the folder's UDDS file, otherwise in the second-run column. "
                 "*cell T* is the temperature the cell was actually at (min / max over the discharge). *C/20 charge* "
                 "is the Ah put back by the charge part of the same C20DisCh file (highest counter after the "
                 "discharge minus the counter at the end of the discharge); it is shown for comparison only.")
    lines.append("")
    lines.append("| folder | C/20 discharge (Ah) | C/20 charge, same file (Ah) | charge / discharge "
                 "| 1C first run (Ah) | first run: file, cell T (degC) | 1C second run (Ah) "
                 "| second run: file, cell T (degC) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for folder in folders:
        records = [r for r in capacity_records if r["folder"] == folder]
        c20 = [r for r in records if r["test_type"] == "c20"]
        if c20:
            c = c20[0]["capacity"]
            c20_text = fmt(c["ah_removed"], 4)
            charge_text = fmt(c["charge_after_ah"], 4)
            ratio_text = fmt(c["charge_after_ah"] / c["ah_removed"], 3)
        else:
            c20_text, charge_text, ratio_text = "missing", "n/a", "n/a"
        cells = []
        for r in one_c_runs(records_by_folder[folder]):
            if r is None:
                cells.append("missing")
                cells.append("no file")
                continue
            c = r["capacity"]
            file_text = f"`{short_file(r['file'])}`, {fmt_pair(c['temp_min'], c['temp_max'], 1)}"
            if one_c_note(r):
                file_text += f"; {one_c_note(r)}"
            cells.append(fmt(c["ah_removed"], 4))
            cells.append(file_text)
        lines.append(f"| {folder} | {c20_text} | {charge_text} | {ratio_text} | {' | '.join(cells)} |")
    lines.append("")
    for note in one_c_notes(folders, records_by_folder):
        lines.append(f"- {note}")
    other_off = [r for r in capacity_records if r["test_type"] != "cap_1c" and not at_folder_temperature(r)]
    if other_off:
        lines.append(f"- Other capacity tests whose cell is more than {TEMP_FLAG_DEGC:.0f} degC from the folder "
                     "temperature when the discharge starts: " +
                     "; ".join(f"`{r['folder']}/{short_file(r['file'])}` ({r['capacity']['temp_start']:.1f} degC)"
                               for r in other_off) + ".")
    else:
        lines.append(f"- The C/20, 0.5C and 2C tests all start their discharge within {TEMP_FLAG_DEGC:.0f} degC of "
                     "the folder temperature.")
    lines.append("")

    # Drive-cycle stop rule: readme says drive cycles stop at 95 % of the 1C capacity at that temperature.
    groups = drive_groups(folders, records_by_folder)
    lines.append("## Drive-cycle stop rule")
    lines.append("")
    lines.append(f"The readme says drive cycles repeat until {STOP_RULE_FRACTION * 100:.0f} % of the 1C capacity at "
                 "that temperature is discharged. Drive cycles are grouped by folder and cycler test number; *Ah "
                 "removed* is the first Ah value minus the last one (cycler sign, so positive). Each group is "
                 "compared with the 1C test that has the same test number, if the data has one, and with the first "
                 "1C test of the folder that ran at the folder temperature (cell within "
                 f"{TEMP_FLAG_DEGC:.0f} degC when the discharge starts). *implied 1C* = Ah removed / "
                 f"{STOP_RULE_FRACTION}. PausCycl files are left out (they stop much earlier). The verdict is under "
                 "*Anomalies*.")
    lines.append("")
    lines.append("| folder | test number | drive cycles | Ah removed min / max (Ah) | 1C test with this number (Ah) "
                 "| Ah removed / same-number 1C, min / max | first 1C at the folder temperature (Ah) "
                 "| Ah removed / first at-temperature 1C, min / max | implied 1C min / max (Ah) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for g in groups:
        removed = g["removed"]
        compare_cells = []
        for one_c in (g["same_test"], g["reference"]):
            if one_c is None:
                compare_cells += ["none in the data", "n/a"]
                continue
            capacity = one_c["capacity"]["ah_removed"]
            compare_cells.append(f"{capacity:.4f} (`{short_file(one_c['file'])}`)")
            compare_cells.append(fmt_pair(min(removed) / capacity, max(removed) / capacity, 4))
        implied_text = fmt_pair(min(removed) / STOP_RULE_FRACTION, max(removed) / STOP_RULE_FRACTION, 4)
        types = ", ".join(r["test_type"] for r in g["cycles"])
        if g["dead"]:
            types += " (left out, no current: " + ", ".join(g["dead"]) + ")"
        lines.append(f"| {g['folder']} | {g['number']} | {types} | {fmt_pair(min(removed), max(removed), 4)} "
                     f"| {' | '.join(compare_cells)} | {implied_text} |")
    lines.append("")

    lines.append("## Anomalies")
    lines.append("")
    for note in current_scaling_notes(folders, records_by_folder):
        lines.append(note)
    lines.append(c20_ratio_note(folders, records_by_folder))
    lines.append(stop_rule_verdict(groups))
    lines.append("")

    out_path.write_text("\n".join(lines))


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    """Walk data/raw/, summarise every file, write both reports."""
    folder_names = [path.name for path in RAW_DIR.iterdir() if path.is_dir()]
    unknown = [name for name in folder_names if name not in FOLDER_TEMPS_DEGC]
    if unknown:
        print(f"warning: folders with no known temperature: {unknown}")

    records_by_folder = {}
    failures = []
    for folder in sorted(folder_names):
        records = []
        for path in sorted((RAW_DIR / folder).glob("*.mat")):
            try:
                records.append(summarize_file(folder, path))
            except Exception as error:   # report and continue: one bad file must not hide the rest
                failures.append((f"{folder}/{path.name}", f"{type(error).__name__}: {error}"))
        records.sort(key=lambda r: r["start"])
        for r in records:
            r["full_charge"] = full_charge_start(r, records)
        for previous, r in zip(records, records[1:]):
            check_previous_file(r, previous)
        for r in records:
            check_inside_earlier(r, records)
        for r in records:
            del r["abs_time_s"], r["voltage"], r["current"]
        records_by_folder[folder] = records
        print(f"{folder}: {len(records)} files")

    # Campaign order: folders sorted by their earliest TimeStamp.
    folders = sorted((f for f in records_by_folder if records_by_folder[f]),
                     key=lambda f: min(r["start"] for r in records_by_folder[f]))

    RESULTS_DIR.mkdir(exist_ok=True)
    write_inventory(folders, records_by_folder, failures, RESULTS_DIR / "s0" / "data_inventory.md")
    write_capacity(folders, records_by_folder, RESULTS_DIR / "s0" / "capacity.md")
    total = sum(len(records) for records in records_by_folder.values())
    print(f"wrote results/s0/data_inventory.md ({total} files, {len(failures)} failed) and results/s0/capacity.md")
    for path, error in failures:
        print(f"failed: {path}: {error}")


if __name__ == "__main__":
    main()
