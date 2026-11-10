"""S12 step B: the omitted Jacobian terms of the 3RC-D0 filter, and the three Jacobian variants on the Mix runs.

Part 1 replays the stored 3RC-D0 traces under the S2 settings (experiment 1 of the 63 runs, and the 30 wrong-start
cases of guard 7 of decision 1.48 over their first 30 s) and measures the omitted terms at the recorded states.
Part 2 runs the incumbent and the three variants on the 40 Mix runs, experiments 1 to 4. The standard runs are never
run under a changed filter (decision 1.56).
"""

from multiprocessing import Pool

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from diagnose_accuracy import JACOBIAN_CSV as S10_JACOBIAN_CSV, fmt
from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.ekf import EkfConfig
from ekfsoc.loader import load_run
from ekfsoc.metrics import max_abs_pp, window_mask
from ekfsoc.plots import MODEL_COLORS, save
from export_params import md_table, write_text
from fit_3rcd0 import load_candidate
from run_all import CONFIG_JSON, SCORED, load_traces
from s10_jacobian import replay_case, summarize_jacobian
from s10_protocol import COLD, DISCLOSURE, RESULTS, splits
from s11_evaluate import WRONG, trace_path
from s12_prescreen import (EXP1_LIMIT_PP, PEAK_LIMIT_PP, SCREEN_HEADER, prescreen, screen_cells, temperature_table,
                           variant_metric, wrong_start_peaks)
from s12_variants import TRACES, VARIANTS, replay_variant


CSV = RESULTS / "jacobian_3rcd0.csv"
REPORT = RESULTS / "jacobian_3rcd0.md"
PLOT = RESULTS / "plots" / "s12" / "jacobian_3rcd0.png"
GUARD7_CASES = 30
START_SPAN_S = 30.0
CROSS_EXPECTED = 0.5  # expected before the run in the cold (decision 1.56)
COLUMNS = (
    "split", "folder", "file", "cycle", "T_degC", "experiment", "scope", "peak_abs_pp", "samples", "ratio_samples",
    "H_abs_median_V_per_soc", "H_abs_p95_V_per_soc", "H_abs_max_V_per_soc", "H_over_OCV_slope_p95",
    "H_abs_low_slope_max_V_per_soc", "F1_abs_p95_V_per_soc", "F2_abs_p95_V_per_soc", "F3_abs_p95_V_per_soc",
    "covariance_norm_ratio_p95", "normalized_cross_change_p95", "correction_change_p95_pp", "correction_change_sum_pp",
)
SUMMARY = ("H_abs_p95_V_per_soc", "H_over_OCV_slope_p95", *COLUMNS[15:])


def measure_run(task):
    """Part 1 on one run: experiment 1 over the whole run and the window, each guard-7 case over its first 30 s."""
    split, spec = task
    run = load_run(spec.path)
    t, _, reference, cases = load_traces(trace_path(spec, TRACES))
    params, cfg = load_candidate(), EkfConfig.from_json(CONFIG_JSON)
    rows = []
    for experiment in ("exp1", *WRONG):
        case = cases[experiment]
        start = case["start"]
        window = window_mask(reference, start)
        peak = max_abs_pp(case["soc"] - reference, window)
        if experiment != "exp1" and peak <= PEAK_LIMIT_PP:
            continue
        measured = replay_case(run, params, cfg, case["soc0"], start, case["soc"], case["v_pred"])
        elapsed = t[start:] - t[start]
        if experiment == "exp1":
            scopes = {"full": elapsed >= 0, "window": window[start:]}
        else:
            scopes = {"first 30 s": elapsed <= START_SPAN_S}
        for scope, mask in scopes.items():
            correction = measured["correction_pp"][mask]
            rows.append([split, spec.folder, spec.path.name, spec.cycle_name, spec.nominal_temp_degc, experiment, scope,
                         peak, *summarize_jacobian(measured, mask), np.percentile(correction, 95), correction.sum()])
    return rows


