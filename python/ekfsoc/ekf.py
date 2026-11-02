"""The extended Kalman filter of the RC model: state x = [SoC, V1, ..., Vn], input I, measurement V.

n is the branch count of the parameters: 2 for the 2RC model of v1.0, 3 for the 3RC model of S6
(docs/decisions.md 1.21, 1.22). Branches are taken in the order 1, 2, 3, so a 2RC filter does the
v1.0 arithmetic operation for operation.

Equation numbers ("Eq. n") are those of docs/model.md. One step is predict() (Eq. 6, 7) then update()
(Eq. 8 to 11); the C port repeats both function for function, with the same operation order. Eq. 3 is
the SoC row of Eq. 6 and the table lookups are Eq. 4 (model.interp2). Every (1 + n) x (1 + n) product
is its own named step. limit_soc() (the projection of Eq. 10) needs the posterior P of Eq. 11, so update() forms
Eq. 11 first.
"""

import json
import math
from dataclasses import asdict, dataclass

import numpy as np

from ekfsoc.constants import Q_REF_AH
from ekfsoc.model import interp2, interp_current


@dataclass
class EkfConfig:
    """The noise settings of the filter, the same for every experiment and temperature (the spec, S2).

    q_soc       process noise of the SoC state in 1/s (Q[0][0] = q_soc * dt)
    q_v         process noise of each branch voltage in V^2/s (Q[i][i] = q_v * dt for i >= 1)
    r           measurement noise variance in V^2
    p0_soc_std  initial standard deviation of the SoC state (0.2 = 20 pp)
    p0_v_std    initial standard deviation of each branch voltage in V (0.05 = 50 mV)
    """

    q_soc: float
    q_v: float
    r: float
    p0_soc_std: float = 0.2
    p0_v_std: float = 0.05

    @classmethod
    def from_json(cls, path):
        with open(path) as handle:
            return cls(**json.load(handle))

    def to_json(self, path):
        with open(path, "w") as handle:
            json.dump(asdict(self), handle, indent=2)
            handle.write("\n")


