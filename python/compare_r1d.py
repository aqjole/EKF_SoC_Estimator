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

import numpy as np
import pandas as pd

from compare_r1i import RESULTS_RI_CSV, exp1_means, load_params_ri, per_temperature, process_run, verdict
from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.model import Params
from ekfsoc.plots import plot_model_compare
from export_params import PARAMS_CSV, md_table, write_text
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, validate_us06
from fit_r1_current import R1_CURRENT_CSV, pooled_rmse_mv
from run_all import RESULTS_CSV


RUNS_DIR = REPO_DIR / "results" / "runs" / "r1d"
RESULTS_RD_CSV = REPO_DIR / "results" / "ekf_results_r1d.csv"
COMPARE_MD = REPO_DIR / "results" / "model_compare_r1d.md"
COMPARE_PNG = REPO_DIR / "results" / "plots" / "s8" / "model_compare_r1d.png"
MODELS = ("2RC", "2RC-I", "2RC-Id")

# The guards of decisions 1.32, in pp.
MAX_RUN_HIGHER_PP = 0.50
MAX_CYCLE_HIGHER_PP = 0.25
MAX_EXP4_HIGHER_PP = 0.10
# The test for step B of decisions 1.33: US06 experiment 1 lower by at least this much at each of these temperatures.
B_TEST_TEMPS = (0, -10, -20)
B_TEST_MIN_DROP_PP = 0.10
# The R1 ratio of decisions 1.32: at this current node, over the grid SoC in this range.
RATIO_CURRENT_A = 1.5
RATIO_SOC = (0.5, 0.95)
# Current bands of the open-loop US06 error (decisions 1.33), by the row's own current in A; they do not overlap.
BANDS = (("regen, I <= -0.05", lambda i: i <= -0.05),
         ("rest, abs(I) < 0.05", lambda i: np.abs(i) < 0.05),
         ("0.05 <= I < 1.5", lambda i: (i >= 0.05) & (i < 1.5)),
         ("1.5 <= I < 3", lambda i: (i >= 1.5) & (i < 3.0)),
         ("3 <= I < 6", lambda i: (i >= 3.0) & (i < 6.0)),
         ("I >= 6", lambda i: i >= 6.0))


def load_params_rd():
    """The 2RC-Id tables: the 2RC-I tables with R1 from the r1 table under a negative held current (1.33)."""
    return replace(load_params_ri(), r1_current_discharge_only=True)


def exp1_by_run(results):
    """Experiment-1 rows of the evaluation runs, indexed by (folder, file)."""
    rows = results[(results["experiment"] == "exp1") & ~results["is_tuning"]]
    return rows.set_index(["folder", "file"])


def guard_rows(results, tables, us06_rmse):
    """[guard, value, pass] for each guard of decisions 1.32, 2RC-Id against the incumbent 2RC-I, on CSV values."""
    old, new = exp1_by_run(results["2RC-I"]), exp1_by_run(results["2RC-Id"])
    change = new["rmse_pp"] - old["rmse_pp"]
    over = change[change > MAX_RUN_HIGHER_PP].sort_values(ascending=False)
    over_text = ", ".join(f"{new.loc[run, 'cycle']} at {new.loc[run, 'T_degC']} degC {value:+.4f}"
                          for run, value in over.items()) or "none"
    cycle_change = new.groupby("cycle")["rmse_pp"].mean() - old.groupby("cycle")["rmse_pp"].mean()
    exp4_change = {temp: tables["2RC-Id"][temp]["exp4"] - tables["2RC-I"][temp]["exp4"] for temp in T_GRID_DEGC}
    fewer = [f"{experiment} at {temp} degC" for temp in T_GRID_DEGC for experiment in ("exp2", "exp3_low", "exp3_high")
             if tables["2RC-Id"][temp][experiment] < tables["2RC-I"][temp][experiment]]
    adopted_by_rule, lower, worse = verdict(tables["2RC-I"], tables["2RC-Id"])
    gate = us06_rmse["2RC-Id"][GATE_TEMP_DEGC]
    return [
        ["1. S1 gate", f"US06 at {GATE_TEMP_DEGC} degC: {gate:.4f} mV (limit {GATE_RMSE_MV:.0f})", gate <= GATE_RMSE_MV],
        ["2. rule of 1.22", f"lower at {lower} of 6; higher by more than 0.10 pp at "
                            f"{', '.join(f'{temp} degC' for temp in worse) or 'none'}", adopted_by_rule],
        ["3. run increase", f"largest {change.max():+.4f} pp; above the limit of +{MAX_RUN_HIGHER_PP:.2f}: {over_text}",
         change.max() <= MAX_RUN_HIGHER_PP],
        ["4. largest cycle increase", f"{cycle_change.max():+.4f} pp ({cycle_change.idxmax()}, "
                                      f"limit +{MAX_CYCLE_HIGHER_PP:.2f})", cycle_change.max() <= MAX_CYCLE_HIGHER_PP],
        ["5. worst run", f"{new['rmse_pp'].max():.4f} pp against {old['rmse_pp'].max():.4f} pp",
         new["rmse_pp"].max() <= old["rmse_pp"].max()],
        ["6. experiments 2 to 4", f"largest exp4 increase {max(exp4_change.values()):+.4f} pp (limit "
                                  f"+{MAX_EXP4_HIGHER_PP:.2f}); fewer reached: {', '.join(fewer) or 'none'}",
         max(exp4_change.values()) <= MAX_EXP4_HIGHER_PP and not fewer],
    ]


