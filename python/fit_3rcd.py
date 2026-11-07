"""Fit the two 3RC-D tables on the Mix runs (docs/decisions.md 1.40 and 1.41)."""

import csv
from dataclasses import dataclass, replace

import matplotlib.pyplot as plt
import numpy as np
from scipy.linalg import solve_banded
from scipy.optimize import lsq_linear

from compare_r1i import load_params_ri
from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import rms, window_mask
from ekfsoc.model import Params, simulate_open_loop
from ekfsoc.r1_current import read_r1_current
from export_params import md_table, write_text
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC
from fit_r1_current import R1_CURRENT_CSV


RESULTS = REPO_DIR / "results"
PARAMS_3RCD_CSV = RESULTS / "params_3rcd.csv"
NODES_CSV = RESULTS / "fit_nodes_3rcd.csv"
FIT_MD = RESULTS / "model_fit_3rcd.md"
PLOTS = RESULTS / "plots" / "s9"
SOC_NODES = np.array([0.0, 0.1, 0.4, 0.7, 1.0])
TAU3 = 45.0
MIN_SUPPORT = 1000
DISCLOSURE = (
    "The standard cycles were held out of the final parameter fit. Prior diagnostics and the low-SoC boundary "
    "choice used these runs, and they share segments with the Mix runs (docs/decisions.md 1.40 and 1.41)."
)


def load_params_3rcd():
    return read_r1_current(Params.from_csv(PARAMS_3RCD_CSV), R1_CURRENT_CSV)


def drive_split(specs):
    """Separate the 63 runs of 1.40 before any calibration data are loaded."""
    mix = [spec for spec in specs if spec.cycle_name.startswith("Mix ")]
    standard = [spec for spec in specs if spec.cycle_name in ("UDDS", "HWFET", "LA92", "US06")]
    if (len(mix), len(standard), len(specs)) != (40, 23, 63):
        raise ValueError("S9 requires the 40 Mix and 23 standard-cycle runs of decisions 1.40")
    return mix, standard


def basis_tables(params):
    """One unit hat per fitted node, in temperature-major order (1.41)."""
    hats = np.column_stack([np.interp(params.soc_grid, SOC_NODES, node)
                            for node in np.eye(len(SOC_NODES))[1:]])
    return np.einsum("tj,sm->tsjm", np.eye(len(params.t_grid)), hats).reshape(
        len(params.t_grid), len(params.soc_grid), -1
    )


def grid_cell(axis, values):
    """Vector form of Eq. 4's clamped cell search and fractional weight."""
    direction = 1 if axis[-1] > axis[0] else -1
    clamped = np.clip(values, min(axis[0], axis[-1]), max(axis[0], axis[-1]))
    index = np.searchsorted(direction * axis, direction * clamped, side="right") - 1
    index = np.minimum(index, len(axis) - 2)
    weight = (clamped - axis[index]) / (axis[index + 1] - axis[index])
    return index, weight[:, None]


def read_tables(tables, temp_cell, soc_cell):
    """Read a stack of tables using the weighted sums of Eq. 4."""
    j, wt = temp_cell
    m, ws = soc_cell
    low = (1 - ws) * tables[j, m] + ws * tables[j, m + 1]
    high = (1 - ws) * tables[j + 1, m] + ws * tables[j + 1, m + 1]
    return (1 - wt) * low + wt * high


def branch_regressors(resistance, tau, current, dt):
    """Solve Eq. 1 for minus the branch voltage, with a zero state at row 0."""
    decay = np.exp(-dt[1:] / tau)
    rhs = np.zeros_like(resistance)
    rhs[1:] = resistance[:-1] * (-(1 - decay) * current[:-1])[:, None]
    # Each row has coefficient 1 on its voltage and -decay on the previous voltage.
    band = np.ones((2, len(current)))
    band[1, :-1] = -decay
    return solve_banded((1, 0), band, rhs, overwrite_ab=True, overwrite_b=True)


def regressors(params, basis, run, soc, cost_rows):
    """Return full-rate X and the node support from the cost rows."""
    temp_cell = grid_cell(params.t_grid, run.temp)
    soc_cell = grid_cell(params.soc_grid, soc)
    weights = read_tables(basis, temp_cell, soc_cell)
    support = weights[cost_rows].sum(axis=0)
    r2 = read_tables(basis * params.r2[:, :, None], temp_cell, soc_cell)
    tau2 = read_tables(params.tau2[:, :, None], temp_cell, soc_cell)[:-1, 0]
    x3 = branch_regressors(weights, TAU3, run.i, run.dt)
    x2 = branch_regressors(r2, tau2, run.i, run.dt)
    return np.column_stack((x3, x2)), support


