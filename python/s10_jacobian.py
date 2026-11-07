"""Measure omitted Jacobian terms without applying them to the estimator."""

import numpy as np

from ekfsoc.ekf import Ekf
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


def process_partials(dt, held, branch_v, resistance, tau, dr, dtau):
    """SoC column from differentiating Eq. 6 at a fixed branch state."""
    decay = np.exp(-dt / tau)
    da = decay * dt / tau**2 * dtau
    return da * (branch_v - resistance * held) + (1 - decay) * held * dr


def replay_measurements(run, reference, params, cfg, expected_soc, expected_v):
    """Replay experiment 1 and evaluate local derivatives at its recorded states."""
    ekf = Ekf(params, cfg, float(reference[0]))
    size = len(ekf.x)
    posterior = np.empty((len(run.t), size))
    prior_soc = np.empty(len(run.t))
    covariance = np.empty((len(run.t), size, size))
    prior_covariance = np.empty_like(covariance)
    samples = zip(run.i.tolist(), run.v.tolist(), run.temp.tolist(), run.dt.tolist())
    for k, (current, volts, temp, dt) in enumerate(samples):
        posterior[k], covariance[k] = ekf.x, ekf.P
        ekf.predict(ekf.i_held, temp, dt)
        prior_soc[k], prior_covariance[k] = ekf.x[0], ekf.P
        ekf.update(current, volts, temp)
        ekf.i_held = current
        if ekf.x[0] != expected_soc[k] or ekf.y_hat != expected_v[k]:
            raise RuntimeError(f"Jacobian replay differs from experiment 1 at row {k}")

    held = np.r_[0.0, run.i[:-1]]
    t_cell = grid_cell(params.t_grid, run.temp)
    s_cell = grid_cell(params.soc_grid, posterior[:, 0])
    r_names, tau_names = zip(*params.branches)
    resistance = read_tables(np.stack([getattr(params, name) for name in r_names], axis=-1), t_cell, s_cell)
    # Only the current-dependent incumbent is replayed. Read its R1 exactly as the EKF does.
    resistance[:, 0] = [ekf.read_r1(t, s, i) for t, s, i in zip(run.temp, posterior[:, 0], held)]
    tau_tables = np.stack([getattr(params, name) for name in tau_names], axis=-1)
    tau = read_tables(tau_tables, t_cell, s_cell)
    dr2 = soc_slopes(params.r2[:, :, None], params.soc_grid, t_cell, posterior[:, 0])
    dr = np.column_stack((r1_slopes(params, t_cell, posterior[:, 0], held), dr2))
    dtau = soc_slopes(tau_tables, params.soc_grid, t_cell, posterior[:, 0])
    column = process_partials(run.dt[:, None], held[:, None], posterior[:, 1:], resistance, tau, dr, dtau)

    # Difference F_full P F_full^T - F_legacy P F_legacy^T. Both share the same Q.
    diag = np.column_stack((np.ones(len(held)), np.exp(-run.dt[:, None] / tau)))
    row = diag * covariance[:, 0, :]
    column_cov = diag * covariance[:, :, 0]
    omitted = np.column_stack((np.zeros(len(held)), column))
    delta_cov = omitted[:, :, None] * row[:, None, :]
    delta_cov += column_cov[:, :, None] * omitted[:, None, :]
    delta_cov += omitted[:, :, None] * omitted[:, None, :] * covariance[:, 0, 0][:, None, None]
    relative_cov = np.linalg.norm(delta_cov, axis=(1, 2)) / np.linalg.norm(prior_covariance, axis=(1, 2))
    branch_var = np.diagonal(prior_covariance, axis1=1, axis2=2)[:, 1:]
    normalized_cross = np.abs(delta_cov[:, 0, 1:]) / np.sqrt(prior_covariance[:, :1, 0] * branch_var)

    dr0 = soc_slopes(params.r0[:, :, None], params.soc_grid, t_cell, prior_soc)[:, 0]
    slope = read_tables(params.docv[:, :, None], t_cell, grid_cell(params.soc_grid, prior_soc))[:, 0]
    omitted_h = -run.i * dr0
    return omitted_h, slope, column, relative_cov, normalized_cross
