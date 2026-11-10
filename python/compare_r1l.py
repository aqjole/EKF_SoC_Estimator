"""Stage S8, step C: the 2RC-Il model against 2RC-I, with 2RC alongside (docs/decisions.md 1.32, 1.37).

Run from the repo root:  .venv/bin/python python/compare_r1l.py
(or: make ekf-r1l; needs make ekf, ekf-r1i and fit-r1l)

  1. Every run of experiments.evaluation_runs() runs experiments 1 to 4 with the 2RC-Il tables (the 2RC-I tables with
     the R1 table of results/s8/r1_low.csv) and the frozen noise settings. Traces go to results/runs/r1l/ (not committed)
     and are reused while fresh.
  2. results/s8/ekf_results_r1l.csv holds one row per run and experiment, in the columns of results/s2/ekf_results.csv. Its
     40 degC rows must equal those of results/s7/ekf_results_r1i.csv, since the 40 degC runs read only unscaled slices.
  3. results/s8/model_compare_r1l.md puts 2RC, 2RC-I and 2RC-Il side by side, gives the US06 share of steps where 2RC-Il
     reads a scaled R1 and the R1 ratio of 1.32 for both current models, every guard of 1.32, 2RC-Il against 2RC-I,
     with the rounding rule of 1.35, and the verdict. results/plots/s8/model_compare_r1l.png draws the open-loop and
     experiment-1 columns.
"""

from functools import partial
from multiprocessing import Pool

import numpy as np
import pandas as pd

import compare_r1i
from compare_r1c import scored_frame
from compare_r1i import RESULTS_RI_CSV, exp1_means, load_params_ri, per_temperature, process_run
from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.model import Params
from ekfsoc.plots import plot_model_compare
from ekfsoc.r1_current import read_r1_current
from export_params import PARAMS_CSV, md_table, write_text
from fit_all import load_test
from fit_r1_current import PULSES_CSV, R1_CURRENT_CSV
from fit_r1_low import FIT_TEMPS_DEGC, R1_LOW_CSV
from run_all import RESULTS_CSV
from s8_compare import (RATIO_CURRENT_A, RATIO_SOC, RECOMPUTE_WITHIN, comparison_lines, decided_guards, guard_rows,
                        guard_table, open_loop_numbers, r1_ratio)


RUNS_DIR = REPO_DIR / "results" / "runs" / "r1l"
RESULTS_RL_CSV = REPO_DIR / "results" / "s8" / "ekf_results_r1l.csv"
COMPARE_MD = REPO_DIR / "results" / "s8" / "model_compare_r1l.md"
COMPARE_PNG = REPO_DIR / "results" / "plots" / "s8" / "model_compare_r1l.png"
MODELS = ("2RC", "2RC-I", "2RC-Il")
CANDIDATE, INCUMBENT = "2RC-Il", "2RC-I"
UNSCALED_TEMP_DEGC = 40  # its runs read only slices with r = 1 (decisions 1.37)


def load_params_rl():
    """The 2RC-Il tables: results/s1/params.csv with the R1 table over current of results/s8/r1_low.csv (decisions 1.37)."""
    return read_r1_current(Params.from_csv(PARAMS_CSV), R1_LOW_CSV)


def check_unscaled_rows(results_ri, results_rl):
    """Raise if the 40 degC rows of the two results frames differ: those runs must equal 2RC-I (decisions 1.37)."""
    old = results_ri[results_ri["T_degC"] == UNSCALED_TEMP_DEGC].reset_index(drop=True)
    new = results_rl[results_rl["T_degC"] == UNSCALED_TEMP_DEGC].reset_index(drop=True)
    if not old.equals(new):
        raise SystemExit(f"compare_r1l: the {UNSCALED_TEMP_DEGC} degC rows differ from 2RC-I")


def second_pulse_currents():
    """Temperature to the median over its levels of the second-smallest pulse current in the 2RC-I fit (I_2 of 1.37)."""
    pulses = pd.read_csv(PULSES_CSV)
    used = pulses[pulses["used"]].sort_values("I_A")
    second = used.groupby(["T_degC", "level"])["I_A"].nth(1)
    return {temp: float(np.median(second[used.loc[second.index, "T_degC"] == temp])) for temp in FIT_TEMPS_DEGC}


def low_share(temp, i_2):
    """Share of the US06 steps at a temperature whose held |I| lies in [0.05 A, i_2): where 2RC-Il reads a scaled R1
    (decisions 1.37)."""
    held = np.abs(load_test(temp, "us06").i[:-1])
    return float(np.mean((held >= 0.05) & (held < i_2)))


def low_share_lines(params, ratios):
    """Lines of the US06 share of steps where 2RC-Il reads a scaled R1, and the R1 ratio of 1.32 for both models."""
    i_2 = second_pulse_currents()
    rows = []
    for temp in T_GRID_DEGC:
        share = f"{100.0 * low_share(temp, i_2[temp]):.1f}" if temp in i_2 else "n/a"
        limit = f"{i_2[temp]:.2f}" if temp in i_2 else "n/a"
        rows.append([str(temp), limit, share, f"{ratios[temp]:.2f}",
                     f"{r1_ratio(params['2RC'], params['2RC-Il'], temp):.2f}"])
    lines = ["", f"Steps whose held |I| lies from 0.05 A up to the temperature's second pulse current I_2 (the median "
             f"over its levels), where {CANDIDATE} reads a scaled R1 (docs/decisions.md 1.37); 40 and 25 degC are not "
             "scaled, although the 25 degC runs read the 10 degC slice with a small weight. Then the R1 ratio of 1.32: "
             f"the median R1 of the model at {RATIO_CURRENT_A} A over the grid SoC {RATIO_SOC[0]} to {RATIO_SOC[1]}, "
             "divided by the median v1.0 R1 there.", ""]
    lines += md_table(["T (degC)", "I_2 (A)", "US06 steps with a scaled R1 (%)", "R1 ratio 2RC-I", "R1 ratio 2RC-Il"],
                      rows)
    return lines


