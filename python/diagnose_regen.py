"""S11 step B diagnostic: the regen rows at the cycler's 4.2 V limit and each model's SoC error across them (decision 1.48).

A limit row is a row at or above LIMIT_V whose own current is below zero (regen). A limit interval is a maximal set
of limit rows in which consecutive limit rows are at most GAP_S apart; rows between them belong to the interval.
For every interval of the 63 runs the report gives the experiment-1 SoC error of each model at the row before the
interval and at its last row, read from the stored traces that the models' own make targets write (`make all` runs
them first). 3RC-D0 appears under the S2 settings and under the S11 step A candidate, as 1.51 asks.
"""

from multiprocessing import Pool

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from compare_3rcd import RUNS_DIR as RUNS_3RCD
from compare_3rcd0 import RUNS_DIR as RUNS_3RCD0
from compare_r1c import RUNS_DIR as RUNS_RC
from compare_r1d import RUNS_DIR as RUNS_RD
from compare_r1i import RUNS_DIR as RUNS_RI
from compare_r1l import RUNS_DIR as RUNS_RL
from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import PP
from ekfsoc.plots import DOTS, MODEL_COLOR, save
from export_params import md_table, write_text
from run_all import RUNS_DIR as RUNS_2RC, load_traces
from s10_protocol import DISCLOSURE, RESULTS, splits
from s11_evaluate import RUNS as RUNS_3RCD0N


LIMIT_V = 4.1995
GAP_S = 1.0
BIG_CHANGE_PP = 1.0
MODELS = {
    "2RC": RUNS_2RC, "2RC-I": RUNS_RI, "2RC-Id": RUNS_RD, "2RC-Ic": RUNS_RC, "2RC-Il": RUNS_RL,
    "3RC-D": RUNS_3RCD, "3RC-D0": RUNS_3RCD0, "3RC-D0-N": RUNS_3RCD0N,
}
CSV = RESULTS / "s11" / "regen_limit.csv"
REPORT = RESULTS / "s11" / "regen_limit.md"
PLOT = RESULTS / "plots" / "s11" / "regen_limit.png"


def limit_intervals(t, v, i):
    """Return the (first row, last row) of each limit interval."""
    rows = np.flatnonzero((v >= LIMIT_V) & (i < 0))
    if len(rows) == 0:
        return []
    breaks = np.flatnonzero(np.diff(t[rows]) > GAP_S)
    return list(zip(rows[np.r_[0, breaks + 1]], rows[np.r_[breaks, len(rows) - 1]]))


def exp1_errors(spec, run, reference):
    """Each model's experiment-1 SoC error in pp, after checking that its trace belongs to this run."""
    errors = {}
    for name, folder in MODELS.items():
        t, v, saved_reference, cases = load_traces(folder / f"{spec.folder}__{spec.path.stem}.npz")
        if not all(np.array_equal(x, y) for x, y in ((t, run.t), (v, run.v), (saved_reference, reference))):
            raise ValueError(f"{name} trace of {spec.path.name} does not match the run; rerun its make target")
        errors[name] = PP * (cases["exp1"]["soc"] - reference)
    return errors


def run_rows(task):
    spec, split = task
    run = load_run(spec.path)
    reference = soc_ref(run)
    errors = exp1_errors(spec, run, reference)
    rows = []
    for k, (first, last) in enumerate(limit_intervals(run.t, run.v, run.i), 1):
        limit = np.flatnonzero((run.v[first:last + 1] >= LIMIT_V) & (run.i[first:last + 1] < 0)) + first
        row = {"split": split, "folder": spec.folder, "file": spec.path.name, "cycle": spec.cycle_name,
               "T_degC": spec.nominal_temp_degc, "interval": k, "t_start_s": run.t[first] - run.t[0],
               "duration_s": run.t[last] - run.t[first], "limit_rows": len(limit),
               "soc_ref_min": reference[first:last + 1].min(), "soc_ref_max": reference[first:last + 1].max(),
               "i_min_A": run.i[limit].min(), "i_max_A": run.i[limit].max()}
        for name, error in errors.items():
            row[f"{name}_before_pp"] = error[first - 1] if first > 0 else np.nan
            row[f"{name}_after_pp"] = error[last]
        rows.append(row)
    return rows


def changes(frame):
    """The change of each model's error across each interval, in pp, one column per model."""
    return pd.DataFrame({name: frame[f"{name}_after_pp"] - frame[f"{name}_before_pp"] for name in MODELS})


