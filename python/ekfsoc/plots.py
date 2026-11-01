"""Figures of stages S1 and S2 (docs/decisions.md 1.14).

S1: OCV and its correction, dOCV/dSoC, the fitted 2RC tables, the open-loop check.
S2: one run's SoC traces with the error band, the summaries over all runs, the synthetic convergence test.

Every figure is a PNG written with the Agg backend and no metadata, so a rerun is byte-identical.
The S1 figures use one colour per temperature, the same in every one: slots 1 to 6 of the dataviz reference palette
(adjacent slots pass the colour-blind check; the legend names every temperature). The S2 figures never colour by
temperature; their colours stand for the series named in each legend.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.fit import FITTED_TABLES


TEMP_COLORS = dict(zip(T_GRID_DEGC, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")))
MEASURED_COLOR = "#2a78d6"
MODEL_COLOR = "#eb6834"
ESTIMATE_COLORS = (MODEL_COLOR, "#1baf7a")
INK_COLOR = "#52514e"
GRID_COLOR = "#e1e0d9"
DOTS = {"linestyle": "none", "marker": "o", "markersize": 3.5}
SUMMARY_DOTS = {"linestyle": "none", "markersize": 5, "alpha": 0.7}


def save(fig, path):
    """Light grid, no top and right spines, tight layout, then write the PNG and close the figure."""
    for axis in fig.axes:
        axis.grid(color=GRID_COLOR, linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, metadata={"Software": None})
    plt.close(fig)


def stacked_panels(height):
    """A figure with a tall panel over a short one on a shared x axis, 10 in wide; returns fig, top, bottom."""
    fig, (top, bottom) = plt.subplots(2, 1, sharex=True, figsize=(10, height), gridspec_kw={"height_ratios": [3, 1.5]})
    return fig, top, bottom


def key(label, color=INK_COLOR, **style):
    """A legend entry that stands for a colour or a line style, not for one plotted line."""
    return Line2D([], [], color=color, label=label, **style)


def temperature_keys():
    """One legend entry per temperature, in table row order."""
    return [key(f"{temp} degC", color) for temp, color in TEMP_COLORS.items()]


def plot_ocv(ocv_table, correction, path):
    """ocv.png: per temperature the C/20 curve (dashed), the corrected OCV (solid) and the HPPC rest voltages (dots).

    The panel below shows the correction in mV: the smooth curve added to the C/20 curve, and delta at each rest
    point (decisions 1.1). `correction` is the table of results/ocv_correction.csv.
    """
    fig, top, bottom = stacked_panels(7)
    soc_percent = 100.0 * ocv_table.soc_grid
    for temp, ocv_c20, ocv, delta_v in zip(ocv_table.t_grid, ocv_table.ocv_c20, ocv_table.ocv, ocv_table.delta_v):
        color = TEMP_COLORS[int(temp)]
        rest = correction[correction["T_degC"] == temp]
        top.plot(soc_percent, ocv_c20, color=color, linestyle="--", linewidth=1.0)
        top.plot(soc_percent, ocv, color=color, linewidth=1.2)
        top.plot(100.0 * rest["soc"], rest["v_rest_V"], color=color, **DOTS)
        bottom.plot(soc_percent, 1000.0 * delta_v, color=color, linewidth=1.2)
        bottom.plot(100.0 * rest["soc"], rest["delta_mV"], color=color, **DOTS)

    top.set_ylabel("OCV (V)")
    top.legend(handles=temperature_keys() + [key("C/20 discharge curve", linestyle="--"), key("corrected OCV"),
                                             key("HPPC rest voltage", linestyle="none", marker="o")],
               loc="upper left", ncol=3, frameon=False)
    bottom.set_ylabel("correction (mV)")
    bottom.set_xlabel("SoC (%)")
    save(fig, path)


def plot_docv(params, path):
    """docv.png: dOCV/dSoC on the SoC grid, one line per temperature."""
    fig, axis = plt.subplots(figsize=(10, 5))
    for temp, docv in zip(params.t_grid, params.docv):
        axis.plot(100.0 * params.soc_grid, docv, color=TEMP_COLORS[int(temp)], linewidth=1.2)
    axis.set_xlabel("SoC (%)")
    axis.set_ylabel("dOCV/dSoC (V per unit SoC)")
    axis.legend(handles=temperature_keys(), frameon=False)
    save(fig, path)


def plot_params(levels, params, path, fitted_tables=FITTED_TABLES):
    """params.png: R0, R1, tau1, R2, tau2 (and R3, tau3 for FITTED_TABLES_3RC) against SoC, one panel each,
    one line per temperature.

    Solid line with dots: the HPPC level fits (`levels`, the table of results/fit_levels.csv), each at the SoC
    its fit belongs to. Dashed: the table on the SoC grid (`params`) that was resampled from them.
    The last panel holds the legend: the sixth of a 2 x 3 grid for five tables, the eighth of 2 x 4 for seven.
    """
    n_cols = (len(fitted_tables) + 2) // 2
    fig, grid = plt.subplots(2, n_cols, figsize=(4 * n_cols, 6.5))
    *panels, legend_panel = grid.flat
    for panel, (field, soc_key, column) in zip(panels, fitted_tables):
        for temp, table_row in zip(params.t_grid, getattr(params, field)):
            color = TEMP_COLORS[int(temp)]
            fits = levels[levels["T_degC"] == temp]
            panel.plot(100.0 * fits[soc_key], fits[column], color=color, linewidth=0.8, marker="o", markersize=3)
            panel.plot(100.0 * params.soc_grid, table_row, color=color, linestyle="--", linewidth=1.0)
        name, unit = column.split("_")
        panel.set_xlabel("SoC (%)")
        panel.set_ylabel(f"{name} ({unit})")

    for panel in panels[len(fitted_tables):]:  # a grid with more panels than tables (the two of decisions 1.26)
        panel.axis("off")
    legend_panel.axis("off")
    legend_panel.legend(handles=temperature_keys() + [key("HPPC level fit", linestyle="-", marker="o"),
                                                      key("table on the SoC grid", linestyle="--")],
                        loc="center", frameon=False)
    save(fig, path)


def plot_model_fit(result, path):
    """model_fit_<folder>.png: measured and model voltage over time, with the error in mV below. `result` is validate_us06's dict."""
    run = result["run"]
    minutes = (run.t - run.t[0]) / 60.0

    fig, top, bottom = stacked_panels(6)
    top.plot(minutes, run.v, color=MEASURED_COLOR, linewidth=0.8, label="measured")
    top.plot(minutes, result["v_model"], color=MODEL_COLOR, linewidth=0.8, label="model (open loop)")
    top.set_ylabel("terminal voltage (V)")
    top.legend(loc="lower left", frameon=False)
    top.set_title(
        f"US06 at {result['temp']} degC: RMSE {result['rmse_mv']:.1f} mV, max |error| {result['max_abs_mv']:.1f} mV",
        color=INK_COLOR,
    )

    bottom.axhline(0.0, color=INK_COLOR, linewidth=0.5)
    bottom.plot(minutes, result["error_mv"], color=MODEL_COLOR, linewidth=0.8)
    bottom.set_ylabel("model - measured (mV)")
    bottom.set_xlabel("time (min)")
    save(fig, path)


