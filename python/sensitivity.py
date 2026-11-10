"""Stage S5 driver: experiment 1 with a wrong filter capacity and at 1 Hz on every evaluation run, then the tables and plots.

Run from the repo root:  .venv/bin/python python/sensitivity.py   (or: make sensitivity)

  1. results/s1/params.csv (S1) and results/s2/ekf_config.json (frozen, docs/decisions.md 1.15) are read. Nothing is tuned.
  2. Each run of experiments.evaluation_runs() is processed in a process pool, from the reference SoC at row 0:
     - capacity error (docs/decisions.md 1.18): the EKF and the coulomb counter believe 0.95 Q_ref and 1.05 Q_ref,
       scored against the unchanged reference over the unchanged evaluation window;
     - sample rate (docs/decisions.md 1.19): every 10th row of the run, filtered with the nominal capacity.
  3. results/s5/sensitivity.csv has one row per run, with the experiment-1 values of results/s2/ekf_results.csv as the
     nominal columns (they are read, not rerun).
  4. results/s5/sensitivity.md is written from that CSV, read back; results/plots/s5/ gets sensitivity_capacity.png
     and sensitivity_rate.png (docs/decisions.md 1.14).
"""

import time
from dataclasses import replace
from multiprocessing import Pool

import numpy as np
import pandas as pd

from ekfsoc.constants import Q_REF_AH, RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.experiments import evaluation_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import PP, coulomb_count, max_abs_pp, rmse_pp, window_mask
from ekfsoc.model import Params
from ekfsoc.plots import ESTIMATE_COLORS, INK_COLOR, MEASURED_COLOR, MODEL_COLOR, key, plt, save
from export_params import PARAMS_CSV, md_table, write_text
from run_all import CONFIG_JSON, RESULTS_CSV


SENSITIVITY_CSV = REPO_DIR / "results" / "s5" / "sensitivity.csv"
SENSITIVITY_MD = REPO_DIR / "results" / "s5" / "sensitivity.md"
PLOTS_DIR = REPO_DIR / "results" / "plots" / "s5"

# The capacities the filter and the coulomb counter believe, as multiples of Q_ref (docs/decisions.md 1.18).
CAPACITY_SCALES = (0.95, 1.05)

# The 1 Hz run keeps every DECIMATION-th row of the 0.1 s run (docs/decisions.md 1.19).
DECIMATION = 10

# Experiment-1 columns of results/s2/ekf_results.csv -> the nominal columns of results/s5/sensitivity.csv.
NOMINAL_COLUMNS = {"rmse_pp": "ekf_rmse_pp_nominal", "max_abs_pp": "ekf_max_abs_pp_nominal", "cc_rmse_pp": "cc_rmse_pp_nominal"}


def scale_suffix(scale):
    """Column suffix of a capacity scaling: 0.95 -> '095', 1.05 -> '105'."""
    return f"{round(PP * scale):03d}"


def scale_label(scale):
    """Table and legend label of a capacity scaling: 0.95 -> '-5 %', 1.05 -> '+5 %'."""
    return f"{PP * (scale - 1.0):+.0f} %"


def capacity_variants():
    """(column suffix, label) of the low scaling, nominal and the high scaling, in table and legend order."""
    low, high = CAPACITY_SCALES
    return [(scale_suffix(low), scale_label(low)), ("nominal", "nominal"), (scale_suffix(high), scale_label(high))]


# --- one run -------------------------------------------------------------------------------------


def decimate_run(run, every):
    """Return the loader Run made of rows 0, every, 2 * every, ... of `run`, with dt recomputed between the kept rows.

    Nothing else changes: the kept sample's current is held over the whole longer step by the filter and the
    counter (docs/model.md C11), and the reference is read from the kept rows' counter values.
    """
    t = run.t[::every]
    dt = np.zeros(len(t))
    dt[1:] = t[1:] - t[:-1]
    return replace(run, t=t, i=run.i[::every], v=run.v[::every], temp=run.temp[::every],
                   ah_removed=run.ah_removed[::every], dt=dt)


def experiment1(run, params, cfg, q_ref_ah):
    """Run the EKF and the coulomb counter from the reference SoC at row 0 with capacity q_ref_ah; return both SoC traces."""
    soc0 = float(soc_ref(run)[0])
    ekf = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, soc0, q_ref_ah=q_ref_ah)
    cc = coulomb_count(run.i, run.dt, soc0, q_ref_ah)
    return ekf["soc"], cc


def capacity_columns(run, params, cfg):
    """SoC RMSE of the EKF and of coulomb counting at each capacity scaling, against the unchanged reference and window."""
    reference = soc_ref(run)
    mask = window_mask(reference, 0)
    columns = {}
    for scale in CAPACITY_SCALES:
        soc, cc = experiment1(run, params, cfg, scale * Q_REF_AH)
        columns[f"ekf_rmse_pp_{scale_suffix(scale)}"] = rmse_pp(soc - reference, mask)
        columns[f"cc_rmse_pp_{scale_suffix(scale)}"] = rmse_pp(cc - reference, mask)
    return columns


