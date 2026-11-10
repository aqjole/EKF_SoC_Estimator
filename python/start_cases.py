"""S12 step A, parts 1 and 2 (decision 1.56): the history before each run and the 189 wrong-start cases of 3RC-D0.

Part 1 reads every raw file with the record building of `data_checks.py` (section 8 finds the previous file of a
folder by first TimeStamp, section 9 measures the final rest of a Charge file) and classes each run as rested or
unknown. Part 2 replays experiment 1 and the three wrong starts of every run under the S2 settings with the state
history of `run_ekf`, checks each replay row by row against the stored trace, and measures each wrong-start case.
Nothing here changes the filter.
"""

import math

import numpy as np

from compare_3rcd0 import RUNS_DIR as RUNS_3RCD0
from data_checks import DRIVE_TYPES, previous_file, scan_file, short_name
from ekfsoc import rawio
from ekfsoc.constants import Q_REF_AH
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.loader import load_run
from ekfsoc.metrics import MV, PP, max_abs_pp, window_mask
from fit_3rcd0 import load_candidate
from run_all import CONFIG_JSON, load_traces
from s11_evaluate import WRONG, trace_path
from s12_prescreen import PEAK_LIMIT_PP


# The history classes of part 1: a rest of at least REST_MIN_S at the end of the previous file and at most GAP_MAX_S
# from its last row to the run's first used row make a start rested.
REST_MIN_S = 600.0
GAP_MAX_S = 60.0
RESTED, UNKNOWN, IN_RUN = "rested", "unknown", "in-run"
CLASS_CODE = {RESTED: 0, UNKNOWN: 1, IN_RUN: 2}
# The spans after a start over which the current, voltage and error are measured, and the history before an
# experiment-3 start, in s.
SPANS_S = (1, 10, 30)
BEFORE_S = 30.0


def scan_record(record):
    """One file's record as data_checks builds it, plus the TimeStamp of a drive file's first used row."""
    data = rawio.load_mat(record["path"])
    scan_file(record, data, Q_REF_AH)
    if record["test_type"] in DRIVE_TYPES:
        record["first_used_stamp"] = rawio.parse_timestamp(data["TimeStamp"][record["first_row_used"]])
    return record


def history_class(rest_s, gap_s):
    """Rested when the previous file ends in a rest of at least REST_MIN_S and the gap is at most GAP_MAX_S.

    A missing previous file or rest (NaN) is unknown.
    """
    return RESTED if rest_s >= REST_MIN_S and gap_s <= GAP_MAX_S else UNKNOWN


def run_history(spec, records):
    """The previous file of a run, the gap to its first used row on TimeStamp, the final rest and last voltage."""
    record = next(r for r in records if r["folder"] == spec.folder and r["file"] == spec.path.name)
    previous = previous_file(record, records)
    if previous is None:
        name, gap_s, rest_s, last_v = "none", math.nan, math.nan, math.nan
    else:
        name = short_name(previous["file"])
        gap_s = (record["first_used_stamp"] - previous["end"]).total_seconds()
        rest_s = previous["charge"]["rest_after_s"]
        last_v = previous["last_valid_v"]
    return {"previous_file": name, "gap_s": gap_s, "rest_s": rest_s, "previous_last_v": last_v,
            "i_first_A": -record["first_used_i"], "run_class": history_class(rest_s, gap_s)}


def span_end(t, start, seconds):
    """The first row at least `seconds` after the start row (the last row if the run ends sooner), as S11 replays."""
    return min(int(np.searchsorted(t, t[start] + seconds)), len(t) - 1)


