"""S0 data checks: measured dataset properties that the docs cite.

Writes results/s0/data_checks.md. docs/decisions.md and docs/model.md cite
measured properties of the raw files: sampling steps, duplicate rows, gaps,
the three damaged drive files, temperatures, run lengths, the charge
procedure, the HPPC and C/20 structure, the Q_ref row, the Ah counter, the
campaign order and the 10 degC current scaling. results/s0/data_inventory.md and
results/s0/capacity.md (python/inventory.py) do not contain these, so this
script measures them from data/raw/ and writes them out, each with the files
it comes from.

Run from the repo root:  .venv/bin/python python/data_checks.py   (or: make checks)

Values quoted from the files keep the cycler's sign (discharge current is
negative, the Ah counter falls while discharging). Amounts named "removed",
"returned" or "charged" are positive. The reference SoC and the coulomb
counter use the project sign, I = -Current (positive = discharge).
"""

import math
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

from ekfsoc import rawio


REPO_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_DIR / "data" / "raw"
OUT_PATH = REPO_DIR / "results" / "s0" / "data_checks.md"

# Folder name -> chamber temperature it stands for (degC); the temperature grid nodes.
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

# Thresholds used by the checks. The section texts in results/s0/data_checks.md state the ones that shape a result.
FLOW_CURRENT_A = 0.05        # |I| above this is a discharge (I < 0) or a charge (I > 0); below it is a rest
REST_START_CURRENT_A = 0.10  # a drive file "opens at rest" when |I| on its first row is below this
FULL_VOLTAGE_V = 4.15        # full-charge rule: first V above this ...
FULL_CURRENT_A = 0.05        # ... and |I| below this
LINK_GAP_S = 300.0           # a drive file that opens under load counts as linked to a full charge this close after it
DT_BAND_S = (0.09, 0.11)     # a drive-cycle step in this band is a normal 0.1 s step
LONG_STEP_S = 0.2            # count drive-cycle steps above this
GAP_S = 1.0                  # the spec: steps longer than 1 s are recorded as gaps
CC_CURRENT_A = 2.9           # a Charge file has a 1C CC phase if its current exceeds this
CV_VOLTAGE_V = 4.195         # charge samples at or above this voltage are in the CV phase
CV_START_V = 4.1995          # the C/20 charge enters CV at the first sample at or above this voltage
LOW_LIMIT_V = 2.8005         # a sample at or below this voltage sits at the 2.8 V cutoff
HIGH_LIMIT_V = 4.1995        # a charge pulse that reaches this voltage is limited by the 4.2 V CV limit
PULSE_MAX_S = 12.0           # an HPPC current step this short or shorter is a pulse; longer ones are moves or charges
FULL_PULSE_S = 9.9           # a pulse that lasts at least this long ran its full 10 s
SHORT_PULSE_S = 9.5          # a discharge pulse shorter than this was cut by the 2.8 V limit
FIRST_SAMPLE_FRACTION = 0.98 # R0 rule: the current must reach 98 % of the command ...
FIRST_SAMPLE_WINDOW_S = 0.3  # ... within 0.3 s of the pulse's first row with current (section 10 also shows the stricter count from the row before)
ONE_HOUR_REST_S = 3000.0     # an HPPC rest after a move that lasts longer than this is one of the 1 h rests
RELAX_WINDOW_S = 600.0       # residual relaxation is measured over the last 10 min of a 1 h rest
COUNTER_TOLERANCE_AH = 2e-5  # the Ah counter is logged to 1e-5 Ah; a reset must exceed what the current explains by more
OFFSET_GUARD_PP = 5.0        # the spec: coulomb-counting drift at the end of the shortest run must be >= 5 pp
OFFSET_STEP_A = 0.05         # offsets are rounded up to a multiple of 50 mA
OFFSETS_A = (0.100, 0.200)   # offsets whose drift is shown
WINDOW_SOC = 0.10            # the spec's evaluation window ends at the last sample with SoC_ref >= 10 %
EXP3_START_SOC = (0.70, 0.50)  # experiment 3 start levels compared in section 7
RECHARGE_MIN_A = 2.0         # the CC samples of an in-file recharge draw more than this
HWFET_SECONDS = 765.0        # length of one HWFET cycle, used to find it inside a mix
MATCH_CORRELATION = 0.99     # a window of a mix "is" the HWFET cycle when the correlation reaches this

# The file Q_ref comes from (the spec: the C/20 discharge capacity at 25 degC).
QREF_FOLDER = "25degC"
QREF_TEST_TYPE = "c20"

# Per-file loader cuts decided in S0 (docs/decisions.md); section 4 shows the evidence for each.
FIRST_ROW_USED = {"571_Mixed6": 391}          # start after the 10.4 h hidden pause between rows 390 and 391
ONLY_ROWS_DATED = {"582_LA92": (2018, 11, 26)}  # keep the real run (26/11); drop the false start dated 25/11

# Drive files that are not in the evaluation set, with the reason (docs/decisions.md).
NOT_EVALUATED = {
    "551_HWFET": "excluded: no current",
    "551_Mixed1": "tuning cycle",
    "562_Mixed4": "excluded: partial run",
    "562_Mixed5": "excluded: partial run",
    "562_Mixed6": "excluded: partial run",
    "562_Mixed7": "excluded: partial run",
    "562_Mixed8": "excluded: partial run",
    "602_Mixed4": "excluded: corrupt (frozen rows and a 416 s hole)",
}