def fit_nodes(x, y, support):
    """Fit R3 and s - 1 jointly. Omitted columns keep the incumbent's values."""
    supported = support >= MIN_SUPPORT
    active = np.tile(supported, 2)
    lower = np.repeat([0.0, -1.0], len(support))
    upper = np.repeat([0.3, 2.0], len(support))
    fit = lsq_linear(x[:, active], y, bounds=(lower[active], upper[active]), method="bvls")
    if not (fit.success and np.isfinite(fit.x).all() and np.isfinite(fit.optimality)):
        raise RuntimeError(f"3RC-D BVLS failed (status {fit.status}, optimality {fit.optimality}): {fit.message}")
    values = np.zeros(len(active))
    values[active] = fit.x
    bound = np.zeros(len(active), dtype=int)
    bound[active] = fit.active_mask
    return values, bound, fit


def make_params(base, basis, values):
    r3, scale_delta = np.split(values, 2)
    return replace(base, r2=base.r2 * (1.0 + basis @ scale_delta),
                   r3=basis @ r3, tau3=np.full_like(base.r2, TAU3))


def voltage(params, run, soc):
    return simulate_open_loop(params, run.i, run.temp, soc, run.dt)


@dataclass
class CalibrationRun:
    spec: object
    run: object
    soc: np.ndarray
    baseline: np.ndarray
    cost_rows: np.ndarray
    x: np.ndarray
    y: np.ndarray
    support: np.ndarray


def prepare_mix(base, basis, spec):
    run = load_run(spec.path)
    soc = soc_ref(run)
    rows = np.flatnonzero(window_mask(soc, 0))[::10]
    baseline = voltage(base, run, soc)
    x, support = regressors(base, basis, run, soc, rows)
    return CalibrationRun(spec, run, soc, baseline, rows, x[rows], (run.v - baseline)[rows], support)


def solve_mix(calibration):
    support = np.sum([item.support for item in calibration], axis=0)
    x = np.concatenate([item.x for item in calibration])
    y = np.concatenate([item.y for item in calibration])
    values, bound, fit = fit_nodes(x, y, support)
    return values, bound, fit, support


def check_and_cross_validate(base, basis, calibration, values):
    """Check full-rate linearity and score each Mix run with its fold's fit."""
    candidate = make_params(base, basis, values)
    largest = 0.0
    folds = {temp: [] for temp in T_GRID_DEGC}
    for index, item in enumerate(calibration):
        x, _ = regressors(base, basis, item.run, item.soc, item.cost_rows)
        prediction = item.baseline + x @ values
        actual = voltage(candidate, item.run, item.soc)
        error = float(np.max(np.abs(actual - prediction)))
        if not error < 1e-9:
            raise RuntimeError(f"3RC-D linearity check failed on {item.spec.path.name}: {error:g} V")
        largest = max(largest, error)
        fold, _, _, _ = solve_mix(calibration[:index] + calibration[index + 1:])
        window = window_mask(item.soc, 0)
        measured = item.run.v[window]
        folds[item.spec.nominal_temp_degc].append([
            rms(item.baseline[window] - measured) * 1000,
            rms(item.baseline[window] + x[window] @ fold - measured) * 1000,
        ])
    return largest, folds


def score_open_loop(models, specs):
    """Per-temperature pooled window RMSE and the all-row US06 gate inputs."""
    totals = {temp: np.zeros(len(models)) for temp in T_GRID_DEGC}
    counts = dict.fromkeys(T_GRID_DEGC, 0)
    us06 = {}
    for spec in specs:
        run = load_run(spec.path)
        soc = soc_ref(run)
        window = window_mask(soc, 0)
        temp = spec.nominal_temp_degc
        errors = [voltage(params, run, soc) - run.v for params in models]
        totals[temp] += [np.sum(error[window] ** 2) for error in errors]
        counts[temp] += int(window.sum())
        if spec.cycle_name == "US06":
            us06[temp] = [[rms(error[mask]) * 1000 for error in errors]
                          for mask in (slice(None), window, ~window)]
    return {temp: np.sqrt(totals[temp] / counts[temp]) * 1000 for temp in T_GRID_DEGC}, us06


def node_rows(base, values, bound, support):
    r3, scale_delta = np.split(values, 2)
    r3_bound, s_bound = np.split(bound, 2)
    rows = []
    for j, temp in enumerate(base.t_grid):
        rows.append([f"{temp:g}", "0", "0", "1", "", "fixed", "0", "0"])
        for m, soc in enumerate(SOC_NODES[1:]):
            k = j * (len(SOC_NODES) - 1) + m
            rows.append([f"{temp:g}", f"{soc:g}", f"{r3[k]:.9g}", f"{1 + scale_delta[k]:.9g}",
                         f"{support[k]:.4f}", "yes" if support[k] >= MIN_SUPPORT else "no",
                         str(r3_bound[k]), str(s_bound[k])])
    return rows


