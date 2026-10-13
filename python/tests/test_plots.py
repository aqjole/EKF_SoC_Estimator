"""Tests for the figures in ekfsoc/plots.py (S1 and S2): each one is written as a PNG and a rerun gives the same bytes."""

import numpy as np
import pandas as pd
import pytest

from ekfsoc.constants import SOC_GRID, T_GRID_DEGC
from ekfsoc.model import Params
from ekfsoc.ocv import OcvTable
from ekfsoc.plots import plot_docv, plot_ocv, plot_params, plot_summary, plot_synthetic, plot_trace


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def flat_tables(value):
    """A table of one value on the (temperature, SoC) grid."""
    return np.full((len(T_GRID_DEGC), len(SOC_GRID)), value)


def synthetic_params():
    tables = {name: flat_tables(1.0) for name in ("ocv", "docv", "r0", "r1", "tau1", "r2", "tau2")}
    return Params(t_grid=T_GRID_DEGC, soc_grid=SOC_GRID, **tables)


def synthetic_ocv_table():
    ends = np.zeros(len(T_GRID_DEGC))
    return OcvTable(SOC_GRID, np.array(T_GRID_DEGC, dtype=float), ocv=flat_tables(3.7), docv=flat_tables(1.0),
                    ocv_c20=flat_tables(3.6), delta_v=flat_tables(0.1), soc_min=ends, soc_max=ends + 1.0,
                    monotone=np.ones(len(T_GRID_DEGC), dtype=bool), fallback_used=False)


def synthetic_correction():
    return pd.DataFrame({"T_degC": T_GRID_DEGC, "soc": 0.5, "v_rest_V": 3.7, "v_c20_V": 3.6, "delta_mV": 100.0})


def synthetic_levels():
    """Two levels per temperature; the second has no slow fit, as the last level of a real run."""
    return pd.DataFrame({
        "T_degC": np.repeat(T_GRID_DEGC, 2), "level": [1, 2] * len(T_GRID_DEGC),
        "soc_pulses": [0.9, 0.5] * len(T_GRID_DEGC), "soc_rest": [0.8, np.nan] * len(T_GRID_DEGC),
        "R0_ohm": 0.02, "R1_ohm": 0.01, "tau1_s": 3.0, "R2_ohm": [0.05, np.nan] * len(T_GRID_DEGC),
        "tau2_s": [300.0, np.nan] * len(T_GRID_DEGC),
    })


def synthetic_trace():
    """A falling reference over 30 min; the estimates start 10 samples late and begin 20 pp low and 5 pp high."""
    t = np.arange(0.0, 1800.0, 1.0)
    soc_ref = np.linspace(1.0, 0.2, len(t))
    soc_est = soc_ref - 0.20 * np.exp(-t / 300.0)
    cc = soc_ref + 0.05
    soc_est[:10] = np.nan
    cc[:10] = np.nan
    return t, soc_ref, soc_est, cc


def synthetic_results():
    """Two experiments over the six temperatures, one tuning-cycle run each, and one convergence time not reached."""
    results = pd.DataFrame({
        "experiment": ["exp1"] * 12 + ["exp2"] * 12, "T_degC": T_GRID_DEGC * 4,
        "is_tuning": ([True] + [False] * 5) * 2 + [False] * 6 + [True] + [False] * 5,
        "rmse_pp": np.linspace(0.5, 3.0, 24), "t_conv_s": np.linspace(60.0, 900.0, 24),
    })
    results.loc[results.index[-1], "t_conv_s"] = np.nan
    return results


T, SOC_REF, SOC_EST, CC = synthetic_trace()
RESULTS = synthetic_results()

FIGURES = {
    "ocv": lambda path: plot_ocv(synthetic_ocv_table(), synthetic_correction(), path),
    "docv": lambda path: plot_docv(synthetic_params(), path),
    "params": lambda path: plot_params(synthetic_levels(), synthetic_params(), path),
    "trace": lambda path: plot_trace(path, T, SOC_REF, SOC_EST, CC, 2.0, "synthetic run"),
    "synthetic": lambda path: plot_synthetic(path, T, SOC_REF, {"EKF, 20 pp low": SOC_EST}, 1.0, "synthetic data"),
    "summary_rmse": lambda path: plot_summary(path, RESULTS, "rmse_pp", "SoC RMSE"),
    "summary_convergence": lambda path: plot_summary(path, RESULTS, "t_conv_s", "convergence time"),
}


@pytest.mark.parametrize("draw", FIGURES.values(), ids=FIGURES.keys())
def test_a_figure_is_a_png_and_a_rerun_is_byte_identical(draw, tmp_path):
    draw(tmp_path / "first.png")
    draw(tmp_path / "second.png")

    assert (tmp_path / "first.png").read_bytes().startswith(PNG_SIGNATURE)
    assert (tmp_path / "first.png").read_bytes() == (tmp_path / "second.png").read_bytes()
