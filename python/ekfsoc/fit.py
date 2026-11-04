"""RC fit of an HPPC run: R0 and the fast branches from the discharge pulses, R2, tau2 from the 1 h rest after the move.

Rules: docs/decisions.md 1.12 (2RC) and 1.21 (3RC: a middle branch R3, tau3 is fitted with R1, tau1 in fit (a),
and the bounds change; everything else is the same). Equation numbers are those of docs/model.md. HPPC levels come from
hppc.segment_hppc. Every fit runs on the data that resolves its branch (fit (b) holds the fast branch
fixed), so the two RC branches cannot swap.

Fit (a), fit_level_fast: R0, R1, tau1 of one level, from its usable discharge pulses D1 to D4.
  - R0 is not fitted. It is the median over the usable pulses of the step rule,
    R0 = (V(before) - V(r0_row)) / (I(r0_row) - I(before)), where "before" is the row before the
    pulse and r0_row the first row at 98 % of the pulse current (hppc.py). R0 is then held fixed.
  - Each pulse w gives a window: its rows plus the 40 s rest after it (0.1 s data). With the
    reference SoC (Eq. 3 on the cycler's counter) and the OCV table (Eq. 4), Eq. 2 solved for the
    RC drops gives the measured quantity
        z_w(k) = V(k) - OCV(SoC_ref(k)) + R0 * I(k)  =  c_w - V1(k) - V2(k)
  - V1 follows Eq. 1 with (R1, tau1) and V1 = 0 at the first pulse row: the rest before a pulse is
    610 s or 3600 s, far longer than tau1 (30 s at most).
  - c_w is one free constant per window. It absorbs the slow branch V2 at the start of the pulse,
    the error of the discharge-branch OCV and the small hysteresis. V2 is not modelled: its change
    over the 50 s window (a ramp during the pulse, a slow recovery after it) goes into R1 and tau1.
    For given (R1, tau1) the best c_w is the window mean, so the residual is
        e_w(k) = [z_w(k) + V1(k)] - mean_w[z_w + V1]
    and least_squares runs over (R1, tau1) alone. This is the same minimum as fitting c_w as well.
  - The OCV change inside a window comes from the OCV table at the file's nominal temperature.
  - tau1 is bounded to [0.5, 30] s. In the 3RC model, z_w(k) = c_w - V1(k) - V3(k) - V2(k) and fit (a)
    runs over (R1, tau1, R3, tau3) with tau1 in [0.5, 10] s and tau3 in [10, 50] s (FIT_BOUNDS).

Fit (b), fit_level_slow: R2, tau2 of the 1 h rest after the move that follows the level.
  - The fast branch is taken from fit (a) (both fast branches, V1 + V3, in the 3RC model, where tau2 is
    bounded to [50, 3600] s). V1 is computed with Eq. 1 over the move and the rest
    (V1 = 0 at the first move row, which follows a 610 s rest) and added back to the measurement:
        y(k) = V(k) + V1(k) + R0 * I(k)  =  A - B * exp(-(t(k) - t0) / tau2)
    The rest has I = 0, so Eq. 1 lets V2 decay from its value B at the first rest row (time t0),
    and the OCV is constant.
  - A (the asymptote) is free and absorbs the OCV error and the part of the relaxation that is slower
    than the rest. B is the slow-branch amplitude, 0 or more. tau2 is bounded to [30, 3600] s.
    Only the rows logged at 10 s are used (the step from the row before is over 1 s), so the 0.1 s
    tail of the rest does not outweigh the rest of it.
  - R2 is derived from B, tau2, the move current and the move duration. The current of the move rows
    is held over each step (Eq. 1), so for a move of constant current I_move that lasts
    T_move = t(first rest row) - t(first move row), starting with V2 = 0:
        B = R2 * (1 - exp(-T_move / tau2)) * I_move   ->   R2 = B / (I_move * (1 - exp(-T_move / tau2)))
    Assumed: V2 = 0 at the start of the move (the pulses before it moved V2 little), and I_move is
    the median current over the move rows.

A fit that does not converge, or has no pulse to use, returns None for its values and fast_ok / slow_ok = False.
"""

import math

import numpy as np
from scipy.optimize import least_squares

from ekfsoc.hppc import segment_hppc
from ekfsoc.loader import soc_ref
from ekfsoc.model import interp2, rc_step

TAU1_BOUNDS_S = (0.5, 30.0)
TAU2_BOUNDS_S = (30.0, 3600.0)
SLOW_STEP_MIN_S = 1.0                  # fit (b) uses rows at least this far from the row before them

