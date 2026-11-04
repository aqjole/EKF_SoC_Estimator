"""Tests of the R1 table over current of the 2RC-I model (S7): Eq. 4b, its use in the open-loop simulation and the
filter, the results/r1_current.csv round trip, and the one-line R1 fit of decisions 1.28. No raw data is needed."""

from dataclasses import replace

import numpy as np

from ekfsoc.ekf import Ekf, EkfConfig
from ekfsoc.fit import rc_voltage
from ekfsoc.model import Params, R1Reader, interp2, interp_current, simulate_open_loop
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


def test_the_2rc_id_filter_reads_the_r1_table_under_a_negative_current_only():
    """2RC-Id (decisions 1.33) with every slice at half the r1 table: the branch input is the 2RC one at -3 A held
    and half of it at +3 A held."""
    params_2rc = Params.from_csv(PARAMS_CSV)
    params_rd = replace(with_current_axis(params_2rc, (0.5,) * len(I_GRID_A)), r1_current_discharge_only=True)
    cfg = EkfConfig(q_soc=1e-7, q_v=1e-6, r=0.01)
    ratios = []
    for current in (-3.0, 3.0):
        v1 = []
        for params in (params_2rc, params_rd):
            ekf = Ekf(params, cfg, soc0=0.8)
            ekf.predict(current, 25.0, 1.0)
            v1.append(float(ekf.x[1]))
        ratios.append(v1[1] / v1[0])
    assert np.allclose(ratios, [1.0, 0.5], rtol=1e-12)


def test_the_2rc_id_open_loop_voltage_is_the_2rc_one_when_every_current_is_negative():
    params_2rc = Params.from_csv(PARAMS_CSV)
    params_rd = replace(with_current_axis(params_2rc, (0.5,) * len(I_GRID_A)), r1_current_discharge_only=True)
    rng = np.random.default_rng(2)
    n = 400
    current, dt = rng.uniform(-6.0, -0.1, n), np.full(n, 0.1)
    temp, soc = np.full(n, -12.0), np.linspace(0.5, 0.52, n)
    v_2rc = simulate_open_loop(params_2rc, current, temp, soc, dt)
    assert np.array_equal(simulate_open_loop(params_rd, current, temp, soc, dt), v_2rc)


def test_the_2rc_ic_reader_takes_the_charge_table_under_a_negative_current_only():
    """2RC-Ic (decisions 1.35): discharge slices at the r1 table, charge slices at twice it."""
    params_2rc = Params.from_csv(PARAMS_CSV)
    params_rc = replace(with_current_axis(params_2rc, (1.0,) * len(I_GRID_A)), i_grid_charge=(0.375, 6.0),
                        r1_charge=np.stack([2.0 * params_2rc.r1] * 2, axis=2))
    read_r1 = R1Reader(params_rc)
    base = interp2(params_2rc.r1.tolist(), params_2rc.t_grid.tolist(), params_2rc.soc_grid.tolist(), -3.0, 0.6)
    assert np.allclose([read_r1(-3.0, 0.6, -2.0), read_r1(-3.0, 0.6, 2.0)], [2.0 * base, base], rtol=1e-12)


def test_window_r1_with_equal_weights_is_the_unweighted_fit():
    dt = np.full(300, 0.1)
    current = np.where(np.arange(300) < 100, -3.0, 0.0)
    z = 0.002 - 0.009 * rc_voltage(current, dt, 1.0, 2.0) + 1e-4 * np.sin(np.arange(300))
    assert np.isclose(window_r1(current, dt, z, 2.0, weights=np.full(300, 0.7))[0], window_r1(current, dt, z, 2.0)[0],
                      rtol=1e-12)
