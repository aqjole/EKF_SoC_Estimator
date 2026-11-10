"""Measure omitted Jacobian terms without applying them to the estimator (decisions 1.44, 1.47, 1.56).

Any branch count; R1 by the model's reader (Eq. 4, or Eq. 4b over the held current); a case starts at any row.
"""

import numpy as np

from ekfsoc.ekf import Ekf
from ekfsoc.metrics import PP
from fit_3rcd import grid_cell, read_tables


SLOPE_FLOOR = 0.05  # V per unit SoC (decision 1.44)


def soc_slopes(table, soc_grid, temp_cell, soc):
    """SoC partial derivative in Eq. 4's active cell, zero outside the SoC axis."""
    j, wt = temp_cell
    m, _ = grid_cell(soc_grid, soc)
    slopes = ((1 - wt) * (table[j, m + 1] - table[j, m]) + wt * (table[j + 1, m + 1] - table[j + 1, m]))
    slopes /= (soc_grid[m + 1] - soc_grid[m])[:, None]
    slopes[(soc < min(soc_grid)) | (soc > max(soc_grid))] = 0
    return slopes


def r1_slopes(params, temp_cell, soc, held):
    """Differentiate Eq. 4b along SoC while holding current magnitude fixed."""
    slopes = soc_slopes(params.r1_current, params.soc_grid, temp_cell, soc)
    index, weight = grid_cell(params.i_grid, np.abs(held))
    rows = np.arange(len(soc))
    return ((1 - weight[:, 0]) * slopes[rows, index] + weight[:, 0] * slopes[rows, index + 1])[:, None]


def resistance_slopes(params, temp_cell, soc, held):
    """dR_i/dSoC of every branch, in branch order: Eq. 4 differentiated, R1 by Eq. 4b when the model reads it over
    current. The regen readers of S8 switch tables by the sign of the current and are not differentiated."""
    if params.r1_charge is not None or params.r1_current_discharge_only:
        raise ValueError("only the Eq. 4 and Eq. 4b readers of R1 are differentiated")
    names = [r_name for r_name, _ in params.branches]
    if params.r1_current is None:
        return soc_slopes(np.stack([getattr(params, name) for name in names], axis=-1), params.soc_grid, temp_cell, soc)
    rest = soc_slopes(np.stack([getattr(params, name) for name in names[1:]], axis=-1), params.soc_grid, temp_cell, soc)
    return np.column_stack((r1_slopes(params, temp_cell, soc, held), rest))


def process_partials(dt, held, branch_v, resistance, tau, dr, dtau):
    """SoC column from differentiating Eq. 6 at a fixed branch state."""
    decay = np.exp(-dt / tau)
    da = decay * dt / tau**2 * dtau
    return da * (branch_v - resistance * held) + (1 - decay) * held * dr


def soc_column(params, read_r1, temp, posterior, held, dt):
    """Per row: the branch rows of F's SoC column that Eq. 7 leaves out, and the diagonal of the F it uses.

    R_i and tau_i are read at the posterior SoC and the row's temperature, as predict reads them; R1 by read_r1
    at the held current.
    """
    soc = posterior[:, 0]
    t_cell = grid_cell(params.t_grid, temp)
    s_cell = grid_cell(params.soc_grid, soc)
    r_names, tau_names = zip(*params.branches)
    resistance = read_tables(np.stack([getattr(params, name) for name in r_names], axis=-1), t_cell, s_cell)
    resistance[:, 0] = [read_r1(t, s, i) for t, s, i in zip(temp, soc, held)]
    tau_tables = np.stack([getattr(params, name) for name in tau_names], axis=-1)
    tau = read_tables(tau_tables, t_cell, s_cell)
    dr = resistance_slopes(params, t_cell, soc, held)
    dtau = soc_slopes(tau_tables, params.soc_grid, t_cell, soc)
    column = process_partials(dt[:, None], held[:, None], posterior[:, 1:], resistance, tau, dr, dtau)
    diag = np.column_stack((np.ones(len(held)), np.exp(-dt[:, None] / tau)))
    return column, diag


def covariance_change(omitted, diag, covariance):
    """F_full P F_full^T - F P F^T, where F_full is diag(diag) plus `omitted` as its SoC column (Eq. 7).

    Works on one row or on a stack of rows (leading axis).
    """
    row = diag * covariance[..., 0, :]
    column_cov = diag * covariance[..., :, 0]
    change = omitted[..., :, None] * row[..., None, :]
    change += column_cov[..., :, None] * omitted[..., None, :]
    change += omitted[..., :, None] * omitted[..., None, :] * covariance[..., 0, 0][..., None, None]
    return change


