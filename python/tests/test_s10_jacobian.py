import numpy as np
import pytest

from ekfsoc.model import interp2, rc_step
from fit_3rcd import grid_cell
from s10_jacobian import process_partials, soc_slopes


def test_lookup_slope_at_interior_matches_finite_difference():
    temps = np.array([20.0, 0.0])
    socs = np.array([0.0, 0.5, 1.0])
    table = np.array([[0.01, 0.02, 0.06], [0.03, 0.06, 0.07]])
    cell = grid_cell(temps, np.array([15.0]))
    soc = 0.63
    eps = 1e-6
    difference = (interp2(table, temps, socs, 15.0, soc + eps)
                  - interp2(table, temps, socs, 15.0, soc - eps)) / (2 * eps)
    assert soc_slopes(table[:, :, None], socs, cell, np.array([soc]))[0, 0] == pytest.approx(difference)


def test_lookup_slope_at_knots_and_outside_clamped_axis():
    temps = np.array([20.0, 0.0])
    socs = np.array([0.0, 0.5, 1.0])
    table = np.array([[0.01, 0.02, 0.06], [0.03, 0.06, 0.07]])
    cells = grid_cell(temps, np.full(5, 30.0))
    slopes = soc_slopes(table[:, :, None], socs, cells, np.array([-0.01, 0.0, 0.5, 1.0, 1.01]))
    np.testing.assert_allclose(slopes[:, 0], [0, 0.02, 0.08, 0.08, 0])


@pytest.mark.parametrize("dt", [0.0, 0.1, 2.0])
def test_process_partial_matches_finite_difference_with_fixed_branch_state(dt):
    state, resistance, tau, held = 0.05, 0.024, 4.0, -5.0
    dr, dtau = 0.035, -2.0
    eps = 1e-6
    plus = rc_step(state, resistance + eps * dr, tau + eps * dtau, held, dt)
    minus = rc_step(state, resistance - eps * dr, tau - eps * dtau, held, dt)
    assert process_partials(dt, held, state, resistance, tau, dr, dtau) == pytest.approx((plus - minus) / (2 * eps))


def test_replay_observes_the_legacy_filter_without_changing_its_estimates():
    from dataclasses import replace
    from types import SimpleNamespace

    from ekfsoc.ekf import EkfConfig, run_ekf
    from ekfsoc.model import Params
    from s10_jacobian import replay_measurements

    axis = np.array([0.0, 0.5, 1.0])
    surface = np.tile(axis, (2, 1))
    base = Params([25, 10], axis, 3.2 + surface, np.ones_like(surface),
                  0.02 + 0.001 * surface, 0.01 + 0.002 * surface, 4 + surface,
                  0.03 - 0.015 * surface, 280 - 60 * surface)
    params = replace(base, i_grid=[0.0, 10.0], r1_current=np.stack((base.r1, 0.5 * base.r1), axis=-1))
    count = 30
    run = SimpleNamespace(t=np.arange(count) * 0.1, dt=np.r_[0, np.full(count - 1, 0.1)],
                          i=5 * np.sin(np.arange(count)), v=np.full(count, 3.8), temp=np.full(count, 18.0))
    cfg = EkfConfig(1e-7, 1e-6, 0.01)
    reference = np.full(count, 0.6)
    expected = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, reference[0])
    measurements = replay_measurements(run, reference, params, cfg, expected["soc"], expected["v_pred"])
    assert all(np.isfinite(values).all() for values in measurements)
