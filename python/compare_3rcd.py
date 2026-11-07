"""Run S9 experiments after the S1 gate and apply decisions 1.40 on the standard cycles."""

from functools import partial
from multiprocessing import Pool

import matplotlib.pyplot as plt
import pandas as pd

from compare_r1c import scored_frame
from compare_r1i import RESULTS_RI_CSV, RUNS_DIR as RI_TRACES
from compare_r1i import load_params_ri, per_temperature, process_run
from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.ekf import EkfConfig
from ekfsoc.experiments import evaluation_runs, experiment_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.model import Params
from ekfsoc.plots import MODEL_COLORS, save
from export_params import PARAMS_CSV, md_table, write_text
from fit_3rcd import DISCLOSURE, PARAMS_3RCD_CSV, PLOTS, RESULTS, drive_split, load_params_3rcd, score_open_loop
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, validate_us06
from fit_r1_current import R1_CURRENT_CSV
from run_all import CONFIG_JSON, DEPENDENCIES, RESULTS_CSV, is_fresh, load_traces, score_run
from s8_compare import decided_guards, exp1_by_run, guard_rows, guard_table


RUNS_DIR = RESULTS / "runs" / "3rcd"
CANDIDATE_CSV = RESULTS / "ekf_results_3rcd.csv"
COMPARE_MD = RESULTS / "model_compare_3rcd.md"
MODELS = ("2RC", "2RC-I", "3RC-D")
INCUMBENT, CANDIDATE = MODELS[1:]


def incumbent_rows(spec):
    """Read fresh traces for unrounded guard values or score in memory."""
    trace = RI_TRACES / f"{spec.folder}__{spec.path.stem}.npz"
    inputs = [spec.path, R1_CURRENT_CSV, REPO_DIR / "python" / "compare_r1i.py", *DEPENDENCIES]
    if is_fresh([trace], inputs):
        return score_run(spec, *load_traces(trace))
    run = load_run(spec.path)
    cases = experiment_runs(run, load_params_ri(), EkfConfig.from_json(CONFIG_JSON))
    return score_run(spec, run.t, run.v, soc_ref(run), cases)


def subset(frame, specs):
    keys = {(spec.folder, spec.path.name) for spec in specs}
    selected = frame[[key in keys for key in zip(frame["folder"], frame["file"])]]
    if set(zip(selected["folder"], selected["file"])) != keys:
        raise ValueError("S9 comparison results are missing runs from the frozen split")
    return selected


def temperature_lines(tables, pooled):
    means = []
    others = []
    for temp in T_GRID_DEGC:
        ref = tables[INCUMBENT][temp]
        new = tables[CANDIDATE][temp]
        lower = int((new["exp1_by_run"] < ref["exp1_by_run"]).sum())
        means.append([str(temp), str(ref["runs"]), *[f"{v:.2f}" for v in pooled[temp]],
                      *[f"{tables[model][temp]['exp1']:.2f}" for model in MODELS],
                      *[f"{tables[model][temp]['exp1_median']:.2f}" for model in MODELS], str(lower)])
        others.append([str(temp), *[f"{tables[model][temp]['exp4']:.2f}" for model in MODELS],
                       *[" / ".join(str(tables[model][temp][exp]) for model in MODELS)
                         for exp in ("exp2", "exp3_low", "exp3_high")]])
    return [
        "Open-loop RMSE is pooled over window rows in mV. SoC RMSE is in pp. The lower count compares 3RC-D with 2RC-I.", "",
        *md_table(["T (degC)", "runs", *[f"{model} voltage" for model in MODELS],
                   *[f"{model} exp1 mean" for model in MODELS], *[f"{model} exp1 median" for model in MODELS],
                   "runs lower"], means),
        "", "Reached counts are in the order 2RC / 2RC-I / 3RC-D.", "",
        *md_table(["T (degC)", *[f"{model} exp4 mean" for model in MODELS], "exp2 reached",
                   "exp3 low reached", "exp3 high reached"], others),
    ]


def guard_details(unrounded, tables, gate, candidate=CANDIDATE):
    old = exp1_by_run(unrounded[INCUMBENT])
    new = exp1_by_run(unrounded[candidate])
    change = new["rmse_pp"] - old["rmse_pp"]
    cycle = new.groupby("cycle")["rmse_pp"].mean() - old.groupby("cycle")["rmse_pp"].mean()
    exp1 = [tables[candidate][t]["exp1"] - tables[INCUMBENT][t]["exp1"] for t in T_GRID_DEGC]
    exp4 = [tables[candidate][t]["exp4"] - tables[INCUMBENT][t]["exp4"] for t in T_GRID_DEGC]
    return [
        "Guard inputs from unrounded traces. SoC changes are in pp and temperatures follow the table order above.", "",
        *md_table(["guard", "unrounded values"], [
            ["1", f"{gate:.12g} mV"],
            ["2", " / ".join(f"{v:+.12g}" for v in exp1)],
            ["3", f"Largest run increase {change.max():+.12g}"],
            ["4", ", ".join(f"{name} {value:+.12g}" for name, value in cycle.items())],
            ["5", f"Worst run {old['rmse_pp'].max():.12g} to {new['rmse_pp'].max():.12g}"],
            ["6", "Experiment 4 changes " + " / ".join(f"{v:+.12g}" for v in exp4)],
        ]),
    ]


def experiment1_cycle_rows(runs, models):
    cycle = {model: runs[model].groupby("cycle")["rmse_pp"].mean() for model in models}
    return [[name, *[f"{cycle[model][name]:.4f}" for model in models]] for name in cycle[models[0]].index]