def rate_columns(run, params, cfg):
    """SoC RMSE and max |error| of the EKF and the coulomb-counting RMSE on the 1 Hz run, and its row count."""
    decimated = decimate_run(run, DECIMATION)
    reference = soc_ref(decimated)
    mask = window_mask(reference, 0)
    soc, cc = experiment1(decimated, params, cfg, Q_REF_AH)
    return {
        "ekf_rmse_pp_1hz": rmse_pp(soc - reference, mask),
        "ekf_max_abs_pp_1hz": max_abs_pp(soc - reference, mask),
        "cc_rmse_pp_1hz": rmse_pp(cc - reference, mask),
        "rows_1hz": len(decimated.t),
    }


def process_run(spec):
    """Return the row of results/s5/sensitivity.csv of one run, without the nominal columns."""
    run = load_run(spec.path)
    params = Params.from_csv(PARAMS_CSV)
    cfg = EkfConfig.from_json(CONFIG_JSON)
    return {
        "folder": spec.folder,
        "file": spec.path.name,
        "cycle": spec.cycle_name,
        "T_degC": spec.nominal_temp_degc,
        "is_tuning": spec.is_tuning,
        **capacity_columns(run, params, cfg),
        **rate_columns(run, params, cfg),
    }


def with_nominal(table, results):
    """Append the experiment-1 values of results/s2/ekf_results.csv (`results`) to each run's row, matched on folder and file."""
    exp1 = results.loc[results["experiment"] == "exp1", ["folder", "file", *NOMINAL_COLUMNS]]
    return table.merge(exp1.rename(columns=NOMINAL_COLUMNS), on=["folder", "file"], how="left", validate="one_to_one")


# --- results/s5/sensitivity.md ----------------------------------------------------------------------


def summary_rows(table, columns):
    """Rows of a per-temperature table: each T_GRID_DEGC node, then 'all'; the run count and each (column, aggregate), 2 decimals."""
    groups = [(str(temp), table[table["T_degC"] == temp]) for temp in T_GRID_DEGC] + [("all", table)]
    rows = []
    for label, runs in groups:
        cells = [f"{runs[column].agg(how):.2f}" for column, how in columns]
        rows.append([label, str(len(runs)), *cells])
    return rows


def largest_text(table, estimator):
    """'x.xx pp (cycle at T degC, -5 %)': the largest per-run RMSE of `estimator` ('ekf' or 'cc') over the two scalings."""
    candidates = []
    for scale in CAPACITY_SCALES:
        column = table[f"{estimator}_rmse_pp_{scale_suffix(scale)}"]
        candidates.append((column.max(), column.idxmax(), scale))
    value, index, scale = max(candidates, key=lambda candidate: candidate[0])
    row = table.loc[index]
    return f"{value:.2f} pp ({row['cycle']} at {row['T_degC']} degC, {scale_label(scale)})"


def capacity_lines(table):
    """The capacity-error section of results/s5/sensitivity.md (docs/decisions.md 1.18)."""
    variants = capacity_variants()
    columns = [(f"{estimator}_rmse_pp_{suffix}", "mean") for estimator in ("ekf", "cc") for suffix, _ in variants]
    header = ["T (degC)", "runs", *(f"{name} {label}" for name in ("EKF", "coulomb counting") for _, label in variants)]
    return [
        f"## Capacity error: the filter capacity at {variants[0][1]} and {variants[2][1]}",
        "",
        f"- The filter and the coulomb counter both believe {CAPACITY_SCALES[0]:g} Q_ref and {CAPACITY_SCALES[1]:g} Q_ref "
        f"(Q_ref = {Q_REF_AH:g} Ah) and start from the reference SoC at the first row (experiment 1).",
        "- Every cell is the mean SoC RMSE in pp over the evaluation window of the folder's runs; nominal is the "
        "experiment-1 value of `results/s2/ekf_results.csv`; the reference SoC does not change.",
        "",
        *md_table(header, summary_rows(table, columns)),
        "",
        f"Largest per-run EKF RMSE: {largest_text(table, 'ekf')}; largest per-run coulomb-counting RMSE: {largest_text(table, 'cc')}.",
        "",
        "Plot: `results/plots/s5/sensitivity_capacity.png`.",
    ]


