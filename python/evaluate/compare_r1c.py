"""Stage S8, step B: the 2RC-Ic model against 2RC-I, with 2RC and 2RC-Id alongside (docs/decisions.md 1.32, 1.35).

Run from the repo root:  PYTHONPATH=python .venv/bin/python python/evaluate/compare_r1c.py
(or: make ekf-r1c; needs make ekf, ekf-r1i, ekf-r1d and fit-r1c)

  1. Every run of experiments.evaluation_runs() runs experiments 1 to 4 with the 2RC-Ic tables (the 2RC-I tables plus
     the charge-side R1 of results/s8/r1_charge.csv) and the frozen noise settings. Traces go to results/runs/r1c/ (not
     committed) and are reused while fresh.
  2. results/s8/ekf_results_r1c.csv holds one row per run and experiment, in the columns of results/s2/ekf_results.csv.
  3. results/s8/model_compare_r1c.md puts 2RC, 2RC-I, 2RC-Id and 2RC-Ic side by side and gives every guard of 1.32,
     2RC-Ic against 2RC-I, with the rounding rule of 1.35, and the verdict. results/plots/s8/model_compare_r1c.png
     draws the open-loop and experiment-1 columns.
"""

from functools import partial
from multiprocessing import Pool

import pandas as pd

from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.model import Params
from ekfsoc.plots import plot_model_compare
from ekfsoc.r1_current import read_r1_charge
from ekfsoc.report import write_text
from evaluate import compare_r1i
from evaluate.compare_r1d import RESULTS_RD_CSV, load_params_rd
from evaluate.compare_r1i import RESULTS_RI_CSV, exp1_means, load_params_ri, per_temperature, process_run
from evaluate.run_all import RESULTS_CSV
from evaluate.s8_compare import (comparison_lines, decided_guards, guard_rows, guard_section, negative_share_lines,
                                 open_loop_numbers)
from fit.export_params import PARAMS_CSV
from fit.fit_r1_charge import R1_CHARGE_CSV
from fit.fit_r1_current import R1_CURRENT_CSV


RUNS_DIR = REPO_DIR / "results" / "runs" / "r1c"
RESULTS_RC_CSV = REPO_DIR / "results" / "s8" / "ekf_results_r1c.csv"
COMPARE_MD = REPO_DIR / "results" / "s8" / "model_compare_r1c.md"
COMPARE_PNG = REPO_DIR / "results" / "plots" / "s8" / "model_compare_r1c.png"
MODELS = ("2RC", "2RC-I", "2RC-Id", "2RC-Ic")
CANDIDATE, INCUMBENT = "2RC-Ic", "2RC-I"


def load_params_rc():
    """The 2RC-Ic tables: the 2RC-I tables with the charge-side R1 of results/s8/r1_charge.csv (decisions 1.35)."""
    return read_r1_charge(load_params_ri(), R1_CHARGE_CSV)


def scored_frame(scored):
    """The unrounded results frame of a list of per-run scored rows."""
    return pd.DataFrame([row for run_rows in scored for row in run_rows])


def compare_text(results, tables, open_loop, bands, ratios, guards):
    """Text of results/s8/model_compare_r1c.md."""
    lines = [
        "# Model comparison: 2RC, 2RC-I, 2RC-Id and 2RC-Ic (S8, step B)", "",
        "Written by `python/evaluate/compare_r1c.py` (`make ekf-r1c`). Do not edit by hand.", "",
        "2RC-Ic is the 2RC-I model with R1 from the charge-side table of `results/s8/r1_charge.csv` when the held current "
        "is negative (docs/decisions.md 1.35). The four filters run experiments 1 to 4 on the 63 runs with the frozen "
        "noise settings of `results/s2/ekf_config.json`; the numbers come from `results/s2/ekf_results.csv`, "
        "`results/s7/ekf_results_r1i.csv`, `results/s8/ekf_results_r1d.csv` and `results/s8/ekf_results_r1c.csv`. SoC "
        "statistics are over the evaluation runs (tuning cycle excluded). These 62 runs have been inspected in every "
        "stage since S2, so this is a comparison on a repeatedly inspected set, not a confirmation (1.32).", "",
    ]
    lines += comparison_lines(results, tables, open_loop, bands, MODELS, CANDIDATE, INCUMBENT)
    lines += negative_share_lines(bands, ratios, CANDIDATE)
    lines += guard_section(guards, CANDIDATE, INCUMBENT)
    return "\n".join(lines) + "\n"


def main():
    specs = evaluation_runs(RAW_DIR)
    python_dir = REPO_DIR / "python"
    with Pool() as pool:
        inputs_ri = [R1_CURRENT_CSV, python_dir / "evaluate" / "compare_r1i.py"]
        scored_ri = pool.map(partial(process_run, load_params_ri, compare_r1i.RUNS_DIR, inputs_ri), specs, chunksize=1)
        inputs_rc = [R1_CURRENT_CSV, R1_CHARGE_CSV, python_dir / "evaluate" / "compare_r1i.py",
                     python_dir / "evaluate" / "compare_r1c.py", python_dir / "evaluate" / "s8_compare.py"]
        scored_rc = pool.map(partial(process_run, load_params_rc, RUNS_DIR, inputs_rc), specs, chunksize=1)
    scored_frame(scored_rc).to_csv(RESULTS_RC_CSV, index=False, float_format="%.4f")
    print(f"wrote {RESULTS_RC_CSV.relative_to(REPO_DIR)}")

    params = {"2RC": Params.from_csv(PARAMS_CSV), "2RC-I": load_params_ri(), "2RC-Id": load_params_rd(),
              "2RC-Ic": load_params_rc()}
    open_loop, bands, ratios = open_loop_numbers(params, specs)
    us06_rmse = {model: {temp: open_loop[temp][model][0] for temp in T_GRID_DEGC} for model in MODELS}
    results = {"2RC": pd.read_csv(RESULTS_CSV), "2RC-I": pd.read_csv(RESULTS_RI_CSV),
               "2RC-Id": pd.read_csv(RESULTS_RD_CSV), "2RC-Ic": pd.read_csv(RESULTS_RC_CSV)}
    tables = {model: per_temperature(results[model]) for model in MODELS}
    unrounded = {INCUMBENT: scored_frame(scored_ri), CANDIDATE: scored_frame(scored_rc)}
    unrounded_tables = {model: per_temperature(frame) for model, frame in unrounded.items()}
    guards = decided_guards(guard_rows(results, tables, us06_rmse, CANDIDATE, INCUMBENT),
                            guard_rows(unrounded, unrounded_tables, us06_rmse, CANDIDATE, INCUMBENT))
    write_text(COMPARE_MD, compare_text(results, tables, open_loop, bands, ratios, guards))
    plot_model_compare([(model, {temp: open_loop[temp][model][1] for temp in T_GRID_DEGC}, exp1_means(tables[model]))
                        for model in MODELS], COMPARE_PNG)
    print(f"wrote {COMPARE_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
