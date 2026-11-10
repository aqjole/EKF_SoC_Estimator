"""The three Jacobian variants of the 3RC-D0 filter and their replay on one Mix run (decision 1.56, step B part 2).

A variant changes only the linearisations: the predicted state and voltage keep the nonlinear Eq. 6 and Eq. 8, so
only P and K move. The derivatives are those of the clamped bilinear tables (Eq. 4); the stored OCV slope stays.
"""

from functools import partial

import numpy as np

from compare_3rcd0 import RUNS_DIR as TRACES
from ekfsoc.constants import Q_REF_AH
from ekfsoc.ekf import Ekf, EkfConfig, run_ekf
from ekfsoc.experiments import OFFSET_A
from ekfsoc.loader import load_run
from fit_3rcd import grid_cell
from fit_3rcd0 import load_candidate
from run_all import CONFIG_JSON, load_traces, score_run
from s10_jacobian import covariance_change, soc_column, soc_slopes
from s11_evaluate import trace_path


# (name, process term in F, measurement term in H); the first is the incumbent.
VARIANTS = (("Incumbent", False, False), ("Process", True, False), ("Measurement", False, True), ("Both", True, True))


class JacobianEkf(Ekf):
    """The 3RC-D0 filter with the SoC column of F (Eq. 6 differentiated along SoC through every R_i and tau_i)
    and/or the R0 term of H (-I dR0/dSoC in Eq. 8) put back. With neither, it is the incumbent operation for
    operation."""

    def __init__(self, params, cfg, soc0, q_ref_ah=Q_REF_AH, *, process, measurement):
        super().__init__(params, cfg, soc0, q_ref_ah)
        self.params = params
        self.process = process
        self.measurement = measurement

    def predict(self, i_held, t_degC, dt_s):
        """Eq. 6 and Eq. 7, then the covariance change of the full F, formed at the posterior state before the step."""
        x_post, p_post = self.x, self.P
        super().predict(i_held, t_degC, dt_s)
        if self.process:
            column, diag = soc_column(self.params, self.read_r1, np.array([t_degC]), x_post[None, :],
                                      np.array([i_held]), np.array([dt_s]))
            self.P = self.P + covariance_change(np.r_[0.0, column[0]], diag[0], p_post)

    def h_soc(self, i_a, t_degC, soc):
        """The SoC entry of H; the measurement variant adds -I dR0/dSoC at the prior SoC and the row's own current."""
        value = super().h_soc(i_a, t_degC, soc)
        if self.measurement:
            t_cell = grid_cell(self.params.t_grid, np.array([t_degC]))
            dr0 = soc_slopes(self.params.r0[:, :, None], self.params.soc_grid, t_cell, np.array([soc]))[0, 0]
            value -= i_a * dr0
        return value


def replay_variant(task):
    """Score one variant on one run: every case of the stored 3RC-D0 trace again from its start and soc0, with the
    experiment-4 offset, under the S2 settings. The incumbent must equal the stored trace row by row."""
    spec, (name, process, measurement) = task
    run = load_run(spec.path)
    t, v, reference, stored = load_traces(trace_path(spec, TRACES))
    if not (np.array_equal(t, run.t) and np.array_equal(v, run.v)):
        raise RuntimeError(f"stored 3RC-D0 trace of {spec.path.name} is not from this run")
    params, cfg = load_candidate(), EkfConfig.from_json(CONFIG_JSON)
    variant = partial(JacobianEkf, process=process, measurement=measurement)
    cases = {}
    for experiment, case in stored.items():
        result = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, case["soc0"], case["start"],
                         OFFSET_A if experiment == "exp4" else 0.0, filter_class=variant)
        if name == VARIANTS[0][0] and not (np.array_equal(result["soc"], case["soc"], equal_nan=True)
                                           and np.array_equal(result["v_pred"], case["v_pred"], equal_nan=True)):
            raise RuntimeError(f"incumbent replay differs from the stored trace: {spec.path.name} {experiment}")
        cases[experiment] = case | {"soc": result["soc"], "v_pred": result["v_pred"]}
    return [row | {"variant": name} for row in score_run(spec, t, v, reference, cases)]
