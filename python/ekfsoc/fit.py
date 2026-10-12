"""2RC fit of an HPPC run: R0, R1, tau1 from the discharge pulses, R2, tau2 from the 1 h rest after the move.

Rules: docs/decisions.md 1.12. Equation numbers are those of docs/model.md. HPPC levels come from
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
  - tau1 is bounded to [0.5, 30] s.

Fit (b), fit_level_slow: R2, tau2 of the 1 h rest after the move that follows the level.
  - The fast branch is taken from fit (a). V1 is computed with Eq. 1 over the move and the rest
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

A fit that does not converge, or has no pulse to use, returns None for its values and ok = False.
"""

import math

import numpy as np
from scipy.optimize import least_squares

from ekfsoc.hppc import segment_hppc
from ekfsoc.loader import soc_ref
from ekfsoc.model import interp2

TAU1_BOUNDS_S = (0.5, 30.0)
TAU2_BOUNDS_S = (30.0, 3600.0)
SLOW_STEP_MIN_S = 1.0                  # fit (b) uses rows at least this far from the row before them


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
        a = math.exp(-dt[k] / tau)
        v = a * v + r * (1.0 - a) * current[k - 1]
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


def rmse_mv(result, n_rows):
    """RMSE in mV of a least_squares result over n_rows residuals (cost = half the sum of squares)."""
    return 1000.0 * math.sqrt(2.0 * result.cost / n_rows)


def step_r0(run, pulse):
    """R0 of one pulse by the step rule: voltage drop over the current rise from the row before to r0_row."""
    before = pulse.rows.start - 1
    row = pulse.r0_row
    return (run.v[before] - run.v[row]) / (run.i[row] - run.i[before])


def ocv_at(ocv_table, temp_degc, soc):
    """OCV in V at one temperature and SoC (Eq. 4)."""
    return interp2(ocv_table.ocv, ocv_table.t_grid, ocv_table.soc_grid, temp_degc, soc)


def fit_level_fast(run, level, ocv_table):
    """Fit (a) for one level: returns {R0_ohm, R1_ohm, tau1_s, rmse_mV, n_pulses_used, ok}."""
    pulses = [pulse for pulse in level.pulses if pulse.kind == "D" and pulse.usable]
    failed = {"R0_ohm": None, "R1_ohm": None, "tau1_s": None, "rmse_mV": None,
              "n_pulses_used": len(pulses), "ok": False}
    if not pulses:
        return failed

    r0 = float(np.median([step_r0(run, pulse) for pulse in pulses]))
    temp_degc = run.meta["nominal_temp_degc"]
    soc = soc_ref(run)

    windows = []
    for pulse in pulses:
        rows = slice(pulse.rows.start, pulse.rest_rows.stop)
        ocv = np.array([ocv_at(ocv_table, temp_degc, s) for s in soc[rows]])
        z = run.v[rows] - ocv + r0 * run.i[rows]
        windows.append((run.i[rows], run.dt[rows], z))

    def residuals(x):
        r1, tau1 = x
        pieces = []
        for current, dt, z in windows:
            shifted = z + rc_voltage(current, dt, r1, tau1)
            pieces.append(shifted - shifted.mean())
        return np.concatenate(pieces)

    best = solve(residuals, (0.01, 5.0), (0.0, TAU1_BOUNDS_S[0]), (1.0, TAU1_BOUNDS_S[1]))
    if best is None:
        return failed

    n_rows = sum(len(z) for _, _, z in windows)
    return {"R0_ohm": r0, "R1_ohm": float(best.x[0]), "tau1_s": float(best.x[1]),
            "rmse_mV": rmse_mv(best, n_rows), "n_pulses_used": len(pulses), "ok": True}


def fit_level_slow(run, level, fast_params, ocv_table):
    """Fit (b) for one level: returns {R2_ohm, tau2_s, rmse_mV, ok}.

    fast_params is the dict of fit_level_fast; if its fit failed, this one fails too. ocv_table gives
    the starting value of the asymptote. Raises ValueError for a level with no rest after its move.
    """
    if level.rest_after_move is None:
        raise ValueError(f"level {level.k} has no rest after its move")
    failed = {"R2_ohm": None, "tau2_s": None, "rmse_mV": None, "ok": False}
    if not fast_params["ok"]:
        return failed

    # Fast branch over the move and the rest, added back to the measurement.
    span = slice(level.move.start, level.rest_after_move.stop)
    v1 = rc_voltage(run.i[span], run.dt[span], fast_params["R1_ohm"], fast_params["tau1_s"])
    rest = slice(level.rest_after_move.start - span.start, level.rest_after_move.stop - span.start)
    y = run.v[span] + v1 + fast_params["R0_ohm"] * run.i[span]

    t0 = run.t[level.rest_after_move.start]
    keep = run.dt[span][rest] > SLOW_STEP_MIN_S
    seconds = run.t[span][rest][keep] - t0
    y = y[rest][keep]

    def residuals(x):
        asymptote, amplitude, tau2 = x
        return y - (asymptote - amplitude * np.exp(-seconds / tau2))

    asymptote_start = ocv_at(ocv_table, run.meta["nominal_temp_degc"], level.soc_after_move)
    best = solve(residuals, (asymptote_start, 0.01, 600.0),
                 (-np.inf, 0.0, TAU2_BOUNDS_S[0]), (np.inf, 1.0, TAU2_BOUNDS_S[1]))
    if best is None:
        return failed

    _, amplitude, tau2 = best.x
    i_move = float(np.median(run.i[level.move]))
    t_move = run.t[level.rest_after_move.start] - run.t[level.move.start]
    r2 = amplitude / (i_move * (1.0 - math.exp(-t_move / tau2)))
    return {"R2_ohm": float(r2), "tau2_s": float(tau2), "rmse_mV": rmse_mv(best, len(y)), "ok": True}


def fit_hppc_run(run, ocv_table):
    """Fit every level of an HPPC run; returns one dict per level, in file order.

    Keys: T_degC, level, soc_pulses, R0_ohm, R1_ohm, tau1_s, rmse_fast_mV, n_pulses_used, fast_ok,
    soc_rest, R2_ohm, tau2_s, rmse_slow_mV, slow_ok. R0, R1 and tau1 belong at soc_pulses; R2 and tau2 at
    soc_rest, the SoC where the move ended. The last level has no 1 h rest: soc_rest, R2, tau2,
    rmse_slow_mV and slow_ok are None there.
    """
    rows = []
    for level in segment_hppc(run):
        fast = fit_level_fast(run, level, ocv_table)
        row = {"T_degC": run.meta["nominal_temp_degc"], "level": level.k, "soc_pulses": level.soc_pulses,
               "R0_ohm": fast["R0_ohm"], "R1_ohm": fast["R1_ohm"], "tau1_s": fast["tau1_s"],
               "rmse_fast_mV": fast["rmse_mV"], "n_pulses_used": fast["n_pulses_used"], "fast_ok": fast["ok"],
               "soc_rest": None, "R2_ohm": None, "tau2_s": None, "rmse_slow_mV": None, "slow_ok": None}
        if level.rest_after_move is not None:
            slow = fit_level_slow(run, level, fast, ocv_table)
            row.update({"soc_rest": level.soc_after_move, "R2_ohm": slow["R2_ohm"], "tau2_s": slow["tau2_s"],
                        "rmse_slow_mV": slow["rmse_mV"], "slow_ok": slow["ok"]})
        rows.append(row)
    return rows
