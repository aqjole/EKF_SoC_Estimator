"""S12 step A, part 3 (decision 1.56): the branch prior alone, by the current rule of kind (i), on the 40 Mix runs.

Experiments 1, 2 and 4 start at row 0 and run through the native evaluator of 1.50 under the S2 settings with
p0_v_std set by the filter's own rule (`ekfsoc.ekf.branch_std`); experiment 3 is taken from the stored S2 traces,
which the rule leaves as they are because every Mix experiment-3 start is above the threshold (checked per run).
The S2 value itself is scored from the stored Python traces, and the native evaluator must reproduce those at the S2
prior before any number is used.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from compare_3rcd0 import RUNS_DIR as RUNS_3RCD0
from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.ekf import RESTED_CURRENT_A, EkfConfig, branch_std
from ekfsoc.experiments import OFFSET_A
from ekfsoc.loader import load_run
from fit_3rcd0 import load_candidate
from run_all import CONFIG_JSON, load_traces, score_run
from s11_evaluate import WRONG, trace_path
from s11_native import NativeModel
from s12_prescreen import temperature_table, wrong_start_peaks


PRIORS_V = (0.005, 0.010, 0.015, 0.020, 0.025, 0.030)
# The row-0 experiments and the current offset each one adds (experiments.experiment_runs).
ROW0_OFFSETS_A = {"exp1": 0.0, "exp2": 0.0, "exp4": OFFSET_A}
NATIVE_TOLERANCE = 1e-12


def prior_run(spec):
    """Scored rows of one Mix run at the S2 prior (stored traces) and at each value of PRIORS_V (native), and the
    largest native-minus-stored difference at the S2 prior (SoC, predicted voltage)."""
    run = load_run(spec.path)
    t, v, reference, stored = load_traces(trace_path(spec, RUNS_3RCD0))
    cfg = EkfConfig.from_json(CONFIG_JSON)
    if min(abs(run.i[stored[name]["start"]]) for name in WRONG[1:]) < RESTED_CURRENT_A:
        raise ValueError(f"an experiment-3 start of {spec.path.name} is below the threshold; it cannot stay at S2")
    model = NativeModel(load_candidate())

    def cases_at(small_v):
        cases = dict(stored)
        for name, offset in ROW0_OFFSETS_A.items():
            prior = replace(cfg, p0_v_std=branch_std(replace(cfg, p0_v_std_rested=small_v), run.i[0] + offset))
            out = model.run(run, prior, stored[name]["soc0"], offset)
            cases[name] = stored[name] | {"soc": out["soc"], "v_pred": out["v_pred"]}
        return cases

    native = cases_at(cfg.p0_v_std)
    deviation = [max(float(np.max(np.abs(native[name][field] - stored[name][field]))) for name in ROW0_OFFSETS_A)
                 for field in ("soc", "v_pred")]
    rows = [row | {"prior_V": cfg.p0_v_std} for row in score_run(spec, t, v, reference, stored)]
    for small_v in PRIORS_V:
        rows += [row | {"prior_V": small_v} for row in score_run(spec, t, v, reference, cases_at(small_v))]
    return rows, deviation


def prior_table(frame):
    """Per temperature: s12_prescreen.temperature_table, and the experiment-2 count above PEAK_LIMIT_PP and its
    largest peak."""
    table = temperature_table(frame)
    for temp in T_GRID_DEGC:
        above, peak = wrong_start_peaks(frame[(frame.T_degC == temp) & (frame.experiment == "exp2")])
        table[temp] |= {"exp2_above": above, "exp2_peak": peak}
    return table


def prior_frame(results):
    """One frame of every scored row of prior_run over the Mix runs, and the largest native deviation."""
    frame = pd.DataFrame([row for rows, _ in results for row in rows])
    deviation = np.max([deviation for _, deviation in results], axis=0)
    return frame, deviation