def gains(covariance, h, r):
    """Kalman gain of Eq. 9 per row, for a stack of prior covariances and measurement rows."""
    p_ht = np.einsum("kij,kj->ki", covariance, h)
    return p_ht / (np.einsum("ki,ki->k", h, p_ht) + r)[:, None]


def replay_case(run, params, cfg, soc0, start, expected_soc, expected_v):
    """Replay one case from row `start` and evaluate local derivatives at its recorded states.

    Row `start` gets dt = 0, as in run_ekf. Every row must equal the stored trace (expected_soc, expected_v).
    Returns per-row arrays over rows start onward:
      h                  omitted measurement term -I dR0/dSoC (V per unit SoC)
      slope              stored OCV slope at the prior SoC
      column             omitted SoC column of F, one column per branch (V per unit SoC)
      covariance_ratio   Frobenius norm of the one-step prior covariance change over that of the prior
      cross_change       SoC-to-branch prior covariance change over the legacy standard deviations, per branch
      correction_pp      |(K_full - K_legacy)_SoC| times |innovation|, in pp
    """
    ekf = Ekf(params, cfg, soc0)
    rows = len(run.t) - start
    size = len(ekf.x)
    posterior = np.empty((rows, size))
    prior_soc = np.empty(rows)
    covariance = np.empty((rows, size, size))
    prior_covariance = np.empty_like(covariance)
    current, temp, volts = run.i[start:], run.temp[start:], run.v[start:]
    dt = run.dt[start:].copy()
    dt[0] = 0.0
    for k, (i_k, v_k, t_k, dt_k) in enumerate(zip(current.tolist(), volts.tolist(), temp.tolist(), dt.tolist())):
        posterior[k], covariance[k] = ekf.x, ekf.P
        ekf.predict(ekf.i_held, t_k, dt_k)
        prior_soc[k], prior_covariance[k] = ekf.x[0], ekf.P
        ekf.update(i_k, v_k, t_k)
        ekf.i_held = i_k
        if ekf.x[0] != expected_soc[start + k] or ekf.y_hat != expected_v[start + k]:
            raise RuntimeError(f"Jacobian replay differs from the stored trace at row {start + k}")

    held = np.r_[0.0, current[:-1]]
    column, diag = soc_column(params, ekf.read_r1, temp, posterior, held, dt)
    omitted = np.column_stack((np.zeros(rows), column))
    delta_cov = covariance_change(omitted, diag, covariance)
    relative_cov = np.linalg.norm(delta_cov, axis=(1, 2)) / np.linalg.norm(prior_covariance, axis=(1, 2))
    branch_var = np.diagonal(prior_covariance, axis1=1, axis2=2)[:, 1:]
    normalized_cross = np.abs(delta_cov[:, 0, 1:]) / np.sqrt(prior_covariance[:, :1, 0] * branch_var)

    t_cell = grid_cell(params.t_grid, temp)
    dr0 = soc_slopes(params.r0[:, :, None], params.soc_grid, t_cell, prior_soc)[:, 0]
    slope = read_tables(params.docv[:, :, None], t_cell, grid_cell(params.soc_grid, prior_soc))[:, 0]
    omitted_h = -current * dr0

    # Eq. 9 twice: the filter's prior and H, and the full prior (formed at the previous posterior with the held
    # current) with the full H (at the prior SoC with the row's own current).
    legacy_h = np.column_stack((slope, -np.ones((rows, size - 1))))
    full_h = legacy_h.copy()
    full_h[:, 0] += omitted_h
    full_gain = gains(prior_covariance + delta_cov, full_h, cfg.r)
    gain_change = full_gain[:, 0] - gains(prior_covariance, legacy_h, cfg.r)[:, 0]
    innovation = volts - expected_v[start:]
    return {"h": omitted_h, "slope": slope, "column": column, "covariance_ratio": relative_cov,
            "cross_change": normalized_cross, "correction_pp": PP * np.abs(gain_change * innovation)}


def summarize_jacobian(measurements, mask):
    """Support, |H| percentiles, the measurement ratio, |F| 95th percentiles per branch and the covariance changes."""
    h, slope, process, covariance, cross = (measurements[name][mask] for name in
                                            ("h", "slope", "column", "covariance_ratio", "cross_change"))
    safe = np.abs(slope) >= SLOPE_FLOOR
    ratio = np.abs(h[safe] / slope[safe])
    return [len(h), len(ratio), *np.percentile(np.abs(h), [50, 95, 100]),
            np.percentile(ratio, 95) if len(ratio) else np.nan,
            np.max(np.abs(h[~safe])) if (~safe).any() else np.nan,
            *np.percentile(np.abs(process), 95, axis=0), np.percentile(covariance, 95),
            np.percentile(cross.max(axis=1), 95)]