def run_sums(frame, absolute=False):
    """The change summed over each run's intervals (signed, or in size), one row per run."""
    delta = changes(frame).abs() if absolute else changes(frame)
    keys = ["split", "folder", "cycle", "T_degC"]
    return pd.concat([frame[keys], delta], axis=1).groupby(keys, sort=False).sum().reset_index()


def model_table(title, values, fmt):
    """One row per model, one column per temperature from 40 degC down."""
    values = values.reindex(sorted(T_GRID_DEGC, reverse=True))
    cells = [[name, *[format(value, fmt) for value in values[name]]] for name in MODELS]
    return [f"## {title}", "", *md_table(["Model", *[f"{t} degC" for t in values.index]], cells), ""]


def report_lines(frame, signed):
    rows = [[str(temp), str(here.file.nunique()), str(len(here)), str(here.limit_rows.sum()),
             f"{(here.t_start_s + here.duration_s).max():.1f}", f"{here.soc_ref_min.min():.4f}",
             f"{here.i_min_A.min():.3f}"] for temp, here in sorted(frame.groupby("T_degC"), reverse=True)]
    big = pd.concat([frame[["T_degC"]], changes(frame).abs().gt(BIG_CHANGE_PP)], axis=1)
    lines = ["# Regen rows at the 4.2 V limit (S11 step B diagnostic)", "",
             "Generated by `make diagnose-regen`; decisions 1.48 and 1.51.", "", DISCLOSURE, "",
             f"A limit row is a row at or above {LIMIT_V} V whose own current is below zero. A limit interval is a "
             f"maximal set of limit rows in which consecutive limit rows are at most {GAP_S:g} s apart; the rows "
             "between them belong to the interval. The change across an interval is the experiment-1 SoC error at "
             "its last row minus the error at the row before it, from the stored traces, so it includes the "
             "filter's response to every row inside the interval. 3RC-D0-N is 3RC-D0 under the S11 step A "
             "candidate settings (1.51), which were not adopted.", "",
             "## Limit rows per temperature", "",
             *md_table(["T (degC)", "runs", "intervals", "limit rows", "end of last interval (s)",
                        "lowest reference SoC", "most negative current (A)"], rows), "",
             *model_table("Mean over runs of the summed signed change (pp)",
                          signed.groupby("T_degC")[list(MODELS)].mean(), "+.3f"),
             *model_table("Mean over runs of the summed change in size (pp)",
                          run_sums(frame, absolute=True).groupby("T_degC")[list(MODELS)].mean(), ".3f"),
             *model_table(f"Intervals whose change exceeds {BIG_CHANGE_PP:g} pp in size",
                          big.groupby("T_degC")[list(MODELS)].sum(), "d")]
    cells = [[row["split"], row["folder"], row["cycle"], *[f"{row[name]:+.3f}" for name in MODELS]]
             for _, row in signed.iterrows()]
    lines += ["## Summed signed change per run (pp)", "", *md_table(["Split", "Folder", "Cycle", *MODELS], cells), ""]
    return "\n".join(lines)


def plot(runs):
    fig, axes = plt.subplots(2, 3, figsize=(12, 6), sharey=True)
    for axis, temp in zip(axes.flat, sorted(T_GRID_DEGC, reverse=True)):
        here = runs[runs.T_degC == temp]
        for k, name in enumerate(MODELS):
            axis.plot(np.full(len(here), k), here[name], color=MODEL_COLOR, **DOTS)
        axis.axhline(0.0, color="black", linewidth=0.5)
        axis.set_xticks(range(len(MODELS)), MODELS, rotation=60)
        axis.set_title(f"{temp} degC")
    for axis in axes[:, 0]:
        axis.set_ylabel("change per run (pp)")
    fig.suptitle("Experiment-1 SoC error change summed over each run's limit intervals")
    save(fig, PLOT)


def main():
    mix, standard = splits()
    tasks = [(spec, "Mix") for spec in mix] + [(spec, "standard") for spec in standard]
    with Pool() as pool:
        frame = pd.DataFrame([row for rows in pool.map(run_rows, tasks, chunksize=1) for row in rows])
    frame.to_csv(CSV, index=False, float_format="%.4f")
    signed = run_sums(frame)
    write_text(REPORT, report_lines(frame, signed))
    plot(signed)


if __name__ == "__main__":
    main()