def part1_lines(jacobian):
    """Experiment 1 by split, temperature and scope (largest run-level values), then the guard-7 cases one by one."""
    exp1 = jacobian[jacobian["experiment"] == "exp1"]
    groups = exp1.groupby(["split", "T_degC", "scope"])
    support = groups.agg(runs=("file", "size"), rows=("samples", "sum"), ratio_rows=("ratio_samples", "sum"))
    summary = support.join(groups[list(SUMMARY)].max()).reset_index()
    names = ["abs H", "abs H/OCV slope", "abs F1", "abs F2", "abs F3", "covariance norm ratio",
             "normalized cross change", "correction change p95 (pp)", "correction change sum (pp)"]
    starts = jacobian[jacobian["experiment"] != "exp1"]
    case_rows = starts[["folder", "cycle", "experiment", "peak_abs_pp", "samples", *SUMMARY]]
    return [
        *md_table(["Split", "T (degC)", "scope", "runs", "rows", "ratio rows", *names],
                  fmt(summary.itertuples(index=False, name=None))), "",
        "### The 30 wrong-start cases of guard 7, first 30 s after the start", "",
        "Peak is the case's largest absolute SoC error inside its evaluation window (pp). The other columns are "
        "over the rows of the first 30 s, as above.", "",
        *md_table(["Folder", "Cycle", "Experiment", "peak (pp)", "rows", *names],
                  fmt(case_rows.itertuples(index=False, name=None))),
    ]


def cross_by_temperature(exp1):
    """Largest run-level 95th percentile of the normalised cross change over the window, from experiment-1 rows."""
    return exp1[exp1["scope"] == "window"].groupby("T_degC")["normalized_cross_change_p95"].max()


def cross_lines(jacobian, s10):
    ours, theirs = cross_by_temperature(jacobian[jacobian["experiment"] == "exp1"]), cross_by_temperature(s10)
    above = [temp for temp in COLD if ours[temp] > CROSS_EXPECTED]
    rows = [[temp, theirs[temp], ours[temp]] for temp in T_GRID_DEGC]
    return [*md_table(["T (degC)", "2RC-I (S10)", "3RC-D0"], fmt(rows)), "",
            f"Expected before the run (decision 1.56): above {CROSS_EXPECTED} in the cold, as on 2RC-I. Measured: above "
            f"{CROSS_EXPECTED} at {', '.join(f'{temp} degC' for temp in above) or 'no cold temperature'} "
            f"({len(above)} of {len(COLD)})."]


def experiment_means(frame):
    """Mean SoC RMSE per temperature and experiment, for display."""
    return frame.groupby(["T_degC", "experiment"])["rmse_pp"].mean()


def temperature_rows(frames, screens):
    """Per temperature and variant: the run count, the mean SoC RMSE of every experiment, the experiment-1 change
    against the incumbent, the reached counts of experiments 2 and 3, and the wrong-start cases above PEAK_LIMIT_PP
    with the largest peak."""
    means = {name: experiment_means(frame) for name, frame in frames.items()}
    tables = {name: temperature_table(frame) for name, frame in frames.items()}
    rows = []
    for temp in T_GRID_DEGC:
        for name, frame in frames.items():
            table = tables[name][temp]
            count, peak = wrong_start_peaks(frame[frame["T_degC"] == temp])
            rows.append([str(temp), name, str(table["runs"]),
                         *[f"{means[name][(temp, experiment)]:.4f}" for experiment in SCORED],
                         f"{screens[name]['exp1_change'][temp]:+.4f}", " / ".join(str(table[e]) for e in WRONG),
                         str(count), f"{peak:.4f}"])
    return rows


def mix_run_rows(frames, mix):
    """Experiment 1 of every Mix run: the incumbent's SoC RMSE and each variant's change."""
    exp1 = {name: frame[frame["experiment"] == "exp1"].set_index(["folder", "file"])["rmse_pp"]
            for name, frame in frames.items()}
    incumbent = exp1.pop(VARIANTS[0][0])
    rows = []
    for spec in mix:
        key = (spec.folder, spec.path.name)
        rows.append([spec.folder, spec.cycle_name, f"{incumbent[key]:.4f}",
                     *[f"{values[key] - incumbent[key]:+.4f}" for values in exp1.values()]])
    return rows


