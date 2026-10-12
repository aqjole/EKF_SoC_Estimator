"""Stage S2 driver: run the experiments of S2 on every evaluation run, then write the tables and the plots.

Run from the repo root:  .venv/bin/python python/run_all.py   (or: make ekf)

  1. results/params.csv (S1) and results/ekf_config.json (frozen by python/tune.py) are read. Nothing is tuned here.
  2. Each run of experiments.evaluation_runs() is processed in a process pool. Its experiments (experiment_runs) are
     saved to results/runs/<folder>__<file>.npz, and its trace plots to results/runs/plots/. A run whose files
     are all newer than the parameters, the noise settings and the code is not computed again.
  3. Every number is scored from the saved traces (ekfsoc.metrics): results/ekf_results.csv has one row per run and
     experiment.
  4. results/ekf_summary.md has the cycle x temperature tables and the 3 pp gate, read back from that CSV.
  5. results/plots/s2/ gets the two summary plots, the 16 example traces (copied from results/runs/plots/) and the
     synthetic-data plot (docs/decisions.md 1.14).
"""

import math
import shutil
import time
from functools import partial
from multiprocessing import Pool

import numpy as np
import pandas as pd

from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.experiments import CYCLE_NAMES, EXP3_START_SOC, OFFSET_A, evaluation_runs, experiment_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import (
    CONV_BAND_PP,
    FORGET_BAND_PP,
    PP,
    SOC_MIN,
    after_conv_mask,
    band_times,
    init_forgetting_time,
    max_abs_pp,
    rmse_pp,
    voltage_rmse_mv,
    window_mask,
)
from ekfsoc.model import Params
from ekfsoc.plots import plot_summary, plot_synthetic, plot_trace
from ekfsoc.synthetic import SOC_START, SYNTHETIC_CFG, WRONG_INIT_PP, synthetic_data
from export_params import PARAMS_CSV, md_table, write_text


CONFIG_JSON = REPO_DIR / "results" / "ekf_config.json"
RESULTS_CSV = REPO_DIR / "results" / "ekf_results.csv"
SUMMARY_MD = REPO_DIR / "results" / "ekf_summary.md"
RUNS_DIR = REPO_DIR / "results" / "runs"
PLOTS_DIR = REPO_DIR / "results" / "plots" / "s2"

# What the saved traces depend on: the parameters, the noise settings, the code of the package and this driver.
DEPENDENCIES = [PARAMS_CSV, CONFIG_JSON, REPO_DIR / "python" / "run_all.py",
                *sorted((REPO_DIR / "python" / "ekfsoc").glob("*.py"))]

# The scored experiments, in table order. exp3_ref is the comparator of the init-forgetting time and is not scored.
SCORED = ("exp1", "exp2", "exp3_low", "exp3_high", "exp4")

# Init-forgetting time (docs/model.md C14): an experiment against the run with the correct init.
FORGET_AGAINST = {"exp2": "exp1", "exp3_low": "exp3_ref", "exp3_high": "exp3_ref"}

# The example traces of results/plots/s2/ (docs/decisions.md 1.14).
EXAMPLE_CYCLES = ("US06", "Mix 1")
EXAMPLE_TEMPS = (25, -20)
EXAMPLE_EXPERIMENTS = ("exp1", "exp2", "exp3_low", "exp4")

# Sanity gate of the stage (the spec, S2): the correct-init SoC RMSE at 25 degC.
GATE_TEMP_DEGC = 25
GATE_RMSE_PP = 3.0

COLUMNS = ("folder", "file", "cycle", "T_degC", "is_tuning", "experiment", "start_s", "soc0", "rmse_pp",
           "max_abs_pp", "rmse_after_conv_pp", "t_first_s", "t_conv_s", "t_forget_s", "v_rmse_mV", "cc_rmse_pp",
           "end_err_pp", "cc_end_err_pp", "expected_drift_pp", "window_end_s")


# --- the saved traces ----------------------------------------------------------------------------


def save_traces(path, t, v, reference, cases):
    """Write the time, measured voltage, reference SoC and every experiment's case to one .npz (keys 'exp1.soc', ...)."""
    flat = {"t": t, "v": v, "reference": reference}
    for name, case in cases.items():
        for field, value in case.items():
            flat[f"{name}.{field}"] = np.asarray(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **flat)


