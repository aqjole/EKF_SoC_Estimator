"""S11 close: the 3RC-D0 C build against the Python filter on every experiment of every run (decisions 1.46, 1.54).

Run from the repo root:  .venv/bin/python python/compare_c_3rcd0.py   (or: make equiv-3rcd0; needs make ekf-3rcd0)

For each of the 63 runs and each of experiments 1, 2, 3 low, 3 high, 3 reference and 4, the filter inputs from the
experiment's start row to the end of the run are written to results/runs/c_inputs_3rcd0/ with dt = 0 at the start
row and, in experiment 4, the current offset added in float64 as Python adds it. The float and the double build of
c/tools/ekf_run_csv with -DEKF_USE_3RCD0=ON run them from the Python soc0, and their SoC is compared row by row with
the stored Python trace of results/runs/3rcd0/. The report and the CSV give max and RMS |delta SoC| in pp; the
command exits with status 1 when a build reaches its threshold.
"""

from functools import partial
from multiprocessing import Pool

import numpy as np
import pandas as pd

from compare_3rcd0 import RUNS_DIR as TRACES_DIR
from compare_c import (INPUT_COLUMNS, build_c, check_finite, exit_on_failure, frozen_config, pp_text,
                       run_c, stat_columns, temperature_lines, verdict_lines)
from ekfsoc import rawio
from ekfsoc.constants import RAW_DIR, REPO_DIR
from ekfsoc.experiments import OFFSET_A, evaluation_runs
from ekfsoc.loader import load_run
from ekfsoc.metrics import max_abs_pp, rmse_pp
from export_params import md_table, write_text
from run_all import RUNS_DIR, load_traces


INPUTS_DIR = RUNS_DIR / "c_inputs_3rcd0"
REPORT_MD = REPO_DIR / "results" / "equivalence_3rcd0.md"
REPORT_CSV = REPO_DIR / "results" / "equivalence_3rcd0.csv"
EXPERIMENTS = ("exp1", "exp2", "exp3_low", "exp3_high", "exp3_ref", "exp4")
IMPLEMENTATIONS = {"float": (partial(run_c, "float", model="3rcd0"), 0.1),
                   "double": (partial(run_c, "double", model="3rcd0"), 1e-3)}


def write_inputs(path, run, start, offset):
    """The filter inputs from row `start` on, with dt = 0 at the restart, as run_ekf processes them."""
    dt = run.dt[start:].copy()
    dt[0] = 0.0
    np.savetxt(path, np.column_stack([dt, run.i[start:] + offset, run.v[start:], run.temp[start:]]), fmt="%.17g",
               delimiter=",", header=INPUT_COLUMNS, comments="")


def compare_run(spec, cfg):
    """One table row per experiment of a run."""
    name = f"{spec.folder}__{spec.path.stem}"
    _, _, _, cases = load_traces(TRACES_DIR / f"{name}.npz")
    run = load_run(spec.path)
    rows = []
    for experiment in EXPERIMENTS:
        case = cases[experiment]
        start = case["start"]
        path = INPUTS_DIR / f"{name}__{experiment}.csv"
        write_inputs(path, run, start, OFFSET_A if experiment == "exp4" else 0.0)
        soc_python = case["soc"][start:]
        everywhere = np.ones(len(soc_python), dtype=bool)
        row = {"folder": spec.folder, "T": spec.nominal_temp_degc, "cycle": spec.cycle_name,
               "test": rawio.parse_filename(spec.path.name)["test_number"], "experiment": experiment,
               "rows": len(soc_python)}
        for implementation, (runner, _) in IMPLEMENTATIONS.items():
            delta = soc_python - runner(path, cfg, case["soc0"])
            row[f"{implementation}_max_pp"] = max_abs_pp(delta, everywhere)
            row[f"{implementation}_rms_pp"] = rmse_pp(delta, everywhere)
        rows.append(row)
    return rows


def experiment_lines(table):
    rows = [[experiment, str(len(group)), *[pp_text(group[column].max()) for column in stat_columns(IMPLEMENTATIONS)]]
            for experiment, group in table.groupby("experiment", sort=False)]
    headers = [f"{name} {stat} (pp)" for name in IMPLEMENTATIONS for stat in ("max", "largest RMS")]
    return md_table(["experiment", "cases", *headers], rows)


def report_text(table, cfg, runs):
    labelled = table.assign(cycle=table.cycle + ", " + table.experiment)
    lines = [
        "# C port equivalence, 3RC-D0 (S11 close)",
        "",
        "Written by `python/compare_c_3rcd0.py` (`make equiv-3rcd0`); decisions 1.46 and 1.54. The four-state C "
        "build (`-DEKF_USE_3RCD0=ON`, `c/tools/ekf_run_csv`) runs experiments 1, 2, 3 low, 3 high, 3 reference and 4 "
        f"on the {runs} runs with the frozen settings of "
        f"`results/ekf_config.json` (q_soc = {cfg.q_soc:g}, q_v = {cfg.q_v:g}, r = {cfg.r:g}), each from its "
        "start row with dt = 0 there and the Python soc0, experiment 4 with its current offset. delta SoC = Python "
        "SoC - C SoC over every processed row, tails included, in pp; the Python SoC is the stored trace of "
        "`results/runs/3rcd0/`. The thresholds on max |delta SoC| are those of 1.46. The tool writes SoC with 10 "
        "significant digits, so the double build sits near 5e-9 pp. Per-case values: "
        "[`equivalence_3rcd0.csv`](equivalence_3rcd0.csv).",
        "",
        "## Result",
        "",
        *verdict_lines(labelled, IMPLEMENTATIONS),
        "",
        "## Per experiment",
        "",
        *experiment_lines(table),
        "",
        "## Per temperature",
        "",
        *temperature_lines(table, IMPLEMENTATIONS),
    ]
    return "\n".join(lines) + "\n"


def main():
    cfg = frozen_config()
    specs = evaluation_runs(RAW_DIR)
    build_c("3rcd0")
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with Pool() as pool:
        compared = pool.map(partial(compare_run, cfg=cfg), specs, chunksize=1)
    table = pd.DataFrame([row for rows in compared for row in rows])
    check_finite(table, IMPLEMENTATIONS)
    table.to_csv(REPORT_CSV, index=False, float_format="%.6e")
    write_text(REPORT_MD, report_text(table, cfg, len(specs)))
    print(f"wrote {REPORT_MD.relative_to(REPO_DIR)}")
    print("\n".join(verdict_lines(table.assign(cycle=table.cycle + ", " + table.experiment), IMPLEMENTATIONS)))
    exit_on_failure(table, IMPLEMENTATIONS, REPORT_MD)


if __name__ == "__main__":
    main()
