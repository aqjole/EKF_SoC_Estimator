"""Evaluate 3RC-D0 against the frozen 2RC-I comparator (decision 1.44)."""

from functools import partial
from multiprocessing import Pool

import matplotlib.pyplot as plt
import pandas as pd

from compare_3rcd import CANDIDATE_CSV as S9_CSV
from compare_3rcd import experiment1_cycle_rows, experiment1_run_rows, guard_details, incumbent_rows, subset
from compare_r1c import scored_frame
from compare_r1i import RESULTS_RI_CSV, load_params_ri, per_temperature, process_run
from ekfsoc.constants import REPO_DIR, T_GRID_DEGC
from ekfsoc.ekf import EkfConfig
from ekfsoc.experiments import run_case
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import rmse_pp, window_mask
from ekfsoc.plots import save
from export_params import md_table, write_text
from fit_3rcd import PARAMS_3RCD_CSV
from fit_3rcd0 import CANDIDATE, INCUMBENT, MODELS, PARAMS_CSV_D0, SUBSTITUTION, load_candidate, load_substitution
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, validate_us06
from run_all import CONFIG_JSON, RESULTS_CSV
from s10_protocol import DISCLOSURE, PLOTS, RESULTS, splits, verify_baseline
from s8_compare import decided_guards, exp1_by_run, guard_rows, guard_table
from sensitivity import capacity_columns, rate_columns


RUNS_DIR = RESULTS / "runs" / "3rcd0"
CANDIDATE_CSV = RESULTS / "ekf_results_3rcd0.csv"
SENSITIVITY_CSV = RESULTS / "sensitivity_3rcd0.csv"
COMPARE_MD = RESULTS / "model_compare_3rcd0.md"
SCORED_MODELS = MODELS[:-1]
SENSITIVITY_COLUMNS = ("ekf_rmse_pp_095", "ekf_rmse_pp_105", "ekf_rmse_pp_1hz")


def diagnostic_substitution(spec):
    run = load_run(spec.path)
    reference = soc_ref(run)
    cfg = EkfConfig.from_json(CONFIG_JSON)
    case = run_case(run, load_substitution(), cfg, float(reference[0]), 0, 0.0)
    return {
        "folder": spec.folder, "file": spec.path.name, "T_degC": spec.nominal_temp_degc, "cycle": spec.cycle_name,
        "experiment": "exp1", "is_tuning": spec.is_tuning, "rmse_pp": rmse_pp(case["soc"] - reference, window_mask(reference, 0)),
    }


def sensitivity_rows(spec):
    run = load_run(spec.path)
    cfg = EkfConfig.from_json(CONFIG_JSON)
    rows = []
    for model, params in ((INCUMBENT, load_params_ri()), (CANDIDATE, load_candidate())):
        perturbations = capacity_columns(run, params, cfg) | rate_columns(run, params, cfg)
        rows.append({"model": model, "folder": spec.folder, "file": spec.path.name,
                     "T_degC": spec.nominal_temp_degc, "cycle": spec.cycle_name,
                     **{key: perturbations[key] for key in SENSITIVITY_COLUMNS}})
    return rows


def exp1_frames(results, substitution, specs):
    """Report every member of a split, including the Mix tuning run."""
    frames = results | {SUBSTITUTION: subset(substitution, specs)}
    return {model: exp1_by_run(frame.assign(is_tuning=False)) for model, frame in frames.items()}


def temperature_lines(results, tables):
    rows = []
    other = []
    for temp in T_GRID_DEGC:
        means = [results[model].loc[results[model]["T_degC"] == temp, "rmse_pp"].mean() for model in MODELS]
        medians = [results[model].loc[results[model]["T_degC"] == temp, "rmse_pp"].median() for model in MODELS]
        rows.append([str(temp), str(tables[INCUMBENT][temp]["runs"]), *[f"{v:.3f}" for v in means],
                     *[f"{v:.3f}" for v in medians]])
        other.append([str(temp), *[f"{tables[model][temp]['exp4']:.3f}" for model in SCORED_MODELS],
                      *[" / ".join(str(tables[model][temp][exp]) for model in SCORED_MODELS)
                        for exp in ("exp2", "exp3_low", "exp3_high")]])
    return [
        "Experiment-1 SoC RMSE in pp. The S9 R1 substitution is an experiment-1 diagnostic.", "",
        *md_table(["T (degC)", "runs", *[f"{model} mean" for model in MODELS], *[f"{model} median" for model in MODELS]],
                  rows), "",
        f"Experiment-4 mean SoC RMSE in pp. Reached counts follow {' / '.join(SCORED_MODELS)}.", "",
        *md_table(["T (degC)", *[f"{model} exp4" for model in SCORED_MODELS],
                   "exp2 reached", "exp3 low reached", "exp3 high reached"], other),
    ]