def load_traces(path):
    """Return (t, v, reference, cases) as save_traces wrote them; the scalars of a case come back as Python numbers."""
    with np.load(path) as saved:
        flat = {key: saved[key] for key in saved.files}
    cases = {}
    for key, value in flat.items():
        if "." in key:
            name, field = key.split(".")
            cases.setdefault(name, {})[field] = value if value.ndim > 0 else value.item()
    return flat["t"], flat["v"], flat["reference"], cases


def is_fresh(outputs):
    """True if every output file exists and is newer than every file the results depend on."""
    newest_input = max(path.stat().st_mtime_ns for path in DEPENDENCIES)
    return all(path.exists() and path.stat().st_mtime_ns > newest_input for path in outputs)


def trace_name(experiment, spec):
    """trace_<experiment>_<cycle>_<T>degC.png, for example trace_exp2_Mix1_n20degC.png."""
    temp = spec.nominal_temp_degc
    return f"trace_{experiment}_{spec.cycle_name.replace(' ', '')}_{'n' if temp < 0 else ''}{abs(temp)}degC.png"


def is_example(spec):
    return spec.cycle_name in EXAMPLE_CYCLES and spec.nominal_temp_degc in EXAMPLE_TEMPS


# --- scoring -------------------------------------------------------------------------------------


def none_as_nan(value):
    return math.nan if value is None else value


def score_run(spec, t, v, reference, cases):
    """Return one dict per scored experiment with the columns of results/ekf_results.csv (metrics.py, docs/model.md C14).

    Times are seconds since the filter start. Errors are estimate - reference, in pp.
    """
    rows = []
    for experiment in SCORED:
        case = cases[experiment]
        start = case["start"]
        t_rel = t - t[start]
        mask = window_mask(reference, start)
        last = np.flatnonzero(mask)[-1]

        err = case["soc"] - reference
        cc_err = case["cc"] - reference
        t_first, t_conv = band_times(t_rel, PP * err, mask, CONV_BAND_PP)
        after_conv = after_conv_mask(mask, t_rel, t_conv)
        if experiment in FORGET_AGAINST:
            comparator = cases[FORGET_AGAINST[experiment]]["soc"]
            t_forget = init_forgetting_time(t_rel, case["soc"], comparator, mask)
        else:
            t_forget = None

        rows.append({
            "folder": spec.folder,
            "file": spec.path.name,
            "cycle": spec.cycle_name,
            "T_degC": spec.nominal_temp_degc,
            "is_tuning": spec.is_tuning,
            "experiment": experiment,
            "start_s": t[start] - t[0],
            "soc0": case["soc0"],
            "rmse_pp": rmse_pp(err, mask),
            "max_abs_pp": max_abs_pp(err, mask),
            "rmse_after_conv_pp": rmse_pp(err, after_conv),
            "t_first_s": none_as_nan(t_first),
            "t_conv_s": none_as_nan(t_conv),
            "t_forget_s": none_as_nan(t_forget),
            "v_rmse_mV": voltage_rmse_mv(case["v_pred"], v, mask),
            "cc_rmse_pp": rmse_pp(cc_err, mask),
            "end_err_pp": PP * err[last],
            "cc_end_err_pp": PP * cc_err[last],
            "expected_drift_pp": case.get("expected_drift_pp", math.nan),
            "window_end_s": t_rel[last],
        })
    return rows


# --- one run -------------------------------------------------------------------------------------


def draw_traces(spec, t, reference, cases, rows, plots_dir):
    """Write the trace plot of each scored experiment of one run to plots_dir."""
    for row in rows:
        case = cases[row["experiment"]]
        title = (f"{spec.cycle_name} at {spec.nominal_temp_degc} degC, {row['experiment']}: "
                 f"EKF RMSE {row['rmse_pp']:.2f} pp, coulomb counting {row['cc_rmse_pp']:.2f} pp")
        plot_trace(plots_dir / trace_name(row["experiment"], spec), t, reference, case["soc"], case["cc"],
                   CONV_BAND_PP, title)


