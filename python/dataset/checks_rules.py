"""The thresholds, the loader cuts and the small helpers of results/s0/data_checks.md, and the rows the loader keeps."""

import math

import numpy as np

from dataset.common import fmt
from ekfsoc import rawio
from ekfsoc.constants import RAW_DIR


LINK_GAP_S = 300.0           # a drive file that opens under load counts as linked to a full charge this close after it
REST_START_CURRENT_A = 0.10  # a drive file "opens at rest" when |I| on its first row is below this
FULL_CURRENT_A = 0.05        # full-charge rule: ... with |I| below this
DT_BAND_S = (0.09, 0.11)     # a drive-cycle step in this band is a normal 0.1 s step
LONG_STEP_S = 0.2            # count drive-cycle steps above this
CC_CURRENT_A = 2.9           # a Charge file has a 1C CC phase if its current exceeds this
CV_PHASE_V = 4.195           # charge samples at or above this voltage are in the CV phase
CV_START_V = 4.1995          # the C/20 charge enters CV at the first sample at or above this voltage
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
