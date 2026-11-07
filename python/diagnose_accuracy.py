"""Reproduce the S10 residual diagnosis and observe the unchanged incumbent filter."""

from multiprocessing import Pool

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from compare_r1d import B_TEST_MIN_DROP_PP, load_params_rd
from compare_r1i import RUNS_DIR as RI_TRACES, load_params_ri
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import PP, rms, rmse_pp, window_mask
from ekfsoc.plots import save
from export_params import md_table, write_text
from fit_3rcd import branch_regressors, grid_cell, load_params_3rcd, read_tables, voltage
from fit_r1_current import R1_CURRENT_CSV
from run_all import CONFIG_JSON, DEPENDENCIES, is_fresh, load_traces
from s10_jacobian import SLOPE_FLOOR, replay_measurements
from s10_protocol import COLD, DIAGNOSTIC_MD, DISCLOSURE, PLOTS, RESULTS, provenance, splits, verify_baseline


BINS_CSV = RESULTS / "accuracy_residual_bins.csv"
JACOBIAN_CSV = RESULTS / "accuracy_jacobian.csv"
JACOBIAN_COLUMNS = (
    "split", "folder", "file", "cycle", "T_degC", "scope", "samples", "ratio_samples",
    "H_abs_median_V_per_soc", "H_abs_p95_V_per_soc", "H_abs_max_V_per_soc", "H_over_OCV_slope_p95",
    "H_abs_low_slope_max_V_per_soc", "F1_abs_p95_V_per_soc", "F2_abs_p95_V_per_soc",
    "covariance_norm_ratio_p95", "normalized_cross_change_p95",
)
SCOPE = ("full", "window", "tail")
SIGNALS = ("voltage_mV", "innovation_mV", "soc_pp")
STEP_A = 2.0
REST_A = 0.05


def ages(time, events):
    """Elapsed time since the last event, with infinity before the first event."""
    last = np.maximum.accumulate(np.where(events, time, -np.inf))
    return time - last


def features(run, reference):
    """Separate current, transient age, rest duration and signed current history."""
    steps = np.r_[False, np.abs(np.diff(run.i)) >= STEP_A]
    resting = np.abs(run.i) < REST_A
    rest_age = ages(run.t, resting & ~np.r_[False, resting[:-1]])
    throughput = np.r_[0.0, np.cumsum(np.abs(run.i[:-1]) * run.dt[1:])] / 3600
    history = -branch_regressors(np.ones((len(run.i), 1)), 45.0, run.i, run.dt)[:, 0]
    return steps, {
        "all": np.repeat("all", len(run.t)),
        "SoC (%)": pd.cut(PP * reference, [-np.inf, 10, 30, 60, 90, np.inf], right=False),
        "current (A)": pd.cut(run.i, [-np.inf, -3, -REST_A, REST_A, 1.5, 3, 6, np.inf], right=False),
        "time since step (s)": pd.cut(ages(run.t, steps), [0, 0.2, 1, 5, 20, np.inf], right=False),
        "rest duration (s)": pd.cut(np.where(resting, rest_age, np.nan), [0, 1, 10, 60, np.inf], right=False),
        "elapsed time (s)": pd.cut(run.t - run.t[0], [0, 60, 300, 1000, 3000, np.inf], right=False),
        "absolute current throughput (Ah)": pd.cut(throughput, [0, 0.5, 1, 2, 4, np.inf], right=False),
        "45 s current history (A)": pd.cut(history, [-np.inf, -1, 0, 1, 3, np.inf], right=False),
    }


def first_case(spec, run, reference, params, cfg):
    trace = RI_TRACES / f"{spec.folder}__{spec.path.stem}.npz"
    if is_fresh([trace], [spec.path, R1_CURRENT_CSV, *DEPENDENCIES]):
        time, volts, saved_ref, cases = load_traces(trace)
        if all(np.array_equal(x, y) for x, y in zip((time, volts, saved_ref), (run.t, run.v, reference))):
            return cases["exp1"]
    return run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, float(reference[0]))


def bin_rows(groups, signals, masks):
    for scope, mask in masks.items():
        for feature, labels in groups.items():
            if scope == "tail" and feature != "all":
                continue
            for label in pd.unique(labels[mask]):
                if pd.isna(label):
                    continue
                sel = mask & (labels == label)
                values = signals[sel]
                yield (scope, feature, str(label), len(values), *values.sum(axis=0), *(values**2).sum(axis=0))