# Per model: the tau bounds of the fast branches of fit (a), in the order of FAST_BRANCHES, and of tau2 in fit (b).
FIT_BOUNDS = {
    "2rc": {"fast": (TAU1_BOUNDS_S,), "tau2": TAU2_BOUNDS_S},           # docs/decisions.md 1.12
    "3rc": {"fast": ((0.5, 10.0), (10.0, 50.0)), "tau2": (50.0, 3600.0)},  # docs/decisions.md 1.21
}
# The fast branches of fit (a): (key of R, key of tau, start of R, start of tau). Branch 3 is the middle one.
FAST_BRANCHES = (("R1_ohm", "tau1_s", 0.01, 5.0), ("R3_ohm", "tau3_s", 0.005, 20.0))

# The fitted tables of fit_hppc_run: (Params field, key of the SoC the value belongs to, key of the value).
FITTED_TABLES = (("r0", "soc_pulses", "R0_ohm"), ("r1", "soc_pulses", "R1_ohm"), ("tau1", "soc_pulses", "tau1_s"),
                 ("r2", "soc_rest", "R2_ohm"), ("tau2", "soc_rest", "tau2_s"))
FITTED_TABLES_3RC = FITTED_TABLES + (("r3", "soc_pulses", "R3_ohm"), ("tau3", "soc_pulses", "tau3_s"))


def rc_voltage(current, dt, r, tau):
    """Voltage of one RC branch over a stretch of rows by Eq. 1, starting at 0 on the first row.

    current[k] is held over the step dt[k + 1] (dt[0] is not used), so a row's own current enters
    the voltage from the next row on.
    """
    current = current.tolist()
    dt = dt.tolist()
    voltage = np.zeros(len(current))
    v = 0.0
    for k in range(1, len(current)):
        v = rc_step(v, r, tau, current[k - 1], dt[k])
        voltage[k] = v
    return voltage


def solve(residuals, start, lower, upper):
    """Bounded least squares from one start; returns the result, or None if it did not converge.

    On the six HPPC files, three different starts per fit end at the same minimum, so one start is used.
    """
    result = least_squares(residuals, start, bounds=(lower, upper), x_scale="jac")
    if not (result.success and np.all(np.isfinite(result.x))):
        return None
    return result


def rmse_mv(result):
    """RMSE in mV of a least_squares result (its cost is half the sum of squares of the residuals)."""
    return 1000.0 * math.sqrt(2.0 * result.cost / len(result.fun))


def step_r0(run, pulse):
    """R0 of one pulse by the step rule: voltage drop over the current rise from the row before to r0_row."""
    before = pulse.rows.start - 1
    row = pulse.r0_row
    return (run.v[before] - run.v[row]) / (run.i[row] - run.i[before])


def ocv_at(ocv_table, temp_degc, soc):
    """OCV in V at one temperature and SoC (Eq. 4)."""
    return interp2(ocv_table.ocv, ocv_table.t_grid, ocv_table.soc_grid, temp_degc, soc)


def pulse_windows(run, pulses, r0, ocv_table):
    """The windows of fit (a), one per pulse: (current, dt, z) over the pulse and the rest after it.

    z = V - OCV(SoC_ref) + R0 * I, the RC drops with a free constant per window (module docstring). The S7 fit
    of R1 over current uses the same windows (docs/decisions.md 1.28).
    """
    soc = soc_ref(run)
    return [window(run, soc, slice(pulse.rows.start, pulse.rest_rows.stop), r0, ocv_table) for pulse in pulses]


def window(run, soc, rows, r0, ocv_table):
    """(current, dt, z) of one window of fit (a) over the rows given, with soc the run's reference SoC."""
    temp_degc = run.meta["nominal_temp_degc"]
    ocv = np.array([ocv_at(ocv_table, temp_degc, s) for s in soc[rows]])
    z = run.v[rows] - ocv + r0 * run.i[rows]
    return run.i[rows], run.dt[rows], z


def fit_level_fast(run, level, ocv_table, tau_bounds=FIT_BOUNDS["2rc"]["fast"]):
    """Fit (a) for one level: returns {R0_ohm, R1_ohm, tau1_s(, R3_ohm, tau3_s), rmse_fast_mV, n_pulses_used, fast_ok}.

    tau_bounds holds one (lower, upper) pair per fast branch: one for the 2RC model, two for the 3RC model.
    """
    pulses = [pulse for pulse in level.pulses if pulse.kind == "D" and pulse.usable]
    branches = FAST_BRANCHES[:len(tau_bounds)]
    fit = {"R0_ohm": None, "R1_ohm": None, "tau1_s": None, "rmse_fast_mV": None,
           "n_pulses_used": len(pulses), "fast_ok": False}
    if len(branches) == 2:
        fit.update(R3_ohm=None, tau3_s=None)
    if not pulses:
        return fit

    r0 = float(np.median([step_r0(run, pulse) for pulse in pulses]))
    windows = pulse_windows(run, pulses, r0, ocv_table)

    def residuals(x):
        pieces = []
        for current, dt, z in windows:
            shifted = z
            for b in range(len(branches)):
                shifted = shifted + rc_voltage(current, dt, x[2 * b], x[2 * b + 1])
            pieces.append(shifted - shifted.mean())
        return np.concatenate(pieces)

    start, lower, upper = [], [], []
    for (_, _, r_start, tau_start), (tau_low, tau_high) in zip(branches, tau_bounds):
        start += [r_start, tau_start]
        lower += [0.0, tau_low]
        upper += [1.0, tau_high]
    best = solve(residuals, start, lower, upper)
    if best is None:
        return fit

    fit.update(R0_ohm=r0, rmse_fast_mV=rmse_mv(best), fast_ok=True)
    for b, (r_key, tau_key, _, _) in enumerate(branches):
        fit.update({r_key: float(best.x[2 * b]), tau_key: float(best.x[2 * b + 1])})
    return fit


