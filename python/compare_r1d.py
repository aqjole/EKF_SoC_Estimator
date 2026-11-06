"""Stage S8, step A: the regen ablation, the 2RC-Id model, against 2RC-I and 2RC (docs/decisions.md 1.32, 1.33).

Run from the repo root:  .venv/bin/python python/compare_r1d.py   (or: make ekf-r1d; needs make ekf and make ekf-r1i)

  1. Every run of experiments.evaluation_runs() runs experiments 1 to 4 with the 2RC-Id tables (the 2RC-I tables,
     with R1 from results/params.csv when the held current is negative) and the frozen noise settings, as
     compare_r1i.py does for 2RC-I. Traces go to results/runs/r1d/ (not committed) and are reused while fresh.
  2. results/ekf_results_r1d.csv holds one row per run and experiment, in the columns of results/ekf_results.csv.
  3. results/model_compare_r1d.md puts 2RC, 2RC-I and 2RC-Id side by side, splits the open-loop US06 error by
     current band, gives the R1 ratio of 1.32, every guard of 1.32 with its value, the verdict and the test for
     step B of 1.33. results/plots/s8/model_compare_r1d.png draws the open-loop and experiment-1 columns.
"""

from dataclasses import replace
from functools import partial
from multiprocessing import Pool

import pandas as pd

from compare_r1i import RESULTS_RI_CSV, exp1_means, load_params_ri, per_temperature, process_run
from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.model import Params
from ekfsoc.plots import plot_model_compare
from export_params import PARAMS_CSV, write_text
from fit_r1_current import R1_CURRENT_CSV
from run_all import RESULTS_CSV
from s8_compare import (comparison_lines, guard_rows, guard_table, negative_share_lines, open_loop_numbers,
                        us06_exp1)


RUNS_DIR = REPO_DIR / "results" / "runs" / "r1d"
RESULTS_RD_CSV = REPO_DIR / "results" / "ekf_results_r1d.csv"
COMPARE_MD = REPO_DIR / "results" / "model_compare_r1d.md"
COMPARE_PNG = REPO_DIR / "results" / "plots" / "s8" / "model_compare_r1d.png"
MODELS = ("2RC", "2RC-I", "2RC-Id")

# The test for step B of decisions 1.33: US06 experiment 1 lower by at least this much at each of these temperatures.
B_TEST_TEMPS = (0, -10, -20)
B_TEST_MIN_DROP_PP = 0.10


def load_params_rd():
    """The 2RC-Id tables: the 2RC-I tables with R1 from the r1 table under a negative held current (1.33)."""
    return replace(load_params_ri(), r1_current_discharge_only=True)


def b_test(results):
    """(passes, {temp: change}) for the test for step B of decisions 1.33, 2RC-Id against 2RC-I on US06."""
    old, new = us06_exp1(results["2RC-I"]), us06_exp1(results["2RC-Id"])
    change = {temp: new[temp] - old[temp] for temp in B_TEST_TEMPS}
    return all(value <= -B_TEST_MIN_DROP_PP for value in change.values()), change


def compare_text(results, tables, open_loop, bands, ratios):
    """Text of results/model_compare_r1d.md."""
    us06_rmse = {model: {temp: open_loop[temp][model][0] for temp in T_GRID_DEGC} for model in MODELS}
    guards = guard_rows(results, tables, us06_rmse, "2RC-Id", "2RC-I")
    adopted = all(passed for _, _, passed, _ in guards)
    b_passes, b_change = b_test(results)
    b_text = ", ".join(f"{change:+.4f} pp at {temp} degC" for temp, change in b_change.items())

    lines = [
        "# Model comparison: 2RC, 2RC-I and 2RC-Id (S8, step A)", "",
        "Written by `python/compare_r1d.py` (`make ekf-r1d`). Do not edit by hand.", "",
        "2RC-Id is the 2RC-I model with R1 from the v1.0 table of `results/params.csv` when the held current is "
        "negative (docs/decisions.md 1.33). The three filters run experiments 1 to 4 on the 63 runs with the frozen "
        "noise settings of `results/ekf_config.json`; the numbers come from `results/ekf_results.csv`, "
        "`results/ekf_results_r1i.csv` and `results/ekf_results_r1d.csv`. SoC statistics are over the evaluation runs "
        "(tuning cycle excluded). These 62 runs have been inspected in every stage since S2, so this is a comparison "
        "on a repeatedly inspected set, not a confirmation (1.32).", "",
    ]
    lines += comparison_lines(results, tables, open_loop, bands, MODELS, "2RC-Id", "2RC-I")
    lines += negative_share_lines(bands, ratios, "2RC-Id")
    lines += ["", "## Guards and adoption verdict", "",
              "The guards of docs/decisions.md 1.32, 2RC-Id against the incumbent 2RC-I. For step A the incumbent is "
              "2RC-I, the model S8 starts from, so the stage-budget check is the same comparison. Values are those of "
              "the results CSVs (4 decimals), not the rounded values shown above.", ""]
    lines += guard_table(guards)
    lines += ["", f"**{'ADOPTED' if adopted else 'NOT ADOPTED'}.**", "",
              "## Test for step B", "",
              f"docs/decisions.md 1.33: the experiment-1 US06 SoC RMSE of 2RC-Id is lower than 2RC-I by at least "
              f"{B_TEST_MIN_DROP_PP:.2f} pp at each of {', '.join(f'{temp}' for temp in B_TEST_TEMPS)} degC. "
              f"Change: {b_text}.", "",
              f"**{'MET: step B is written' if b_passes else 'NOT MET: step B does not run'}.**"]
    return "\n".join(lines) + "\n"


def main():
    specs = evaluation_runs(RAW_DIR)
    with Pool() as pool:
        inputs = [R1_CURRENT_CSV, REPO_DIR / "python" / "compare_r1i.py", REPO_DIR / "python" / "compare_r1d.py",
                  REPO_DIR / "python" / "s8_compare.py"]
        scored = pool.map(partial(process_run, load_params_rd, RUNS_DIR, inputs), specs, chunksize=1)
    pd.DataFrame([row for run_rows in scored for row in run_rows]).to_csv(RESULTS_RD_CSV, index=False,
                                                                           float_format="%.4f")
    print(f"wrote {RESULTS_RD_CSV.relative_to(REPO_DIR)}")

    params = {"2RC": Params.from_csv(PARAMS_CSV), "2RC-I": load_params_ri(), "2RC-Id": load_params_rd()}
    open_loop, bands, ratios = open_loop_numbers(params, specs)
    results = {"2RC": pd.read_csv(RESULTS_CSV), "2RC-I": pd.read_csv(RESULTS_RI_CSV),
               "2RC-Id": pd.read_csv(RESULTS_RD_CSV)}
    tables = {model: per_temperature(results[model]) for model in MODELS}
    write_text(COMPARE_MD, compare_text(results, tables, open_loop, bands, ratios))
    plot_model_compare([(model, {temp: open_loop[temp][model][1] for temp in T_GRID_DEGC}, exp1_means(tables[model]))
                        for model in MODELS], COMPARE_PNG)
    print(f"wrote {COMPARE_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