class Ekf:
    """The filter state x (numpy, shape (1 + n,)) and covariance P (numpy, shape (1 + n, 1 + n)).

    n is the number of RC branches of params (Params.branches). soc0 is the initial SoC and every
    V_i = 0. The filter is never told whether soc0 is right: P0 is the same diagonal for every run
    (docs/model.md, Symbols).
    q_ref_ah is the capacity the filter believes, in Ah; only the capacity sensitivity of S5 changes it
    (docs/decisions.md 1.18).
    After step() or update(), y_hat is the voltage predicted before the measurement was used (Eq. 8).
    """

    def __init__(self, params, cfg, soc0, q_ref_ah=Q_REF_AH):
        self.cfg = cfg
        self.q_ref_ah = q_ref_ah
        # Plain lists make the lookups in the loop fast; interp2 works on them unchanged.
        self.t_grid = params.t_grid.tolist()
        self.soc_grid = params.soc_grid.tolist()
        self.tables = {name: getattr(params, name).tolist() for name in params.table_names}
        self.branches = params.branches
        self.r1_slices = params.r1_slices()  # the 2RC-I model (S7) reads R1 over current, None otherwise
        self.i_grid = None if self.r1_slices is None else params.i_grid.tolist()
        n_rc = len(self.branches)
        self.x = np.array([soc0] + [0.0] * n_rc)
        self.P = np.diag([cfg.p0_soc_std**2] + [cfg.p0_v_std**2] * n_rc)
        self.i_held = 0.0  # the previous sample's current, held over the next step (docs/model.md C11)
        self.y_hat = math.nan

    def lookup(self, name, t_degC, soc):
        """Read table `name` at (t_degC, soc) with the clamped bilinear rule (Eq. 4)."""
        return interp2(self.tables[name], self.t_grid, self.soc_grid, t_degC, soc)

    def predict(self, i_held, t_degC, dt_s):
        """Move x and P over a step of dt_s with i_held held over it (Eq. 6, Eq. 7).

        Each branch's R_i, tau_i are read at the previous posterior SoC and the measured temperature; in the
        2RC-I model R1 is read at |i_held| as well (Eq. 4b).
        dt_s = 0 leaves x and P unchanged: F is the identity and B and Q are zero.
        """
        soc = float(self.x[0])
        r = [self.lookup(r_name, t_degC, soc) for r_name, _ in self.branches]
        tau = [self.lookup(tau_name, t_degC, soc) for _, tau_name in self.branches]
        if self.r1_slices is not None:
            r[0] = interp_current(self.r1_slices, self.t_grid, self.soc_grid, self.i_grid, t_degC, soc, i_held)

        a = [math.exp(-dt_s / tau_i) for tau_i in tau]
        F = np.diag([1.0] + a)
        B = np.array([-dt_s / (3600.0 * self.q_ref_ah)] + [r_i * (1.0 - a_i) for r_i, a_i in zip(r, a)])
        Q = np.diag([self.cfg.q_soc] + [self.cfg.q_v] * len(a)) * dt_s

        self.x = F @ self.x + B * i_held  # Eq. 6
        F_P = F @ self.P
        self.P = F_P @ F.T + Q  # Eq. 7

    def limit_soc(self, x_post, P_post):
        """Return x_post with its SoC limited to [0, 1] (Eq. 10, docs/decisions.md 1.16); P_post is not changed.

        A SoC inside [0, 1] is left alone. Otherwise the whole state moves onto the nearer bound along
        the posterior covariance, x_c = x - P[:, 0] * (SoC - bound) / P[0][0], so the branch voltages move
        with SoC by their correlation with it. Cutting SoC alone would keep the V2 part of the innovation.
        """
        soc_bound = min(max(x_post[0], 0.0), 1.0)
        if x_post[0] == soc_bound:
            return x_post
        shift = P_post[:, 0] * (x_post[0] - soc_bound) / P_post[0, 0]
        x_limited = x_post - shift
        x_limited[0] = soc_bound  # exactly on the bound, whatever the rounding of the line above
        return x_limited

    def update(self, i_a, v_v, t_degC):
        """Correct x and P with the measured voltage v_v taken at current i_a (Eq. 8 to Eq. 11).

        OCV, dOCV/dSoC and R0 are read at the prior SoC and the measured temperature.
        """
        soc_prior, *v_prior = self.x.tolist()
        ocv = self.lookup("ocv", t_degC, soc_prior)
        docv = self.lookup("docv", t_degC, soc_prior)
        r0 = self.lookup("r0", t_degC, soc_prior)

        v_terminal = ocv
        for v_i in v_prior:
            v_terminal -= v_i
        y_hat = v_terminal - r0 * i_a  # Eq. 8
        H = np.array([docv] + [-1.0] * len(v_prior))  # Eq. 8, dR0/dSoC left out

        P_Ht = self.P @ H
        S = H @ P_Ht + self.cfg.r  # Eq. 9
        K = P_Ht / S  # Eq. 9

        innovation = v_v - y_hat
        x_post = self.x + K * innovation  # Eq. 10

        I_KH = np.eye(len(H)) - np.outer(K, H)
        I_KH_P = I_KH @ self.P
        K_R_Kt = self.cfg.r * np.outer(K, K)
        P_post = I_KH_P @ I_KH.T + K_R_Kt  # Eq. 11

        x_post = self.limit_soc(x_post, P_post)  # Eq. 10, the SoC limit

        self.x = x_post
        self.P = P_post
        self.y_hat = y_hat

    def step(self, i_a, v_v, t_degC, dt_s):
        """Process one sample: predict over dt_s with the previous sample's current, then update; return the SoC.

        i_a is the sample's own current. It enters the update now and is held over the next step.
        """
        self.predict(self.i_held, t_degC, dt_s)
        self.update(i_a, v_v, t_degC)
        self.i_held = i_a
        return float(self.x[0])


def run_ekf(params, cfg, i, v, temp, dt, soc0, start=0, current_offset=0.0, q_ref_ah=Q_REF_AH):
    """Run the filter over rows start .. len(i)-1 of a run and return the per-row results as a dict.

    i, v, temp, dt are float64 arrays like those of a loader Run (A, V, degC, s; dt[k] = t[k] - t[k-1]);
    soc0 is the initial SoC. Every V_i = 0 at row `start`, whose dt is taken as 0: that row gets an
    update and no predict. current_offset (A) is added to every current the filter sees. q_ref_ah is
    the capacity of the SoC row of Eq. 6 (Ekf).
    The dict holds, one entry per row and NaN before `start`:
      soc      posterior SoC (fraction)
      v_pred   terminal voltage predicted before the update (Eq. 8), in V
      p_soc    SoC variance P[0][0] after the update
    """
    n = len(i)
    currents = (i + current_offset).tolist()
    voltages, temps, dts = v.tolist(), temp.tolist(), dt.tolist()

    soc = np.full(n, np.nan)
    v_pred = np.full(n, np.nan)
    p_soc = np.full(n, np.nan)

    ekf = Ekf(params, cfg, soc0, q_ref_ah)
    for k in range(start, n):
        step_dt = 0.0 if k == start else dts[k]
        soc[k] = ekf.step(currents[k], voltages[k], temps[k], step_dt)
        v_pred[k] = ekf.y_hat
        p_soc[k] = ekf.P[0, 0]

    return {"soc": soc, "v_pred": v_pred, "p_soc": p_soc}
