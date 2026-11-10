from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.model import Params, interp2, interp_current, rc_step
from fit_3rcd import grid_cell
from s10_jacobian import covariance_change, process_partials, r1_slopes, replay_case, soc_slopes


TEMPS = np.array([20.0, 0.0])
SOCS = np.array([0.0, 0.5, 1.0])
TABLE = np.array([[0.01, 0.02, 0.06], [0.03, 0.06, 0.07]])
EPS = 1e-7


def params_3rc(flat=False):
    """Three branches, R1 from the plain table; with flat=True no table depends on SoC."""
    axis = np.array([0.0, 0.5, 1.0])
    surface = np.zeros((2, 3)) if flat else np.tile(axis, (2, 1))
    ones = np.ones((2, 3))
    return Params([25, 10], axis, 3.2 + np.tile(axis, (2, 1)), ones, 0.02 + 0.01 * surface, 0.01 + 0.002 * surface,
                  4 + surface, 0.03 - 0.015 * surface, 280 - 60 * surface, 0.02 + 0.01 * surface, 45 + 5 * surface)


def synthetic_run(count):
    return SimpleNamespace(t=np.arange(count) * 0.1, dt=np.r_[0, np.full(count - 1, 0.1)],
                           i=5 * np.sin(np.arange(count)), v=np.full(count, 3.8), temp=np.full(count, 18.0))


@pytest.mark.parametrize("temp, soc", [(15.0, 0.63), (15.0, 0.5), (15.0, 0.0), (15.0, 1.0), (15.0, -0.01),
                                       (15.0, 1.01), (20.0, 0.3), (30.0, 0.3), (-5.0, 0.7)])
def test_lookup_slope_matches_the_one_sided_difference_of_the_active_cell(temp, soc):
    """Interior points, SoC and temperature grid points, and both edges of both clamped axes (Eq. 4)."""
    step = -EPS if soc >= 1.0 else EPS  # the active cell lies above a knot, below the last one
    difference = (interp2(TABLE, TEMPS, SOCS, temp, soc + step) - interp2(TABLE, TEMPS, SOCS, temp, soc)) / step
    slope = soc_slopes(TABLE[:, :, None], SOCS, grid_cell(TEMPS, np.array([temp])), np.array([soc]))[0, 0]
    assert slope == pytest.approx(difference, abs=1e-6)


def test_r1_slope_over_current_matches_finite_difference_at_fixed_current():
    i_grid = np.array([1.0, 4.0])
    tables = np.stack((TABLE, 0.5 * TABLE + 0.01), axis=-1)
    params = SimpleNamespace(r1_current=tables, i_grid=i_grid, soc_grid=SOCS)
    slices = [tables[:, :, q].tolist() for q in range(2)]
    read = lambda soc: interp_current(slices, TEMPS, SOCS, i_grid, 12.0, soc, -2.5)
    difference = (read(0.7 + EPS) - read(0.7 - EPS)) / (2 * EPS)
    slope = r1_slopes(params, grid_cell(TEMPS, np.array([12.0])), np.array([0.7]), np.array([-2.5]))[0, 0]
    assert slope == pytest.approx(difference)


@pytest.mark.parametrize("dt", [0.0, 0.1, 2.0])
def test_process_partial_matches_finite_difference_with_fixed_branch_state(dt):
    state, resistance, tau, held = 0.05, 0.024, 4.0, -5.0
    dr, dtau = 0.035, -2.0
    eps = 1e-6
    plus = rc_step(state, resistance + eps * dr, tau + eps * dtau, held, dt)
    minus = rc_step(state, resistance - eps * dr, tau - eps * dtau, held, dt)
    assert process_partials(dt, held, state, resistance, tau, dr, dtau) == pytest.approx((plus - minus) / (2 * eps))


def test_covariance_change_is_the_full_minus_the_legacy_product():
    rng = np.random.default_rng(1)
    root = rng.normal(size=(4, 4))
    covariance = root @ root.T
    diag = np.array([1.0, 0.9, 0.99, 0.97])
    omitted = np.array([0.0, 0.02, -0.003, 0.01])
    full = np.diag(diag)
    full[:, 0] += omitted
    expected = full @ covariance @ full.T - np.diag(diag) @ covariance @ np.diag(diag)
    np.testing.assert_allclose(covariance_change(omitted, diag, covariance), expected, atol=1e-14)


def test_replay_observes_the_legacy_filter_without_changing_its_estimates():
    axis = np.array([0.0, 0.5, 1.0])
    surface = np.tile(axis, (2, 1))
    base = Params([25, 10], axis, 3.2 + surface, np.ones_like(surface),
                  0.02 + 0.001 * surface, 0.01 + 0.002 * surface, 4 + surface,
                  0.03 - 0.015 * surface, 280 - 60 * surface)
    params = replace(base, i_grid=[0.0, 10.0], r1_current=np.stack((base.r1, 0.5 * base.r1), axis=-1))
    run = synthetic_run(30)
    cfg = EkfConfig(1e-7, 1e-6, 0.01)
    expected = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, 0.6)
    measurements = replay_case(run, params, cfg, 0.6, 0, expected["soc"], expected["v_pred"])
    assert all(np.isfinite(values).all() for values in measurements.values())


def test_replay_follows_a_three_branch_case_from_a_later_row():
    """The stored-trace check passes only if row `start` gets dt = 0 and the given soc0, as in run_ekf."""
    run, params, cfg = synthetic_run(30), params_3rc(), EkfConfig(1e-7, 1e-6, 0.01)
    expected = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, 0.4, start=7)
    measurements = replay_case(run, params, cfg, 0.4, 7, expected["soc"], expected["v_pred"])
    assert measurements["column"].shape == (23, 3)


def test_correction_change_is_zero_when_no_table_depends_on_soc():
    run, params, cfg = synthetic_run(30), params_3rc(flat=True), EkfConfig(1e-7, 1e-6, 0.01)
    expected = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, 0.4)
    measurements = replay_case(run, params, cfg, 0.4, 0, expected["soc"], expected["v_pred"])
    assert not measurements["correction_pp"].any()