def standard_lines(runs):
    per_run = experiment1_run_rows(runs, MODELS)
    us06 = [row for row in per_run if row[1] == "US06"]
    return [
        "### Experiment 1 by standard cycle", "",
        *md_table(["Cycle", *[f"{model} (pp)" for model in MODELS]],
                  experiment1_cycle_rows(runs, MODELS)),
        "", "### US06 experiment 1", "",
        *md_table(["Folder", "Cycle", *[f"{model} (pp)" for model in MODELS]], us06),
        "", "### Experiment 1 by run", "",
        *md_table(["Folder", "Cycle", *[f"{model} (pp)" for model in MODELS]], per_run),
    ]


def additional_diagnostics(results, sensitivity):
    rows = []
    for experiment in ("exp1", "exp2", "exp3_low", "exp3_high", "exp4"):
        for model in SCORED_MODELS:
            frame = results[model]
            case = frame[frame["experiment"] == experiment]
            conv = case["t_conv_s"].dropna()
            median = f"{conv.median():.1f}" if len(conv) else "n/a"
            rows.append([experiment, model, f"{case['max_abs_pp'].max():.4f}", str(len(conv)), median])
    means = []
    for temp in T_GRID_DEGC:
        for model in (INCUMBENT, CANDIDATE):
            here = sensitivity[(sensitivity["T_degC"] == temp) & (sensitivity["model"] == model)]
            scores = here[["nominal_pp", *SENSITIVITY_COLUMNS]].mean()
            means.append([str(temp), model, *[f"{score:.4f}" for score in scores]])
    return [
        "## Standard-run diagnostics", "",
        "Peak absolute SoC error is the maximum within the evaluation windows. Median convergence time "
        "uses only the runs that reached the sustained ±2 pp band.", "",
        *md_table(["Experiment", "Model", "Peak error (pp)", "Runs reached", "Median convergence (s)"], rows),
        "", "### Experiment-1 sensitivity", "",
        "The entries are means across each temperature's standard runs in pp. The reference stays fixed. "
        "Capacity is perturbed by ±5% and sample rate by keeping every tenth row, following S5.", "",
        *md_table(["T (degC)", "Model", "Nominal", "−5% capacity", "+5% capacity", "1 Hz"], means),
        "", "See [per-run sensitivity scores](sensitivity_3rcd0.csv).",
    ]


def comparison_text(standard, mix, standard_runs, mix_runs, guards, raw_details, sensitivity):
    tables = [{model: per_temperature(frame.assign(is_tuning=False)) for model, frame in results.items()}
              for results in (standard, mix)]
    return "\n".join([
        "# 3RC-D0 comparison (S10)", "", "Generated by `make ekf-3rcd0` under decision 1.44.", "",
        DISCLOSURE, "",
        "All filters use frozen S2 noise and legacy Jacobians. Only 3RC-D0 versus 2RC-I enters adoption. "
        "The S9 R1 substitution retains the original S9 R2/R3 coefficients and uses v1.0 R1 for both signs.", "",
        "The [fit report](model_fit_3rcd0.md) compares open-loop voltage for all five models on both splits.", "",
        "## Standard regression runs", "", *temperature_lines(standard_runs, tables[0]), "",
        *standard_lines(standard_runs), "",
        "## Mix calibration runs (in-sample)", "", *temperature_lines(mix_runs, tables[1]), "",
        "## Guards and adoption verdict", "",
        "The S1 gate uses the full-precision full-run voltage RMSE. The SoC guards use CSV precision except "
        "near a limit, where they are recomputed from unrounded traces under decision 1.35. Guard 5 compares "
        "the maximum over all 23 standard runs for each model.", "",
        *guard_table(guards), "", *raw_details, "",
        f"**{'ADOPTED' if all(row[2] for row in guards) else 'NOT ADOPTED'}.**", "",
        *additional_diagnostics(standard, sensitivity), "",
    ])