def us06_exp1(results):
    """Temperature to the experiment-1 SoC RMSE of the US06 run."""
    rows = exp1_by_run(results)
    return rows[rows["cycle"] == "US06"].set_index("T_degC")["rmse_pp"].to_dict()


def b_test(results):
    """(passes, {temp: change}) for the test for step B of decisions 1.33, 2RC-Id against 2RC-I on US06."""
    old, new = us06_exp1(results["2RC-I"]), us06_exp1(results["2RC-Id"])
    change = {temp: new[temp] - old[temp] for temp in B_TEST_TEMPS}
    return all(value <= -B_TEST_MIN_DROP_PP for value in change.values()), change


def band_errors(us06_run):
    """Mean open-loop error in mV per current band of one validate_us06 result, the row's own current deciding."""
    current, error_mv = us06_run["run"].i, us06_run["error_mv"]
    return [float(error_mv[in_band(current)].mean()) for _, in_band in BANDS]


def r1_ratio(params_2rc, params_ri, temp):
    """Median 2RC-I R1 at RATIO_CURRENT_A over the grid SoC in RATIO_SOC, divided by the median v1.0 R1 there."""
    j = list(params_2rc.t_grid).index(temp)
    q = list(params_ri.i_grid).index(RATIO_CURRENT_A)
    soc = (params_2rc.soc_grid >= RATIO_SOC[0]) & (params_2rc.soc_grid <= RATIO_SOC[1])
    return float(np.median(params_ri.r1_current[j, soc, q]) / np.median(params_2rc.r1[j, soc]))