NUMERIC_FIELDS = ("Time", "Voltage", "Current", "Ah", "Wh", "Power", "Battery_Temp_degC")
LOADER_FIELDS = ("Time", "Voltage", "Current", "Ah", "Battery_Temp_degC")   # fields the loader needs finite


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def fmt(value, digits):
    """Format a number with a fixed number of decimals, or 'n/a' for None and NaN."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    text = f"{value:.{digits}f}"
    if text.startswith("-") and float(text) == 0.0:
        text = text[1:]          # show 0.000, not -0.000
    return text


def fmt_range(values, digits):
    """'a to b' for the smallest and largest of some numbers, or just 'a' when they print the same."""
    low = fmt(min(values), digits)
    high = fmt(max(values), digits)
    return low if low == high else f"{low} to {high}"


def short_name(file_name):
    """File name without the date/time prefix and extension, e.g. '551_LA92_25degC_LGHG2'."""
    return file_name.split(" ", 1)[1].replace(".mat", "") if " " in file_name else file_name.replace(".mat", "")


def label(record):
    """How a file is named in the tables: '<folder>/<test>_<descriptor>'."""
    return f"`{record['folder']}/{short_name(record['file'])}`"


def run_key(record):
    """Test number and first descriptor word, e.g. '571_Mixed6' or '549_C20DisCh'; keys the per-file rules."""
    return f"{record['test_number']}_{record['descriptor'].split('_')[0]}"


def stored_rows_text(rows):
    """Compact list of row numbers: consecutive rows become 'a to b'."""
    parts = []
    start = previous = None
    for row in rows:
        if start is None:
            start = previous = row
        elif row == previous + 1:
            previous = row
        else:
            parts.append(f"{start}" if start == previous else f"{start} to {previous}")
            start = previous = row
    if start is not None:
        parts.append(f"{start}" if start == previous else f"{start} to {previous}")
    return ", ".join(parts)


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


def round_up(value, step):
    """Smallest multiple of step that is >= value (with a small tolerance for float noise)."""
    return math.ceil(value / step - 1e-9) * step


def counter_resets(time_s, current, ah):
    """Rows (as given) where the cycler reset its Ah counter to 0.

    A reset is a row whose Ah is exactly 0 while the previous row's Ah is not,
    and whose change from the previous row is larger than the current on
    either row could cause over that step (plus COUNTER_TOLERANCE_AH). The
    second condition leaves out a counter that merely passes through 0, as it
    does under regen near the start of some drive cycles.
    """
    resets = []
    candidates = np.where((ah[1:] == 0.0) & (ah[:-1] != 0.0))[0] + 1    # Ah is 0 and was not
    for k in candidates:
        step_s = abs(time_s[k] - time_s[k - 1])
        possible_ah = max(abs(current[k]), abs(current[k - 1])) * step_s / 3600.0
        if abs(ah[k - 1]) > possible_ah + COUNTER_TOLERANCE_AH:
            resets.append(int(k))
    return resets


def value_at(x, y, x0):
    """Linear interpolation of y(x) at x0 after sorting by x (x need not be sorted)."""
    order = np.argsort(x)
    return float(np.interp(x0, x[order], y[order]))


# ----------------------------------------------------------------------------
# Loading and the loader rules
# ----------------------------------------------------------------------------

def file_records():
    """One dict per raw file with its folder, name, path and name fields, sorted by folder and name."""
    records = []
    for folder in sorted(path.name for path in RAW_DIR.iterdir() if path.is_dir()):
        for path in sorted((RAW_DIR / folder).glob("*.mat")):
            name_info = rawio.parse_filename(path.name)
            records.append({
                "folder": folder,
                "file": path.name,
                "path": path,
                "test_type": name_info["test_type"] if name_info else "other",
                "test_number": name_info["test_number"] if name_info else None,
                "descriptor": name_info["descriptor"] if name_info else path.stem,
            })
    return records


def rows_used(record, data):
    """Row numbers (as stored) that the S1 loader keeps, in order.

    The rules, applied in this order (docs/decisions.md 1.9, docs/model.md):
    1. Drop rows with Voltage <= 0 (the cycler's end-of-test sentinel) and
       rows with NaN in Time, Voltage, Current, Ah or Battery_Temp_degC.
    2. Per-file cuts: 571_Mixed6 starts at row 391 (after a hidden pause), and
       582_LA92 keeps only rows dated 26/11/2018 (the real run). Steps 1 and 2
       commute, because every dropped row lies outside the rows the cuts keep.
    3. Of consecutive kept rows that share one Time value, keep the last:
       at a step change it holds the new step's values.
    """
    n_rows = len(data["Time"])
    keep = np.ones(n_rows, dtype=bool)

    key = run_key(record)
    if key in FIRST_ROW_USED:
        keep[:FIRST_ROW_USED[key]] = False
    if key in ONLY_ROWS_DATED:
        year, month, day = ONLY_ROWS_DATED[key]
        for k in range(n_rows):
            stamp = rawio.parse_timestamp(data["TimeStamp"][k])
            if (stamp.year, stamp.month, stamp.day) != (year, month, day):
                keep[k] = False

    for name in LOADER_FIELDS:
        keep &= ~np.isnan(data[name])
    keep &= ~(data["Voltage"] <= 0.0)

    rows = np.where(keep)[0]
    times = data["Time"][rows]
    is_last_of_its_time = np.concatenate((times[1:] != times[:-1], [True]))
    return rows[is_last_of_its_time]


def run_role(record):
    """'evaluation', 'tuning cycle' or 'excluded: <reason>' for a drive file (the evaluation set of docs/decisions.md)."""
    return NOT_EVALUATED.get(run_key(record), "evaluation")


# ----------------------------------------------------------------------------
# One pass over every file: facts that need every file
# ----------------------------------------------------------------------------

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
    cv = (current > 0.0) & (voltage >= CV_VOLTAGE_V)
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


# ----------------------------------------------------------------------------
# HPPC files (section 10)
# ----------------------------------------------------------------------------

def current_segments(time_s, current):
    """Split rows into runs of discharge (-1, I < -50 mA), rest (0) and charge (+1, I > +50 mA).

    Returns a list of dicts with first and last (positions in the arrays given),
    kind, and duration_s = Time of the first row after the run minus Time of
    its first row (the step lasted until the next logged row showed otherwise).
    The last run ends at the last row.
    """
    kind = np.where(current < -FLOW_CURRENT_A, -1, np.where(current > FLOW_CURRENT_A, 1, 0))
    boundaries = np.concatenate(([0], np.where(np.diff(kind) != 0)[0] + 1, [len(kind)]))
    segments = []
    for first, end in zip(boundaries[:-1], boundaries[1:]):
        end_time = time_s[end] if end < len(time_s) else time_s[-1]
        segments.append({"first": int(first), "last": int(end - 1), "kind": int(kind[first]),
                         "duration_s": float(end_time - time_s[first])})
    return segments


def dt_class(step_s):
    """Name the logging interval of one step: 0.1, 1, 10 or 60 s."""
    if step_s < 0.5:
        return "0.1 s"
    if step_s < 5.0:
        return "1 s"
    if step_s < 30.0:
        return "10 s"
    return "60 s"


def logging_pattern(time_s, first, after):
    """Logging intervals over a rest, e.g. '0.1 s to 9.9 s, 1 s to 59.9 s, 10 s to 599.9 s'.

    first: position of the rest's first row; after: position of the first row
    after the rest (the next pulse), so the last step into the next pulse
    counts. Each part gives the interval and the elapsed time (from the
    rest's first row) at which that interval stops being used.
    """
    parts = []
    current_class = None
    for k in range(first + 1, after + 1):
        step_class = dt_class(time_s[k] - time_s[k - 1])
        elapsed = time_s[k] - time_s[first]
        if step_class != current_class:
            parts.append([step_class, elapsed])
            current_class = step_class
        else:
            parts[-1][1] = elapsed
    return ", ".join(f"{name} to {fmt(end, 1)} s" for name, end in parts)


def most_common(texts):
    """'<most common text> (n of N)' plus the number of other variants."""
    counts = {}
    for text in texts:
        counts[text] = counts.get(text, 0) + 1
    best = max(sorted(counts), key=lambda text: counts[text])
    result = f"{best} ({counts[best]} of {len(texts)})"
    if len(counts) > 1:
        result += f"; {len(counts) - 1} other pattern{'s' if len(counts) > 2 else ''}"
    return result


def analyse_hppc(record, data):
    """Describe one HPPC file: levels, pulses, moves, rests, limits, first-sample rule, relaxation, resets.

    The rows used are the loader's (keep-last, no NaN, V > 0). A pulse is a
    current step of at most 12 s; a move is a longer discharge before the
    final recharge; a level is the group of pulses between two moves.
    Inside a level the discharge pulses are numbered D1-D4 and the charge
    pulses C1-C4 in the order they occur.
    """
    rows = rows_used(record, data)
    t = data["Time"][rows]
    v = data["Voltage"][rows]
    i = data["Current"][rows]
    ah = data["Ah"][rows]
    segments = current_segments(t, i)

    long_charges = [s for s in segments if s["kind"] == 1 and s["duration_s"] > PULSE_MAX_S]
    recharge_first = long_charges[0]["first"] if long_charges else len(t)

    levels = []           # list of lists of pulse segments
    moves = []
    current_level = []
    for index, s in enumerate(segments):
        s["index"] = index
        if s["kind"] != 0 and s["duration_s"] <= PULSE_MAX_S and s["first"] < recharge_first:
            current_level.append(s)
        elif s["kind"] != 0:
            if current_level:
                levels.append(current_level)
                current_level = []
            if s["kind"] == -1 and s["first"] < recharge_first:
                moves.append(s)
    if current_level:
        levels.append(current_level)

    def rest_after(s):
        """The rest segment right after s, or None (also when the file ends on its first row)."""
        following = segments[s["index"] + 1] if s["index"] + 1 < len(segments) else None
        if following is None or following["kind"] != 0 or following["duration_s"] <= 0.0:
            return None
        return following

    def next_active(s):
        """The first non-rest segment after s, or None."""
        for later in segments[s["index"] + 1:]:
            if later["kind"] != 0:
                return later
        return None

    pulses = []
    for level_number, level in enumerate(levels, start=1):
        n_d = n_c = 0
        for s in level:
            if s["kind"] == -1:
                n_d += 1
                position = f"D{n_d}"
            else:
                n_c += 1
                position = f"C{n_c}"
            a, b = s["first"], s["last"]
            pulse_v = v[a:b + 1]
            pulse_i = i[a:b + 1]
            command = float(np.median(pulse_i))
            reached = np.where(np.abs(pulse_i) >= FIRST_SAMPLE_FRACTION * abs(command))[0]
            before_time = t[a - 1] if a > 0 else t[a]
            reach_s = float(t[a + reached[0]] - before_time) if len(reached) else float("inf")
            reach_from_first_s = float(t[a + reached[0]] - t[a]) if len(reached) else float("inf")
            reach_row = int(reached[0]) + 1 if len(reached) else None   # 1 = the pulse's first row
            low_limited = s["kind"] == -1 and float(np.min(pulse_v)) <= LOW_LIMIT_V
            high_limited = s["kind"] == 1 and float(np.max(pulse_v)) >= HIGH_LIMIT_V
            pulses.append({
                "level": level_number, "position": position, "kind": s["kind"],
                "duration_s": s["duration_s"], "command_a": command,
                "first_sample_ok": abs(pulse_i[0]) >= FIRST_SAMPLE_FRACTION * abs(command),
                "reach_s": reach_s, "reach_from_first_s": reach_from_first_s, "reach_row": reach_row,
                "low_limited": low_limited, "high_limited": high_limited,
                "full": s["duration_s"] >= FULL_PULSE_S and not low_limited and not high_limited,
                "rest": rest_after(s),
            })

    # Rests and their logging.
    d_rests = [p["rest"] for p in pulses if p["kind"] == -1 and p["rest"] is not None]
    c_rests = [p["rest"] for p in pulses if p["kind"] == 1 and p["rest"] is not None]
    hour_rests = []        # rests after a move that are followed by a pulse level
    final_rests = []       # the rest after the last move (followed by the recharge or the file end)
    for m in moves:
        rest = rest_after(m)
        if rest is None:
            continue
        following = next_active(rest)
        if following is not None and following["duration_s"] <= PULSE_MAX_S:
            hour_rests.append(rest)
        else:
            final_rests.append(rest)

    def pattern_of(rest):
        after = rest["last"] + 1 if rest["last"] + 1 < len(t) else rest["last"]
        return logging_pattern(t, rest["first"], after)

    def relaxation_mv(rest):
        """V at the last row of the rest minus V 600 s earlier (interpolated), in mV."""
        a, b = rest["first"], rest["last"]
        v_earlier = float(np.interp(t[b] - RELAX_WINDOW_S, t[a:b + 1], v[a:b + 1]))
        return 1000.0 * (v[b] - v_earlier)

    # Logging inside the discharge pulses and their 40 s rests.
    pulse_steps = []
    for p_seg, p in zip([s for level in levels for s in level], pulses):
        if p["kind"] == -1 and p["rest"] is not None:
            pulse_steps.append(np.diff(t[p_seg["first"]:p["rest"]["last"] + 2]))
    pulse_steps = np.concatenate(pulse_steps) if pulse_steps else np.array([np.nan])

    # In-file recharge after the pulse train.
    recharge_cc = float("nan")
    recharge_row = None
    if long_charges:
        s = long_charges[0]
        charge_i = i[s["first"]:s["last"] + 1]
        recharge_cc = (float(np.median(charge_i[charge_i > RECHARGE_MIN_A])) if np.any(charge_i > RECHARGE_MIN_A)
                       else float("nan"))
        recharge_row = int(rows[s["first"]])

    stored_t = data["Time"]
    resets = [(k, float(stored_t[k])) for k in counter_resets(stored_t, data["Current"], data["Ah"])]

    return {
        "record": record,
        "levels": len(levels),
        "pulses": pulses,
        "moves": [{"end_ah": float(ah[m["last"]]), "end_v": float(v[m["last"]]),
                   "median_a": float(np.median(i[m["first"]:m["last"] + 1])), "duration_s": m["duration_s"]}
                  for m in moves],
        "d_rest_s": [r["duration_s"] for r in d_rests],
        "c_rest_s": [r["duration_s"] for r in c_rests],
        "hour_rest_s": [r["duration_s"] for r in hour_rests],
        "final_rest_s": [r["duration_s"] for r in final_rests],
        "d_rest_pattern": most_common([pattern_of(r) for r in d_rests]),
        "c_rest_pattern": most_common([pattern_of(r) for r in c_rests]),
        "hour_rest_pattern": most_common([pattern_of(r) for r in hour_rests]),
        "final_rest_pattern": most_common([pattern_of(r) for r in final_rests]) if final_rests else "none",
        "relax_mv": [relaxation_mv(r) for r in hour_rests if r["duration_s"] > ONE_HOUR_REST_S],
        "final_relax_mv": [relaxation_mv(r) for r in final_rests if r["duration_s"] > ONE_HOUR_REST_S],
        "pulse_steps": pulse_steps,
        "recharge_cc_a": recharge_cc,
        "recharge_row": recharge_row,
        "recharge_time_s": float(stored_t[recharge_row]) if recharge_row is not None else float("nan"),
        "resets": resets,
    }


def position_median(hppc, position):
    """Median command current of the full-length pulses at one position (D1..D4, C1..C4), cycler sign."""
    values = [p["command_a"] for p in hppc["pulses"] if p["position"] == position and p["full"]]
    return float(np.median(values)) if values else float("nan")


# ----------------------------------------------------------------------------
# C/20 files (sections 11 and 12) and the other capacity files (13, 15)
# ----------------------------------------------------------------------------

def analyse_c20(record, data, q_ref):
    """Describe one C20DisCh file: both halves, monotonicity, PCHIP check, alignment gaps.

    q_ref is None while Q_ref itself is being measured (the 25 degC file);
    then the SoC-axis quantities are left out.

    Discharge half: the longest run of rows with I < -50 mA. The file opens
    one 60 s interval into the step, after a counter reset at the step
    start, so Ah removed = -Ah, counted from that zero (docs/decisions.md).
    Charge half: from the first row after the discharge with I > +50 mA to
    the last row with I > 0 (the CV cutoff). The CV phase starts at the
    first charge row at or above 4.1995 V.
    """
    rows = rows_used(record, data)
    t = data["Time"][rows]
    v = data["Voltage"][rows]
    i = data["Current"][rows]
    ah = data["Ah"][rows]
    temp = data["Battery_Temp_degC"][rows]
    positions = np.arange(len(rows))

    dis_first, dis_last = longest_run(i < -FLOW_CURRENT_A)
    charge_first = int(np.where((i > FLOW_CURRENT_A) & (positions > dis_last))[0][0])
    charge_last = int(np.where((i > 0.0) & (positions > dis_last))[0][-1])
    cv_first = int(np.where((v >= CV_START_V) & (positions >= charge_first))[0][0])

    removed = -ah[dis_first:dis_last + 1]                  # counted from the step-start zero
    v_dis = v[dis_first:dis_last + 1]
    q_dis = float(removed[-1])
    added = ah[charge_first:charge_last + 1] - ah[dis_last]
    v_chg = v[charge_first:charge_last + 1]
    q_chg = float(added[-1])

    rises = np.diff(v_dis)
    rebound = v_dis - np.minimum.accumulate(v_dis)
    v_cc = v[charge_first:cv_first]
    falls = np.diff(v_cc)
    dip = np.maximum.accumulate(v_cc) - v_cc if len(v_cc) else np.array([0.0])

    result = {
        "record": record,
        "dis_rows": (int(rows[dis_first]), int(rows[dis_last])),
        "dis_median_a": float(np.median(i[dis_first:dis_last + 1])),
        "dis_end_time_s": float(t[dis_last]),
        "dis_end_v": float(v[dis_last]),
        "dis_end_ah": float(ah[dis_last]),
        "ah_first": float(data["Ah"][0]),
        "q_dis": q_dis,
        "q_chg": q_chg,
        "rest_s": float(t[charge_first] - t[dis_last]),
        "rest_from_first_rest_row_s": float(t[charge_first] - t[dis_last + 1]),
        "cc_median_a": float(np.median(i[charge_first:cv_first])),
        "cv_median_v": float(np.median(v[cv_first:charge_last + 1])),
        "cutoff_a": float(i[charge_last]),
        "cc_s": float(t[cv_first] - t[charge_first]),
        "cv_s": float(t[charge_last] - t[cv_first]),
        "temp_dis": (float(np.min(temp[dis_first:dis_last + 1])), float(np.max(temp[dis_first:dis_last + 1]))),
        "temp_chg": (float(np.min(temp[charge_first:charge_last + 1])),
                     float(np.max(temp[charge_first:charge_last + 1]))),
        "n_dis": len(v_dis),
        "rises": int(np.sum(rises > 0.0)),
        "largest_rise_mv": 1000.0 * float(max(np.max(rises), 0.0)),
        "largest_rebound_mv": 1000.0 * float(np.max(rebound)),
        "n_cc": len(v_cc),
        "falls": int(np.sum(falls < 0.0)),
        "largest_fall_mv": 1000.0 * float(max(-np.min(falls), 0.0)) if len(falls) else 0.0,
        "largest_dip_mv": 1000.0 * float(np.max(dip)),
        "removed_strictly_increasing": bool(np.all(np.diff(removed) > 0.0)),
    }
    if q_ref is None:
        return result

    # PCHIP through the raw discharge half on the Q_ref SoC axis, sampled on the 101-point grid.
    soc_dis = 1.0 - removed / q_ref
    order = np.argsort(soc_dis)
    pchip = PchipInterpolator(soc_dis[order], v_dis[order])
    grid = np.arange(101) / 100.0
    inside = grid[(grid >= soc_dis.min()) & (grid <= soc_dis.max())]
    resampled = pchip(inside)
    result.update({
        "end_soc": 1.0 - q_dis / q_ref,
        "pchip_points": len(inside),
        "pchip_range": (float(inside.min()), float(inside.max())),
        "pchip_monotone": bool(np.all(np.diff(resampled) > 0.0)),
        "pchip_smallest_step_mv": 1000.0 * float(np.min(np.diff(resampled))),
    })

    # Charge-minus-discharge voltage at the same SoC under four ways of placing the charge half.
    soc_a = 1.0 - (q_dis - added) / q_ref          # A: same Ah removed, counted back from the discharge end
    own_dis = 1.0 - removed / q_dis                # B and C: discharge on its own Ah span
    own_chg = added / q_chg                        # B: charge on its own Ah span
    scaled_chg = added / q_dis                     # C: charge Ah from the discharge end, scaled by the discharge Ah
    soc_d = 1.0 - (q_chg - added) / q_ref          # D: charge ends at SoC 1 on the Q_ref axis
    gap = {
        "A50": value_at(soc_a, v_chg, 0.5) - value_at(soc_dis, v_dis, 0.5),
        "B50": value_at(own_chg, v_chg, 0.5) - value_at(own_dis, v_dis, 0.5),
        "C50": value_at(scaled_chg, v_chg, 0.5) - value_at(own_dis, v_dis, 0.5),
        "D50": value_at(soc_d, v_chg, 0.5) - value_at(soc_dis, v_dis, 0.5),
        "A80": value_at(soc_a, v_chg, 0.8) - value_at(soc_dis, v_dis, 0.8),
    }
    result["gap_mv"] = {name: 1000.0 * value for name, value in gap.items()}
    return result


def analyse_capacity_file(record, data):
    """Counter start, discharge end and in-file recharge of a C20DisCh, Dis_0p5C or Dis_2C file (section 13)."""
    time_s = data["Time"]
    current = data["Current"]
    ah = data["Ah"]
    dis_first, dis_last = longest_run(current < -FLOW_CURRENT_A)
    interval_s = float(time_s[1] - time_s[0])
    after = np.where((current > RECHARGE_MIN_A) & (np.arange(len(current)) > dis_last))[0]
    return {
        "record": record,
        "ah_first": float(ah[0]),
        "i_first": float(current[0]),
        "interval_s": interval_s,
        "ah_back_one_interval": float(ah[0] - current[0] * interval_s / 3600.0),
        "ah_dis_end": float(ah[dis_last]),
        "ah_last": float(ah[-1]),
        "dis_median_a": float(np.median(current[dis_first:dis_last + 1])),
        "recharge_cc_a": float(np.median(current[after])) if len(after) else float("nan"),
        "resets": counter_resets(time_s, current, ah),
    }


# ----------------------------------------------------------------------------
# Sections 1 to 9: drive files, duplicates, gaps, special files, temperatures, runs, charges
# ----------------------------------------------------------------------------

def drive_records(records, folder=None):
    """Drive files (UDDS, HWFET, LA92, US06, Mixed1-8), optionally of one folder."""
    return [r for r in records if r["test_type"] in DRIVE_TYPES and (folder is None or r["folder"] == folder)]


def previous_file(record, records):
    """The file of the same folder whose first TimeStamp comes last before this file's first TimeStamp."""
    earlier = [r for r in records if r["folder"] == record["folder"] and r["start"] < record["start"]]
    return max(earlier, key=lambda r: r["start"]) if earlier else None


def section_steps(folders, records):
    """Section 1: drive-cycle step statistics per folder and in total."""
    drives = drive_records(records)
    lines = ["## 1. Drive-cycle sampling steps", ""]
    lines.append(f"Source: all {len(drives)} drive files (UDDS, HWFET, LA92, US06, Mixed1 to Mixed8; names in "
                 "section 7), every row as stored. A step is Time[k] - Time[k-1]. The median and the 1st and 99th "
                 "percentiles are taken over the steps with dt > 0, as in `results/s0/data_inventory.md`.")
    lines.append("")
    lines.append(f"| folder | drive files | steps | steps in {DT_BAND_S[0]} to {DT_BAND_S[1]} s (%) | dt = 0 | dt < 0 "
                 f"| dt > {LONG_STEP_S} s | dt > {GAP_S:.0f} s | median dt (s) | 1st percentile (s) "
                 "| 99th percentile (s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for folder in folders + ["all"]:
        files = drives if folder == "all" else drive_records(records, folder)
        steps = np.concatenate([r["steps"] for r in files])
        positive = steps[steps > 0.0]
        in_band = np.sum((steps >= DT_BAND_S[0]) & (steps <= DT_BAND_S[1]))
        lines.append(f"| {folder} | {len(files)} | {len(steps)} | {fmt(100.0 * in_band / len(steps), 3)} "
                     f"| {int(np.sum(steps == 0.0))} | {int(np.sum(steps < 0.0))} | {int(np.sum(steps > LONG_STEP_S))} "
                     f"| {int(np.sum(steps > GAP_S))} | {fmt(np.median(positive), 3)} "
                     f"| {fmt(np.percentile(positive, 1), 3)} | {fmt(np.percentile(positive, 99), 3)} |")
    lines.append("")
    return lines


def section_duplicates(records):
    """Section 2: duplicate-Time rows in every file, per test type, in the HPPC files and at drive-file ends."""
    lines = ["## 2. Duplicate Time rows", ""]
    lines.append("Source: all files, every row as stored. A duplicate is a row whose Time equals the previous "
                 "row's Time (the *dup* column of `results/s0/data_inventory.md`). A duplicate pair *differs* when "
                 "the two rows have different Current or Voltage; pairs with a NaN are counted apart.")
    lines.append("")
    with_duplicates = [r for r in records if r["n_duplicates"] > 0]
    total = sum(r["n_duplicates"] for r in records)
    lines.append(f"- **Total:** {total} duplicate rows in {len(with_duplicates)} of {len(records)} files.")
    pairs = [(r, pair) for r in records for pair in r["differing_pairs"]]
    nan_pairs = sum(r["n_nan_pairs"] for r in records)
    files_with_pairs = [r for r in records if r["differing_pairs"]]
    lines.append(f"- **Pairs that differ, all files:** {len(pairs)} in {len(files_with_pairs)} files (" +
                 ", ".join(f"{label(r)} {len(r['differing_pairs'])}" for r in files_with_pairs) + "); the largest "
                 f"difference is {fmt(1000.0 * max(p[1] for _, p in pairs), 2)} mA in Current and "
                 f"{fmt(1000.0 * max(p[2] for _, p in pairs), 3)} mV in Voltage. Pairs with a NaN: {nan_pairs} "
                 "(`10degC/582_LA92`, section 4).")
    stall = find_record(records, "n10degC", "602_Mixed4")
    lines.append(f"- **{label(stall)}** holds {stall['n_duplicates']} of the "
                 f"{sum(r['n_duplicates'] for r in drive_records(records))} duplicate rows in drive files: "
                 f"{stall['longest_same_time_rows'] - 1} in its frozen block of {stall['longest_same_time_rows']} rows "
                 f"(section 4c) and {stall['n_duplicates'] - stall['longest_same_time_rows'] + 1} elsewhere.")
    drives = drive_records(records)
    ends = [r for r in drives if r["ends_on_duplicate"]]
    ends_zero = [r for r in drives if r["ends_on_duplicate_zero"]]
    lines.append(f"- **Drive files that end on a duplicated row:** {len(ends)} of {len(drives)}; in "
                 f"{len(ends_zero)} of them both rows have Current = 0 A.")
    lines.append("")

    lines.append("Per test type:")
    lines.append("")
    lines.append("| test type | files | files with duplicates | duplicate rows | min / max per file "
                 "| differing pairs |")
    lines.append("|---|---|---|---|---|---|")
    groups = {}
    for r in records:
        group = "drive (UDDS, HWFET, LA92, US06, Mixed1-8)" if r["test_type"] in DRIVE_TYPES else r["test_type"]
        groups.setdefault(group, []).append(r)
    for group in sorted(groups):
        files = groups[group]
        counts = [r["n_duplicates"] for r in files]
        lines.append(f"| {group} | {len(files)} | {sum(1 for c in counts if c > 0)} | {sum(counts)} "
                     f"| {min(counts)} / {max(counts)} | {sum(len(r['differing_pairs']) for r in files)} |")
    lines.append("")

    lines.append("HPPC files. *At a step end*: the pair carries |I| >= 50 mA and the next row has |I| < 50 mA, "
                 "i.e. the pair is the last sample of a current step.")
    lines.append("")
    lines.append("| file | duplicate rows | pairs that differ | of those, at a step end | rows of the other pairs "
                 "| largest dI (mA) | largest dV (mV) |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in [r for r in records if r["test_type"] == "hppc"]:
        pairs = r["differing_pairs"]
        others = [p[0] for p in pairs if not p[3]]
        lines.append(f"| {label(r)} | {r['n_duplicates']} | {len(pairs)} | {sum(1 for p in pairs if p[3])} "
                     f"| {', '.join(str(k) for k in others) if others else 'none'} "
                     f"| {fmt(1000.0 * max(p[1] for p in pairs), 2)} | {fmt(1000.0 * max(p[2] for p in pairs), 3)} |")
    lines.append("")
    return lines


def section_long_steps(records, q_ref):
    """Section 3: steps longer than 1 s inside drive files, as stored and in the rows the loader keeps."""
    lines = ["## 3. Steps longer than 1 s inside drive files", ""]
    lines.append(f"Source: the drive files listed below (the other drive files have no step above {GAP_S:.0f} s). "
                 "*As stored*: every row. *Rows used*: after the loader rules (legend). Step lengths are in s, "
                 "in file order; a row number k is the row that ends the step from row k-1 (or from the previous "
                 "kept row).")
    lines.append("")
    lines.append("| file | role | steps > 1 s as stored | largest (s) | step lengths as stored (s) "
                 "| steps > 1 s in the rows used | step lengths in the rows used (s) |")
    lines.append("|---|---|---|---|---|---|---|")
    drives = drive_records(records)
    for r in drives:
        if not r["long_steps"] and not r["used_long_steps"]:
            continue
        stored = ", ".join(fmt(dt, 3) for _, dt in r["long_steps"])
        used = ", ".join(fmt(step["dt"], 3) for step in r["used_long_steps"])
        lines.append(f"| {label(r)} | {run_role(r)} | {len(r['long_steps'])} "
                     f"| {fmt(max(dt for _, dt in r['long_steps']), 3)} | {stored} | {len(r['used_long_steps'])} "
                     f"| {used if used else 'none'} |")
    lines.append("")

    evaluated = [r for r in drives if run_role(r) == "evaluation"]
    with_long = [r for r in evaluated if r["used_long_steps"]]
    all_steps = [step for r in with_long for step in r["used_long_steps"]]
    lines.append(f"- **Evaluation runs with steps > {GAP_S:.0f} s (rows used):** {len(with_long)} "
                 f"({', '.join(label(r) for r in with_long)}); {len(all_steps)} steps of "
                 f"{fmt(min(s['dt'] for s in all_steps), 3)} to {fmt(max(s['dt'] for s in all_steps), 3)} s.")
    longest = max(all_steps, key=lambda s: s["dt"])
    regen_a = max(r["used_i_max"] for r in evaluated)
    discharge_a = -min(r["used_i_min"] for r in evaluated)
    lines.append(f"- **Bound on the charge error of one such step:** the longest step, {fmt(longest['dt'], 3)} s, "
                 f"with the largest charging (regen) current in the evaluation runs, {fmt(regen_a, 2)} A, held "
                 f"over it gives {fmt(100.0 * regen_a * longest['dt'] / 3600.0 / q_ref, 3)} pp of Q_ref; with the "
                 f"largest discharge current, {fmt(discharge_a, 2)} A, it gives "
                 f"{fmt(100.0 * discharge_a * longest['dt'] / 3600.0 / q_ref, 3)} pp.")
    worst = max(all_steps, key=lambda s: abs(s["error_pp"]))
    lines.append(f"- **Measured charge error across these steps:** the current held over each step (previous kept "
                 f"row, zero-order hold) against the counter's change over the same step, table below. The largest "
                 f"difference is {fmt(worst['error_pp'], 4)} pp; the held current is at most "
                 f"{fmt(1000.0 * max(abs(s['i_before']) for s in all_steps), 1)} mA at these steps.")
    lines.append("")
    lines.append("| file | row | Time before (s) | dt (s) | I before (A) | I after (A) | held charge removed (mAh) "
                 "| counter removed (mAh) | held minus counter (pp) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in with_long:
        for step in r["used_long_steps"]:
            lines.append(f"| {label(r)} | {step['row']} | {fmt(step['time_before'], 3)} | {fmt(step['dt'], 3)} "
                         f"| {fmt(step['i_before'], 4)} | {fmt(step['i_after'], 4)} | {fmt(step['held_mah'], 4)} "
                         f"| {fmt(step['counter_mah'], 4)} | {fmt(step['error_pp'], 5)} |")
    lines.append("")
    return lines


def find_record(records, folder, key):
    """The record of one folder whose run key (test number and first descriptor word) is key."""
    found = [r for r in records if r["folder"] == folder and run_key(r) == key]
    if len(found) != 1:
        raise ValueError(f"expected one file {folder}/{key}, found {len(found)}")
    return found[0]


def section_special_files(records, q_ref):
    """Section 4: the evidence behind the three per-file rules (571_Mixed6, 582_LA92, 602_Mixed4)."""
    lines = ["## 4. The three damaged drive files", ""]

    # 571_Mixed6: hidden pause between two rows.
    r = find_record(records, "10degC", "571_Mixed6")
    data = rawio.load_mat(r["path"])
    t, v, i, ah, temp, stamps = (data["Time"], data["Voltage"], data["Current"], data["Ah"],
                                 data["Battery_Temp_degC"], data["TimeStamp"])
    stamp_jumps = [(rawio.parse_timestamp(stamps[k]) - rawio.parse_timestamp(stamps[k - 1])).total_seconds()
                   for k in range(1, len(stamps))]
    k = int(np.argmax(stamp_jumps)) + 1                          # first row after the largest TimeStamp jump
    removed_before = -(ah[k] - ah[0])
    lines.append(f"### 4a. {label(r)}")
    lines.append("")
    lines.append(f"Source: `data/raw/10degC/{r['file']}`.")
    lines.append("")
    lines.append(f"- **Hidden pause:** the largest TimeStamp jump is between rows {k - 1} and {k}: "
                 f"{fmt(stamp_jumps[k - 1], 3)} s ({fmt(stamp_jumps[k - 1] / 3600.0, 2)} h; TimeStamps "
                 f"`{stamps[k - 1]}` and `{stamps[k]}`), while Time advances {fmt(t[k] - t[k - 1], 3)} s.")
    lines.append(f"- **Row {k - 1}:** Time {fmt(t[k - 1], 3)} s, V {fmt(v[k - 1], 4)} V, I {fmt(i[k - 1], 5)} A, "
                 f"Ah {fmt(ah[k - 1], 5)} Ah, T {fmt(temp[k - 1], 2)} degC.")
    lines.append(f"- **Row {k}:** Time {fmt(t[k], 3)} s, V {fmt(v[k], 4)} V, I {fmt(i[k], 5)} A, "
                 f"Ah {fmt(ah[k], 5)} Ah, T {fmt(temp[k], 2)} degC. Row 0 has Ah {fmt(ah[0], 5)} Ah.")
    lines.append(f"- **SoC0 when the run starts at row {k}:** 1 - Ah_removed / Q_ref with Ah_removed = -(Ah[{k}] - "
                 f"Ah[0]) = {fmt(removed_before, 5)} Ah, so SoC0 = {fmt(1.0 - removed_before / q_ref, 5)}.")
    lines.append("")

    # 582_LA92: false start spliced in front of the real run.
    r = find_record(records, "10degC", "582_LA92")
    data = rawio.load_mat(r["path"])
    t, v, i, ah, stamps = data["Time"], data["Voltage"], data["Current"], data["Ah"], data["TimeStamp"]
    dates = [rawio.parse_timestamp(stamp).date() for stamp in stamps]
    year, month, day = ONLY_ROWS_DATED["582_LA92"]
    real = np.array([(d.year, d.month, d.day) == (year, month, day) for d in dates])
    first_real = int(np.where(real)[0][0])
    stray = [k for k in range(first_real, len(t)) if not real[k]]
    false_start = np.arange(first_real)
    lowest = int(false_start[np.nanargmin(ah[:first_real])])
    backward = [(k, float(t[k] - t[k - 1])) for k in range(1, len(t)) if t[k] - t[k - 1] < 0.0]
    used = rows_used(r, data)
    removed_before = -(ah[first_real] - ah[0])
    date_counts = {}
    for d in dates:
        date_counts[d] = date_counts.get(d, 0) + 1
    lines.append(f"### 4b. {label(r)}")
    lines.append("")
    lines.append(f"Source: `data/raw/10degC/{r['file']}`.")
    lines.append("")
    lines.append("- **Rows per TimeStamp date:** " +
                 ", ".join(f"{d:%d/%m/%Y}: {n}" for d, n in sorted(date_counts.items())) + f" (of {len(t)} rows).")
    lines.append(f"- **False start:** rows 0 to {first_real - 1}, Time {fmt(t[0], 3)} to {fmt(t[first_real - 1], 3)} s. "
                 f"Its counter is lowest at row {lowest} ({fmt(ah[lowest], 5)} Ah) and ends at "
                 f"{fmt(ah[first_real - 1], 5)} Ah at row {first_real - 1}, which is at {fmt(v[first_real - 1], 4)} V "
                 f"and {fmt(i[first_real - 1], 4)} A.")
    jump = (rawio.parse_timestamp(stamps[first_real]) - rawio.parse_timestamp(stamps[first_real - 1])).total_seconds()
    lines.append(f"- **Pause before the real run:** TimeStamp jumps {fmt(jump, 3)} s ({fmt(jump / 3600.0, 2)} h) "
                 f"between rows {first_real - 1} and {first_real}; Time advances {fmt(t[first_real] - t[first_real - 1], 3)} s.")
    lines.append(f"- **First row of the real run:** row {first_real} (`{stamps[first_real]}`), Time "
                 f"{fmt(t[first_real], 3)} s, V {fmt(v[first_real], 5)} V, I {fmt(i[first_real], 4)} A, Ah "
                 f"{fmt(ah[first_real], 5)} Ah. Row 0 has Ah {fmt(ah[0], 5)} Ah, so Ah_removed before the run = "
                 f"{fmt(removed_before, 5)} Ah and SoC0 = 1 - {fmt(removed_before, 5)} / Q_ref = "
                 f"{fmt(1.0 - removed_before / q_ref, 5)}.")
    lines.append(f"- **Rows dated {stamps[0].split()[0]} inside the real run (row {first_real} onward):** "
                 f"{stored_rows_text(stray)}.")
    nan_text = "; ".join(f"row {k}: {', '.join(fields)}" for k, fields in r["nan_rows"])
    lines.append(f"- **NaN rows:** {nan_text}.")
    lines.append("- **Backward Time steps:** " + "; ".join(
        f"rows {k - 1} to {k}: {fmt(step, 3)} s (dates {dates[k - 1]:%d/%m} and {dates[k]:%d/%m})"
        for k, step in backward) + ".")
    used_steps = np.diff(t[used])
    lines.append(f"- **Rows used (only rows dated {day:02d}/{month:02d}/{year}, then the general loader rules):** "
                 f"{len(used)} rows, Time {fmt(t[used[0]], 3)} to {fmt(t[used[-1]], 3)} s, smallest step "
                 f"{fmt(np.min(used_steps), 3)} s, {int(np.sum(used_steps > GAP_S))} steps above {GAP_S:.0f} s "
                 "(section 3).")
    lines.append("")

    # 602_Mixed4: frozen rows, then an unlogged interval.
    r = find_record(records, "n10degC", "602_Mixed4")
    data = rawio.load_mat(r["path"])
    t, v, i, ah, temp, stamps = (data["Time"], data["Voltage"], data["Current"], data["Ah"],
                                 data["Battery_Temp_degC"], data["TimeStamp"])
    same_as_previous = np.concatenate(([False], t[1:] == t[:-1]))
    first_dup, last_dup = longest_run(same_as_previous)
    block_first = first_dup - 1                       # the row the duplicates repeat
    block_last = last_dup
    identical = all(np.all(data[name][block_first:block_last + 1] == data[name][block_first])
                    for name in NUMERIC_FIELDS)
    stamps_identical = len(set(stamps[block_first:block_last + 1])) == 1
    after = block_last + 1
    gap_s = float(t[after] - t[block_last])
    stamp_gap_s = (rawio.parse_timestamp(stamps[after]) - rawio.parse_timestamp(stamps[block_last])).total_seconds()
    counter_removed = -(ah[after] - ah[block_last])
    held_previous = -i[block_last] * gap_s / 3600.0
    held_next = -i[after] * gap_s / 3600.0
    lines.append(f"### 4c. {label(r)}")
    lines.append("")
    lines.append(f"Source: `data/raw/n10degC/{r['file']}`.")
    lines.append("")
    lines.append(f"- **Frozen rows:** rows {block_first} to {block_last} ({block_last - block_first + 1} rows, i.e. "
                 f"{block_last - block_first} duplicate rows of the file's {r['n_duplicates']}) all have "
                 f"Time {fmt(t[block_first], 3)} s; every numeric field is identical across them: "
                 f"{'yes' if identical else 'no'}; the TimeStamp is identical too: {'yes' if stamps_identical else 'no'} "
                 f"(`{stamps[block_first]}`). The frozen sample: V {fmt(v[block_first], 5)} V, I "
                 f"{fmt(i[block_first], 5)} A, Ah {fmt(ah[block_first], 5)} Ah, T {fmt(temp[block_first], 2)} degC.")
    lines.append(f"- **Gap after the frozen rows:** rows {block_last} to {after}: Time step {fmt(gap_s, 3)} s, "
                 f"TimeStamp step {fmt(stamp_gap_s, 3)} s, so the interval is unlogged rather than hidden.")
    lines.append(f"- **Counter across the gap:** {fmt(ah[block_last], 5)} to {fmt(ah[after], 5)} Ah, i.e. "
                 f"{fmt(counter_removed, 5)} Ah removed = {fmt(100.0 * counter_removed / q_ref, 3)} pp of Q_ref.")
    lines.append(f"- **Current on the rows before and after the gap:** {fmt(i[block_last], 5)} A (row {block_last}) "
                 f"and {fmt(i[after], 5)} A (row {after}). Held over the {fmt(gap_s, 3)} s step (zero-order hold), "
                 f"the row before moves SoC by {fmt(-100.0 * held_previous / q_ref, 2)} pp "
                 f"({fmt(-held_previous, 5)} Ah charged) and the row after by {fmt(-100.0 * held_next / q_ref, 2)} pp "
                 f"({fmt(held_next, 5)} Ah removed); the counter moves SoC_ref by "
                 f"{fmt(-100.0 * counter_removed / q_ref, 2)} pp.")
    lines.append(f"- **Over the whole run (rows used):** the held-current coulomb counter ends "
                 f"{fmt(r['cc_minus_ref_end_pp'], 2)} pp away from the counter-based reference (section 7).")
    lines.append("")
    return lines


def section_bad_rows(records):
    """Section 5: rows with Voltage <= 0 and rows with NaN."""
    lines = ["## 5. Rows with Voltage <= 0 and rows with NaN", ""]
    lines.append("Source: all files, every row as stored. Row numbers count from 0.")
    lines.append("")
    lines.append("| file | rows | Voltage <= 0 | rows in the file |")
    lines.append("|---|---|---|---|")
    for r in records:
        if r["zero_voltage_rows"]:
            rows = [k for k, _ in r["zero_voltage_rows"]]
            values = sorted(set(fmt(value, 3) for _, value in r["zero_voltage_rows"]))
            lines.append(f"| {label(r)} | {stored_rows_text(rows)} | {', '.join(values)} V | {r['n_rows']} |")
    lines.append("")
    lines.append("| file | row | fields that are NaN |")
    lines.append("|---|---|---|")
    for r in records:
        for k, fields in r["nan_rows"]:
            lines.append(f"| {label(r)} | {k} | {', '.join(fields)} |")
    lines.append("")
    n_zero = sum(1 for r in records if r["zero_voltage_rows"])
    n_nan = sum(1 for r in records if r["nan_rows"])
    lines.append(f"- Files with rows at Voltage <= 0: {n_zero}. Files with NaN rows: {n_nan}. No other file has either.")
    lines.append("")
    return lines


def temperature_text(values):
    """'median (5th to 95th percentile)' of temperatures in degC."""
    return (f"{fmt(np.median(values), 2)} ({fmt(np.percentile(values, 5), 2)} to "
            f"{fmt(np.percentile(values, 95), 2)})")


def section_temperatures(folders, records):
    """Section 6: pooled cell temperature during drive cycles per folder."""
    lines = ["## 6. Cell temperature during drive cycles", ""]
    lines.append("Source: the drive files of each folder, field Battery_Temp_degC, pooled over samples. "
                 "Values are median (5th to 95th percentile) in degC. *All drive files*: every row with a finite "
                 "temperature. *Without 562_Mixed4-8*: the same, leaving out the five partial 40 degC runs. "
                 "*Evaluation set*: the 62 evaluation runs, rows used (legend).")
    lines.append("")
    lines.append("| folder | grid node (degC) | all drive files | without 562_Mixed4-8 | evaluation set, rows used |")
    lines.append("|---|---|---|---|---|")
    for folder in folders:
        files = drive_records(records, folder)
        all_temps = np.concatenate([r["temp_all"] for r in files])
        without = np.concatenate([r["temp_all"] for r in files if not run_key(r).startswith("562_Mixed")])
        evaluated = np.concatenate([r["temp_used"] for r in files if run_role(r) == "evaluation"])
        lines.append(f"| {folder} | {fmt(FOLDER_TEMPS_DEGC[folder], 0)} | {temperature_text(all_temps)} "
                     f"| {temperature_text(without)} | {temperature_text(evaluated)} |")
    lines.append("")
    partial = [r for r in drive_records(records) if run_key(r).startswith("562_Mixed")]
    partial_temps = np.concatenate([r["temp_all"] for r in partial])
    lines.append(f"- The five 562 partial runs alone ({', '.join(label(r) for r in partial)}): "
                 f"{temperature_text(partial_temps)} degC, min / max {fmt(np.min(partial_temps), 2)} / "
                 f"{fmt(np.max(partial_temps), 2)} degC.")
    lines.append("")
    return lines


def guard_threshold_a(duration_s, q_ref):
    """Smallest offset (A) whose coulomb-counting drift over duration_s reaches the 5 pp guard."""
    return OFFSET_GUARD_PP * 3600.0 * q_ref / (100.0 * duration_s)


def drift_pp(offset_a, duration_s, q_ref):
    """Coulomb-counting drift in pp after duration_s with a constant offset: 100 * dI * t / (3600 * Q_ref)."""
    return 100.0 * offset_a * duration_s / (3600.0 * q_ref)


def section_runs(folders, records, q_ref):
    """Section 7: run durations, reference SoC at the end, coulomb counter against the reference, offset guard."""
    lines = ["## 7. Run durations, reference SoC and the offset guard", ""]
    lines.append("Source: the drive files below and the six PausCycl files. *Duration as stored*: last Time minus "
                 "first Time. *Rows used*: after the loader rules (legend). *Window*: Time from the first row used "
                 f"to the last row with SoC_ref >= {fmt(100 * WINDOW_SOC, 0)} % (the spec's evaluation window). "
                 "SoC_ref follows the cycler's counter: SoC_ref = SoC0 - Ah_removed / Q_ref with Ah_removed = "
                 "-(Ah - Ah at the first row used), and SoC0 = 1 - (Ah the counter removed before the first row "
                 "used) / Q_ref. *CC - ref*: the coulomb-counting baseline (the project-sign current of the previous "
                 "kept row held over the actual dt) minus SoC_ref, at the end and the largest absolute difference "
                 "over the run, in pp.")
    lines.append("")
    lines.append("| file | role | duration as stored (s) | first row used | duration, rows used (s) | window (s) "
                 "| SoC0 | SoC_ref at end (%) | CC - ref at end (pp) | max abs(CC - ref) (pp) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for folder in folders:
        for r in sorted(drive_records(records, folder), key=lambda r: r["start"]):
            lines.append(f"| {label(r)} | {run_role(r)} | {fmt(r['stored_duration_s'], 1)} | {r['first_row_used']} "
                         f"| {fmt(r['used_duration_s'], 1)} | {fmt(r['window_s'], 1)} | {fmt(r['soc0'], 5)} "
                         f"| {fmt(100.0 * r['soc_end'], 2)} | {fmt(r['cc_minus_ref_end_pp'], 3)} "
                         f"| {fmt(r['cc_minus_ref_max_pp'], 3)} |")
    lines.append("")

    evaluated = [r for r in drive_records(records) if run_role(r) == "evaluation"]
    lines.append(f"Evaluation set ({len(evaluated)} runs) per folder. *Travel after a start level L*: L minus "
                 f"max(SoC_ref at end, {fmt(100 * WINDOW_SOC, 0)} %), the SoC range inside the window after an "
                 "experiment-3 start at L; min / max over the folder's runs.")
    lines.append("")
    lines.append("| folder | runs | shortest run (s) | longest run (s) | SoC_ref at end, min / max (%) "
                 + "".join(f"| travel after {fmt(100 * level, 0)} %, min / max (pp) " for level in EXP3_START_SOC)
                 + "| largest max abs(CC - ref) (pp) |")
    lines.append("|---" * (6 + len(EXP3_START_SOC)) + "|")
    for folder in folders:
        runs = [r for r in evaluated if r["folder"] == folder]
        shortest = min(runs, key=lambda r: r["used_duration_s"])
        longest = max(runs, key=lambda r: r["used_duration_s"])
        ends = [100.0 * r["soc_end"] for r in runs]
        travel_cells = ""
        for level in EXP3_START_SOC:
            travel = [100.0 * (level - max(r["soc_end"], WINDOW_SOC)) for r in runs]
            travel_cells += f"| {fmt(min(travel), 2)} / {fmt(max(travel), 2)} "
        worst = max(runs, key=lambda r: r["cc_minus_ref_max_pp"])
        lines.append(f"| {folder} | {len(runs)} | {fmt(shortest['used_duration_s'], 1)} ({label(shortest)}) "
                     f"| {fmt(longest['used_duration_s'], 1)} ({label(longest)}) | {fmt(min(ends), 2)} / "
                     f"{fmt(max(ends), 2)} {travel_cells}| {fmt(worst['cc_minus_ref_max_pp'], 3)} ({label(worst)}) |")
    lines.append("")

    shortest = min(evaluated, key=lambda r: r["used_duration_s"])
    shortest_window = min(evaluated, key=lambda r: r["window_s"])
    worst = max(evaluated, key=lambda r: r["cc_minus_ref_max_pp"])
    lines.append(f"- **Coulomb counting against the reference, evaluation set:** the largest |CC - ref| over a run "
                 f"is {fmt(worst['cc_minus_ref_max_pp'], 3)} pp ({label(worst)}).")
    duration = shortest["used_duration_s"]
    lines.append(f"- **Offset guard (the spec):** drift_pp = 100 x offset x duration / (3600 x Q_ref) at the end of "
                 f"the shortest evaluation run, {label(shortest)}, {fmt(duration, 1)} s (its window is "
                 f"{fmt(shortest['window_s'], 1)} s; the shortest window is {label(shortest_window)}, "
                 f"{fmt(shortest_window['window_s'], 1)} s). " +
                 "; ".join(f"{fmt(1000 * offset, 0)} mA gives {fmt(drift_pp(offset, duration, q_ref), 3)} pp"
                           for offset in OFFSETS_A) +
                 f". The threshold for {fmt(OFFSET_GUARD_PP, 0)} pp is {fmt(1000 * guard_threshold_a(duration, q_ref), 1)} "
                 f"mA; the smallest multiple of {fmt(1000 * OFFSET_STEP_A, 0)} mA that meets it is "
                 f"{fmt(1000 * round_up(guard_threshold_a(duration, q_ref), OFFSET_STEP_A), 0)} mA.")

    paus = sorted([r for r in records if r["test_type"] == "pauscycl"], key=lambda r: r["used_duration_s"])
    partial = sorted([r for r in drive_records(records) if run_key(r).startswith("562_Mixed")],
                     key=lambda r: r["used_duration_s"])
    for name, extra in (("the six PausCycl files", paus), ("the 562 partial runs (562_Mixed4-8)", partial),
                        ("both", paus + partial)):
        candidate = min(evaluated + extra, key=lambda r: r["used_duration_s"])
        threshold = guard_threshold_a(candidate["used_duration_s"], q_ref)
        lines.append(f"- **Hypothetical, if {name} were in the set:** shortest run {label(candidate)}, "
                     f"{fmt(candidate['used_duration_s'], 1)} s; threshold {fmt(1000 * threshold, 1)} mA, so "
                     f"{fmt(1000 * round_up(threshold, OFFSET_STEP_A), 0)} mA.")
    lines.append("")
    lines.append("PausCycl files (not drive cycles; not in the evaluation set):")
    lines.append("")
    lines.append("| file | duration, rows used (s) | Ah at the last row (Ah) |")
    lines.append("|---|---|---|")
    for r in sorted(paus, key=lambda r: r["start"]):
        lines.append(f"| {label(r)} | {fmt(r['used_duration_s'], 1)} | {fmt(r['ah_last'], 5)} |")
    lines.append("")
    return lines


def charge_kind(record):
    """Short description of a Charge file for the drive-file table: CC-CV, top-up or no current."""
    charge = record.get("charge")
    if charge is None:
        return "no current"
    if charge["has_cc"]:
        return "CC-CV charge (CC above 2.9 A)"
    return f"no CC phase (peak {fmt(charge['peak_a'], 3)} A)"


def section_full_charge(folders, records):
    """Section 8: how each drive file opens, and what was logged just before it."""
    lines = ["## 8. Full-charge start of the drive files", ""]
    lines.append("Source: the 70 drive files and, for each, the previous file of its folder (by first TimeStamp). "
                 f"*Rule*: first V > {FULL_VOLTAGE_V} V and |I| < {fmt(1000 * FULL_CURRENT_A, 0)} mA on the first row. "
                 "*Gap*: first TimeStamp of the drive file minus last TimeStamp of the previous file (1 s resolution). "
                 "*Previous file's last row*: the last row with V > 0.")
    lines.append("")
    lines.append("| file | role | first row: V (V), I (A) | meets the rule | first row used: row, V (V), I (A) "
                 "| previous file | its last row: V (V), I (A) | gap (s) | previous file is |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    drives = []
    for folder in folders:
        drives += sorted(drive_records(records, folder), key=lambda r: r["start"])
    for r in drives:
        previous = r["previous"]
        meets = r["first_v"] > FULL_VOLTAGE_V and abs(r["first_i"]) < FULL_CURRENT_A
        r["meets_full_rule"] = meets
        used_text = "row 0" if r["first_row_used"] == 0 else (
            f"row {r['first_row_used']}: {fmt(r['first_used_v'], 4)}, {fmt(r['first_used_i'], 4)}")
        if previous is None:
            previous_cells = "none in the folder | n/a | n/a | n/a"
        else:
            gap = r["previous_gap_s"]
            kind = charge_kind(previous) if previous["test_type"] == "charge" else f"a {previous['test_type']} file"
            previous_cells = (f"{label(previous)} | {fmt(previous['last_valid_v'], 4)}, "
                              f"{fmt(previous['last_valid_i'], 4)} | {fmt(gap, 0)} | {kind}")
        lines.append(f"| {label(r)} | {run_role(r)} | {fmt(r['first_v'], 4)}, {fmt(r['first_i'], 4)} "
                     f"| {'yes' if meets else 'no'} | {used_text} | {previous_cells} |")
    lines.append("")

    with_current = [r for r in drives if r["has_current"]]
    meeting = [r for r in drives if r["meets_full_rule"]]
    at_rest = [r for r in with_current if abs(r["first_i"]) < REST_START_CURRENT_A]
    rest_not_rule = [r for r in at_rest if not r["meets_full_rule"]]
    under_load = [r for r in with_current if abs(r["first_i"]) >= REST_START_CURRENT_A]
    linked = []
    unlinked = []
    for r in under_load:
        previous = r["previous"]
        ok = (previous is not None and previous["test_type"] == "charge" and r["previous_gap_s"] <= LINK_GAP_S
              and previous["last_valid_v"] > FULL_VOLTAGE_V and abs(previous["last_valid_i"]) < FULL_CURRENT_A)
        (linked if ok else unlinked).append(r)
    lines.append(f"- **Meet the rule (first row):** {len(meeting)} of {len(drives)} drive files.")
    lines.append(f"- **Open at rest** (|I| < {fmt(1000 * REST_START_CURRENT_A, 0)} mA on the first row; the "
                 f"{len(with_current)} drive files with current): {len(at_rest)}, at "
                 f"{fmt_range([r['first_v'] for r in at_rest], 4)} V and {fmt_range([r['first_i'] for r in at_rest], 4)} A. "
                 f"{len(rest_not_rule)} of them miss the rule only on current: " +
                 ", ".join(f"{label(r)} ({fmt(r['first_i'], 4)} A)" for r in rest_not_rule) + ".")
    lines.append(f"- **Open under load** (|I| >= {fmt(1000 * REST_START_CURRENT_A, 0)} mA): {len(under_load)}, at "
                 f"{fmt_range([r['first_v'] for r in under_load], 4)} V and {fmt_range([r['first_i'] for r in under_load], 4)} A. "
                 f"{len(linked)} of them start at most {fmt(LINK_GAP_S, 0)} s after a Charge file whose last row is a "
                 f"rest above {FULL_VOLTAGE_V} V. The other {len(unlinked)}: " +
                 "; ".join(f"{label(r)} (opens at {fmt(r['first_v'], 4)} V, {fmt(r['first_i'], 4)} A; previous file "
                           f"{label(r['previous'])}, {charge_kind(r['previous'])}, ends at "
                           f"{fmt(r['previous']['last_valid_v'], 4)} V, {fmt(r['previous_gap_s'], 0)} s earlier)"
                           for r in unlinked) + ".")
    special = [r for r in drives if r["first_row_used"] != 0]
    lines.append("- **First row used where the loader cuts the file:** " + "; ".join(
        f"{label(r)} row {r['first_row_used']}: {fmt(r['first_used_v'], 5)} V, {fmt(r['first_used_i'], 4)} A, "
        f"meets the rule: {'yes' if r['first_used_v'] > FULL_VOLTAGE_V and abs(r['first_used_i']) < FULL_CURRENT_A else 'no'}"
        for r in special) + ".")
    no_previous_charge = [r for r in drives if r["previous"] is None or r["previous"]["test_type"] != "charge"]
    lines.append("- **Drive files whose previous file is not a Charge file:** " + "; ".join(
        f"{label(r)} (" + ("first file of its folder" if r["previous"] is None else
                           f"after {label(r['previous'])}, gap {fmt(r['previous_gap_s'], 0)} s") + ")"
        for r in no_previous_charge) + ".")
    lines.append("")
    return lines


def section_charges(records):
    """Section 9: the charge procedure in the Charge files."""
    charges = [r for r in records if r["test_type"] == "charge"]
    with_current = [r for r in charges if r["charge"] is not None]
    with_cc = [r for r in with_current if r["charge"]["has_cc"]]
    without_cc = [r for r in with_current if not r["charge"]["has_cc"]]
    multi = [r for r in with_current if r["charge_runs"] > 1]
    lines = ["## 9. Charge files", ""]
    lines.append(f"Source: the {len(charges)} Charge files (`*_Charge*.mat` in every folder). A row is *charging* "
                 f"when Current > {fmt(1000 * FLOW_CURRENT_A, 0)} mA. *CC phase*: Current above {CC_CURRENT_A} A. "
                 f"*CV voltage*: median Voltage over rows with Current > 0 and Voltage >= {CV_VOLTAGE_V} V. "
                 "*Last charge current*: Current on the last row with Current > 0. *Rest before*: first charging row "
                 "minus the first row; *rest after*: last row with V > 0 minus the last row with Current > 0 (Time, s).")
    lines.append("")
    empty = [r for r in charges if r["charge"] is None]
    lines.append(f"- **Charge files with current:** {len(with_current)} of {len(charges)}; without: "
                 + ", ".join(label(r) for r in empty) + ".")
    lines.append(f"- **With a CC phase above {CC_CURRENT_A} A:** {len(with_cc)}; without: {len(without_cc)} (table "
                 "below). Files with more than one charge (runs of charging rows): " +
                 ", ".join(f"{label(r)} ({r['charge_runs']} charges)" for r in multi) + ".")
    cc = [r["charge"]["cc_median_a"] for r in with_cc]
    lines.append(f"- **CC current:** per-file median {fmt_range(cc, 4)} A (median over files {fmt(np.median(cc), 4)} A); "
                 f"largest sample {fmt(max(r['charge']['peak_a'] for r in with_cc), 4)} A.")
    lines.append(f"- **CV voltage:** per-file median {fmt_range([r['charge']['cv_median_v'] for r in with_current], 4)} V; "
                 f"highest sample {fmt(max(r['charge']['v_max'] for r in with_current), 4)} V.")
    lines.append(f"- **Last charge current (cutoff):** {fmt_range([r['charge']['last_current_a'] for r in with_current], 4)} A "
                 f"in all {len(with_current)} files.")
    lines.append(f"- **Rest before the charge:** {fmt_range([r['charge']['rest_before_s'] for r in with_current], 1)} s; "
                 f"**rest after:** {fmt_range([r['charge']['rest_after_s'] for r in with_current], 1)} s.")
    lines.append(f"- **Cell temperature at the first charging row:** "
                 f"{fmt_range([r['charge']['temp_at_start'] for r in with_current], 2)} degC; over all charging rows "
                 f"{fmt(min(r['charge']['temp_min'] for r in with_current), 2)} to "
                 f"{fmt(max(r['charge']['temp_max'] for r in with_current), 2)} degC.")
    lines.append("")
    lines.append(f"Charge files with current but no CC phase above {CC_CURRENT_A} A, and the file logged next in the "
                 "folder:")
    lines.append("")
    lines.append("| file | peak current (A) | Ah charged (Ah) | charging time (s) | next file |")
    lines.append("|---|---|---|---|---|")
    for r in sorted(without_cc, key=lambda r: (r["folder"], r["start"])):
        later = [x for x in records if x["folder"] == r["folder"] and x["start"] > r["start"]]
        following = min(later, key=lambda x: x["start"]) if later else None
        lines.append(f"| {label(r)} | {fmt(r['charge']['peak_a'], 3)} | {fmt(r['charge']['ah_charged'], 4)} "
                     f"| {fmt(r['charge']['charge_s'], 0)} | {label(following) if following else 'none'} |")
    lines.append("")
    after_top_up = [r for r in drive_records(records)
                    if r["previous"] is not None and r["previous"]["test_type"] == "charge"
                    and r["previous"]["charge"] is not None and not r["previous"]["charge"]["has_cc"]]
    lines.append(f"- **Drive files that follow a Charge file without a CC phase:** " + "; ".join(
        f"{label(r)} after {label(r['previous'])} ({run_role(r)})" for r in after_top_up) + ".")
    lines.append("")
    return lines


# ----------------------------------------------------------------------------
# Sections 10 to 15: HPPC, C/20, Q_ref, counter starts, chronology, 10 degC scaling
# ----------------------------------------------------------------------------

def section_hppc(folders, hppc):
    """Section 10: HPPC structure, currents, rests, logging, limits, first-sample rule, relaxation, resets."""
    lines = ["## 10. HPPC structure", ""]
    lines.append("Source: the six HPPC files (`*_HPPC_*.mat`, one per folder), rows used (legend). A *pulse* is a "
                 f"current step (|I| > {fmt(1000 * FLOW_CURRENT_A, 0)} mA) of at most {PULSE_MAX_S:.0f} s; a *move* is "
                 "a longer discharge before the final recharge; a *level* is the group of pulses between two moves. "
                 "Within a level the discharge pulses are D1 to D4 and the charge pulses C1 to C4, in the order "
                 "they run (D1, C1, D2, C2, ...). Durations run from a step's first row to the first row after it. "
                 "Currents are in the cycler's sign.")
    lines.append("")
    lines.append("| folder | file | levels | D pulses | C pulses | moves | move current, median (A) "
                 "| counter at the end of each move (Ah) | V at the end of the last move (V) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for folder in folders:
        h = hppc[folder]
        n_d = sum(1 for p in h["pulses"] if p["kind"] == -1)
        n_c = sum(1 for p in h["pulses"] if p["kind"] == 1)
        moves = h["moves"]
        lines.append(f"| {folder} | {label(h['record'])} | {h['levels']} | {n_d} | {n_c} | {len(moves)} "
                     f"| {fmt(np.median([m['median_a'] for m in moves]), 4)} "
                     f"| {', '.join(fmt(m['end_ah'], 4) for m in moves)} | {fmt(moves[-1]['end_v'], 4)} |")
    lines.append("")
    lines.append("Pulse currents: median command current (the median current over a pulse) of the full-length "
                 f"pulses at each position, in A. A pulse is full-length when it lasts at least {FULL_PULSE_S} s and "
                 "reaches neither 2.8 V nor 4.2 V.")
    lines.append("")
    positions = ("D1", "D2", "D3", "D4", "C1", "C2", "C3", "C4")
    lines.append("| folder | " + " | ".join(positions) + " | full-length pulses | full-length duration, median (s) |")
    lines.append("|---" * (len(positions) + 3) + "|")
    for folder in folders:
        h = hppc[folder]
        full = [p for p in h["pulses"] if p["full"]]
        lines.append(f"| {folder} | " + " | ".join(fmt(position_median(h, pos), 4) for pos in positions) +
                     f" | {len(full)} of {len(h['pulses'])} | {fmt(np.median([p['duration_s'] for p in full]), 3)} |")
    lines.append("")
    lines.append("Rest lengths (s), min / median / max. *1 h rests*: the rests after a move that lead into the "
                 "next level's pulses; their length is the spec's t_rest (`docs/decisions.md`). *Final rest*: the rest after the last move.")
    lines.append("")
    lines.append("| folder | after D pulses | after C pulses | 1 h rests | final rest |")
    lines.append("|---|---|---|---|---|")

    def three(values):
        return (f"{fmt(min(values), 3)} / {fmt(np.median(values), 3)} / {fmt(max(values), 3)}"
                if values else "none")

    for folder in folders:
        h = hppc[folder]
        lines.append(f"| {folder} | {three(h['d_rest_s'])} | {three(h['c_rest_s'])} | {three(h['hour_rest_s'])} "
                     f"| {three(h['final_rest_s'])} |")
    lines.append("")
    lines.append("Logging inside the rests: the interval used and the elapsed time (from the rest's first row) up "
                 "to which it is used, ending at the next pulse's first row; the most common pattern and how many "
                 "rests follow it. *D pulse + rest*: every step from a discharge pulse's first row to the end of "
                 "its 40 s rest.")
    lines.append("")
    lines.append("| folder | D pulse + rest: dt median / 99th percentile / max (s) | rests after D pulses "
                 "| rests after C pulses | 1 h rests | final rest |")
    lines.append("|---|---|---|---|---|---|")
    for folder in folders:
        h = hppc[folder]
        steps = h["pulse_steps"]
        lines.append(f"| {folder} | {fmt(np.median(steps), 3)} / {fmt(np.percentile(steps, 99), 3)} / "
                     f"{fmt(np.max(steps), 3)} | {h['d_rest_pattern']} | {h['c_rest_pattern']} "
                     f"| {h['hour_rest_pattern']} | {h['final_rest_pattern']} |")
    lines.append("")
    lines.append(f"Voltage limits and the R0 rule. *At 2.8 V*: a D pulse with a row at or below {LOW_LIMIT_V} V "
                 f"(in brackets: how many of them end before {SHORT_PULSE_S} s). *At 4.2 V*: a C pulse with a row at or "
                 f"above {HIGH_LIMIT_V} V. *First row*: the D pulse's first row reaches "
                 f"{fmt(100 * FIRST_SAMPLE_FRACTION, 0)} % of its command current. *Within 0.3 s*: the first row that "
                 f"reaches it comes at most {FIRST_SAMPLE_WINDOW_S} s after the reference, counted either from the "
                 "last row before the pulse (the step happened after it) or from the pulse's first row (the step "
                 "happened before it); the true step time lies between the two. *Usable for R0*: within 0.3 s of the "
                 "pulse's first row with current (the rule fixed for S1; the column counted from the last row before "
                 "is the stricter alternative, shown for information) and not at 2.8 V. "
                 "*Residual relaxation*: V at the last row of a rest "
                 f"minus V {fmt(RELAX_WINDOW_S, 0)} s earlier (interpolated), in mV.")
    lines.append("")
    lines.append("| folder | D pulses | D at 2.8 V | C pulses at 4.2 V | D first row >= 98 % "
                 "| D within 0.3 s of the last row before | D within 0.3 s of the first pulse row "
                 "| latest time to 98 %, from the last row before / from the first pulse row (s) | D usable for R0 "
                 "| 1 h rests: relaxation median / max (mV) | final rest relaxation (mV) |")
    lines.append("|---" * 11 + "|")
    late_notes = []
    for folder in folders:
        h = hppc[folder]
        d_pulses = [p for p in h["pulses"] if p["kind"] == -1]
        c_pulses = [p for p in h["pulses"] if p["kind"] == 1]
        low = [p for p in d_pulses if p["low_limited"]]
        short = [p for p in low if p["duration_s"] < SHORT_PULSE_S]
        first_ok = [p for p in d_pulses if p["first_sample_ok"]]
        within_before = [p for p in d_pulses if p["reach_s"] <= FIRST_SAMPLE_WINDOW_S]
        within_first = [p for p in d_pulses if p["reach_from_first_s"] <= FIRST_SAMPLE_WINDOW_S]
        usable = [p for p in within_first if not p["low_limited"]]
        not_low = [p for p in d_pulses if not p["low_limited"]]
        relax = h["relax_mv"]
        final = h["final_relax_mv"]
        n_d = len(d_pulses)
        lines.append(f"| {folder} | {n_d} | {len(low)} ({len(short)}) "
                     f"| {sum(1 for p in c_pulses if p['high_limited'])} "
                     f"| {len(first_ok)} ({fmt(100.0 * len(first_ok) / n_d, 1)} %) "
                     f"| {len(within_before)} ({fmt(100.0 * len(within_before) / n_d, 1)} %) "
                     f"| {len(within_first)} ({fmt(100.0 * len(within_first) / n_d, 1)} %) "
                     f"| {fmt(max(p['reach_s'] for p in not_low), 3)} / "
                     f"{fmt(max(p['reach_from_first_s'] for p in not_low), 3)} "
                     f"| {len(usable)} | {fmt(np.median(relax), 2)} / {fmt(max(relax), 2)} "
                     f"| {', '.join(fmt(x, 2) for x in final) if final else 'none'} |")
        late = [p for p in d_pulses if not p["first_sample_ok"]]
        if late:
            positions = sorted(set(p["position"] for p in late))
            late_notes.append(
                f"{folder}: {len(late)} D pulses ({', '.join(positions)}, command "
                f"{fmt_range([p['command_a'] for p in late], 4)} A, levels "
                f"{stored_rows_text(sorted(p['level'] for p in late))}) reach 98 % on pulse row "
                f"{fmt_range([p['reach_row'] for p in late], 0)}, {fmt_range([p['reach_s'] for p in late], 3)} s after "
                f"the last row before the pulse ({fmt_range([p['reach_from_first_s'] for p in late], 3)} s after the "
                "pulse's first row)")
    lines.append("")
    lines.append("- **D pulses whose first row is below 98 % of the command:** " +
                 ("; ".join(late_notes) if late_notes else "none") + ".")
    lines.append("")
    lines.append("Ah counter resets inside the HPPC files (rows as stored; the reset rule of section 16) and the "
                 "in-file recharge after the pulse train:")
    lines.append("")
    lines.append("| folder | counter resets: row (Time, h) | recharge starts: row (Time, h) "
                 "| recharge CC current, median (A) | rows in the file |")
    lines.append("|---|---|---|---|---|")
    for folder in folders:
        h = hppc[folder]
        resets = ", ".join(f"{row} ({fmt(time_s / 3600.0, 2)} h)" for row, time_s in h["resets"]) or "none"
        recharge = (f"{h['recharge_row']} ({fmt(h['recharge_time_s'] / 3600.0, 2)} h)"
                    if h["recharge_row"] is not None else "none")
        lines.append(f"| {folder} | {resets} | {recharge} | {fmt(h['recharge_cc_a'], 4)} | {h['record']['n_rows']} |")
    lines.append("")
    return lines


def section_c20(folders, c20):
    """Section 11: C/20 discharge and charge halves per folder."""
    lines = ["## 11. C/20 tests", ""]
    lines.append("Source: the six C20DisCh files (`*_C20DisCh_*.mat`), rows used (legend). *Discharge half*: the "
                 f"longest run of rows with I < -{fmt(1000 * FLOW_CURRENT_A, 0)} mA; Ah removed = -Ah, counted from "
                 "the counter's zero at the step start (the file opens one 60 s interval after it). *Charge half*: "
                 f"from the first row after the discharge with I > +{fmt(1000 * FLOW_CURRENT_A, 0)} mA to the last row "
                 f"with I > 0 (the CV cutoff); CV starts at the first charge row at or above {CV_START_V} V. Ah "
                 "returned = counter at the last charge row minus counter at the last discharge row. Durations are "
                 "differences of logged Times; at 60 s logging each boundary is known to within 60 s. Rest = Time "
                 "of the first charge row minus Time of the last discharge row, or of the first rest row after it. "
                 "End-of-discharge SoC = 1 - Ah removed / Q_ref. Currents in the cycler's sign.")
    lines.append("")
    lines.append("| folder | file | discharge I, median (A) | charge CC I, median (A) | CV voltage, median (V) "
                 "| cutoff I (A) | CC time (s) | CV time (s) | rest between halves, from the last discharge row / "
                 "from the first rest row (s) | Ah removed (Ah) "
                 "| Ah returned (Ah) | returned / removed | end-of-discharge SoC (%) | cell T discharge, min / max (degC) "
                 "| cell T charge, min / max (degC) |")
    lines.append("|---" * 15 + "|")
    for folder in folders:
        c = c20[folder]
        lines.append(f"| {folder} | {label(c['record'])} | {fmt(c['dis_median_a'], 5)} | {fmt(c['cc_median_a'], 5)} "
                     f"| {fmt(c['cv_median_v'], 5)} | {fmt(c['cutoff_a'], 5)} | {fmt(c['cc_s'], 1)} | {fmt(c['cv_s'], 1)} "
                     f"| {fmt(c['rest_s'], 1)} / {fmt(c['rest_from_first_rest_row_s'], 1)} | {fmt(c['q_dis'], 5)} "
                     f"| {fmt(c['q_chg'], 5)} "
                     f"| {fmt(c['q_chg'] / c['q_dis'], 4)} | {fmt(100.0 * c['end_soc'], 2)} "
                     f"| {fmt(c['temp_dis'][0], 2)} / {fmt(c['temp_dis'][1], 2)} "
                     f"| {fmt(c['temp_chg'][0], 2)} / {fmt(c['temp_chg'][1], 2)} |")
    lines.append("")
    lines.append("Monotonicity. Discharge half: *rises* = rows where V is above the previous row's V; *rebound* = "
                 "the largest V above the lowest V so far. Charge half, CC part only (before CV): *falls* and *dip* "
                 "likewise. *PCHIP*: a PCHIP through the raw discharge half (V against SoC = 1 - Ah removed / Q_ref), "
                 "evaluated at the points of the 101-point SoC grid (0, 0.01, ..., 1) that lie inside the measured "
                 "SoC range; *monotone* means V rises strictly from each grid point to the next.")
    lines.append("")
    lines.append("| folder | discharge rows | rises | largest rise (mV) | largest rebound (mV) | CC rows | falls "
                 "| largest fall (mV) | largest dip (mV) | PCHIP grid points (SoC range) | PCHIP monotone "
                 "| smallest PCHIP step (mV) |")
    lines.append("|---" * 12 + "|")
    for folder in folders:
        c = c20[folder]
        lines.append(f"| {folder} | {c['n_dis']} | {c['rises']} | {fmt(c['largest_rise_mv'], 2)} "
                     f"| {fmt(c['largest_rebound_mv'], 2)} | {c['n_cc']} | {c['falls']} | {fmt(c['largest_fall_mv'], 2)} "
                     f"| {fmt(c['largest_dip_mv'], 2)} | {c['pchip_points']} ({fmt(c['pchip_range'][0], 2)} to "
                     f"{fmt(c['pchip_range'][1], 2)}) | {'yes' if c['pchip_monotone'] else 'no'} "
                     f"| {fmt(c['pchip_smallest_step_mv'], 2)} |")
    lines.append("")
    lines.append("Charge-minus-discharge voltage (mV) at the same SoC, by how the charge half is placed against "
                 "the discharge half (linear interpolation in both halves):")
    lines.append("")
    lines.append("- **A**: same Ah removed. The charge half's Ah removed is the discharge's Ah removed minus the Ah "
                 "returned so far, measured from the discharge end; both halves on SoC = 1 - Ah removed / Q_ref.")
    lines.append("- **B**: each half normalised to its own Ah span: discharge at 1 - Ah removed / (Ah removed in "
                 "total), charge at Ah returned / (Ah returned in total).")
    lines.append("- **C**: charge Ah counted from the discharge end but scaled by the discharge Ah: discharge as in "
                 "B, charge at Ah returned / (Ah removed in total).")
    lines.append("- **D**: Q_ref axis with the charge half ending at SoC 1: charge at 1 - (Ah returned in total - Ah "
                 "returned so far) / Q_ref; discharge as in A.")
    lines.append("")
    lines.append("| folder | A at 50 % | B at 50 % | C at 50 % | D at 50 % | A at 80 % |")
    lines.append("|---|---|---|---|---|---|")
    for folder in folders:
        gap = c20[folder]["gap_mv"]
        lines.append(f"| {folder} | {fmt(gap['A50'], 1)} | {fmt(gap['B50'], 1)} | {fmt(gap['C50'], 1)} "
                     f"| {fmt(gap['D50'], 1)} | {fmt(gap['A80'], 1)} |")
    lines.append("")
    return lines


def section_qref(c20_25, q_ref):
    """Section 12: where Q_ref comes from."""
    r = c20_25["record"]
    first_row, last_row = c20_25["dis_rows"]
    lines = ["## 12. Q_ref provenance", ""]
    lines.append(f"Source: `data/raw/{r['folder']}/{r['file']}`.")
    lines.append("")
    lines.append(f"- **Discharge half:** rows {first_row} to {last_row}, median current "
                 f"{fmt(c20_25['dis_median_a'], 5)} A.")
    lines.append(f"- **Last discharge row:** row {last_row}, Time {fmt(c20_25['dis_end_time_s'], 2)} s "
                 f"({fmt(c20_25['dis_end_time_s'] / 3600.0, 2)} h after the first row), Voltage "
                 f"{fmt(c20_25['dis_end_v'], 5)} V, counter Ah {fmt(c20_25['dis_end_ah'], 5)} Ah.")
    lines.append(f"- **Q_ref** = -Ah at that row = **{fmt(q_ref, 5)} Ah** (counted from the counter's zero at the "
                 "step start).")
    lines.append(f"- **First row:** Ah[0] = {fmt(c20_25['ah_first'], 5)} Ah (the file opens one 60 s interval into the "
                 f"discharge). The alternative -(Ah - Ah[0]) = {fmt(-(c20_25['dis_end_ah'] - c20_25['ah_first']), 5)} Ah "
                 f"leaves out that first interval ({fmt(100.0 * c20_25['ah_first'] / -q_ref, 3)} % of Q_ref).")
    lines.append("")
    return lines


def start_value_ah(folder, test_type, capacity_files):
    """Counter value the discharge of a capacity file starts from: 0 after a reset, or the carried C/20 end value."""
    if test_type == "dis_0p5c":
        return capacity_files[(folder, "c20")]["ah_last"]
    return 0.0


def start_difference_ah(folders, capacity_files):
    """Largest |start value - counter one interval before the first row| over the C/20, 0.5C and 2C files."""
    return max(abs(start_value_ah(folder, test_type, capacity_files)
                   - capacity_files[(folder, test_type)]["ah_back_one_interval"])
               for folder in folders for test_type in ("c20", "dis_0p5c", "dis_2c"))


def section_counter_starts(folders, capacity_files):
    """Section 13: where the counter of each C20DisCh, Dis_0p5C and Dis_2C file starts, and the capacity both ways."""
    lines = ["## 13. Counter start of the C/20, 0.5C and 2C files", ""]
    lines.append("Source: the C20DisCh, Dis_0p5C and Dis_2C files of every folder, rows as stored. *Back one "
                 "interval*: Ah[0] - I[0] x (Time[1] - Time[0]) / 3600, the counter one logging interval before the "
                 "first row. C20DisCh and Dis_2C files start one interval after a counter reset (back one interval "
                 "= 0); Dis_0p5C files continue the counter of the folder's C20DisCh file (back one interval = that "
                 "file's last Ah). *Capacity from the start value*: start value minus the counter at the end of the "
                 "discharge, where the start value is 0 (C20DisCh, Dis_2C: the step-start zero) or the C20DisCh "
                 "file's last Ah (Dis_0p5C: the carried counter). *Capacity -(Ah_end - Ah[0])*: logged rows only. "
                 "`results/s0/capacity.md` starts from *back one interval* instead; the two start values differ by at "
                 f"most {fmt(1000.0 * start_difference_ah(folders, capacity_files), 2)} mAh here, so its capacities can "
                 "differ from this column in the last digit.")
    lines.append("")
    lines.append("| folder | file | Ah[0] (Ah) | I[0] (A) | first interval (s) | back one interval (Ah) "
                 "| C20DisCh last Ah (Ah) | counter at discharge end (Ah) | capacity from the start value (Ah) "
                 "| capacity -(Ah_end - Ah[0]) (Ah) |")
    lines.append("|---" * 10 + "|")
    for folder in folders:
        c20_last = capacity_files[(folder, "c20")]["ah_last"]
        for test_type in ("c20", "dis_0p5c", "dis_2c"):
            f = capacity_files[(folder, test_type)]
            start_value = start_value_ah(folder, test_type, capacity_files)
            lines.append(f"| {folder} | {label(f['record'])} | {fmt(f['ah_first'], 5)} | {fmt(f['i_first'], 4)} "
                         f"| {fmt(f['interval_s'], 1)} | {fmt(f['ah_back_one_interval'], 5)} "
                         f"| {fmt(c20_last, 5) if test_type == 'dis_0p5c' else 'n/a'} | {fmt(f['ah_dis_end'], 5)} "
                         f"| {fmt(start_value - f['ah_dis_end'], 4)} | {fmt(f['ah_first'] - f['ah_dis_end'], 4)} |")
    lines.append("")
    return lines


def section_chronology(folders, records):
    """Section 14: first and last TimeStamp per folder, test numbers, and overlapping neighbours."""
    lines = ["## 14. Campaign chronology", ""]
    lines.append("Source: the first and last TimeStamp of every file (`ekfsoc.rawio.parse_timestamp`, which reads "
                 "both TimeStamp formats), shown to the whole second because the fraction is unreliable. Folders in "
                 "campaign order (sorted by their first TimeStamp).")
    lines.append("")
    lines.append("| folder | first TimeStamp | first file | last TimeStamp | last file | test numbers |")
    lines.append("|---|---|---|---|---|---|")
    for folder in folders:
        files = [r for r in records if r["folder"] == folder]
        first = min(files, key=lambda r: r["start"])
        last = max(files, key=lambda r: r["end"])
        numbers = sorted(set(r["test_number"] for r in files if r["test_number"] is not None))
        lines.append(f"| {folder} | {first['start'].isoformat(sep=' ', timespec='seconds')} | {label(first)} "
                     f"| {last['end'].isoformat(sep=' ', timespec='seconds')} | {label(last)} | {numbers[0]} to {numbers[-1]} "
                     f"({', '.join(str(n) for n in numbers)}) |")
    lines.append("")
    overlaps = []
    for r in records:
        previous = r["previous"]
        if previous is None:
            continue
        overlap_s = (previous["end"] - r["start"]).total_seconds()
        if overlap_s > 2.0 and r["end"] > previous["end"]:
            overlaps.append((r, previous, overlap_s))
    for r, previous, overlap_s in overlaps:
        lines.append(f"- **Overlap:** {label(r)} starts at {r['start'].isoformat(sep=' ', timespec='seconds')}, "
                     f"{fmt(overlap_s / 60.0, 1)} min before {label(previous)} ends at "
                     f"{previous['end'].isoformat(sep=' ', timespec='seconds')} (both by TimeStamp; checked for every "
                     "pair of neighbouring files).")
    if not overlaps:
        lines.append("- No neighbouring files overlap.")
    lines.append("")
    return lines


def section_scaling(folders, hppc, c20, capacity_files, records):
    """Section 15: the 10 degC test-575 currents against the other folders."""
    lines = ["## 15. Test currents per folder (the 10 degC test-575 scaling)", ""]
    lines.append("Source: the HPPC, C20DisCh, Dis_0p5C, Dis_2C and Cap_1C files of every folder. Medians in A, "
                 "cycler sign (HPPC values as in section 10, C/20 values as in section 11). *In-file recharge*: "
                 f"median of the rows above {RECHARGE_MIN_A} A in the recharge after the discharge. The last column "
                 "divides the 10 degC value by the 25 degC value.")
    lines.append("")
    rows = []
    for position in ("D1", "D2", "D3", "D4", "C1", "C2", "C3", "C4"):
        rows.append((f"HPPC pulse {position}", {f: position_median(hppc[f], position) for f in folders}))
    rows.append(("HPPC move current", {f: float(np.median([m["median_a"] for m in hppc[f]["moves"]])) for f in folders}))
    rows.append(("HPPC counter at the end of the first move (Ah)", {f: hppc[f]["moves"][0]["end_ah"] for f in folders}))
    rows.append(("HPPC in-file recharge", {f: hppc[f]["recharge_cc_a"] for f in folders}))
    rows.append(("C/20 discharge", {f: c20[f]["dis_median_a"] for f in folders}))
    rows.append(("C/20 charge CC", {f: c20[f]["cc_median_a"] for f in folders}))
    rows.append(("0.5C discharge (Dis_0p5C)", {f: capacity_files[(f, "dis_0p5c")]["dis_median_a"] for f in folders}))
    rows.append(("0.5C in-file recharge", {f: capacity_files[(f, "dis_0p5c")]["recharge_cc_a"] for f in folders}))
    rows.append(("2C discharge (Dis_2C)", {f: capacity_files[(f, "dis_2c")]["dis_median_a"] for f in folders}))
    rows.append(("2C in-file recharge", {f: capacity_files[(f, "dis_2c")]["recharge_cc_a"] for f in folders}))
    one_c = {}
    for f in folders:
        values = [r["median_current_discharge"] for r in records if r["folder"] == f and r["test_type"] == "cap_1c"]
        one_c[f] = float(np.median(values)) if values else float("nan")
    rows.append(("1C discharge (Cap_1C, median over the folder's files)", one_c))
    lines.append("| quantity | " + " | ".join(folders) + " | 10degC / 25degC |")
    lines.append("|---" * (len(folders) + 2) + "|")
    for name, values in rows:
        ratio = values["10degC"] / values["25degC"] if values["25degC"] not in (0.0,) else float("nan")
        lines.append(f"| {name} | " + " | ".join(fmt(values[f], 4) for f in folders) + f" | {fmt(ratio, 3)} |")
    lines.append("")
    lines.append("- 10 degC files of test 575: " + ", ".join(
        label(r) for r in records if r["folder"] == "10degC" and r["test_number"] == 575) + ".")
    lines.append("")
    return lines


# ----------------------------------------------------------------------------
# Extra checks cited by the docs (16 to 19)
# ----------------------------------------------------------------------------

def section_counter_per_type(records):
    """Extra 16: the Ah counter on the first row and its resets, per test type."""
    lines = ["## 16. Ah counter: first row and resets, per test type", ""]
    lines.append("Source: all files, rows as stored. A *reset* is a row where Ah is exactly 0 while the previous "
                 "row's Ah is not, by more than the current on either row could change the counter over that step "
                 f"(+{COUNTER_TOLERANCE_AH * 1000:.2f} mAh). This leaves out a counter that only passes through 0, as "
                 "it does under regen early in some drive cycles.")
    lines.append("")
    lines.append("| test type | files | Ah at the first row, min / max (Ah) | files with a reset | resets on the "
                 "last row | resets on the second-to-last row | resets on other rows |")
    lines.append("|---|---|---|---|---|---|---|")
    groups = {}
    for r in records:
        group = "drive (UDDS, HWFET, LA92, US06, Mixed1-8)" if r["test_type"] in DRIVE_TYPES else r["test_type"]
        groups.setdefault(group, []).append(r)
    for group in sorted(groups):
        files = groups[group]
        first = [r["ah_first"] for r in files]
        last = sum(1 for r in files for k in r["reset_rows"] if k == r["n_rows"] - 1)
        second = sum(1 for r in files for k in r["reset_rows"] if k == r["n_rows"] - 2)
        other = sum(1 for r in files for k in r["reset_rows"] if k < r["n_rows"] - 2)
        lines.append(f"| {group} | {len(files)} | {fmt(min(first), 5)} / {fmt(max(first), 5)} "
                     f"| {sum(1 for r in files if r['reset_rows'])} | {last} | {second} | {other} |")
    lines.append("")
    return lines


def section_low_limit(folders, records):
    """Extra 17: drive files that reach the 2.8 V cutoff."""
    lines = ["## 17. Drive files at the 2.8 V cutoff", ""]
    lines.append(f"Source: the drive files of every folder, rows as stored. A row is *at the cutoff* when "
                 f"0 < V <= {LOW_LIMIT_V} V. *Earliest*: the smallest Time of such a row in any of the folder's files.")
    lines.append("")
    lines.append("| folder | drive files with current | files with rows at the cutoff | rows at the cutoff "
                 "| earliest (s), file |")
    lines.append("|---|---|---|---|---|")
    for folder in folders:
        files = [r for r in drive_records(records, folder) if r["has_current"]]
        hit = [r for r in files if r["low_limit_rows"] > 0]
        earliest = min(hit, key=lambda r: r["low_limit_first_s"]) if hit else None
        earliest_text = f"{fmt(earliest['low_limit_first_s'], 1)}, {label(earliest)}" if earliest else "none"
        lines.append(f"| {folder} | {len(files)} | {len(hit)} | {sum(r['low_limit_rows'] for r in hit)} "
                     f"| {earliest_text} |")
    lines.append("")
    return lines


def section_shared_segments(records):
    """Extra 18: where the 40 degC HWFET current reappears inside the 25 degC tuning cycle (Mix 1)."""
    hwfet = find_record(records, "40degC", "556_HWFET")
    mix = find_record(records, "25degC", "551_Mixed1")
    hwfet_data = rawio.load_mat(hwfet["path"])
    mix_data = rawio.load_mat(mix["path"])
    hwfet_rows = rows_used(hwfet, hwfet_data)
    mix_rows = rows_used(mix, mix_data)
    hwfet_t = hwfet_data["Time"][hwfet_rows]
    pattern = hwfet_data["Current"][hwfet_rows][hwfet_t - hwfet_t[0] < HWFET_SECONDS]
    signal = mix_data["Current"][mix_rows]
    mix_t = mix_data["Time"][mix_rows]

    # Pearson correlation of the pattern with every window of the same number of rows in the mix.
    n = len(pattern)
    pattern_centred = pattern - pattern.mean()
    numerator = np.correlate(signal, pattern_centred, mode="valid")
    sums = np.concatenate(([0.0], np.cumsum(signal)))
    squares = np.concatenate(([0.0], np.cumsum(signal ** 2)))
    window_sum = sums[n:] - sums[:-n]
    window_var = squares[n:] - squares[:-n] - window_sum ** 2 / n
    correlation = numerator / np.sqrt(np.maximum(window_var, 1e-12) * np.sum(pattern_centred ** 2))

    matches = []
    for first, last in runs_of(correlation >= MATCH_CORRELATION):
        best = first + int(np.argmax(correlation[first:last + 1]))
        matches.append((best, float(correlation[best])))
    lines = ["## 18. A standard cycle inside a mix", ""]
    lines.append(f"Source: {label(hwfet)} and {label(mix)}, rows used. The current of the first "
                 f"{fmt(HWFET_SECONDS, 0)} s of the HWFET file ({n} rows) is correlated (Pearson) with every window "
                 "of the same number of rows of the mix (rows matched by position; both log at about 0.1 s).")
    lines.append("")
    lines.append(f"- **Windows with correlation >= {MATCH_CORRELATION}:** " + ("; ".join(
        f"starting at Time {fmt(mix_t[k], 1)} s of the mix, correlation {fmt(value, 4)}" for k, value in matches)
        if matches else "none") + f". Highest correlation anywhere: {fmt(float(np.max(correlation)), 4)}.")
    lines.append("")
    return lines


def section_sign(records):
    """Extra 19: the cycler's sign on a known discharge step and a known charge step."""
    lines = ["## 19. Sign of current on known steps", ""]
    cap = find_record(records, "25degC", "551_Cap")
    charge = find_record(records, "25degC", "551_Charge2")
    lines.append(f"Source: {label(cap)} and {label(charge)}, rows as stored. The row before and the row of the first "
                 f"step change of current (|I| crossing {fmt(1000 * FLOW_CURRENT_A, 0)} mA).")
    lines.append("")
    for r in (cap, charge):
        data = rawio.load_mat(r["path"])
        i = data["Current"]
        k = int(np.where(np.abs(i) > FLOW_CURRENT_A)[0][0])
        lines.append(f"- {label(r)}: at Time {fmt(data['Time'][k], 3)} s (row {k}) Current goes from "
                     f"{fmt(i[k - 1], 4)} to {fmt(i[k], 4)} A and Voltage from {fmt(data['Voltage'][k - 1], 4)} to "
                     f"{fmt(data['Voltage'][k], 4)} V; Ah goes from {fmt(data['Ah'][k - 1], 5)} to "
                     f"{fmt(data['Ah'][k + 1], 5)} Ah over the next row.")
    lines.append("- Discharge (voltage falls) shows as negative Current and a falling Ah counter; charge (voltage "
                 "rises) as positive Current. The project sign is I = -Current.")
    lines.append("")
    return lines


# ----------------------------------------------------------------------------
# Header, legend and main
# ----------------------------------------------------------------------------

def header_lines(folders, records, q_ref):
    """Title, purpose, sign convention and the definitions every section uses."""
    drives = drive_records(records)
    evaluated = [r for r in drives if run_role(r) == "evaluation"]
    lines = ["# Data checks (S0)", ""]
    lines.append("Generated by `python/data_checks.py` (`make checks`) from `data/raw/`: LG 18650HG2 Li-ion Battery "
                 "Data, Kollmeyer et al., McMaster University, Mendeley Data v2, DOI 10.17632/b5mj79w5w9.2, "
                 "CC BY 4.0. Do not edit by hand. Every number is measured from the `.mat` files.")
    lines.append("")
    lines.append("These are the measured dataset properties that `docs/decisions.md` and `docs/model.md` cite and "
                 "that `results/s0/data_inventory.md` and `results/s0/capacity.md` do not contain. Each section names the "
                 "files it reads.")
    lines.append("")
    lines.append("## Legend and conventions")
    lines.append("")
    lines.append("- **Sign convention:** values quoted from the files (Current, Ah, V) are **as the cycler wrote "
                 "them: discharge current is negative and the Ah counter falls while discharging**. Amounts named "
                 "*removed*, *returned* or *charged* are positive. SoC_ref and the coulomb counter use the project "
                 "sign, I = -Current (positive = discharge). Units: V, A, s, Ah, degC; SoC differences in "
                 "percentage points (pp).")
    lines.append("- **Rows** count from 0 in the file as stored, before any row is dropped. **Time** is the Time "
                 "field (s); TimeStamp is used only where a section says so.")
    lines.append(f"- **Q_ref** = {fmt(q_ref, 5)} Ah, measured by this script in section 12 and used everywhere below.")
    lines.append("- **Rows used** (the loader rules of `docs/decisions.md` 1.9 and `docs/model.md`, applied in this "
                 "order): (1) drop rows with Voltage <= 0 and rows with NaN in Time, Voltage, Current, Ah or "
                 f"Battery_Temp_degC; (2) per-file cuts: `10degC/571_Mixed6` starts at row {FIRST_ROW_USED['571_Mixed6']}, "
                 "and `10degC/582_LA92` keeps only rows dated 26/11/2018 (section 4); (3) of consecutive kept rows that "
                 "share one Time value, keep the last. Steps 1 and 2 commute: the dropped rows all lie outside the rows "
                 "the cuts keep.")
    counts = ", ".join(f"{folder} {sum(1 for r in evaluated if r['folder'] == folder)}" for folder in folders)
    lines.append(f"- **Evaluation set** (`docs/decisions.md`): {len(evaluated)} of the {len(drives)} drive files "
                 f"({counts}). Not in it: " +
                 "; ".join(f"{label(r)} ({run_role(r)})" for r in drives if run_role(r) != "evaluation") +
                 ". The six PausCycl files are not drive cycles and are not in it either.")
    lines.append("- **Drive files** are the UDDS, HWFET, LA92, US06 and Mixed1 to Mixed8 files; files are named "
                 "`<folder>/<test number>_<descriptor>` (the full names are in `results/s0/data_inventory.md`).")
    lines.append("- Sections 1 to 15 are the checks the S0 decisions rely on; 16 to 19 are further measured facts "
                 "the docs cite.")
    lines.append("")
    return lines


def main():
    """Read every raw file, run the checks, write results/s0/data_checks.md."""
    records = file_records()

    # Q_ref first: every SoC below depends on it.
    qref_record = [r for r in records if r["folder"] == QREF_FOLDER and r["test_type"] == QREF_TEST_TYPE][0]
    qref_check = analyse_c20(qref_record, rawio.load_mat(qref_record["path"]), None)
    q_ref = qref_check["q_dis"]

    for r in records:
        scan_file(r, rawio.load_mat(r["path"]), q_ref)
    for r in records:
        r["previous"] = previous_file(r, records)
        r["previous_gap_s"] = ((r["start"] - r["previous"]["end"]).total_seconds()
                               if r["previous"] is not None else float("nan"))
    print(f"scanned {len(records)} files")

    # Campaign order: folders by their first TimeStamp, files by their first TimeStamp within a folder.
    folders = sorted(set(r["folder"] for r in records), key=lambda f: min(r["start"] for r in records if r["folder"] == f))
    records.sort(key=lambda r: (folders.index(r["folder"]), r["start"]))
    hppc = {}
    c20 = {}
    capacity_files = {}
    for r in records:
        if r["test_type"] == "hppc":
            hppc[r["folder"]] = analyse_hppc(r, rawio.load_mat(r["path"]))
        if r["test_type"] in ("c20", "dis_0p5c", "dis_2c"):
            data = rawio.load_mat(r["path"])
            capacity_files[(r["folder"], r["test_type"])] = analyse_capacity_file(r, data)
            if r["test_type"] == "c20":
                c20[r["folder"]] = analyse_c20(r, data, q_ref)

    lines = header_lines(folders, records, q_ref)
    lines += section_steps(folders, records)
    lines += section_duplicates(records)
    lines += section_long_steps(records, q_ref)
    lines += section_special_files(records, q_ref)
    lines += section_bad_rows(records)
    lines += section_temperatures(folders, records)
    lines += section_runs(folders, records, q_ref)
    lines += section_full_charge(folders, records)
    lines += section_charges(records)
    lines += section_hppc(folders, hppc)
    lines += section_c20(folders, c20)
    lines += section_qref(c20[QREF_FOLDER], q_ref)
    lines += section_counter_starts(folders, capacity_files)
    lines += section_chronology(folders, records)
    lines += section_scaling(folders, hppc, c20, capacity_files, records)
    lines += section_counter_per_type(records)
    lines += section_low_limit(folders, records)
    lines += section_shared_segments(records)
    lines += section_sign(records)

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text("\n".join(lines))
    print(f"wrote {OUT_PATH.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