def part2_lines(frames, mix):
    incumbent = frames[VARIANTS[0][0]]
    screens = {name: prescreen(frame, incumbent) for name, frame in frames.items()}
    variants = list(frames)[1:]
    return [
        *md_table(["T (degC)", "variant", "runs", *[f"{e} mean (pp)" for e in SCORED], "exp1 change (pp)",
                   "reached (" + " / ".join(WRONG) + ")", f"cases above {PEAK_LIMIT_PP:.0f} pp", "largest peak (pp)"],
                  temperature_rows(frames, screens)), "",
        "### Step C pre-screen", "",
        f"Against the incumbent, over the 40 Mix runs: the change of each temperature's experiment-1 mean (limit "
        f"+{EXP1_LIMIT_PP:.2f} pp), the count of the 120 wrong-start cases above {PEAK_LIMIT_PP:.0f} pp and the largest "
        "peak, every temperature and experiment whose reached count (experiments 2 and 3, as guard 6 counts them) is "
        "lower, the selection metric (the experiment-1 mean over the 40 runs) and whether the variant qualifies under "
        "step C's pre-screen of decision 1.56. Step C's entry names the outcome.", "",
        *md_table(["variant", *SCREEN_HEADER],
                  [[name, *screen_cells(screen, variant_metric(frames[name]))] for name, screen in screens.items()]), "",
        "### Experiment 1, every Mix run", "",
        *md_table(["Folder", "Cycle", f"{VARIANTS[0][0]} (pp)", *[f"{name} change (pp)" for name in variants]],
                  mix_run_rows(frames, mix)),
    ]


def report(jacobian, s10, frames, mix):
    return "\n".join([
        "# Jacobian of the 3RC-D0 filter (S12 step B)", "",
        "Generated by `make diagnose-jacobian` under decision 1.56. 3RC-D0 (`results/params_3rcd0.csv`) under the S2 "
        "settings (`results/ekf_config.json`).", "", DISCLOSURE, "",
        "## Part 1: omitted terms along the unchanged filter", "",
        "Each case is replayed from its start row (dt = 0 there) with its stored initial SoC, and the estimate and "
        "prior voltage equal the stored trace in `results/runs/3rcd0/` on every row. Experiment 1 is measured on all "
        "63 runs over the whole run (full) and over the evaluation window; the 30 wrong-start cases of guard 7 "
        "(decision 1.48: peak above 25 pp in experiment 2, 3 low or 3 high) over the first 30 s after their start. "
        "Current, temperature and the stored OCV slope are held as in S10 (`results/accuracy_diagnostics.md`): the "
        "SoC derivatives are those of the clamped bilinear tables, zero outside the SoC axis; H is the omitted "
        "-I dR0/dSoC at the prior SoC and the row's own current; its ratio to the stored OCV slope uses the rows "
        "where that slope is at least 0.05 V per unit SoC; F1 to F3 are the omitted SoC column of F per branch at "
        "the previous posterior state and the held current. The covariance ratio and the normalised cross change "
        "compare F_full P F_full^T with F P F^T at the recorded posterior P and Q, as in S10. The correction change "
        "is |(K_full - K_legacy)_SoC| times the absolute innovation, in pp per row: K_legacy is Eq. 9 with the "
        "filter's prior covariance and H, K_full with F_full P F_full^T + Q and the full H.", "",
        "Each entry is the largest run-level value in its split, temperature and scope: the 95th percentile, or "
        "the sum over the scope for the last column. Support is summed. Per-run values are in "
        "[jacobian_3rcd0.csv](jacobian_3rcd0.csv). These are local sensitivities: a one-step change in P or K "
        "does not bound the cumulative effect of a changed filter in either direction.", "",
        *part1_lines(jacobian), "",
        "### Normalised cross change against 2RC-I", "",
        "Largest run-level 95th percentile, experiment 1 over the evaluation window, all 63 runs; 2RC-I from "
        "[accuracy_jacobian.csv](accuracy_jacobian.csv).", "",
        *cross_lines(jacobian, s10), "",
        "## Part 2: the three variants on the Mix runs", "",
        "The incumbent and three variants under the frozen S2 settings on the 40 Mix runs, the tuning run "
        "included: Process puts the SoC column of F back (through every R_i and tau_i), Measurement puts "
        "-I dR0/dSoC into H, Both does both. The predicted state and voltage are unchanged; only P and K move. "
        "Every case starts as in `results/runs/3rcd0/`, experiment 4 with its 0.2 A offset. The incumbent replay "
        "equals the stored 3RC-D0 traces on every row of every case. Experiments 1 to 4 are scored as in "
        "`results/ekf_results.csv`; reached counts the runs whose error stays inside +-2 pp from some time on; the "
        "wrong-start cases are experiment 2, 3 low and 3 high (120). These are in-sample Mix-run numbers; the "
        "standard runs were not run. Nothing here is a guard.", "",
        *part2_lines(frames, mix), "",
        "See [the plot](plots/s12/jacobian_3rcd0.png).", "",
    ])