def compare_text(results, tables, open_loop, bands, ratios):
    """Text of results/model_compare_r1d.md."""
    us06_rmse = {model: {temp: open_loop[temp][model][0] for temp in T_GRID_DEGC} for model in MODELS}
    runs = {model: exp1_by_run(results[model]) for model in MODELS}
    us06 = {model: us06_exp1(results[model]) for model in MODELS}

    open_rows = [[str(temp)] + [f"{open_loop[temp][model][0]:.2f}" for model in MODELS]
                 + [f"{open_loop[temp][model][1]:.2f}" for model in MODELS] for temp in T_GRID_DEGC]
    exp1_rows, other_rows, us06_rows = [], [], []
    for temp in T_GRID_DEGC:
        t = {model: tables[model][temp] for model in MODELS}
        lower = int((t["2RC-Id"]["exp1_by_run"] < t["2RC-I"]["exp1_by_run"]).sum())
        exp1_rows.append([str(temp), str(t["2RC"]["runs"])] + [f"{t[model]['exp1']:.2f}" for model in MODELS]
                         + [f"{t['2RC-Id']['exp1'] - t['2RC-I']['exp1']:+.2f}", f"{t['2RC-I']['exp1_median']:.2f}",
                            f"{t['2RC-Id']['exp1_median']:.2f}", f"{lower} of {t['2RC']['runs']}"])
        other_rows.append([str(temp)] + [f"{t[model]['exp4']:.2f}" for model in MODELS]
                          + [" / ".join(str(t[model][experiment]) for model in MODELS)
                             for experiment in ("exp2", "exp3_low", "exp3_high")])
        us06_rows.append([str(temp)] + [f"{us06[model][temp]:.2f}" for model in MODELS]
                         + [f"{us06['2RC-Id'][temp] - us06['2RC-I'][temp]:+.2f}"])
    cycles = sorted(runs["2RC"]["cycle"].unique())
    cycle_rows = []
    for cycle in cycles:
        means = {model: runs[model][runs[model]["cycle"] == cycle]["rmse_pp"].mean() for model in MODELS}
        count = int((runs["2RC"]["cycle"] == cycle).sum())
        cycle_rows.append([cycle, str(count)] + [f"{means[model]:.2f}" for model in MODELS]
                          + [f"{means['2RC-Id'] - means['2RC-I']:+.2f}"])
    band_rows = []
    for temp in T_GRID_DEGC:
        for index, (name, _) in enumerate(BANDS):
            band_rows.append([str(temp), name] + [f"{bands[temp][model][index]:+.1f}" for model in MODELS])
    share_rows = [[str(temp), f"{100.0 * bands[temp]['held_negative']:.1f}", f"{ratios[temp]:.2f}"]
                  for temp in T_GRID_DEGC]
    guards = guard_rows(results, tables, us06_rmse)
    adopted = all(passed for _, _, passed in guards)
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
        "## Open loop", "",
        "The US06 RMSE and the RMSE pooled over every drive run, model minus measured voltage (docs/decisions.md 1.25).",
        "",
    ]
    lines += md_table(["T (degC)"] + [f"US06 {model} (mV)" for model in MODELS]
                      + [f"pooled {model} (mV)" for model in MODELS], open_rows)
    lines += ["", "## Experiment 1", "",
              "SoC RMSE with the correct initial SoC; change and runs lower are 2RC-Id against 2RC-I.", ""]
    lines += md_table(["T (degC)", "evaluation runs"] + [f"mean {model} (pp)" for model in MODELS]
                      + ["mean change (pp)", "median 2RC-I (pp)", "median 2RC-Id (pp)", "runs lower with 2RC-Id"],
                      exp1_rows)
    lines += ["", "### Per drive cycle", "", "Experiment-1 mean SoC RMSE over the cycle's evaluation runs.", ""]
    lines += md_table(["cycle", "runs"] + [f"{model} (pp)" for model in MODELS] + ["change (pp)"], cycle_rows)
    lines += ["", "### US06", "", "Experiment-1 SoC RMSE of the US06 run.", ""]
    lines += md_table(["T (degC)"] + [f"{model} (pp)" for model in MODELS] + ["change (pp)"], us06_rows)
    lines += ["", "## Experiments 2 to 4", "",
              "Experiment 4: mean SoC RMSE with the current offset. Reached: evaluation runs whose error stays within "
              "+-2 pp from some time on, 2RC / 2RC-I / 2RC-Id.", ""]
    lines += md_table(["T (degC)"] + [f"exp4 {model} (pp)" for model in MODELS]
                      + ["exp2 reached", "exp3 low reached", "exp3 high reached"], other_rows)
    lines += ["", "## Open-loop US06 error by current band", "",
              "Mean error in mV, model minus measured. A row's band is set by its own current, the current at the "
              "voltage sample (docs/decisions.md 1.33). The branch states carry over between rows, so a band's error "
              "also holds what the rows before it left in the branches.", ""]
    lines += md_table(["T (degC)", "band (A)"] + [f"{model} (mV)" for model in MODELS], band_rows)
    lines += ["", "Steps whose held current is negative (the steps where 2RC-Id switches R1), and the R1 ratio of "
              f"docs/decisions.md 1.32: the median 2RC-I R1 at {RATIO_CURRENT_A} A over the grid SoC {RATIO_SOC[0]} to "
              f"{RATIO_SOC[1]}, divided by the median v1.0 R1 there.", ""]
    lines += md_table(["T (degC)", "US06 steps with held I < 0 (%)", "R1 ratio"], share_rows)
    lines += ["", "## Guards and adoption verdict", "",
              "The guards of docs/decisions.md 1.32, 2RC-Id against the incumbent 2RC-I. For step A the incumbent is "
              "2RC-I, the model S8 starts from, so the stage-budget check is the same comparison. Values are those of "
              "the results CSVs (4 decimals), not the rounded values shown above.", ""]
    lines += md_table(["guard", "value", "result"], [[name, value, "pass" if passed else "FAIL"]
                                                     for name, value, passed in guards])
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
        inputs = [R1_CURRENT_CSV, REPO_DIR / "python" / "compare_r1i.py", REPO_DIR / "python" / "compare_r1d.py"]
        scored = pool.map(partial(process_run, load_params_rd, RUNS_DIR, inputs), specs, chunksize=1)
    pd.DataFrame([row for run_rows in scored for row in run_rows]).to_csv(RESULTS_RD_CSV, index=False,
                                                                           float_format="%.4f")
    print(f"wrote {RESULTS_RD_CSV.relative_to(REPO_DIR)}")

    params = {"2RC": Params.from_csv(PARAMS_CSV), "2RC-I": load_params_ri(), "2RC-Id": load_params_rd()}
    open_loop, bands, ratios = {}, {}, {}
    for temp in T_GRID_DEGC:
        here = [spec for spec in specs if spec.nominal_temp_degc == temp]
        us06 = {model: validate_us06(params[model], temp) for model in MODELS}
        open_loop[temp] = {model: (us06[model]["rmse_mv"], pooled_rmse_mv(params[model], here)) for model in MODELS}
        bands[temp] = {model: band_errors(us06[model]) for model in MODELS}
        bands[temp]["held_negative"] = float(np.mean(us06["2RC"]["run"].i[:-1] < 0.0))
        ratios[temp] = r1_ratio(params["2RC"], params["2RC-I"], temp)

    results = {"2RC": pd.read_csv(RESULTS_CSV), "2RC-I": pd.read_csv(RESULTS_RI_CSV),
               "2RC-Id": pd.read_csv(RESULTS_RD_CSV)}
    tables = {model: per_temperature(results[model]) for model in MODELS}
    text = compare_text(results, tables, open_loop, bands, ratios)
    write_text(COMPARE_MD, text)
    plot_model_compare([(model, {temp: open_loop[temp][model][1] for temp in T_GRID_DEGC}, exp1_means(tables[model]))
                        for model in MODELS], COMPARE_PNG)
    print(f"wrote {COMPARE_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