def process_run(spec, runs_dir):
    """Return the scored rows of one run; compute and save its traces and plots first unless they are fresh."""
    traces_path = runs_dir / f"{spec.folder}__{spec.path.stem}.npz"
    plots_dir = runs_dir / "plots"
    plot_paths = [plots_dir / trace_name(experiment, spec) for experiment in SCORED]

    stale = not is_fresh([traces_path, *plot_paths])
    if stale:
        run = load_run(spec.path)
        cases = experiment_runs(run, Params.from_csv(PARAMS_CSV), EkfConfig.from_json(CONFIG_JSON))
        save_traces(traces_path, run.t, run.v, soc_ref(run), cases)

    t, v, reference, cases = load_traces(traces_path)
    rows = score_run(spec, t, v, reference, cases)
    if stale:
        draw_traces(spec, t, reference, cases, rows, plots_dir)
    return rows


# --- the summary tables --------------------------------------------------------------------------

# Per experiment: the section title, what it is, and its tables as (column of the CSV, table title, number format).
RMSE_TABLE = ("rmse_pp", "SoC RMSE (pp)", "{:.2f}")
CONV_TABLES = (
    RMSE_TABLE,
    ("t_conv_s", f"Convergence time t_conv (s): the error stays within +-{CONV_BAND_PP:g} pp from then on", "{:.1f}"),
    ("t_forget_s", f"Init-forgetting time (s): within +-{FORGET_BAND_PP:g} pp of the run with the correct init", "{:.1f}"),
)
EXPERIMENT_TABLES = {
    "exp1": ("Experiment 1: correct initial SoC",
             "SoC0 = the reference at the first row. The filter and plain coulomb counting are both scored.",
             (RMSE_TABLE, ("cc_rmse_pp", "Coulomb counting against the reference: SoC RMSE (pp)", "{:.2f}"))),
    "exp2": ("Experiment 2: initial SoC 20 pp too low",
             "SoC0 = the reference at the first row - 20 pp. The init-forgetting time is against experiment 1.",
             CONV_TABLES),
    "exp3_low": ("Experiment 3, low start: initial SoC 50 % from a reference of "
                 f"{PP * EXP3_START_SOC:.0f} %",
                 f"The filter starts where the reference first reaches {PP * EXP3_START_SOC:.0f} % with SoC0 = 50 %. "
                 f"The init-forgetting time is against the restart with SoC0 = {PP * EXP3_START_SOC:.0f} %.",
                 CONV_TABLES),
    "exp3_high": ("Experiment 3, high start: initial SoC 90 % from a reference of "
                  f"{PP * EXP3_START_SOC:.0f} %",
                  "The same start with SoC0 = 90 %; the init-forgetting time is against the same restart.",
                  CONV_TABLES),
    "exp4": ("Experiment 4: current offset",
             f"The current seen by the filter and by coulomb counting is {OFFSET_A:+.3f} A off (positive = discharge). "
             "The expected drift is what the offset does to a coulomb counter over the window.",
             (RMSE_TABLE,
              ("end_err_pp", "EKF error at the end of the window (pp)", "{:+.2f}"),
              ("cc_end_err_pp", "Coulomb counting error at the end of the window (pp)", "{:+.2f}"),
              ("expected_drift_pp", "Expected coulomb-counting drift over the window (pp)", "{:+.2f}"))),
}

# The columns whose empty cell means "not reached", which get a "reached" count under the table.
TIME_COLUMNS = ("t_conv_s", "t_forget_s")


def cell_text(rows, column, number_format):
    """Text of one table cell from the CSV rows of one (cycle, temperature): n/a, not reached, or the number, with * for the tuning cycle."""
    if len(rows) == 0:
        return "n/a"
    row = rows.iloc[0]
    if math.isnan(row[column]):
        return "not reached"
    return number_format.format(row[column]) + ("*" if row["is_tuning"] else "")


def footer_cells(results, experiment, column, number_format):
    """Under a table, one list of cells per temperature: the mean over the evaluation runs, and for times the reached count."""
    rows = results[(results["experiment"] == experiment) & ~results["is_tuning"]]
    means, reached = [], []
    for temp in T_GRID_DEGC:
        values = rows.loc[rows["T_degC"] == temp, column]
        found = values.dropna()
        means.append(number_format.format(found.mean()) if len(found) > 0 else "n/a")
        reached.append(f"{len(found)} of {len(values)}")
    if column in TIME_COLUMNS:
        return [("mean of reached", means), ("reached", reached)]
    return [("mean", means)]


