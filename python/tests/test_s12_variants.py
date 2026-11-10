from functools import partial

import numpy as np
import pytest

from ekfsoc.ekf import Ekf, EkfConfig, run_ekf
from ekfsoc.model import interp2
from s12_variants import JacobianEkf
from test_s10_jacobian import params_3rc, synthetic_run


CFG = EkfConfig(1e-7, 1e-6, 0.01)
STATE = np.array([0.63, 0.012, -0.004, 0.02])


def predicted_state(params, state, current, temp, dt):
    """Eq. 6 from a given posterior state, read from the plain filter."""
    ekf = Ekf(params, CFG, state[0])
    ekf.x = state
    ekf.predict(current, temp, dt)
    return ekf.x


def variant(process, measurement):
    return partial(JacobianEkf, process=process, measurement=measurement)


def test_incumbent_variant_repeats_the_plain_filter_from_a_later_row_with_an_offset():
    run, params = synthetic_run(40), params_3rc()
    expected = run_ekf(params, CFG, run.i, run.v, run.temp, run.dt, 0.4, start=5, current_offset=0.2)
    result = run_ekf(params, CFG, run.i, run.v, run.temp, run.dt, 0.4, start=5, current_offset=0.2,
                     filter_class=variant(False, False))
    np.testing.assert_array_equal(result["soc"], expected["soc"])


def test_process_variant_propagates_the_covariance_with_the_jacobian_of_eq6():
    params = params_3rc()
    current, temp, dt, h = -3.0, 18.0, 2.0, 1e-6
    columns = [(predicted_state(params, STATE + h * unit, current, temp, dt)
                - predicted_state(params, STATE - h * unit, current, temp, dt)) / (2 * h) for unit in np.eye(4)]
    jacobian = np.column_stack(columns)
    covariance = np.diag([0.01, 1e-4, 4e-4, 2e-4]) + 1e-5
    ekf = variant(True, False)(params, CFG, STATE[0])
    ekf.x, ekf.P = STATE, covariance
    ekf.predict(current, temp, dt)
    expected = jacobian @ covariance @ jacobian.T + np.diag([CFG.q_soc, CFG.q_v, CFG.q_v, CFG.q_v]) * dt
    np.testing.assert_allclose(ekf.P, expected, rtol=1e-6, atol=1e-13)


def test_measurement_variant_adds_the_r0_term_to_the_soc_entry_of_h():
    params = params_3rc()
    ekf = variant(False, True)(params, CFG, 0.5)
    dr0 = (interp2(params.r0, params.t_grid, params.soc_grid, 18.0, 0.7 + 1e-7)
           - interp2(params.r0, params.t_grid, params.soc_grid, 18.0, 0.7 - 1e-7)) / 2e-7
    expected = interp2(params.docv, params.t_grid, params.soc_grid, 18.0, 0.7) - 4.0 * dr0
    assert ekf.h_soc(4.0, 18.0, 0.7) == pytest.approx(expected)


def test_run_ekf_runs_the_given_filter_class():
    run, params = synthetic_run(40), params_3rc()
    plain = run_ekf(params, CFG, run.i, run.v, run.temp, run.dt, 0.4)
    measured = run_ekf(params, CFG, run.i, run.v, run.temp, run.dt, 0.4, filter_class=variant(False, True))
    assert not np.array_equal(measured["soc"], plain["soc"])
