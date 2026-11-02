"""Tests of the R1 table over current of the 2RC-I model (S7): Eq. 4b, its use in the open-loop simulation and the
filter, the results/r1_current.csv round trip, and the one-line R1 fit of decisions 1.28. No raw data is needed."""

from dataclasses import replace

import numpy as np

from ekfsoc.ekf import Ekf, EkfConfig
from ekfsoc.fit import rc_voltage
from ekfsoc.model import Params, interp2, interp_current, simulate_open_loop
from ekfsoc.r1_current import read_r1_current, write_r1_current
from export_params import PARAMS_CSV
from fit_r1_current import I_GRID_A, window_r1


def with_current_axis(params, scales):
    """params with an R1 table over I_GRID_A whose slice q is params.r1 times scales[q]."""
    table = np.stack([params.r1 * scale for scale in scales], axis=2)
    return replace(params, i_grid=I_GRID_A, r1_current=table)


def test_eq_4b_on_a_current_node_returns_that_slice_exactly():
    params = with_current_axis(Params.from_csv(PARAMS_CSV), (1.0, 0.9, 0.8, 0.7, 0.6, 0.5))
    slices = params.r1_slices()
    t_grid, soc_grid = params.t_grid.tolist(), params.soc_grid.tolist()
    expected = interp2(slices[2], t_grid, soc_grid, -7.3, 0.437)
    assert interp_current(slices, t_grid, soc_grid, list(I_GRID_A), -7.3, 0.437, -3.0) == expected


def test_eq_4b_weights_linearly_between_nodes_and_clamps_beyond_them():
    params = with_current_axis(Params.from_csv(PARAMS_CSV), (1.0, 0.9, 0.8, 0.7, 0.6, 0.5))
    slices = params.r1_slices()
    t_grid, soc_grid, i_grid = params.t_grid.tolist(), params.soc_grid.tolist(), list(I_GRID_A)
    base = interp2(params.r1.tolist(), t_grid, soc_grid, 12.0, 0.61)
    got = [interp_current(slices, t_grid, soc_grid, i_grid, 12.0, 0.61, current) for current in (4.5, 0.1, 40.0)]
    assert np.allclose(got, [0.75 * base, 1.0 * base, 0.5 * base], rtol=1e-12)


def test_identical_current_slices_give_the_2rc_open_loop_voltage():
    params_2rc = Params.from_csv(PARAMS_CSV)
    params_ri = with_current_axis(params_2rc, (1.0,) * len(I_GRID_A))
    rng = np.random.default_rng(1)
    n = 400
    current, dt = rng.uniform(-3.0, 12.0, n), np.full(n, 0.1)
    temp, soc = np.full(n, 3.0), np.linspace(0.9, 0.88, n)
    v_2rc = simulate_open_loop(params_2rc, current, temp, soc, dt)
    assert np.allclose(simulate_open_loop(params_ri, current, temp, soc, dt), v_2rc, rtol=0.0, atol=1e-12)


def test_the_filter_reads_r1_at_the_held_current():
    """With R1 halved on every slice from 6 A up, the step's branch input halves when 12 A is held, not 1 A."""
    params_2rc = Params.from_csv(PARAMS_CSV)
    params_ri = with_current_axis(params_2rc, (1.0, 1.0, 1.0, 0.5, 0.5, 0.5))
    cfg = EkfConfig(q_soc=1e-7, q_v=1e-6, r=0.01)
    v1 = []
    for params in (params_2rc, params_ri):
        ekf = Ekf(params, cfg, soc0=0.8)
        ekf.predict(12.0, 25.0, 1.0)
        v1.append(float(ekf.x[1]))
    assert np.isclose(v1[1], 0.5 * v1[0], rtol=1e-12)


def test_r1_current_csv_round_trips(tmp_path):
    params_2rc = Params.from_csv(PARAMS_CSV)
    params_ri = with_current_axis(params_2rc, (1.3, 1.2, 1.1, 1.0, 0.9, 0.8))
    path = tmp_path / "r1_current.csv"
    write_r1_current(params_ri, path)
    back = read_r1_current(params_2rc, path)
    assert np.allclose(back.r1_current, params_ri.r1_current, rtol=1e-5) and np.array_equal(back.i_grid, I_GRID_A)


def test_window_r1_recovers_a_known_r1_with_a_free_constant():
    dt = np.full(500, 0.1)
    dt[0] = 0.0
    current = np.where(np.arange(500) < 100, 6.0, 0.0)
    true_r1, tau1 = 0.012, 3.0
    z = 0.004 - true_r1 * rc_voltage(current, dt, 1.0, tau1)
    r1, rmse_mv = window_r1(current, dt, z, tau1)
    assert np.isclose(r1, true_r1, rtol=1e-12) and rmse_mv < 1e-9
