"""Tests of python/fit_3rc.py that need no raw data."""

from dataclasses import replace

import numpy as np

from ekfsoc.model import Params, simulate_open_loop
from export_params import PARAMS_CSV
from fit_3rc import POOLED_R3_OHM, POOLED_TAU3_S, branch_sse


def test_branch_sse_matches_a_full_3rc_simulation():
    """The pooled ceiling scores the whole grid from one 2RC run; that must equal simulating each 3RC model."""
    rng = np.random.default_rng(0)
    n = 600
    current = rng.uniform(-2.0, 6.0, n)
    dt = np.full(n, 0.1)
    dt[0] = 0.0
    temp = np.full(n, -10.0)
    soc = np.linspace(0.8, 0.75, n)
    v_measured = rng.uniform(3.6, 3.9, n)
    params_2rc = Params.from_csv(PARAMS_CSV)
    error_2rc_mv = 1000.0 * (simulate_open_loop(params_2rc, current, temp, soc, dt) - v_measured)

    sse = branch_sse(error_2rc_mv, current, dt)

    a, b = 2, 4  # tau3 = 30 s, R3 = 35 mOhm
    shape = params_2rc.ocv.shape
    params_3rc = replace(params_2rc, r3=np.full(shape, POOLED_R3_OHM[b]), tau3=np.full(shape, POOLED_TAU3_S[a]))
    error_3rc_mv = 1000.0 * (simulate_open_loop(params_3rc, current, temp, soc, dt) - v_measured)
    assert np.isclose(sse[a, b], np.sum(error_3rc_mv ** 2), rtol=1e-12, atol=0.0)