def plot_comparison(standard_runs, mix_runs):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, runs, label in zip(axes, (standard_runs, mix_runs), ("Standard regression", "Mix calibration")):
        for model in MODELS:
            means = runs[model].groupby("T_degC")["rmse_pp"].mean()
            ax.plot(means.index, means, "o-", label=model)
        ax.set(title=label, xlabel="Temperature (°C)", ylabel="Exp. 1 mean SoC RMSE (pp)", xticks=T_GRID_DEGC)
        ax.grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    save(fig, PLOTS / "model_compare_3rcd0.png")


def main():
    verify_baseline()
    gate = validate_us06(load_candidate(), GATE_TEMP_DEGC)["rmse_mv"]
    if not gate <= GATE_RMSE_MV:
        write_text(COMPARE_MD, "\n".join([
            "# 3RC-D0 comparison (S10)", "", "Generated by `make ekf-3rcd0` under decision 1.44.", "",
            "## Standard regression runs", "",
            "EKF experiments were gated on the S1 voltage check. Open-loop scores are in the fit report.", "",
            "## Guards and adoption verdict", "",
            f"**NOT ADOPTED.** The full-run 25 degC US06 voltage RMSE was {gate:.12g} mV, "
            f"above the {GATE_RMSE_MV:g} mV S1 limit. EKF experiments are gated on a voltage pass.", "",
            "See the [fit report](model_fit_3rcd0.md) for open-loop scores for all five models.", "",
        ]))
        print("3RC-D0 NOT ADOPTED (S1 voltage gate)", flush=True)
        return

    mix, standard = splits()
    specs = mix + standard
    inputs = [PARAMS_CSV_D0, REPO_DIR / "python" / "fit_3rcd0.py"]
    print("Running 3RC-D0 experiments 1 to 4 on the frozen 63 runs", flush=True)
    with Pool(processes=6) as pool:
        scored = pool.map(partial(process_run, load_candidate, RUNS_DIR, inputs), specs, chunksize=1)
        raw_incumbent = scored_frame(pool.map(incumbent_rows, standard, chunksize=1))
        print("Scoring the S9 R1 substitution and standard-run sensitivity", flush=True)
        substitution = pd.DataFrame(pool.map(diagnostic_substitution, specs, chunksize=1))
        sensitivity = pd.DataFrame([row for rows in pool.map(sensitivity_rows, standard, chunksize=1) for row in rows])
    raw_candidate = scored_frame(scored)
    raw_candidate.to_csv(CANDIDATE_CSV, index=False, float_format="%.4f")
    results = dict(zip(SCORED_MODELS, map(pd.read_csv, (RESULTS_CSV, RESULTS_RI_CSV, S9_CSV, CANDIDATE_CSV))))
    standard_results = {model: subset(frame, standard) for model, frame in results.items()}
    mix_results = {model: subset(frame, mix) for model, frame in results.items()}
    standard_runs = exp1_frames(standard_results, substitution, standard)
    mix_runs = exp1_frames(mix_results, substitution, mix)
    tables = {model: per_temperature(frame) for model, frame in standard_results.items()}
    unrounded = {INCUMBENT: raw_incumbent, CANDIDATE: subset(raw_candidate, standard)}
    raw_tables = {model: per_temperature(frame) for model, frame in unrounded.items()}
    gates = {CANDIDATE: {GATE_TEMP_DEGC: gate}}
    guards = decided_guards(guard_rows(standard_results, tables, gates, CANDIDATE, INCUMBENT),
                            guard_rows(unrounded, raw_tables, gates, CANDIDATE, INCUMBENT))
    nominal = pd.concat([standard_runs[model][["rmse_pp"]].assign(model=model).reset_index()
                         for model in (INCUMBENT, CANDIDATE)]).rename(columns={"rmse_pp": "nominal_pp"})
    sensitivity = sensitivity.merge(nominal, on=["model", "folder", "file"], validate="one_to_one")
    sensitivity.to_csv(SENSITIVITY_CSV, index=False, float_format="%.4f")
    write_text(COMPARE_MD, comparison_text(standard_results, mix_results, standard_runs, mix_runs, guards,
                                           guard_details(unrounded, raw_tables, gate, CANDIDATE), sensitivity))
    plot_comparison(standard_runs, mix_runs)
    print("3RC-D0 " + ("ADOPTED" if all(row[2] for row in guards) else "NOT ADOPTED"), flush=True)


if __name__ == "__main__":
    main()