def rate_lines(table):
    """The sample-rate section of results/s5/sensitivity.md (docs/decisions.md 1.19)."""
    columns = [("ekf_rmse_pp_nominal", "mean"), ("ekf_rmse_pp_1hz", "mean"),
               ("ekf_max_abs_pp_nominal", "max"), ("ekf_max_abs_pp_1hz", "max"),
               ("cc_rmse_pp_nominal", "mean"), ("cc_rmse_pp_1hz", "mean")]
    header = ["T (degC)", "runs", "EKF RMSE 0.1 s", "EKF RMSE 1 s", "EKF max \\|error\\| 0.1 s", "EKF max \\|error\\| 1 s",
              "coulomb counting RMSE 0.1 s", "coulomb counting RMSE 1 s"]
    return [
        f"## Sample rate: every {DECIMATION}th row (1 Hz)",
        "",
        f"- The 1 Hz run keeps rows 0, {DECIMATION}, {2 * DECIMATION}, ... of the loader's run and recomputes dt between them. "
        "The kept sample's current is held over the whole step (docs/model.md C11), the reference SoC is read at the kept rows "
        "and the evaluation window is C14 on them.",
        "- RMSE cells are means over the folder's runs; max |error| cells are the largest over the folder's runs. "
        "The 0.1 s columns are experiment 1 of `results/s2/ekf_results.csv`.",
        "",
        *md_table(header, summary_rows(table, columns)),
        "",
        "Plot: `results/plots/s5/sensitivity_rate.png`.",
    ]


def sensitivity_text(table, cfg):
    """Return the text of results/s5/sensitivity.md. Every number comes from the rows of results/s5/sensitivity.csv or cfg."""
    lines = [
        "# Sensitivity (S5)",
        "",
        "Written by `python/sensitivity.py` (`make sensitivity`) from `results/s5/sensitivity.csv`. Do not edit by hand. "
        f"Experiment 1 on the {len(table)} runs (the evaluation set and the tuning cycle) with the frozen noise settings of "
        f"`results/s2/ekf_config.json` (q_soc = {cfg.q_soc:g} 1/s, q_v = {cfg.q_v:g} V^2/s, r = {cfg.r:g} V^2), with a wrong "
        "filter capacity (docs/decisions.md 1.18) and at 1 Hz (docs/decisions.md 1.19).",
        "",
        *capacity_lines(table),
        "",
        *rate_lines(table),
    ]
    return "\n".join(lines) + "\n"


# --- plots ---------------------------------------------------------------------------------------


def plot_lines(path, table, variants, title):
    """Mean SoC RMSE per temperature, one colour per variant (column suffix, label, colour): EKF solid, coulomb counting dashed."""
    fig, axis = plt.subplots(figsize=(8, 4.5))
    for suffix, _, color in variants:
        for estimator, linestyle in (("ekf", "-"), ("cc", "--")):
            means = table.groupby("T_degC")[f"{estimator}_rmse_pp_{suffix}"].mean()  # ascending in temperature
            axis.plot(means.index, means.values, color=color, linestyle=linestyle, marker="o", markersize=4, linewidth=1.2)
    axis.set_xticks(sorted(T_GRID_DEGC))
    axis.set_ylim(bottom=0.0)
    axis.set_xlabel("temperature (degC)")
    axis.set_ylabel("mean SoC RMSE over the folder's runs (pp)")
    handles = [key(label, color) for _, label, color in variants] + [key("EKF"), key("coulomb counting", linestyle="--")]
    axis.legend(handles=handles, loc="best", frameon=False)
    axis.set_title(title, color=INK_COLOR)
    save(fig, path)


def plot_capacity(table):
    """sensitivity_capacity.png: one colour per capacity scaling."""
    colors = (ESTIMATE_COLORS[0], MEASURED_COLOR, ESTIMATE_COLORS[1])
    variants = [(suffix, f"capacity {label}", color) for (suffix, label), color in zip(capacity_variants(), colors)]
    plot_lines(PLOTS_DIR / "sensitivity_capacity.png", table, variants,
               f"Experiment 1 with the filter capacity at {scale_label(CAPACITY_SCALES[0])} and {scale_label(CAPACITY_SCALES[1])}")


def plot_rate(table):
    """sensitivity_rate.png: the 0.1 s run and the 1 Hz run in two colours."""
    variants = [("nominal", "0.1 s", MEASURED_COLOR), ("1hz", "1 s", MODEL_COLOR)]
    plot_lines(PLOTS_DIR / "sensitivity_rate.png", table, variants, f"Experiment 1 at 0.1 s and at 1 s (every {DECIMATION}th row)")


def main():
    started = time.perf_counter()
    specs = evaluation_runs(RAW_DIR)
    with Pool() as pool:
        rows = pool.map(process_run, specs, chunksize=1)
    with_nominal(pd.DataFrame(rows), pd.read_csv(RESULTS_CSV)).to_csv(SENSITIVITY_CSV, index=False, float_format="%.4f")
    table = pd.read_csv(SENSITIVITY_CSV)
    print(f"wrote {SENSITIVITY_CSV.relative_to(REPO_DIR)}: {len(table)} runs")

    write_text(SENSITIVITY_MD, sensitivity_text(table, EkfConfig.from_json(CONFIG_JSON)))
    print(f"wrote {SENSITIVITY_MD.relative_to(REPO_DIR)}")
    plot_capacity(table)
    plot_rate(table)
    print(f"wrote {PLOTS_DIR.relative_to(REPO_DIR)}/sensitivity_*.png")
    print(f"runtime {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