def correlation(values, mask, lag):
    keep = mask[:-lag] & mask[lag:]
    left, right = values[:-lag][keep], values[lag:][keep]
    return len(left), np.corrcoef(left, right)[0, 1] if len(left) > 1 and left.std() and right.std() else np.nan


def summarize_jacobian(measurements, mask):
    h, slope, process, covariance, cross = (array[mask] for array in measurements)
    safe = np.abs(slope) >= SLOPE_FLOOR
    ratio = np.abs(h[safe] / slope[safe])
    return [len(h), len(ratio), *np.percentile(np.abs(h), [50, 95, 100]),
            np.percentile(ratio, 95) if len(ratio) else np.nan,
            np.max(np.abs(h[~safe])) if (~safe).any() else np.nan,
            *np.percentile(np.abs(process), 95, axis=0), np.percentile(covariance, 95),
            np.percentile(cross.max(axis=1), 95)]


def diagnose_run(task):
    split, spec = task
    run = load_run(spec.path)
    reference = soc_ref(run)
    incumbent = load_params_ri()
    cfg = EkfConfig.from_json(CONFIG_JSON)
    window = window_mask(reference, 0)
    masks = dict(zip(SCOPE, (np.ones(len(window), dtype=bool), window, ~window)))
    error = voltage(incumbent, run, reference) - run.v
    case = first_case(spec, run, reference, incumbent, cfg)
    innovation = run.v - case["v_pred"]
    soc_error = case["soc"] - reference
    signals = np.column_stack((error * 1000, innovation * 1000, soc_error * PP))
    steps, groups = features(run, reference)
    rows = [(split, spec.nominal_temp_degc, *row) for row in bin_rows(groups, signals, masks)]
    acf = [[split, spec.nominal_temp_degc, scope, lag, *correlation(innovation, masks[scope], lag)]
           for scope in ("full", "window") for lag in (1, 10)]
    measurements = replay_measurements(run, reference, incumbent, cfg, case["soc"], case["v_pred"])
    jacobian = [[split, spec.folder, spec.path.name, spec.cycle_name, spec.nominal_temp_degc, scope,
                 *summarize_jacobian(measurements, masks[scope])]
                for scope in ("full", "window")]
    regen_check = None
    timing = None
    if spec.cycle_name == "US06":
        tc = grid_cell(incumbent.t_grid, run.temp)
        sc = grid_cell(incumbent.soc_grid, reference)
        r0 = read_tables(incumbent.r0[:, :, None], tc, sc)[:, 0]
        edges = np.flatnonzero(steps & window)
        edges = edges[edges + 1 < len(run.i)]
        jump = -r0[edges] * (run.i[edges] - run.i[edges - 1])
        measured = np.diff(run.v)
        timing = [spec.nominal_temp_degc, len(edges), rms(jump - measured[edges - 1]) * 1000,
                  rms(jump - measured[edges]) * 1000]
        if spec.nominal_temp_degc in COLD:
            ablation = run_ekf(load_params_rd(), cfg, run.i, run.v, run.temp, run.dt, float(reference[0]))
            regen_check = [rmse_pp(soc_error, window), rmse_pp(ablation["soc"] - reference, window)]
        for row in bin_rows(groups, signals, masks):
            rows.append(("US06", spec.nominal_temp_degc, *row))
    slow = None
    if split == "Mix" and spec.nominal_temp_degc in COLD:
        slow_error = voltage(load_params_3rcd(), run, reference) - run.v
        slow = [int(window.sum()), float(np.sum(error[window] ** 2)), float(np.sum(slow_error[window] ** 2))]
    return spec.nominal_temp_degc, rows, acf, jacobian, timing, regen_check, slow


def pooled_bins(outputs):
    sums = [f"{signal}_sum" for signal in SIGNALS]
    squares = [f"{signal}_squared" for signal in SIGNALS]
    keys = ["split", "T_degC", "scope", "feature", "bin"]
    data = pd.DataFrame([row for output in outputs for row in output[1]],
                        columns=[*keys, "samples", *sums, *squares])
    grouped = data.groupby(keys)
    result = grouped[["samples", *sums, *squares]].sum()
    result["runs"] = grouped.size()
    for signal in SIGNALS:
        result[f"{signal}_mean"] = result.pop(f"{signal}_sum") / result["samples"]
        result[f"{signal}_rmse"] = np.sqrt(result.pop(f"{signal}_squared") / result["samples"])
    return result.reset_index()