def plot_soc_error(path, t, soc_ref, estimates, band_pp, title, reference_label):
    """SoC traces over time on top, the error of each estimate in pp with a +-band_pp band below.

    `t` is in s, `soc_ref` and the arrays of `estimates` (label -> SoC array, at most two) are fractions of one
    length; NaN leaves a gap, as before a filter start. The error is estimate - reference.
    """
    minutes = (t - t[0]) / 60.0

    fig, top, bottom = stacked_panels(6)
    top.plot(minutes, 100.0 * soc_ref, color=MEASURED_COLOR, linewidth=1.2, label=reference_label)
    bottom.axhspan(-band_pp, band_pp, facecolor=INK_COLOR, alpha=0.12, linewidth=0, label=f"+-{band_pp:g} pp band")
    bottom.axhline(0.0, color=INK_COLOR, linewidth=0.5)
    for (label, soc), color in zip(estimates.items(), ESTIMATE_COLORS):
        top.plot(minutes, 100.0 * soc, color=color, linewidth=0.8, label=label)
        bottom.plot(minutes, 100.0 * (soc - soc_ref), color=color, linewidth=0.8)

    top.set_ylabel("SoC (%)")
    top.legend(loc="best", frameon=False)
    top.set_title(title, color=INK_COLOR)
    bottom.set_ylabel("error (pp)")
    bottom.set_xlabel("time (min)")
    bottom.legend(loc="best", frameon=False)
    save(fig, path)


def plot_trace(path, t, soc_ref, soc_est, cc, band_pp, title):
    """trace_<experiment>_<cycle>_<T>degC.png: reference, EKF and coulomb-counting SoC of one run, with their errors below."""
    plot_soc_error(path, t, soc_ref, {"EKF": soc_est, "coulomb counting": cc}, band_pp, title, "reference (cycler Ah counter)")


def plot_synthetic(path, t, soc_true, estimates, band_pp, title):
    """synthetic.png: the SoC the model generated and the EKF estimates from wrong initial SoCs (label -> SoC array)."""
    plot_soc_error(path, t, soc_true, estimates, band_pp, title, "true SoC (model-generated)")


def plot_summary(path, results_df, metric, title):
    """summary_rmse.png, summary_convergence.png: a column of results/ekf_results.csv against temperature, one panel per experiment.

    One dot per run; the tuning cycle is marked apart. A NaN (convergence not reached) is an x at the top of
    the panel. The metric is not negative, so the axis starts at 0. The rows of `results_df` are the experiments
    to show; the panels follow their order of first appearance.
    """
    experiments = results_df["experiment"].unique()
    fig, axes = plt.subplots(1, len(experiments), sharex=True, sharey=True, squeeze=False,
                             figsize=(2.6 * len(experiments) + 1.0, 4.5))
    axes = axes[0]

    styles = ((False, MEASURED_COLOR, "o"), (True, MODEL_COLOR, "D"))
    for axis, experiment in zip(axes, experiments):
        runs = results_df[results_df["experiment"] == experiment]
        for is_tuning, color, marker in styles:
            rows = runs[runs["is_tuning"] == is_tuning]
            reached = rows[metric].notna()
            axis.plot(rows["T_degC"][reached], rows[metric][reached], color=color, marker=marker, **SUMMARY_DOTS)
            missing = rows["T_degC"][~reached]
            axis.plot(missing, np.full(len(missing), 0.98), color=color, marker="x",
                      transform=axis.get_xaxis_transform(), **SUMMARY_DOTS)
        axis.set_title(experiment, color=INK_COLOR)
        axis.set_xlabel("temperature (degC)")

    axes[0].set_xticks(sorted(T_GRID_DEGC))
    axes[0].set_ylim(bottom=0.0)
    axes[0].set_ylabel(metric)
    keys = [key("evaluation runs", MEASURED_COLOR, linestyle="none", marker="o"),
            key("tuning cycle", MODEL_COLOR, linestyle="none", marker="D")]
    if results_df[metric].isna().any():
        keys.append(key("not reached", linestyle="none", marker="x"))
    axes[0].legend(handles=keys, loc="best", frameon=False)
    fig.suptitle(title, color=INK_COLOR)
    save(fig, path)
