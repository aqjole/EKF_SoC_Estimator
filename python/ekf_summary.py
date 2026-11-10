"""results/s2/ekf_summary.md: the 3 pp gate and the cycle x temperature tables of every experiment.

Written by python/run_all.py (`make ekf`). Every number is read back from results/s2/ekf_results.csv, apart from the
synthetic-data section, which takes the data and the estimates of run_all.synthetic_runs.
"""

import math

import numpy as np

from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.experiments import CYCLE_NAMES, EXP3_START_SOC, OFFSET_A
from ekfsoc.metrics import CONV_BAND_PP, FORGET_BAND_PP, PP, SOC_MIN, after_conv_mask, band_times, rmse_pp
from ekfsoc.synthetic import SOC_START, SYNTHETIC_CFG
from export_params import md_table


# Sanity gate of the stage (the spec, S2): the correct-init SoC RMSE at 25 degC.
GATE_TEMP_DEGC = 25
GATE_RMSE_PP = 3.0

# A table is (column of results/s2/ekf_results.csv, title, number format).
RMSE_TABLE = ("rmse_pp", "SoC RMSE (pp)", "{:.2f}")
CONV_TABLES = (
    RMSE_TABLE,
    ("t_conv_s", f"Convergence time t_conv (s): the error stays within +-{CONV_BAND_PP:g} pp from then on", "{:.1f}"),
    ("t_forget_s", f"Init-forgetting time (s): within +-{FORGET_BAND_PP:g} pp of the run with the correct init", "{:.1f}"),
)
# Per experiment: the section title, what it is, and its tables.
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


def footer_cells(runs, column, number_format):
    """The rows under a table as (label, one cell per temperature): the mean over the evaluation runs, and for times the reached count."""
    evaluation = runs[~runs["is_tuning"]]
    means, reached = [], []
    for temp in T_GRID_DEGC:
        values = evaluation.loc[evaluation["T_degC"] == temp, column]
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
    for label, cells in footer_cells(runs, column, number_format):
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
        f"Data from the model itself: the 2RC model at {data['temp'][0]:g} degC from `results/s1/params.csv` on a made-up current "
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
    """Return the text of results/s2/ekf_summary.md. Every number comes from the CSV rows or the synthetic run."""
    n_runs = results["file"].nunique()
    lines = [
        "# EKF results (S2)",
        "",
        "Written by `python/run_all.py` (`make ekf`) from `results/s2/ekf_results.csv`. Do not edit by hand.",
        "",
        gate_text(results),
        "",
        "## Legend",
        "",
        f"- {n_runs} runs (the evaluation set and the tuning cycle), one row per run and experiment in `results/s2/ekf_results.csv`. "
        f"The noise settings are the frozen ones of `results/s2/ekf_config.json`: q_soc = {cfg.q_soc:g} 1/s, q_v = {cfg.q_v:g} V^2/s, "
        f"r = {cfg.r:g} V^2, and the same for every experiment and temperature.",
        "- Error = estimate - reference; the reference follows the cycler's Ah counter (docs/model.md C4).",
        f"- Evaluation window: from the filter start to the last sample where the reference SoC is at least {PP * SOC_MIN:.0f} % "
        "(docs/model.md C14). Every metric is over this window. Times are in s since the filter start.",
        "- `*` marks the tuning cycle (Mix 1 at 25 degC), on which the noise settings were tuned for experiments 2 and 4 (the mean of their SoC RMSE, docs/decisions.md 1.16). "
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