def plot_nodes(base, values, path=PLOTS / "params_3rcd.png"):
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), layout="constrained")
    r3, scale_delta = np.split(values, 2)
    for ax, table, anchor, label in zip(axes, (r3 * 1000, 1 + scale_delta), (0, 1), ("R3 (mΩ)", "R2 scale")):
        for temp, nodes in zip(base.t_grid, table.reshape(len(base.t_grid), -1)):
            ax.plot(SOC_NODES, [anchor, *nodes], "o-", label=f"{temp:g} °C")
        ax.set(xlabel="SoC", ylabel=label)
        ax.grid(alpha=0.25)
    axes[1].legend(ncol=2, fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fit_checks(fit, largest):
    singular = fit.unbounded_sol[3]
    condition = singular[0] / singular[-1] if singular[-1] else np.inf
    return [
        f"BVLS status {fit.status}. Success {fit.success}. First-order optimality {fit.optimality:.3g}.",
        f"Design matrix rank {fit.unbounded_sol[2]} of {len(singular)}. Condition number {condition:.3g}.",
        f"Largest full-rate difference from the linear prediction over all Mix runs {largest:.3g} V "
        "(limit 1e-9 V).",
    ]


def fit_report(rows, headers, fit, largest, folds, in_sample, held_out, us06):
    gate = us06[GATE_TEMP_DEGC][0][1]
    lines = [
        "# 3RC-D fit on the Mix runs (S9)", "",
        "Written by `python/fit_3rcd.py` (`make fit-3rcd`).", "", DISCLOSURE, "",
        "## Fit and checks", "",
        *fit_checks(fit, largest), "",
        "A bound flag of -1 marks the lower bound, +1 the upper bound and 0 no active solver bound.", "",
        *md_table(headers, rows), "",
        "## Open-loop voltage", "",
        "RMSE in mV, pooled over the evaluation-window rows and scored using the exported tables.", "",
        *md_table(["T (degC)", "Mix 2RC-I", "Mix 3RC-D (in-sample)", "Standard 2RC-I", "Standard 3RC-D"],
                  [[str(temp), *[f"{v:.2f}" for v in (*in_sample[temp], *held_out[temp])]] for temp in T_GRID_DEGC]),
        "", "## US06 gate", "",
        f"**{'PASS' if gate <= GATE_RMSE_MV else 'FAIL'}.** "
        f"3RC-D scores {gate:.4f} mV over all rows at {GATE_TEMP_DEGC} degC (limit {GATE_RMSE_MV:g} mV).", "",
        "The window and tail columns separate the in-window and subsequent rows. All columns are in mV.", "",
        *md_table(["T (degC)", *[f"{model} {part}" for part in ("all", "window", "tail")
                                for model in ("2RC-I", "3RC-D")]],
                  [[str(temp), *[f"{v:.2f}" if np.isfinite(v) else "n/a" for part in us06[temp] for v in part]]
                   for temp in T_GRID_DEGC]),
        "", "## Leave-one-Mix-run-out voltage", "",
        "Mean per-run window RMSE in mV. Each fold recomputes node support and fits on the other 39 Mix runs. "
        "Earlier Mix diagnostics selected the structure, so the folds evaluate that selected structure.", "",
        *md_table(["T (degC)", "2RC-I", "3RC-D"],
                  [[str(temp), *[f"{v:.2f}" for v in np.mean(folds[temp], axis=0)]] for temp in T_GRID_DEGC]),
    ]
    return "\n".join(lines) + "\n"


def calibrate_mix(base, mix):
    """Run the full calibration and its prescribed Mix folds."""
    basis = basis_tables(base)
    print("Building the 40 Mix run regressors", flush=True)
    calibration = [prepare_mix(base, basis, spec) for spec in mix]
    values, bound, fit, support = solve_mix(calibration)
    print("Checking full-rate linearity and scoring the 40 Mix folds", flush=True)
    largest, folds = check_and_cross_validate(base, basis, calibration, values)
    return make_params(base, basis, values), values, bound, fit, support, largest, folds


def write_nodes(path, base, values, bound, support):
    headers = ["T_degC", "soc", "R3_ohm", "s", "support", "fitted", "R3_bound", "s_bound"]
    rows = node_rows(base, values, bound, support)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)
    return headers, rows


def main():
    base = load_params_ri()
    mix, standard = drive_split(evaluation_runs(RAW_DIR))
    params, values, bound, fit, support, largest, folds = calibrate_mix(base, mix)
    headers, rows = write_nodes(NODES_CSV, base, values, bound, support)
    params.to_csv(PARAMS_3RCD_CSV)
    print("Scoring the exported tables on the Mix and standard runs", flush=True)
    models = (base, load_params_3rcd())
    in_sample, _ = score_open_loop(models, mix)
    held_out, us06 = score_open_loop(models, standard)
    write_text(FIT_MD, fit_report(rows, headers, fit, largest, folds, in_sample, held_out, us06))
    plot_nodes(base, values)
    gate = us06[GATE_TEMP_DEGC][0][1]
    print(f"S1 gate {'PASS' if gate <= GATE_RMSE_MV else 'FAIL'} ({gate:.4f} mV)")


if __name__ == "__main__":
    main()
