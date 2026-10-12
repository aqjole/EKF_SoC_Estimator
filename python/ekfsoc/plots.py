"""Stage S1 figures (docs/decisions.md 1.14): OCV and its correction, dOCV/dSoC, the fitted 2RC tables, the open-loop check.

Every figure is a PNG written with the Agg backend and no metadata, so a rerun is byte-identical.
One colour per temperature in all figures, the same in every one: slots 1 to 6 of the dataviz reference palette
(adjacent slots pass the colour-blind check; the legend names every temperature).
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.fit import FITTED_TABLES


TEMP_COLORS = dict(zip(T_GRID_DEGC, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")))
MEASURED_COLOR = "#2a78d6"
MODEL_COLOR = "#eb6834"
INK_COLOR = "#52514e"
GRID_COLOR = "#e1e0d9"


def save(fig, axes, path):
    """Light grid, no top and right spines, tight layout, then write the PNG and close the figure."""
    for axis in axes:
        axis.grid(color=GRID_COLOR, linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120, metadata={"Software": None})
    plt.close(fig)


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
    fig, (top, bottom) = plt.subplots(2, 1, sharex=True, figsize=(10, 7), gridspec_kw={"height_ratios": [3, 1.5]})
    soc_percent = 100.0 * ocv_table.soc_grid
    for row, temp in enumerate(ocv_table.t_grid):
        color = TEMP_COLORS[int(temp)]
        rest = correction[correction["T_degC"] == temp]
        top.plot(soc_percent, ocv_table.ocv_c20[row], color=color, linestyle="--", linewidth=1.0)
        top.plot(soc_percent, ocv_table.ocv[row], color=color, linewidth=1.2)
        top.plot(100.0 * rest["soc"], rest["v_rest_V"], color=color, linestyle="none", marker="o", markersize=3.5)
        bottom.plot(soc_percent, 1000.0 * ocv_table.delta_v[row], color=color, linewidth=1.2)
        bottom.plot(100.0 * rest["soc"], rest["delta_mV"], color=color, linestyle="none", marker="o", markersize=3.5)

    top.set_ylabel("OCV (V)")
    top.legend(handles=temperature_keys() + [key("C/20 discharge curve", linestyle="--"), key("corrected OCV"),
                                             key("HPPC rest voltage", linestyle="none", marker="o")],
               loc="upper left", ncol=3, frameon=False)
    bottom.set_ylabel("correction (mV)")
    bottom.set_xlabel("SoC (%)")
    save(fig, (top, bottom), path)


def plot_docv(params, path):
    """docv.png: dOCV/dSoC on the SoC grid, one line per temperature."""
    fig, axis = plt.subplots(figsize=(10, 5))
    for row, temp in enumerate(params.t_grid):
        axis.plot(100.0 * params.soc_grid, params.docv[row], color=TEMP_COLORS[int(temp)], linewidth=1.2)
    axis.set_xlabel("SoC (%)")
    axis.set_ylabel("dOCV/dSoC (V per unit SoC)")
    axis.legend(handles=temperature_keys(), frameon=False)
    save(fig, (axis,), path)


def plot_params(levels, params, path):
    """params.png: R0, R1, tau1, R2, tau2 against SoC, one panel each, one line per temperature.

    Solid line with dots: the HPPC level fits (`levels`, the table of results/fit_levels.csv), each at the SoC
    its fit belongs to. Dashed: the table on the SoC grid (`params`) that was resampled from them.
    The sixth panel holds the legend.
    """
    fig, grid = plt.subplots(2, 3, figsize=(12, 6.5))
    *panels, legend_panel = grid.flat
    for panel, (field, soc_key, column) in zip(panels, FITTED_TABLES):
        for row, temp in enumerate(params.t_grid):
            color = TEMP_COLORS[int(temp)]
            fits = levels[levels["T_degC"] == temp]
            panel.plot(100.0 * fits[soc_key], fits[column], color=color, linewidth=0.8, marker="o", markersize=3)
            panel.plot(100.0 * params.soc_grid, getattr(params, field)[row], color=color, linestyle="--", linewidth=1.0)
        name, unit = column.split("_")
        panel.set_xlabel("SoC (%)")
        panel.set_ylabel(f"{name} ({unit})")

    legend_panel.axis("off")
    legend_panel.legend(handles=temperature_keys() + [key("HPPC level fit", linestyle="-", marker="o"),
                                                      key("table on the SoC grid", linestyle="--")],
                        loc="center", frameon=False)
    save(fig, panels, path)


def plot_model_fit(result, path):
    """Plot measured and model voltage over time, with the error in mV below. `result` is validate_us06's dict."""
    run = result["run"]
    minutes = (run.t - run.t[0]) / 60.0

    fig, (top, bottom) = plt.subplots(2, 1, sharex=True, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1.5]})
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
    save(fig, (top, bottom), path)
