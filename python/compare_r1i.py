"""Stage S7, step 4: the four experiments on the 2RC-I model and the adoption verdict (docs/decisions.md 1.29).

Run from the repo root:  .venv/bin/python python/compare_r1i.py   (or: make ekf-r1i; needs make ekf and make fit-r1i)

  1. Every run of experiments.evaluation_runs() runs experiments 1 to 4 with the 2RC-I tables (results/params.csv
     plus results/r1_current.csv) and the frozen noise settings of results/ekf_config.json, as run_all.py does for
     the 2RC model. Traces go to results/runs/r1i/ (not committed) and are reused while they are fresh.
  2. results/ekf_results_r1i.csv holds one row per run and experiment, in the columns of results/ekf_results.csv.
  3. results/model_compare_r1i.md puts 2RC next to 2RC-I per temperature: open-loop US06 and pooled drive-run
     RMSE, experiment-1 and experiment-4 mean SoC RMSE, the reached counts of experiments 2 and 3, and the
     adoption verdict of decisions 1.29, computed here. results/plots/s7/model_compare_r1i.png draws it.
"""

from functools import partial
from multiprocessing import Pool

import pandas as pd

from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.ekf import EkfConfig
from ekfsoc.experiments import evaluation_runs, experiment_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.model import Params
from ekfsoc.plots import plot_model_compare
from ekfsoc.r1_current import read_r1_current
from export_params import PARAMS_CSV, md_table, write_text
from fit_all import validate_us06
from fit_r1_current import R1_CURRENT_CSV, pooled_rmse_mv
from run_all import CONFIG_JSON, DEPENDENCIES, RESULTS_CSV, is_fresh, load_traces, save_traces, score_run


RUNS_DIR = REPO_DIR / "results" / "runs" / "r1i"
RESULTS_RI_CSV = REPO_DIR / "results" / "ekf_results_r1i.csv"
COMPARE_MD = REPO_DIR / "results" / "model_compare_r1i.md"
COMPARE_PNG = REPO_DIR / "results" / "plots" / "s7" / "model_compare_r1i.png"

# The adoption rule of decisions 1.29 (the rule of 1.22): lower at this many temperatures or more, and higher at
# none by more than this many pp.
MIN_LOWER = 4
MAX_HIGHER_PP = 0.10


def load_params_ri():
    """The 2RC-I tables: results/params.csv with the R1 table over current of results/r1_current.csv."""
    return read_r1_current(Params.from_csv(PARAMS_CSV), R1_CURRENT_CSV)


def process_run_ri(spec):
    """The scored rows of one run on the 2RC-I model; its traces are computed and saved first unless fresh."""
    traces_path = RUNS_DIR / f"{spec.folder}__{spec.path.stem}.npz"
    if not is_fresh([traces_path], [spec.path, R1_CURRENT_CSV, *DEPENDENCIES]):
        run = load_run(spec.path)
        cases = experiment_runs(run, load_params_ri(), EkfConfig.from_json(CONFIG_JSON))
        save_traces(traces_path, run.t, run.v, soc_ref(run), cases)
    return score_run(spec, *load_traces(traces_path))


def per_temperature(results):
    """Per temperature: experiment-1 and -4 mean SoC RMSE and the reached counts of experiments 2 and 3."""
    evaluation = results[~results["is_tuning"]]
    table = {}
    for temp in T_GRID_DEGC:
        here = evaluation[evaluation["T_degC"] == temp]
        mean = lambda experiment: here[here["experiment"] == experiment]["rmse_pp"].mean()
        reached = lambda experiment: int(here[here["experiment"] == experiment]["t_conv_s"].notna().sum())
        exp1 = here[here["experiment"] == "exp1"].set_index("file")["rmse_pp"]
        table[temp] = {"exp1": exp1.mean(), "exp1_median": exp1.median(), "exp1_by_run": exp1, "exp4": mean("exp4"),
                       "runs": len(exp1), "exp2": reached("exp2"), "exp3_low": reached("exp3_low"),
                       "exp3_high": reached("exp3_high")}
    return table


def verdict(old, new):
    """(adopted, lower count, temperatures higher by more than MAX_HIGHER_PP) by the rule of decisions 1.29."""
    lower = sum(new[temp]["exp1"] < old[temp]["exp1"] for temp in T_GRID_DEGC)
    worse = [temp for temp in T_GRID_DEGC if new[temp]["exp1"] - old[temp]["exp1"] > MAX_HIGHER_PP]
    return lower >= MIN_LOWER and not worse, lower, worse


