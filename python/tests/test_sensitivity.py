"""Tests for python/sensitivity.py (S5, docs/decisions.md 1.18 and 1.19): the decimation rule, the capacity scaling of
the coulomb counter and of the filter, and the text of the two tables. All inputs are synthetic; no raw data is needed.
"""

import numpy as np
import pandas as pd
import pytest

import sensitivity
from ekfsoc.constants import Q_REF_AH
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.loader import Run
from ekfsoc.metrics import coulomb_count
from ekfsoc.model import Params


# --- decimate_run ---------------------------------------------------------------------------------


@pytest.fixture
def decimated():
    """25 rows with uneven steps (0.1 s plus k ms at row k), decimated by 10: rows 0, 10 and 20 are kept."""
    steps = 0.1 + 0.001 * np.arange(25)
    steps[0] = 0.0
    t = 5.0 + np.cumsum(steps)
    dt = np.zeros(25)
    dt[1:] = t[1:] - t[:-1]
    rows = np.arange(25.0)
    run = Run(t=t, i=rows, v=3.0 + rows, temp=25.0 + rows, ah_removed=0.01 * rows, dt=dt, soc0=1.0, meta={"file": "x"})
    return run, sensitivity.decimate_run(run, 10)


def test_decimate_run_keeps_rows_0_10_and_20(decimated):
    _, kept = decimated
    assert kept.i.tolist() == [0.0, 10.0, 20.0]


def test_decimate_run_keeps_the_same_rows_of_every_array(decimated):
    run, kept = decimated
    assert [kept.t.tolist(), kept.v.tolist(), kept.temp.tolist(), kept.ah_removed.tolist()] == [
        run.t[[0, 10, 20]].tolist(), [3.0, 13.0, 23.0], [25.0, 35.0, 45.0], run.ah_removed[[0, 10, 20]].tolist()]


def test_decimate_run_recomputes_dt_between_the_kept_rows(decimated):
    run, kept = decimated
    assert kept.dt[1:].tolist() == [run.t[10] - run.t[0], run.t[20] - run.t[10]]


def test_decimate_run_first_dt_is_zero(decimated):
    _, kept = decimated
    assert kept.dt[0] == 0.0


# --- the capacity scaling ------------------------------------------------------------------------


def test_coulomb_count_with_a_smaller_capacity_moves_1_over_0_95_times_further():
    i, dt = np.full(100, 2.0), np.full(100, 1.0)
    nominal = coulomb_count(i, dt, 1.0, Q_REF_AH)
    smaller = coulomb_count(i, dt, 1.0, 0.95 * Q_REF_AH)
    assert 1.0 - smaller[-1] == pytest.approx((1.0 - nominal[-1]) / 0.95, rel=1e-12)


def test_run_ekf_with_twice_the_capacity_moves_soc_by_half_the_coulomb_term():
    # Flat tables (OCV = 3 + SoC, no RC branches) and r = 1e12 V^2: the gain is about 1e-14, so the voltage does not
    # move the SoC and each predict removes I dt / (3600 * 2 Q_ref). 9 steps of 1 s at 2 A: 18 A s in all.
    flat = np.full((2, 2), 0.0)
    params = Params(t_grid=[25.0, 0.0], soc_grid=[0.0, 1.0], ocv=np.array([[3.0, 4.0], [3.0, 4.0]]),
                    docv=flat + 1.0, r0=flat + 0.05, r1=flat, tau1=flat + 1e12, r2=flat, tau2=flat + 1e12)
    cfg = EkfConfig(q_soc=0.0, q_v=0.0, r=1e12)
    n = 10
    out = run_ekf(params, cfg, np.full(n, 2.0), np.full(n, 3.4), np.full(n, 25.0), np.ones(n), 0.5, q_ref_ah=2.0 * Q_REF_AH)
    assert 0.5 - out["soc"][-1] == pytest.approx(0.5 * 18.0 / (3600.0 * Q_REF_AH), rel=1e-9)


# --- the table text ------------------------------------------------------------------------------


@pytest.fixture
def table():
    """Four runs, two at 25 degC and two at -20 degC, with every column of results/s5/sensitivity.csv."""
    columns = ["ekf_rmse_pp_095", "cc_rmse_pp_095", "ekf_rmse_pp_105", "cc_rmse_pp_105", "ekf_rmse_pp_1hz",
               "ekf_max_abs_pp_1hz", "cc_rmse_pp_1hz", "ekf_rmse_pp_nominal", "ekf_max_abs_pp_nominal", "cc_rmse_pp_nominal"]
    rows = []
    for n, (cycle, temp) in enumerate([("UDDS", 25), ("US06", 25), ("UDDS", -20), ("US06", -20)]):
        values = {column: 1.0 + n + 0.1 * c for c, column in enumerate(columns)}
        rows.append({"folder": "f", "file": f"{n}.mat", "cycle": cycle, "T_degC": temp, "is_tuning": False,
                     "rows_1hz": 100, **values})
    return pd.DataFrame(rows)


def test_capacity_section_opens_with_its_heading(table):
    assert sensitivity.capacity_lines(table)[0] == "## Capacity error: the filter capacity at -5 % and +5 %"


def test_capacity_table_ends_with_the_mean_over_all_runs(table):
    # ekf_rmse_pp_095 is 1, 2, 3, 4 over the four runs: mean 2.50; nominal adds 0.7, +5 % adds 0.2, and so on.
    lines = sensitivity.capacity_lines(table)
    all_row = next(line for line in lines if line.startswith("| all |"))
    assert all_row == "| all | 4 | 2.50 | 3.20 | 2.70 | 2.60 | 3.40 | 2.80 |"


def test_capacity_section_names_the_largest_per_run_rmse(table):
    # The largest EKF value is ekf_rmse_pp_105 of the fourth run (4.2), the largest coulomb-counting one cc_rmse_pp_105 (4.3).
    line = next(line for line in sensitivity.capacity_lines(table) if line.startswith("Largest"))
    assert line == ("Largest per-run EKF RMSE: 4.20 pp (US06 at -20 degC, +5 %); "
                    "largest per-run coulomb-counting RMSE: 4.30 pp (US06 at -20 degC, +5 %).")


def test_rate_section_opens_with_its_heading(table):
    assert sensitivity.rate_lines(table)[0] == "## Sample rate: every 10th row (1 Hz)"


def test_rate_table_has_means_of_the_rmse_and_the_largest_max_error(table):
    # RMSE columns are means over the four runs (2.5 + offset); max |error| columns the largest (4 + offset).
    lines = sensitivity.rate_lines(table)
    all_row = next(line for line in lines if line.startswith("| all |"))
    assert all_row == "| all | 4 | 3.20 | 2.90 | 4.80 | 4.50 | 3.40 | 3.10 |"
