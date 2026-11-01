"""Synthetic data for the filter check: the 2RC model's own voltage plus noise (the spec, S2 tests).

The synthetic test of python/tests/test_ekf.py and the figure results/plots/s2/synthetic.png (run_all.py) draw
their data from here, so the picture shows what the test checks: the filter apart from model mismatch.
"""

import numpy as np

from ekfsoc.constants import Q_REF_AH
from ekfsoc.ekf import EkfConfig
from ekfsoc.model import simulate_open_loop


# Provisional noise settings for this check only. The frozen settings come from python/tune.py
# (results/ekf_config.json). R is deliberately larger than the 5 mV noise variance, 2.5e-5 V^2:
# with R at the true noise level a 20 pp start takes more than 1000 s to settle for some noise seeds.
SYNTHETIC_CFG = EkfConfig(q_soc=1e-8, q_v=1e-8, r=1e-3)

NOISE_STD_V = 0.005
NOISE_SEED = 0
SOC_START = 0.8
WRONG_INIT_PP = 20.0

N_SAMPLES = 15000
DT_S = 0.1
TEMP_DEGC = 25.0


def synthetic_data(params):
    """Return 1500 s at 0.1 s and 25 degC: the model voltage for a made-up current plus 5 mV Gaussian noise.

    A dict of the arrays i (A, -2 to +6 A), v (V), temp (degC), dt (s), t (s) and soc_true (fraction),
    with the Params under "params".
    """
    dt = np.full(N_SAMPLES, DT_S)
    dt[0] = 0.0
    t = np.cumsum(dt)
    i = 2.0 + 3.0 * np.sin(2.0 * np.pi * t / 60.0) + 1.0 * np.sin(2.0 * np.pi * t / 7.0)
    temp = np.full(N_SAMPLES, TEMP_DEGC)
    # True SoC by coulomb counting (Eq. 3): the previous sample's current held over each step.
    soc_true = SOC_START - np.concatenate(([0.0], np.cumsum(i[:-1] * dt[1:]))) / (3600.0 * Q_REF_AH)
    v_model = simulate_open_loop(params, i, temp, soc_true, dt)
    v = v_model + np.random.default_rng(NOISE_SEED).normal(0.0, NOISE_STD_V, N_SAMPLES)
    return {"params": params, "i": i, "v": v, "temp": temp, "dt": dt, "t": t, "soc_true": soc_true}
