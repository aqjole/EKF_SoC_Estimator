"""Tests of python/fit_3rc_rest.py that need no raw data."""

from dataclasses import replace

import numpy as np

from ekfsoc.model import Params, simulate_open_loop
from export_params import PARAMS_CSV
from fit_3rc_rest import REST_SKIP_S, fit_middle_branch


def test_fit_middle_branch_recovers_a_known_branch():
    """On a synthetic pulse train made with the 2RC tables plus a known branch and offset, the fit returns them."""
    dt_s = 0.5
    current = np.concatenate([np.zeros(200), np.full(20, 3.0), np.zeros(1200), np.full(20, -1.5), np.zeros(1200)])
    dt = np.full(len(current), dt_s)
    dt[0] = 0.0
    t = np.cumsum(dt)
    temp = np.full(len(current), -10.0)
    soc = np.linspace(0.70, 0.69, len(current))
    pulse_ends = t[[219, 1439]]
    cost = (current == 0.0) & np.any([(t >= end + REST_SKIP_S) & (t < end + 600.0) for end in pulse_ends], axis=0)

    params_2rc = Params.from_csv(PARAMS_CSV)
    shape = params_2rc.ocv.shape
    true = (0.025, 35.0, 0.004)  # R3 in Ohm, tau3 in s, offset in V
    params_3rc = replace(params_2rc, r3=np.full(shape, true[0]), tau3=np.full(shape, true[1]))
    voltage = simulate_open_loop(params_3rc, current, temp, soc, dt) + true[2]

    fit = fit_middle_branch(params_2rc, current, voltage, temp, soc, dt, cost)

    assert np.allclose([fit["R3_ohm"], fit["tau3_s"], fit["offset_mV"] / 1000.0], true, rtol=1e-4)
