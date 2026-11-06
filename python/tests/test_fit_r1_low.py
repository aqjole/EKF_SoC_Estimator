"""Tests of the 2RC-Il table and its factor fit (decisions 1.37): the scale s(I) per level, and the joint linear fit
recovering known factors from voltages the model itself made. No raw data is needed: the pulse rows are those of the
committed results/fit_pulses_r1i.csv, and the runs are synthetic."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ekfsoc.constants import REPO_DIR
from ekfsoc.loader import soc_ref
from ekfsoc.model import Params, simulate_open_loop
from export_params import PARAMS_CSV
from fit_r1_current import level_nodes
from fit_r1_low import FIT_TEMPS_DEGC, fit_factors, low_params, scaled_level_nodes


def pulse_rows():
    """The 2RC-I pulse fits of results/fit_pulses_r1i.csv as row dicts."""
    return pd.read_csv(REPO_DIR / "results" / "fit_pulses_r1i.csv").to_dict("records")


def level(temp, currents):
    """Rows of one level at temp, with R1 = 10 mOhm at every pulse current."""
    return [{"T_degC": temp, "I_A": current, "R1_ohm": 0.010, "used": True} for current in currents]


def test_the_scale_is_the_factor_up_to_the_first_pulse_and_ramps_to_one_at_the_second():
    nodes = (0.75, 1.5, 3.0, 4.5, 6.0, 12.0)
    got = scaled_level_nodes({0: 0.8})(level(0, (3.0, 6.0, 12.0)), nodes) / 0.010
    assert np.allclose(got, [0.8, 0.8, 0.8, 0.9, 1.0, 1.0], rtol=1e-12)


def test_a_level_with_one_pulse_is_scaled_at_every_current():
    nodes = (0.75, 3.0, 18.0)
    got = scaled_level_nodes({0: 0.8})(level(0, (3.0,)), nodes) / 0.010
    assert np.allclose(got, [0.8, 0.8, 0.8], rtol=1e-12)


def test_a_temperature_without_a_factor_keeps_the_2rc_i_values_exactly():
    rows = level(25, (3.0, 6.0))
    nodes = (0.75, 1.5, 3.0, 6.0)
    assert np.array_equal(scaled_level_nodes({0: 0.8})(rows, nodes), level_nodes(rows, nodes))


def synthetic_run(temp, seed):
    """A drive-like run at a cell temperature near temp: random currents from -1 to 4 A held for 1 to 20 s."""
    rng = np.random.default_rng(seed)
    current = np.repeat(rng.uniform(-1.0, 4.0, 60), rng.integers(10, 200, 60))
    dt = np.full(len(current), 0.1)
    dt[0] = 0.0
    ah_removed = np.cumsum(np.concatenate([[0.0], current[:-1]]) * dt) / 3600.0
    return SimpleNamespace(i=current, dt=dt, temp=np.full(len(current), temp + 0.4), soc0=1.0, ah_removed=ah_removed)


def test_the_joint_fit_recovers_the_factors_of_a_model_made_voltage():
    params_2rc = Params.from_csv(PARAMS_CSV)
    rows = pulse_rows()
    truth = {10: 0.9, 0: 0.7, -10: 1.2, -20: 0.6}
    runs = [synthetic_run(temp, seed) for seed, temp in enumerate(FIT_TEMPS_DEGC)]
    params_true = low_params(params_2rc, rows, truth)
    for offset, run in zip((0.01, -0.02, 0.0, 0.005), runs):
        run.v = simulate_open_loop(params_true, run.i, run.temp, soc_ref(run), run.dt) + offset
    factors, _ = fit_factors(params_2rc, rows, runs)
    assert [factors[temp] for temp in FIT_TEMPS_DEGC] == pytest.approx([truth[temp] for temp in FIT_TEMPS_DEGC],
                                                                        abs=1e-9)