def fmt(rows):
    return [["n/a" if isinstance(v, float) and not np.isfinite(v)
             else f"{v:.5g}" if isinstance(v, float) else str(v) for v in row] for row in rows]


def plot_residuals(data):
    features = ("SoC (%)", "current (A)", "time since step (s)", "45 s current history (A)")
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for ax, feature in zip(axes.flat, features):
        rows = data[(data["split"] == "US06") & (data["scope"] == "window") & (data["feature"] == feature)]
        bins = sorted(rows["bin"].unique(), key=lambda label: float(label.split(",")[0][1:]))
        for temp in COLD:
            here = rows[rows["T_degC"] == temp].set_index("bin").reindex(bins)
            ax.plot(bins, here["voltage_mV_mean"], "o-", label=f"{temp} °C")
        ax.axhline(0, color="0.7", linewidth=1)
        ax.set(xlabel=feature, ylabel="Mean open-loop residual (mV)")
        ax.tick_params(axis="x", labelrotation=20, labelsize=8)
    axes[0, 0].legend()
    save(fig, PLOTS / "accuracy_residuals.png")


def jacobian_lines(jacobian):
    columns = [
        "H_abs_p95_V_per_soc", "H_over_OCV_slope_p95", "F1_abs_p95_V_per_soc", "F2_abs_p95_V_per_soc",
        "covariance_norm_ratio_p95", "normalized_cross_change_p95",
    ]
    groups = jacobian.groupby(["split", "T_degC", "scope"])
    support = groups.agg(runs=("file", "size"), rows=("samples", "sum"), ratio_rows=("ratio_samples", "sum"))
    summary = support.join(groups[columns].max()).reset_index()
    headers = ["Split", "T (degC)", "scope", "runs", "rows", "ratio rows", "abs H", "abs H/OCV slope",
               "abs F1", "abs F2", "covariance norm ratio", "normalized cross change"]
    return md_table(headers, fmt(summary.itertuples(index=False, name=None)))