def plot(jacobian, s10, frames):
    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4))
    for (label, data), color in zip((("2RC-I (S10)", s10), ("3RC-D0", jacobian[jacobian["experiment"] == "exp1"])),
                                    MODEL_COLORS):
        values = cross_by_temperature(data)
        left.plot(T_GRID_DEGC, [values[temp] for temp in T_GRID_DEGC], "o-", color=color, label=label)
    left.axhline(CROSS_EXPECTED, color="0.6", linewidth=1, linestyle="--")
    left.set(yscale="log", xlabel="Temperature (°C)", ylabel="Normalised cross change, p95 (largest run)",
             title="Experiment 1, evaluation window, 63 runs")
    left.legend()
    for (name, frame), color in zip(frames.items(), MODEL_COLORS):
        means = experiment_means(frame).xs("exp1", level="experiment")
        right.plot(T_GRID_DEGC, [means[temp] for temp in T_GRID_DEGC], "o-", color=color, label=name)
    right.set(xlabel="Temperature (°C)", ylabel="Exp. 1 mean SoC RMSE (pp)", title="Variants, 40 Mix runs")
    right.legend()
    save(fig, PLOT)


def main():
    """The inputs are checked through the replays: every replayed incumbent case must equal its stored 3RC-D0 trace
    row by row, which ties results/params_3rcd0.csv and results/ekf_config.json to those traces."""
    mix, standard = splits()
    with Pool(processes=6) as pool:
        print("Part 1: replaying the 3RC-D0 cases", flush=True)
        measured = pool.map(measure_run, [("Mix", spec) for spec in mix] + [("Standard", spec) for spec in standard],
                            chunksize=1)
        print("Part 2: the Jacobian variants on the Mix runs", flush=True)
        tasks = [(spec, variant) for spec in mix for variant in VARIANTS]
        replayed = pool.map(replay_variant, tasks, chunksize=1)
    jacobian = pd.DataFrame([row for rows in measured for row in rows], columns=COLUMNS)
    if (jacobian["experiment"] != "exp1").sum() != GUARD7_CASES:
        raise RuntimeError("the stored 3RC-D0 traces do not hold the 30 wrong-start cases of guard 7")
    jacobian.to_csv(CSV, index=False, float_format="%.9g")
    scores = pd.DataFrame([row for rows in replayed for row in rows])
    frames = {name: scores[scores["variant"] == name] for name, _, _ in VARIANTS}
    s10 = pd.read_csv(S10_JACOBIAN_CSV)
    write_text(REPORT, report(jacobian, s10, frames, mix))
    plot(jacobian, s10, frames)
    print("Jacobian diagnostic written", flush=True)


if __name__ == "__main__":
    main()
