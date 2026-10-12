"""Loader: turns one raw .mat file into a Run in the project's conventions.

rawio.py returns the file exactly as the cycler wrote it. This module applies the conventions of
docs/model.md on top of that:

- current: I = -Current, so positive = discharge (C2);
- charge: ah_removed = Ah_start - Ah, positive when charge has been removed (C3);
- time: dt comes from the Time column, never from TimeStamp (C8);
- the loader rules, in this order (docs/model.md, "Files and loader rules"):
  1. drop rows with Voltage <= 0 and rows with NaN in Time, Voltage, Current, Ah or Battery_Temp_degC (C10);
  2. apply the per-file cut (C12);
  3. of consecutive rows that share one Time value, keep the last (C9);
  4. dt(k) = Time(k) - Time(k-1) between the rows that are left, dt(0) = 0;
     steps longer than 1 s are listed in the run's meta and used as they are (C11).

Row numbers in the docs count from 0 in the file as stored. The rule functions therefore work on
arrays of those stored row numbers, and build_run copies the surviving rows into the Run at the end.
"""

import datetime
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ekfsoc import rawio
from ekfsoc.constants import FOLDER_TEMP, Q_REF_AH


# A step between kept rows longer than this is recorded in meta["gaps_over_1s"] (C11).
GAP_S = 1.0

# Fields whose NaN makes a row unusable (C10). Wh and Power are not used, so a NaN in them alone keeps the row.
REQUIRED_FIELDS = ("Time", "Voltage", "Current", "Ah", "Battery_Temp_degC")

# Test types whose counter is read from the step-start zero: ah_removed = -Ah (C3).
# These files open one 60 s interval after the cycler reset the counter, so Ah at the first row is not 0.
AH_FROM_STEP_START_TYPES = ("c20", "dis_2c")

# Files that need a cut and start below full charge (C12, C13; decisions 1.5).
# Key: (folder, test number, test type). Value: SoC0 at the first row used, and the cut.
#   ("start_row", n)   keep rows from stored row n on (571_Mixed6: the 10.42 h pause is before row 391)
#   ("date", d)        keep rows whose TimeStamp date is d (582_LA92: the false start is dated 25/11/2018)
SPECIAL_FILES = {
    ("10degC", 571, "mixed6"): {"soc0": 0.99638, "cut": ("start_row", 391)},
    ("10degC", 582, "la92"): {"soc0": 0.99484, "cut": ("date", datetime.date(2018, 11, 26))},
}


@dataclass
class Run:
    """One test file in the project's conventions. All arrays are 1-D float64 of the same length.

    t           Time in s, as in the file (it does not start at 0 for the two cut files)
    i           current in A, positive = discharge (i = -Current)
    v           terminal voltage in V
    temp        measured cell temperature in degC (Battery_Temp_degC)
    ah_removed  charge removed since the counting start in Ah, positive on discharge (C3)
    dt          step to the previous kept row in s; dt[0] = 0, dt[k] = t[k] - t[k-1] > 0
    soc0        reference SoC at the first row used (1.0, except 571_Mixed6 and 582_LA92)
    meta        dict: file, folder, test_type, nominal_temp_degc, n_rows_raw, n_rows_used,
                n_dropped_rows (rule 1), n_cut_rows (rule 2), n_duplicates_removed (rule 3),
                cut (text or None), gaps_over_1s (list of (row in these arrays, dt))
    """

    t: np.ndarray
    i: np.ndarray
    v: np.ndarray
    temp: np.ndarray
    ah_removed: np.ndarray
    dt: np.ndarray
    soc0: float
    meta: dict


def soc_ref(run):
    """Return the reference SoC for every row: soc0 - ah_removed / Q_ref (docs/model.md C4, C13).

    It follows the cycler's Ah counter, not the integral of the logged current.
    """
    return run.soc0 - run.ah_removed / Q_REF_AH


def drop_invalid_rows(columns):
    """Rule 1: return the stored row numbers whose Voltage is above 0 and that have no NaN (C10).

    columns maps each name in REQUIRED_FIELDS to its float64 array. 0 V is the cycler's end-of-test
    marker, not a measurement, and a NaN row holds no sample.
    """
    valid = columns["Voltage"] > 0.0
    for name in REQUIRED_FIELDS:
        valid &= ~np.isnan(columns[name])
    return np.flatnonzero(valid)


def apply_cut(rows, fields, cut):
    """Rule 2: apply the per-file cut to the row numbers that survived rule 1.

    Returns (rows, text). text describes the cut for meta["cut"], or is None when there is no cut.
    A cut by date reads TimeStamp, which is good to about 1 s; that is enough to tell two dates apart.
    """
    if cut is None:
        return rows, None

    kind, value = cut
    if kind == "start_row":
        return rows[rows >= value], f"starts at stored row {value}"
    if kind == "date":
        stamps = fields["TimeStamp"]
        on_date = [rawio.parse_timestamp(str(stamps[row])).date() == value for row in rows]
        return rows[np.array(on_date, dtype=bool)], f"only rows dated {value.strftime('%d/%m/%Y')}"
    raise ValueError(f"unknown cut kind: {kind!r}")


def keep_last_of_equal_time(rows, time):
    """Rule 3: of consecutive rows that share one Time value, keep the last (C9).

    Both rows are the same instant, and a step with dt = 0 cannot be used. A row is kept when the
    next row in the list has a different Time, or when it is the last row.
    """
    row_times = time[rows]
    next_differs = row_times[1:] != row_times[:-1]
    return rows[np.append(next_differs, True)]