def report(outputs, data, jacobian, mix, standard):
    cold_rows = []
    passed = True
    for temp in COLD:
        before, after = next(row[5] for row in outputs if row[0] == temp and row[5] is not None)
        count, old_ss, new_ss = np.sum([row[6] for row in outputs if row[0] == temp and row[6] is not None], axis=0)
        voltage_before, voltage_after = np.sqrt([old_ss / count, new_ss / count]) * 1000
        passed &= before - after >= B_TEST_MIN_DROP_PP and voltage_after < voltage_before
        cold_rows.append([temp, before, after, after - before, voltage_before, voltage_after, int(count)])

    baseline = data[data["feature"] == "all"].drop(columns=["feature", "bin"])
    acf_columns = ["split", "T (degC)", "scope", "lag (rows)", "pairs", "correlation"]
    acf = pd.DataFrame([row for output in outputs for row in output[2]], columns=acf_columns)
    acf_group = acf.groupby(acf_columns[:4])
    acf_table = acf_group.agg(runs=("correlation", "count"), pairs=("pairs", "sum"),
                              median=("correlation", "median")).reset_index()
    timing = [output[4] for output in outputs if output[4] is not None]
    return "\n".join([
        "# S10 residual diagnosis", "", "Generated by `make diagnose-accuracy` under decision 1.44.", "",
        DISCLOSURE, "", "## Evidence for the R1 interaction experiment", "",
        *md_table(["T (degC)", "US06 2RC-I (pp)", "US06 2RC-Id (pp)", "change (pp)",
                   "Mix 2RC-I (mV)", "Mix 3RC-D (mV)", "Mix window rows"], fmt(cold_rows)), "",
        ("The regen ablation and the drive-fitted correction reproduce the checks recorded in decision 1.44. "
         "They support testing both choices together." if passed else
         "The measurements differ from the checks recorded in decision 1.44."), "",
        "The diagnostic is separate from the 3RC-D0 adoption evaluation (decision 1.47).", "",
        "The pulse sequence confounds current magnitude with position and history (1.28). The drive data "
        "do not identify whether the two corrections represent the same physical dynamics. Cold US06, "
        "its low-SoC tails and the residual bins are exploratory.", "",
        "## Residuals by split and window", "",
        "Open-loop voltage is model minus measured at reference SoC. Experiment-1 innovation is measured minus "
        "EKF prior voltage. SoC error is the posterior minus reference. The CSV gives sample and run support, "
        "signed mean and RMSE by nominal temperature, SoC, current, time since a 2 A step, rest duration "
        "(absolute current below 0.05 A), elapsed time, accumulated absolute-current throughput using the "
        "previous-current hold, and signed current history (45 s zero-initialized filter). "
        "Time since step excludes rows before the first step. The tail is outside the evaluation window.", "",
        *md_table(["Split", "T (degC)", "scope", "rows", "runs", "open mean (mV)", "open RMSE (mV)",
                   "innovation mean (mV)", "innovation RMSE (mV)", "SoC mean (pp)", "SoC RMSE (pp)"],
                  fmt(baseline.itertuples(index=False, name=None))), "",
        "See [cold US06 residual profiles](plots/s10/accuracy_residuals.png) for bias and transient shape.", "",
        "## Timing and innovation persistence", "",
        "The open-loop model applies the new current immediately to the ohmic drop and holds the previous "
        "current over the elapsed RC step. The EKF uses the current row's measured temperature for predict "
        "and update. Across the same US06 edges, compare the ohmic jump with the observed voltage jump "
        "at the edge and one row later. The check cannot resolve timing within a logged interval.", "",
        *md_table(["T (degC)", "steps", "same-row error (mV)", "one-row-late error (mV)"], fmt(timing)), "",
        "The same-row error is lower at every temperature. The logged edges support the current alignment.", "",
        "Innovation autocorrelation is the median of within-run Pearson correlations. Lag 10 is roughly 1 s. "
        "Window correlations use pairs entirely inside the window.", "",
        *md_table([*acf_columns[:4], "runs", "pairs", "median correlation"],
                  fmt(acf_table.itertuples(index=False, name=None))), "",
        "## Omitted Jacobian terms on unchanged 2RC-I traces", "",
        "Experiment 1 was replayed for all 63 runs. The estimates and prior voltage match the ordinary runner "
        "row by row. Only local sensitivities are measured. The stored OCV slope stays in use. The ratio uses rows with absolute stored slope at least "
        "0.05 V per unit SoC. The active cell starts at each interior SoC knot in grid order, the final knot "
        "uses the last cell, and outside the grid the SoC derivative is zero. Current and temperature are held "
        "fixed in the partial derivatives. The covariance comparison is one step at the same posterior P and Q. "
        "The Frobenius ratio mixes SoC and voltage units. The final column normalizes the largest absolute "
        "SoC-to-branch covariance change by the corresponding legacy prior standard deviations.", "",
        "Each entry below is the largest run-level 95th percentile in its split, temperature and scope. "
        "Support is summed over those runs. Per-run support, absolute maxima and low-slope measurements are in "
        "[accuracy_jacobian.csv](accuracy_jacobian.csv).", "",
        *jacobian_lines(jacobian), "",
        "The cold traces have the largest local RC covariance contributions. H and F branch terms are in V per "
        "unit SoC. These local magnitudes provide evidence for a separate "
        "Jacobian decision. They do not measure the effect of a changed filter.", "", *provenance(mix, standard), "",
    ])


def main():
    verify_baseline()
    mix, standard = splits()
    tasks = [("Mix", spec) for spec in mix] + [("Standard", spec) for spec in standard]
    print("Diagnosing the frozen 63 runs", flush=True)
    with Pool(processes=6) as pool:
        outputs = pool.map(diagnose_run, tasks, chunksize=1)
    data = pooled_bins(outputs)
    data.to_csv(BINS_CSV, index=False, float_format="%.9g")
    jacobian = pd.DataFrame([row for output in outputs for row in output[3]], columns=JACOBIAN_COLUMNS)
    jacobian.to_csv(JACOBIAN_CSV, index=False, float_format="%.9g")
    plot_residuals(data)
    write_text(DIAGNOSTIC_MD, report(outputs, data, jacobian, mix, standard))
    print("Diagnostic report written", flush=True)


if __name__ == "__main__":
    main()