def compare_text(results, tables, open_loop, bands, share_lines, guards):
    """Text of results/s8/model_compare_r1l.md."""
    adopted = all(passed for _, _, passed, _ in guards)
    lines = [
        "# Model comparison: 2RC, 2RC-I and 2RC-Il (S8, step C)", "",
        "Written by `python/compare_r1l.py` (`make ekf-r1l`). Do not edit by hand.", "",
        "2RC-Il is the 2RC-I model with R1 from `results/s8/r1_low.csv`: the 2RC-I table scaled at and below each level's "
        "smallest discharge pulse current by factors fitted on the PausCycl files, ramping back to the 2RC-I values at "
        "the level's second pulse (docs/decisions.md 1.37). The table is read at the held |I|, so regen below the "
        "second pulse current reads the scaled R1 too, and a US06 change cannot be credited to the discharge rows "
        "alone. The three "
        "filters run experiments 1 to 4 on the 63 runs with the frozen noise settings of `results/s2/ekf_config.json`; "
        "the numbers come from `results/s2/ekf_results.csv`, `results/s7/ekf_results_r1i.csv` and "
        "`results/s8/ekf_results_r1l.csv`. SoC statistics are over the evaluation runs (tuning cycle excluded). The "
        f"{UNSCALED_TEMP_DEGC} degC runs read only unscaled slices and equal 2RC-I (checked). These 62 runs have been "
        "inspected in every stage since S2, so this is a comparison on a repeatedly inspected set, not a confirmation "
        "(1.32).", "",
    ]
    lines += comparison_lines(results, tables, open_loop, bands, MODELS, CANDIDATE, INCUMBENT)
    lines += share_lines
    lines += ["", "## Guards and adoption verdict", "",
              f"The guards of docs/decisions.md 1.32, {CANDIDATE} against the incumbent {INCUMBENT}, which is also the "
              "model S8 starts from, so the stage-budget check is the same comparison. Values are those of the results "
              f"CSVs (4 decimals); a guard whose value lies within {RECOMPUTE_WITHIN:g} of its limit is recomputed from "
              "unrounded values, which decide (1.35).", ""]
    lines += guard_table(guards)
    recomputed = [f"{name} (unrounded margin {margin:.2e})" for name, value, _, margin in guards
                  if "recomputed" in value]
    lines += ["", f"Guards recomputed from unrounded values: {', '.join(recomputed) or 'none'}. Guard 2 is recomputed "
              f"whenever a temperature's change is exactly 0, as at {UNSCALED_TEMP_DEGC} degC by construction; an "
              "unchanged mean does not count as lower (1.37).", "",
              f"**{'ADOPTED' if adopted else 'NOT ADOPTED'}.**"]
    return "\n".join(lines) + "\n"


def main():
    specs = evaluation_runs(RAW_DIR)
    python_dir = REPO_DIR / "python"
    with Pool() as pool:
        inputs_ri = [R1_CURRENT_CSV, python_dir / "compare_r1i.py"]
        scored_ri = pool.map(partial(process_run, load_params_ri, compare_r1i.RUNS_DIR, inputs_ri), specs, chunksize=1)
        inputs_rl = [R1_LOW_CSV, python_dir / "compare_r1i.py", python_dir / "compare_r1l.py",
                     python_dir / "s8_compare.py"]
        scored_rl = pool.map(partial(process_run, load_params_rl, RUNS_DIR, inputs_rl), specs, chunksize=1)
    scored_frame(scored_rl).to_csv(RESULTS_RL_CSV, index=False, float_format="%.4f")
    print(f"wrote {RESULTS_RL_CSV.relative_to(REPO_DIR)}")

    results = {"2RC": pd.read_csv(RESULTS_CSV), "2RC-I": pd.read_csv(RESULTS_RI_CSV),
               "2RC-Il": pd.read_csv(RESULTS_RL_CSV)}
    check_unscaled_rows(results["2RC-I"], results["2RC-Il"])
    params = {"2RC": Params.from_csv(PARAMS_CSV), "2RC-I": load_params_ri(), "2RC-Il": load_params_rl()}
    open_loop, bands, ratios = open_loop_numbers(params, specs)
    us06_rmse = {model: {temp: open_loop[temp][model][0] for temp in T_GRID_DEGC} for model in MODELS}
    tables = {model: per_temperature(results[model]) for model in MODELS}
    unrounded = {INCUMBENT: scored_frame(scored_ri), CANDIDATE: scored_frame(scored_rl)}
    unrounded_tables = {model: per_temperature(frame) for model, frame in unrounded.items()}
    guards = decided_guards(guard_rows(results, tables, us06_rmse, CANDIDATE, INCUMBENT),
                            guard_rows(unrounded, unrounded_tables, us06_rmse, CANDIDATE, INCUMBENT))
    write_text(COMPARE_MD, compare_text(results, tables, open_loop, bands, low_share_lines(params, ratios), guards))
    plot_model_compare([(model, {temp: open_loop[temp][model][1] for temp in T_GRID_DEGC}, exp1_means(tables[model]))
                        for model in MODELS], COMPARE_PNG)
    print(f"wrote {COMPARE_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