def fit_level_slow(run, level, fast, ocv_table, tau2_bounds=TAU2_BOUNDS_S):
    """Fit (b) for one level: returns {R2_ohm, tau2_s, rmse_slow_mV, slow_ok}.

    `fast` is the dict of fit_level_fast; if its fit failed, this one fails too. Every fast branch it
    holds (R1, tau1 and, in the 3RC model, R3, tau3) is added back. ocv_table gives the starting value
    of the asymptote. Raises ValueError for a level with no rest after its move.
    """
    move, rest = level.move, level.rest_after_move
    if rest is None:
        raise ValueError(f"level {level.k} has no rest after its move")
    fit = {"R2_ohm": None, "tau2_s": None, "rmse_slow_mV": None, "slow_ok": False}
    if not fast["fast_ok"]:
        return fit

    # Fast branches over the move and the rest, added back to the measurement of the rest.
    span = slice(move.start, rest.stop)
    v_fast = 0.0
    for r_key, tau_key, _, _ in FAST_BRANCHES:
        if r_key in fast:
            v_branch = rc_voltage(run.i[span], run.dt[span], fast[r_key], fast[tau_key])
            v_fast = v_fast + v_branch[rest.start - move.start:]
    keep = run.dt[rest] > SLOW_STEP_MIN_S
    seconds = (run.t[rest] - run.t[rest.start])[keep]
    y = (run.v[rest] + v_fast + fast["R0_ohm"] * run.i[rest])[keep]

    def residuals(x):
        asymptote, amplitude, tau2 = x
        return y - (asymptote - amplitude * np.exp(-seconds / tau2))

    asymptote_start = ocv_at(ocv_table, run.meta["nominal_temp_degc"], level.soc_after_move)
    best = solve(residuals, (asymptote_start, 0.01, 600.0),
                 (-np.inf, 0.0, tau2_bounds[0]), (np.inf, 1.0, tau2_bounds[1]))
    if best is None:
        return fit

    _, amplitude, tau2 = best.x
    i_move = float(np.median(run.i[move]))
    t_move = run.t[rest.start] - run.t[move.start]
    r2 = amplitude / (i_move * (1.0 - math.exp(-t_move / tau2)))
    fit.update(R2_ohm=float(r2), tau2_s=float(tau2), rmse_slow_mV=rmse_mv(best), slow_ok=True)
    return fit


def fit_hppc_run(run, ocv_table, model="2rc"):
    """Fit every level of an HPPC run with the bounds of `model` ("2rc" or "3rc"); one dict per level, in file order.

    Keys: T_degC, level, soc_pulses, R0_ohm, R1_ohm, tau1_s, rmse_fast_mV, n_pulses_used, fast_ok,
    soc_rest, R2_ohm, tau2_s, rmse_slow_mV, slow_ok. R0, R1 and tau1 belong at soc_pulses; R2 and tau2 at
    soc_rest, the SoC where the move ended. The last level has no 1 h rest: soc_rest, R2, tau2,
    rmse_slow_mV and slow_ok are None there. The 3RC model adds R3_ohm and tau3_s, which belong at soc_pulses.
    """
    bounds = FIT_BOUNDS[model]
    rows = []
    for level in segment_hppc(run):
        fast = fit_level_fast(run, level, ocv_table, bounds["fast"])
        slow = {"soc_rest": None, "R2_ohm": None, "tau2_s": None, "rmse_slow_mV": None, "slow_ok": None}
        if level.rest_after_move is not None:
            slow = {"soc_rest": level.soc_after_move, **fit_level_slow(run, level, fast, ocv_table, bounds["tau2"])}
        rows.append({"T_degC": run.meta["nominal_temp_degc"], "level": level.k, "soc_pulses": level.soc_pulses,
                     **fast, **slow})
    return rows
