"""Stage S2 driver: run the experiments of S2 on every evaluation run, then write the tables and the plots.

Run from the repo root:  .venv/bin/python python/run_all.py   (or: make ekf)

  1. results/params.csv (S1) and results/ekf_config.json (frozen by python/tune.py) are read. Nothing is tuned here.
  2. Each run of experiments.evaluation_runs() is processed in a process pool. Its experiments (experiment_runs) are
     saved to results/runs/<folder>__<file>.npz, and its trace plots to results/runs/plots/. A run whose files
     are all newer than the parameters, the noise settings and the code is not computed again.
  3. Every number is scored from the saved traces (ekfsoc.metrics): results/ekf_results.csv has one row per run and
     experiment.
  4. results/ekf_summary.md (ekf_summary.py) has the cycle x temperature tables and the 3 pp gate, read back from that CSV.
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

from ekfsoc.constants import RAW_DIR, REPO_DIR
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.experiments import evaluation_runs, experiment_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import (
    CONV_BAND_PP,
    FORGET_BAND_PP,
    PP,
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
from ekf_summary import gate_text, summary_text
from export_params import PARAMS_CSV, write_text


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
        flat = dict(saved)
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


# --- the synthetic check, the plots and the driver -----------------------------------------------


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
    pd.DataFrame([row for run_rows in scored for row in run_rows]).to_csv(RESULTS_CSV, index=False, float_format="%.4f")
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