def experiment1_run_rows(runs, models):
    return [[key[0], row["cycle"], *[f"{runs[model].loc[key, 'rmse_pp']:.4f}" for model in models]]
            for key, row in runs[INCUMBENT].iterrows()]


def comparison_text(standard, tables, pooled, mix_tables, mix_pooled, guards, raw_details):
    runs = {model: exp1_by_run(standard[model]) for model in MODELS}
    return "\n".join([
        "# 3RC-D comparison (S9)", "", "Written by `python/compare_3rcd.py` (`make ekf-3rcd`).", "",
        DISCLOSURE, "", "All models use the frozen S2 noise settings. The adoption guards compare 3RC-D with 2RC-I.", "",
        "## Standard cycles", "", *temperature_lines(tables, pooled), "",
        "### Experiment 1 by standard cycle", "",
        *md_table(["Cycle", *[f"{model} (pp)" for model in MODELS]],
                  experiment1_cycle_rows(runs, MODELS)),
        "", "### Experiment 1 by run", "",
        *md_table(["Folder", "Cycle", *[f"{model} (pp)" for model in MODELS]],
                  experiment1_run_rows(runs, MODELS)),
        "", "## Calibration runs (in-sample)", "",
        *temperature_lines(mix_tables, mix_pooled),
        "", "## Guards and adoption verdict", "",
        "The guards of decisions 1.40 use the results CSVs, with comparisons near a limit recomputed from the "
        "unrounded traces under decisions 1.35. The S1 gate always uses the full-precision open-loop RMSE.", "",
        *guard_table(guards), "", *raw_details, "",
        f"**{'ADOPTED' if all(row[2] for row in guards) else 'NOT ADOPTED'}.**", "",
    ])


def plot_comparison(standard, mix):
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    temps = sorted(T_GRID_DEGC)
    for row, label, (pooled, tables) in zip(axes, ("Standard cycles", "Mix runs (in-sample)"), (standard, mix)):
        for index, (model, color) in enumerate(zip(MODELS, MODEL_COLORS)):
            row[0].plot(temps, [pooled[t][index] for t in temps], "o-", color=color, label=model)
            row[1].plot(temps, [tables[model][t]["exp1"] for t in temps], "o-", color=color, label=model)
        row[0].set_ylabel("Open-loop RMSE (mV)")
        row[1].set_ylabel("Exp. 1 mean SoC RMSE (pp)")
        for ax in row:
            ax.set(title=label, xticks=temps, xlabel="Temperature (°C)", ylim=(0, None))
    axes[0, 1].legend(frameon=False)
    save(fig, PLOTS / "model_compare_3rcd.png")


def open_loop_by_split(models, mix, standard, pool):
    """Pool each model's voltage errors over the window rows of each split."""
    model_sets = [(params,) for params in models]
    splits = []
    for specs in (standard, mix):
        scores = pool.map(partial(score_open_loop, specs=specs), model_sets)
        splits.append({temp: [pooled[temp][0] for pooled, _ in scores] for temp in T_GRID_DEGC})
    return splits


def main():
    params = load_params_3rcd()
    gate = validate_us06(params, GATE_TEMP_DEGC)["rmse_mv"]
    if not gate <= GATE_RMSE_MV:
        print(f"S1 gate FAIL ({gate:.4f} mV). Step B skipped.")
        return

    specs = evaluation_runs(RAW_DIR)
    mix, standard = drive_split(specs)
    inputs = [PARAMS_3RCD_CSV, R1_CURRENT_CSV, REPO_DIR / "python" / "compare_r1i.py",
              REPO_DIR / "python" / "fit_3rcd.py", REPO_DIR / "python" / "compare_3rcd.py"]
    print("Running experiments 1 to 4 on 63 runs", flush=True)
    with Pool() as pool:
        scored = pool.map(partial(process_run, load_params_3rcd, RUNS_DIR, inputs), specs, chunksize=1)
        raw_incumbent = scored_frame(pool.map(incumbent_rows, standard, chunksize=1))
        print("Scoring open-loop voltage for the three models", flush=True)
        models = (Params.from_csv(PARAMS_CSV), load_params_ri(), params)
        pooled, mix_pooled = open_loop_by_split(models, mix, standard, pool)
    raw_candidate = scored_frame(scored)
    raw_candidate.to_csv(CANDIDATE_CSV, index=False, float_format="%.4f")
    results = dict(zip(MODELS, [pd.read_csv(path) for path in (RESULTS_CSV, RESULTS_RI_CSV, CANDIDATE_CSV)]))
    standard_results = {model: subset(frame, standard) for model, frame in results.items()}
    tables = {model: per_temperature(frame) for model, frame in standard_results.items()}
    mix_tables = {model: per_temperature(subset(frame, mix).assign(is_tuning=False)) for model, frame in results.items()}
    unrounded = {INCUMBENT: raw_incumbent, CANDIDATE: subset(raw_candidate, standard)}
    raw_tables = {model: per_temperature(frame) for model, frame in unrounded.items()}
    gates = {CANDIDATE: {GATE_TEMP_DEGC: gate}}
    guards = decided_guards(guard_rows(standard_results, tables, gates, CANDIDATE, INCUMBENT),
                            guard_rows(unrounded, raw_tables, gates, CANDIDATE, INCUMBENT))
    write_text(COMPARE_MD, comparison_text(standard_results, tables, pooled, mix_tables, mix_pooled,
                                           guards, guard_details(unrounded, raw_tables, gate)))
    plot_comparison((pooled, tables), (mix_pooled, mix_tables))
    print("3RC-D " + ("ADOPTED" if all(row[2] for row in guards) else "NOT ADOPTED"))


if __name__ == "__main__":
    main()