def find_gaps(dt):
    """Return [(row, dt)] for every step longer than GAP_S (C11); row indexes the arrays of the Run."""
    return [(int(row), float(dt[row])) for row in np.flatnonzero(dt > GAP_S)]


def build_run(fields, file, folder, test_type, soc0=1.0, cut=None):
    """Apply the four loader rules and the sign conventions to arrays that are already in memory.

    fields     dict of arrays in the cycler's convention (discharge current negative, Ah falling):
               Time, Voltage, Current, Ah, Battery_Temp_degC, plus TimeStamp when the cut is by date
    file       file name, kept in meta
    folder     data folder name such as "25degC", kept in meta (nominal_temp_degc is looked up from it)
    test_type  as rawio.classify_test gives it; "c20" and "dis_2c" count the charge from the step-start zero
    soc0, cut  from SPECIAL_FILES for the two cut files, 1.0 and None otherwise

    load_run() calls this after reading a file; tests call it directly with made-up arrays.
    Raises ValueError if no row is left, or if Time does not increase after the rules.

    Ah semantics (C3, decisions 1.10): C20DisCh and Dis_2C files give ah_removed = -Ah. Every other file
    gives ah_removed = -(Ah - Ah at the first row used), so ah_removed[0] = 0. HPPC counters reset to 0
    after the last move, so there ah_removed is valid only up to that reset.
    """
    columns = {name: np.asarray(fields[name], dtype=np.float64) for name in REQUIRED_FIELDS}
    n_rows_raw = len(columns["Time"])

    rows_after_drop = drop_invalid_rows(columns)
    rows_after_cut, cut_text = apply_cut(rows_after_drop, fields, cut)
    if len(rows_after_cut) == 0:
        raise ValueError(f"{file}: no rows left after dropping invalid rows and applying the cut")
    rows_used = keep_last_of_equal_time(rows_after_cut, columns["Time"])

    t = columns["Time"][rows_used]
    v = columns["Voltage"][rows_used]
    current = columns["Current"][rows_used]
    ah = columns["Ah"][rows_used]
    temp = columns["Battery_Temp_degC"][rows_used]

    # Rule 4: dt from Time, dt[0] = 0 because there is no row before the first.
    dt = np.diff(t, prepend=t[0])
    if not np.all(dt[1:] > 0.0):
        raise ValueError(f"{file}: Time does not increase after the loader rules (smallest step {dt[1:].min()} s)")

    # C2: the cycler writes discharge as negative current. 0.0 - x gives +0.0 for a zero current, not -0.0.
    i = 0.0 - current

    # C3: ah_removed = Ah_start - Ah, positive when charge has been removed.
    ah_start = 0.0 if test_type in AH_FROM_STEP_START_TYPES else ah[0]
    ah_removed = ah_start - ah

    meta = {
        "file": file,
        "folder": folder,
        "test_type": test_type,
        "nominal_temp_degc": FOLDER_TEMP.get(folder),
        "n_rows_raw": n_rows_raw,
        "n_rows_used": len(rows_used),
        "n_dropped_rows": n_rows_raw - len(rows_after_drop),
        "n_cut_rows": len(rows_after_drop) - len(rows_after_cut),
        "n_duplicates_removed": len(rows_after_cut) - len(rows_used),
        "cut": cut_text,
        "gaps_over_1s": find_gaps(dt),
    }
    return Run(t=t, i=i, v=v, temp=temp, ah_removed=ah_removed, dt=dt, soc0=float(soc0), meta=meta)


def load_run(path):
    """Read one dataset .mat file and return it as a Run, with the loader rules applied.

    The test type and test number come from the file name (rawio.parse_filename) and the folder from the
    parent directory. A file whose name does not follow the dataset pattern, such as the CI fixture, gets
    test type "other" and is counted from its first row.
    """
    path = Path(path)
    parsed = rawio.parse_filename(path.name) or {"test_number": None, "test_type": "other"}
    folder = path.parent.name
    special = SPECIAL_FILES.get((folder, parsed["test_number"], parsed["test_type"]), {"soc0": 1.0, "cut": None})
    return build_run(rawio.load_mat(path), path.name, folder, parsed["test_type"], special["soc0"], special["cut"])


def find_runs(raw_dir, test_type=None, folder=None):
    """Return the sorted list of .mat paths under raw_dir/<folder>/, optionally of one test type only.

    test_type is as rawio.classify_test gives it, for example "hppc", "c20", "us06", "cap_1c".
    folder is a folder name such as "25degC"; None searches every sub-folder.
    A file whose name does not follow the dataset pattern is listed only when no test_type is asked for.
    Raises FileNotFoundError if raw_dir (or the named folder) is not a directory, so a wrong path
    does not look like "no files".
    """
    search_dir = Path(raw_dir) if folder is None else Path(raw_dir) / folder
    if not search_dir.is_dir():
        raise FileNotFoundError(f"data directory not found: {search_dir}")

    paths = search_dir.glob("*/*.mat" if folder is None else "*.mat")
    paths = [path for path in paths if not path.name.startswith(".")]
    if test_type is not None:
        paths = [path for path in paths if is_test_type(path, test_type)]
    return sorted(paths)


def is_test_type(path, test_type):
    """True when the file name follows the dataset pattern and names this test type."""
    parsed = rawio.parse_filename(path.name)
    return parsed is not None and parsed["test_type"] == test_type