def pivot_table(results, experiment, column, number_format):
    """Lines of a markdown table: one row per cycle, one column per temperature, then the footer rows."""
    runs = results[results["experiment"] == experiment]
    rows = []
    for cycle in CYCLE_NAMES.values():
        cells = []
        for temp in T_GRID_DEGC:
            cell_runs = runs[(runs["cycle"] == cycle) & (runs["T_degC"] == temp)]
            cells.append(cell_text(cell_runs, column, number_format))
        rows.append([cycle, *cells])
    for label, cells in footer_cells(results, experiment, column, number_format):
        rows.append([f"**{label}**", *cells])
    return md_table(["cycle"] + [f"{temp} degC" for temp in T_GRID_DEGC], rows)


def gate_text(results):
    """The 3 pp sanity gate on experiment 1 at 25 degC: mean over the evaluation runs, max over all runs, the verdict."""
    runs = results[(results["experiment"] == "exp1") & (results["T_degC"] == GATE_TEMP_DEGC)]
    evaluation = runs[~runs["is_tuning"]]
    worst = runs.loc[runs["rmse_pp"].idxmax()]
    passed = evaluation["rmse_pp"].mean() <= GATE_RMSE_PP and worst["rmse_pp"] <= GATE_RMSE_PP
    return (f"Sanity gate: experiment 1 at {GATE_TEMP_DEGC} degC has a mean SoC RMSE of {evaluation['rmse_pp'].mean():.2f} pp "
            f"over the {len(evaluation)} evaluation runs (tuning cycle excluded) and a maximum of {worst['rmse_pp']:.2f} pp "
            f"({worst['cycle']}) over all {len(runs)} runs, against the limit of {GATE_RMSE_PP:g} pp. "
            f"**{'PASS' if passed else 'FAIL'}.** The limit is a bug check, not a published target.")


def synthetic_runs():
    """Run the filter with SYNTHETIC_CFG from SoC0 20 pp below and 20 pp above the truth; return the data and the estimates."""
    data = synthetic_data(Params.from_csv(PARAMS_CSV))
    estimates = {}
    for sign in (-1, 1):
        label = f"EKF started {WRONG_INIT_PP:g} pp {'high' if sign > 0 else 'low'}"
        soc0 = SOC_START + sign * WRONG_INIT_PP / PP
        out = run_ekf(data["params"], SYNTHETIC_CFG, data["i"], data["v"], data["temp"], data["dt"], soc0)
        estimates[label] = out["soc"]
    return data, estimates


def synthetic_lines(data, estimates):
    """Lines of the synthetic-data section: per start, the time after which the error stays within 1 pp and its RMSE after that."""
    rows = []
    mask = np.ones(len(data["t"]), dtype=bool)
    for label, soc in estimates.items():
        err = soc - data["soc_true"]
        _, t_conv = band_times(data["t"], PP * err, mask, FORGET_BAND_PP)
        after = after_conv_mask(mask, data["t"], t_conv)
        rows.append([label, "not reached" if t_conv is None else f"{t_conv:.1f}", f"{rmse_pp(err, after):.3f}"])
    return [
        "## Synthetic data",
        "",
        f"Data from the model itself: the 2RC model at {data['temp'][0]:g} degC from `results/params.csv` on a made-up current "
        f"({data['i'].min():.1f} to {data['i'].max():.1f} A), {data['t'][-1]:.0f} s at {data['dt'][1]:g} s, "
        f"true SoC starting at {PP * SOC_START:.0f} %, plus Gaussian voltage noise. This checks the filter apart from model mismatch. "
        f"The filter uses the settings of the test, not the frozen ones: q_soc = {SYNTHETIC_CFG.q_soc:g} 1/s, "
        f"q_v = {SYNTHETIC_CFG.q_v:g} V^2/s, r = {SYNTHETIC_CFG.r:g} V^2.",
        "",
        *md_table(["start", f"error stays within +-{FORGET_BAND_PP:g} pp from (s)", "RMSE after that (pp)"], rows),
        "",
        "Plot: `results/plots/s2/synthetic.png`.",
    ]