def compare_text(old, new, open_loop):
    """Text of results/model_compare_r1i.md."""
    open_rows, exp1_rows, other_rows = [], [], []
    for temp in T_GRID_DEGC:
        o, n, (us06_old, us06_new, pooled_old, pooled_new) = old[temp], new[temp], open_loop[temp]
        open_rows.append([str(temp), f"{us06_old:.2f}", f"{us06_new:.2f}", f"{pooled_old:.2f}", f"{pooled_new:.2f}"])
        better = int((n["exp1_by_run"] < o["exp1_by_run"]).sum())
        exp1_rows.append([str(temp), str(o["runs"]), f"{o['exp1']:.2f}", f"{n['exp1']:.2f}",
                          f"{n['exp1'] - o['exp1']:+.2f}", f"{o['exp1_median']:.2f}", f"{n['exp1_median']:.2f}",
                          f"{better} of {o['runs']}"])
        other_rows.append([str(temp), f"{o['exp4']:.2f}", f"{n['exp4']:.2f}", f"{o['exp2']} / {n['exp2']}",
                           f"{o['exp3_low']} / {n['exp3_low']}", f"{o['exp3_high']} / {n['exp3_high']}"])
    adopted, lower, worse = verdict(old, new)
    worse_text = ", ".join(f"{temp} degC" for temp in worse) or "none"
    lines = [
        "# Model comparison: 2RC and 2RC-I (S7)", "",
        "Written by `python/compare_r1i.py` (`make ekf-r1i`). Do not edit by hand.", "",
        "2RC-I is the 2RC model with R1 read over current (docs/decisions.md 1.28). Both filters run experiments 1 to 4 "
        "on the 63 runs with the frozen noise settings of `results/ekf_config.json`; the 2RC numbers come from "
        "`results/ekf_results.csv`, the 2RC-I numbers from `results/ekf_results_r1i.csv`. SoC statistics are over the "
        "evaluation runs (tuning cycle excluded).", "",
        "## Open loop", "",
        "The US06 RMSE and the RMSE pooled over every drive run, model minus measured voltage (docs/decisions.md 1.25).",
        "",
    ]
    lines += md_table(["T (degC)", "US06 2RC (mV)", "US06 2RC-I (mV)", "pooled 2RC (mV)", "pooled 2RC-I (mV)"],
                      open_rows)
    lines += ["", "## Experiment 1", "",
              "SoC RMSE with the correct initial SoC. The mean decides the verdict (docs/decisions.md 1.29); the median "
              "and the number of runs whose RMSE is lower with 2RC-I show how the change spreads over the runs.", ""]
    lines += md_table(["T (degC)", "evaluation runs", "mean 2RC (pp)", "mean 2RC-I (pp)", "mean change (pp)",
                       "median 2RC (pp)", "median 2RC-I (pp)", "runs lower with 2RC-I"], exp1_rows)
    lines += ["", "## Experiments 2 to 4", "",
              "Experiment 4: mean SoC RMSE with the current offset. Reached: evaluation runs whose error stays within "
              "+-2 pp from some time on, 2RC / 2RC-I.", ""]
    lines += md_table(["T (degC)", "exp4 2RC (pp)", "exp4 2RC-I (pp)", "exp2 reached", "exp3 low reached",
                       "exp3 high reached"], other_rows)
    lines += [
        "", "## Adoption verdict", "",
        f"Rule (docs/decisions.md 1.29): the experiment-1 mean SoC RMSE is lower than the 2RC value at {MIN_LOWER} or "
        f"more of the six temperatures and higher at none by more than {MAX_HIGHER_PP:.2f} pp.",
        "",
        f"Lower at {lower} of 6 temperatures; higher by more than {MAX_HIGHER_PP:.2f} pp at: {worse_text}. "
        f"**{'ADOPTED' if adopted else 'NOT ADOPTED'}.**",
    ]
    return "\n".join(lines) + "\n"


def main():
    specs = evaluation_runs(RAW_DIR)
    with Pool() as pool:
        scored = pool.map(process_run_ri, specs, chunksize=1)
    pd.DataFrame([row for run_rows in scored for row in run_rows]).to_csv(RESULTS_RI_CSV, index=False,
                                                                           float_format="%.4f")
    print(f"wrote {RESULTS_RI_CSV.relative_to(REPO_DIR)}")

    params_2rc, params_ri = Params.from_csv(PARAMS_CSV), load_params_ri()
    open_loop = {}
    for temp in T_GRID_DEGC:
        here = [spec for spec in specs if spec.nominal_temp_degc == temp]
        open_loop[temp] = (validate_us06(params_2rc, temp)["rmse_mv"], validate_us06(params_ri, temp)["rmse_mv"],
                           pooled_rmse_mv(params_2rc, here), pooled_rmse_mv(params_ri, here))

    old = per_temperature(pd.read_csv(RESULTS_CSV))
    new = per_temperature(pd.read_csv(RESULTS_RI_CSV))
    write_text(COMPARE_MD, compare_text(old, new, open_loop))
    plot_model_compare(old, new, open_loop, COMPARE_PNG)
    print(f"wrote {COMPARE_MD.relative_to(REPO_DIR)}")
    print(compare_text(old, new, open_loop).splitlines()[-1])


if __name__ == "__main__":
    main()