def case_measures(run, reference, start, result, exp1):
    """The quantities of 1.56 part 2 for one case: run data after the start, then the filter's response.

    result is the case's run_ekf output with record_state; exp1 is experiment 1's, whose branch states at the
    start row estimate the polarisation the restart drops. Branch voltages in mV, SoC and its deviation in pp.
    """
    t, i = run.t, run.i
    error_pp = PP * (result["soc"] - reference)
    window = window_mask(reference, start)
    rows = np.flatnonzero(window)
    peak = int(rows[np.argmax(np.abs(error_pp[window]))])
    above = rows[np.abs(error_pp[window]) > PEAK_LIMIT_PP]
    on_bound = (result["soc"] == 0.0) | (result["soc"] == 1.0)
    deviation_pp = PP * np.sqrt(result["p_soc"])
    before = (t >= t[start] - BEFORE_S) & (t < t[start])
    at_10s, at_30s = span_end(t, start, 10), span_end(t, start, 30)

    row = {"i_start_A": i[start],
           "mean_abs_i_before_A": np.abs(i[before]).mean() if before.any() else math.nan}
    for seconds in SPANS_S:
        end = span_end(t, start, seconds)
        row[f"mean_abs_i_{seconds}s_A"] = np.abs(i[start:end + 1]).mean()
        row[f"dv_{seconds}s_mV"] = MV * (run.v[end] - run.v[start])
    for seconds in SPANS_S:
        row[f"error_{seconds}s_pp"] = error_pp[span_end(t, start, seconds)]
    row |= {"peak_abs_pp": max_abs_pp(result["soc"] - reference, window), "peak_error_pp": error_pp[peak],
            "peak_s": t[peak] - t[start], "first_above_s": t[above[0]] - t[start] if len(above) else math.nan,
            "soc_std_start_pp": deviation_pp[start], "soc_std_10s_pp": deviation_pp[at_10s],
            "soc_std_peak_pp": deviation_pp[peak]}
    states = {"10s": result["state"][at_10s], "peak": result["state"][peak], "exp1_start": exp1["state"][start]}
    for label, state in states.items():
        row |= {f"v{n}_{label}_mV": MV * value for n, value in enumerate(state[1:], 1)}
    row |= {"bound_rows_30s": int(on_bound[start:at_30s + 1].sum()),
            "bound_rows_to_peak": int(on_bound[start:peak + 1].sum())}
    return row


def replay_run(spec):
    """Replay experiment 1 and the three wrong starts of one run; one row per wrong start.

    Each replay must equal the stored 3RC-D0 trace of `make ekf-3rcd0` row by row, so these are the scored cases.
    """
    run = load_run(spec.path)
    t, _, reference, cases = load_traces(trace_path(spec, RUNS_3RCD0))
    if not np.array_equal(t, run.t):
        raise ValueError(f"stored 3RC-D0 trace of {spec.path.name} is not this run; rerun make ekf-3rcd0")
    params, cfg = load_candidate(), EkfConfig.from_json(CONFIG_JSON)
    results = {}
    for name in ("exp1", *WRONG):
        case = cases[name]
        result = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, case["soc0"], case["start"], record_state=True)
        for field in ("soc", "v_pred"):
            if not np.array_equal(result[field], case[field], equal_nan=True):
                raise ValueError(f"replay of {spec.path.name} {name} differs from the stored trace in {field}")
        results[name] = result
    return [{"folder": spec.folder, "file": spec.path.name, "cycle": spec.cycle_name, "T_degC": spec.nominal_temp_degc,
             "experiment": name, "start_s": t[cases[name]["start"]] - t[0], "soc0": cases[name]["soc0"],
             **case_measures(run, reference, cases[name]["start"], results[name], results["exp1"])}
            for name in WRONG]


def best_threshold(values, flagged):
    """The threshold on `values` that misclassifies the fewest `flagged` cases: (threshold, side, count).

    A case is predicted flagged when its value lies on `side` (">" or "<") of the threshold. Thresholds are the
    midpoints between neighbouring distinct values and the two infinities; the first best in that order wins.
    """
    distinct = np.unique(values)
    cuts = np.concatenate(([-np.inf], (distinct[1:] + distinct[:-1]) / 2, [np.inf]))
    best = None
    for cut in cuts:
        for side, predicted in ((">", values > cut), ("<", values < cut)):
            wrong = int(np.sum(predicted != flagged))
            if best is None or wrong < best[2]:
                best = (float(cut), side, wrong)
    return best