def summary_text(results, cfg, data, estimates):
    """Return the text of results/ekf_summary.md. Every number comes from the CSV rows or the synthetic run."""
    n_runs = results["file"].nunique()
    lines = [
        "# EKF results (S2)",
        "",
        "Written by `python/run_all.py` (`make ekf`) from `results/ekf_results.csv`. Do not edit by hand.",
        "",
        gate_text(results),
        "",
        "## Legend",
        "",
        f"- {n_runs} runs (the evaluation set and the tuning cycle), one row per run and experiment in `results/ekf_results.csv`. "
        f"The noise settings are the frozen ones of `results/ekf_config.json`: q_soc = {cfg.q_soc:g} 1/s, q_v = {cfg.q_v:g} V^2/s, "
        f"r = {cfg.r:g} V^2, and the same for every experiment and temperature.",
        "- Error = estimate - reference; the reference follows the cycler's Ah counter (docs/model.md C4).",
        f"- Evaluation window: from the filter start to the last sample where the reference SoC is at least {PP * SOC_MIN:.0f} % "
        "(docs/model.md C14). Every metric is over this window. Times are in s since the filter start.",
        "- `*` marks the tuning cycle (Mix 1 at 25 degC), on which the noise settings were tuned for experiment 2. "
        "`n/a`: no run exists. `not reached`: the error is outside the band at the end of the window, or the run is still apart "
        "from the run with the correct init; it is not an average.",
        "- `mean` rows average the evaluation runs of the column (tuning cycle excluded); `mean of reached` leaves out the runs "
        "that did not reach; `reached` counts them.",
    ]
    for experiment, (title, description, tables) in EXPERIMENT_TABLES.items():
        lines += ["", f"## {title}", "", description]
        for column, table_title, number_format in tables:
            lines += ["", f"### {table_title}", "", *pivot_table(results, experiment, column, number_format)]
    lines += ["", *synthetic_lines(data, estimates)]
    return "\n".join(lines) + "\n"


# --- plots and driver ----------------------------------------------------------------------------


def write_plots(results, specs, data, estimates):
    """Write results/plots/s2/: the summary plots, the 16 example traces copied from the run plots, the synthetic plot."""
    plot_summary(PLOTS_DIR / "summary_rmse.png", results, "rmse_pp", "SoC RMSE of each run (pp)")
    plot_summary(PLOTS_DIR / "summary_convergence.png", results, "t_conv_s", "Convergence time t_conv of each run (s)")
    for spec in filter(is_example, specs):
        for experiment in EXAMPLE_EXPERIMENTS:
            name = trace_name(experiment, spec)
            shutil.copyfile(RUNS_DIR / "plots" / name, PLOTS_DIR / name)
    plot_synthetic(PLOTS_DIR / "synthetic.png", data["t"], data["soc_true"], estimates, FORGET_BAND_PP,
                   f"Synthetic data (model voltage + noise): the EKF from SoC0 +-{WRONG_INIT_PP:g} pp")


def main():
    started = time.perf_counter()
    specs = evaluation_runs(RAW_DIR)
    with Pool() as pool:
        scored = pool.map(partial(process_run, runs_dir=RUNS_DIR), specs, chunksize=1)
    pd.DataFrame([row for run_rows in scored for row in run_rows], columns=COLUMNS).to_csv(
        RESULTS_CSV, index=False, float_format="%.4f")
    results = pd.read_csv(RESULTS_CSV)
    print(f"wrote {RESULTS_CSV.relative_to(REPO_DIR)}: {len(results)} rows from {len(specs)} runs")

    data, estimates = synthetic_runs()
    write_text(SUMMARY_MD, summary_text(results, EkfConfig.from_json(CONFIG_JSON), data, estimates))
    print(f"wrote {SUMMARY_MD.relative_to(REPO_DIR)}")
    print(gate_text(results))

    write_plots(results, specs, data, estimates)
    print(f"wrote {PLOTS_DIR.relative_to(REPO_DIR)}/")
    print(f"runtime {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
