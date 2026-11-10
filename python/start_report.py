"""The text of results/start_cases.md (S12 step A, decision 1.56): one function per part.

The report gives numbers only; step C's entry reads them and names its outcome.
"""

import numpy as np

from data_checks import fmt
from ekfsoc.constants import T_GRID_DEGC
from export_params import md_table
from s10_protocol import DISCLOSURE
from s11_evaluate import WRONG
from s12_prescreen import EXP1_LIMIT_PP, PEAK_LIMIT_PP, SCREEN_HEADER, screen_cells
from start_cases import BEFORE_S, CLASS_CODE, GAP_MAX_S, IN_RUN, REST_MIN_S, UNKNOWN, best_threshold
from start_prior import NATIVE_TOLERANCE, PRIORS_V, THRESHOLD_A


MARKS = (f"Mark L: the run's first used row has |I| at or above {THRESHOLD_A} A, so the rule of kind (i) gives it the "
         "S2 prior in experiments 1, 2 and 4. Mark U: its history is unknown (part 1).")


def run_label(row):
    return f"{row.cycle} at {row.T_degC} degC"


def marked_runs(history, temp):
    """The marked runs of one temperature, for the per-temperature tables."""
    here = history[(history.T_degC == temp) & (history.mark != "")]
    return "; ".join(f"{row.cycle} ({row.mark})" for row in here.itertuples()) or "none"


def part1_lines(history, cases):
    exp3 = cases[cases.experiment == "exp3_low"].set_index(["folder", "file"])
    loaded = history[history.i_first_A.abs() >= THRESHOLD_A]
    unknown = history[history.run_class == UNKNOWN]
    below_load = exp3[exp3.i_start_A.abs() < loaded.i_first_A.abs().min()]
    rows = [[row.split, row.folder, row.cycle, row.mark, row.previous_file, fmt(row.gap_s, 0), fmt(row.rest_s, 1),
             fmt(row.previous_last_v, 4), fmt(row.i_first_A, 4), row.run_class,
             fmt(exp3.loc[(row.folder, row.file), "i_start_A"], 4),
             fmt(exp3.loc[(row.folder, row.file), "mean_abs_i_before_A"], 4)] for row in history.itertuples()]
    return [
        "## Part 1: the history before each run", "",
        "The previous file is the file of the same folder whose first TimeStamp comes last before the run's (section 8 "
        "of `results/data_checks.md`, over all 206 raw files). The gap runs from its last row to the run's first used "
        "row on TimeStamp (sub-second resolution), so an unlogged pause inside the run file before the loader's cut counts. The "
        "final rest is the last row with V > 0 minus the last row with Current > 0 (section 9); the last voltage is "
        f"that of its last row with V > 0. A run is *rested* when the final rest is at least {REST_MIN_S:.0f} s and the "
        f"gap at most {GAP_MAX_S:.0f} s, *unknown* otherwise. Every experiment-3 start is *{IN_RUN}*; its history is "
        f"the mean |I| over the {BEFORE_S:.0f} s before the start. Currents are in the project sign (positive = "
        "discharge). These classes serve the inventory only; no policy reads them.", "",
        f"- Rested: {int((history.run_class != UNKNOWN).sum())} of {len(history)} runs. Unknown: "
        + "; ".join(f"{run_label(row)} ({'no previous file' if row.previous_file == 'none' else f'gap {row.gap_s:,.0f} s'})"
                    for row in unknown.itertuples()) + ".",
        f"- First used row: {len(history) - len(loaded)} of {len(history)} runs below {THRESHOLD_A} A "
        f"(|I| {fmt(history.i_first_A.abs().min(), 4)} to {fmt(history.i_first_A.abs()[history.i_first_A.abs() < THRESHOLD_A].max(), 4)} A); "
        f"{len(loaded)} at {fmt(loaded.i_first_A.abs().min(), 4)} to {fmt(loaded.i_first_A.abs().max(), 4)} A: "
        + "; ".join(run_label(row) for row in loaded.itertuples()) + ".",
        f"- Experiment-3 start rows: |I| from {fmt(exp3.i_start_A.abs().min(), 4)} to {fmt(exp3.i_start_A.abs().max(), 4)} A; "
        f"{len(below_load)} of {len(exp3)} lie below the smallest load a run opens under: "
        + "; ".join(f"{run_label(row)} {fmt(abs(row.i_start_A), 4)} A" for row in below_load.itertuples()) + ".",
        "", MARKS, "",
        *md_table(["Split", "Folder", "Cycle", "Mark", "Previous file", "Gap (s)", "Final rest (s)", "Its last V (V)",
                   "I, first used row (A)", "Class", "I, exp-3 start row (A)",
                   f"Mean abs I, {BEFORE_S:.0f} s before exp-3 (A)"], rows), ""]


def guard7_lines(cases):
    flagged = cases[cases.peak_abs_pp > PEAK_LIMIT_PP]
    start_rows = [[row.folder, row.cycle, row.mark, row.experiment, row.start_class, fmt(row.i_start_A, 3),
                   *[fmt(getattr(row, f"mean_abs_i_{s}s_A"), 3) for s in (1, 10, 30)],
                   *[fmt(getattr(row, f"dv_{s}s_mV"), 1) for s in (1, 10, 30)],
                   *[fmt(getattr(row, f"v{n}_exp1_start_mV"), 1) for n in (1, 2, 3)]] for row in flagged.itertuples()]
    response_rows = [[row.folder, row.cycle, row.experiment,
                      *[fmt(getattr(row, f"error_{s}s_pp"), 2) for s in (1, 10, 30)],
                      fmt(row.peak_error_pp, 2), fmt(row.peak_s, 1), fmt(row.first_above_s, 1),
                      fmt(row.soc_std_start_pp, 2), fmt(row.soc_std_10s_pp, 2), fmt(row.soc_std_peak_pp, 2),
                      *[fmt(getattr(row, f"v{n}_10s_mV"), 1) for n in (1, 2, 3)],
                      *[fmt(getattr(row, f"v{n}_peak_mV"), 1) for n in (1, 2, 3)],
                      str(row.bound_rows_30s), str(row.bound_rows_to_peak)] for row in flagged.itertuples()]
    counts = ", ".join(f"{int((flagged.experiment == name).sum())} in {name}" for name in WRONG)
    return [
        f"### The {len(flagged)} cases above {PEAK_LIMIT_PP:.0f} pp (guard 7)", "",
        f"{counts}; the same cases as the guard-7 count of `results/ekf_results_3rcd0.csv`, whose peaks the "
        "replays reproduce.", "",
        "The start. I is the run's current on the start row; mean |I| and the voltage change (V at the span's last "
        "row minus V at the start row) run over the first 1, 10 and 30 s. The experiment-1 branch states at the start "
        "row are the model's estimate of the polarisation the restart drops, not a measurement; an experiment-2 case "
        "starts at row 0, where experiment 1 has made only its first update from zero branch states, so its V1 to V3 "
        "are about 0.", "",
        *md_table(["Folder", "Cycle", "Mark", "Experiment", "Class", "I (A)", "|I| 1 s (A)", "|I| 10 s (A)",
                   "|I| 30 s (A)", "dV 1 s (mV)", "dV 10 s (mV)", "dV 30 s (mV)", "exp1 V1 (mV)", "exp1 V2 (mV)",
                   "exp1 V3 (mV)"], start_rows), "",
        "The filter's response. Errors are estimate minus reference in pp; times are seconds after the start; the "
        "SoC standard deviation is the root of P[0][0] in pp, at the start row after its update; the branch states V1 to V3 are in mV; the bound columns "
        "count rows whose posterior SoC lies on 0 or 1, within the first 30 s and from the start to the peak.", "",
        *md_table(["Folder", "Cycle", "Experiment", "Error 1 s", "Error 10 s", "Error 30 s", "Peak error",
                   "Peak at (s)", "First above 25 pp (s)", "SD after start update", "SD 10 s", "SD peak", "V1 10 s", "V2 10 s",
                   "V3 10 s", "V1 peak", "V2 peak", "V3 peak", "Bound 30 s", "Bound to peak"], response_rows), ""]


def others_lines(cases):
    others = cases[cases.peak_abs_pp <= PEAK_LIMIT_PP]
    rows = []
    for temp in T_GRID_DEGC:
        for name in WRONG:
            here = others[(others.T_degC == temp) & (others.experiment == name)]
            rows.append([str(temp), name, str(len(here)), fmt(here.peak_abs_pp.median(), 2),
                         fmt(here.peak_abs_pp.max(), 2), fmt(here.error_10s_pp.abs().median(), 2),
                         fmt(here.error_30s_pp.abs().median(), 2), fmt(here.soc_std_10s_pp.median(), 2),
                         str(int((here.bound_rows_30s > 0).sum()))])
    return [f"### The other {len(others)} cases per temperature and experiment", "",
            *md_table(["T (degC)", "Experiment", "Cases", "Median peak (pp)", "Largest peak (pp)",
                       "Median abs error 10 s (pp)", "Median abs error 30 s (pp)", "Median SD 10 s (pp)",
                       "Cases with a bound row in 30 s"], rows), ""]


def separation_values(here):
    """The measured quantities of parts 1 and 2 that the separation test reads, by report label."""
    values = {"history class (code)": here.start_class.map(CLASS_CODE).to_numpy(),
              "|I| on the start row (A)": here.i_start_A.abs().to_numpy()}
    for s in (1, 10, 30):
        values[f"mean |I| over {s} s (A)"] = here[f"mean_abs_i_{s}s_A"].to_numpy()
    for s in (1, 10, 30):
        values[f"voltage change over {s} s (mV)"] = here[f"dv_{s}s_mV"].to_numpy()
    return values


def threshold_text(cut, side):
    return "none (one class for all)" if not np.isfinite(cut) else f"{side} {cut:.4g}"


def separation_lines(cases):
    rows, rule_rows = [], []
    for name in WRONG:
        here = cases[cases.experiment == name]
        flagged = (here.peak_abs_pp > PEAK_LIMIT_PP).to_numpy()
        for label, values in separation_values(here).items():
            cut, side, wrong = best_threshold(values, flagged)
            rows.append([name, f"{flagged.sum()} of {len(here)}", label, threshold_text(cut, side), str(wrong),
                         "yes" if wrong == 0 else "no"])
        small = here.i_start_A.abs().to_numpy() < THRESHOLD_A
        rule_rows.append([name, str(small.sum()), str((small & flagged).sum()), str((~small).sum()),
                          str((~small & flagged).sum())])
    codes = ", ".join(f"{label} {code}" for label, code in CLASS_CODE.items())
    return [
        "### Separation", "",
        f"Per experiment and quantity: the threshold that misclassifies the fewest cases above {PEAK_LIMIT_PP:.0f} pp "
        "against the others of that experiment (a case is predicted above when its value lies on the given side), "
        "and that count; a quantity *separates* when the count is zero. An experiment without a case above the limit "
        f"is separated trivially. History class codes: {codes}. The history class separates experiment 2 from "
        "experiment 3 by construction, which is not a finding. A rule that needs 30 s of history can act only after "
        "those 30 s, and the error of those seconds stays in every score.", "",
        *md_table(["Experiment", "Cases above", "Quantity", "Best threshold", "Misclassified", "Separates"], rows), "",
        f"The {THRESHOLD_A} A rule of kind (i) on |I| of the start row (the prior it would set does not enter this "
        "replay):", "",
        *md_table(["Experiment", f"Starts below {THRESHOLD_A} A", "of them above 25 pp", "Starts at or above",
                   "of them above 25 pp"], rule_rows), ""]


def part2_lines(cases):
    return ["## Part 2: the 189 wrong-start cases under 3RC-D0 and the S2 settings", "",
            "Experiment 1 and the three wrong starts of every run are replayed with `run_ekf(record_state=True)`; "
            "every replay equals the stored trace of `results/runs/3rcd0/` row by row in SoC and predicted voltage. "
            "A value at s seconds is read at the first row at least s seconds after the start row, as the S11 replay "
            "did. The peak is the largest absolute SoC error inside the evaluation window, the value guard 7 counts.", "",
            *guard7_lines(cases), *others_lines(cases), *separation_lines(cases)]


def prior_label(prior, incumbent_prior):
    return f"{1000 * prior:.0f} mV (S2)" if prior == incumbent_prior else f"{1000 * prior:.0f} mV"


def prescreen_lines(screens, metrics, incumbent_prior):
    rows = [[prior_label(prior, incumbent_prior), *screen_cells(screen, metrics[prior])]
            for prior, screen in screens.items()]
    return ["### Step C's pre-screen quantities", "",
            f"Per prior value on the 40 Mix runs: the change of each temperature's experiment-1 mean against the S2 "
            f"value (step C's limit +{EXP1_LIMIT_PP:.2f} pp), the count of the 120 Mix wrong-start cases above "
            f"{PEAK_LIMIT_PP:.0f} pp (experiment 3 from the stored S2 traces) and the largest of their peaks, the "
            "experiments and temperatures whose reached count (experiments 2 and 3, as guard 6 counts them) is lower "
            "than at the S2 value, the selection metric (the mean over the six temperatures of the mean of the "
            "experiment-1, -2 and -4 Mix RMSEs) and whether the value qualifies under step C's pre-screen.", "",
            *md_table(["Prior", *SCREEN_HEADER], rows), ""]


def temperature_lines(history, tables, incumbent_prior):
    rows = []
    for prior, table in tables.items():
        for temp in T_GRID_DEGC:
            here = table[temp]
            rows.append([prior_label(prior, incumbent_prior), str(temp), str(here["runs"]), f"{here['exp1']:.4f}",
                         f"{here['exp2_mean']:.4f}", f"{here['exp4']:.4f}", str(here["exp2_above"]),
                         f"{here['exp2_peak']:.4f}", *[str(here[name]) for name in WRONG], marked_runs(history, temp)])
    return ["### Per temperature", "",
            "Mean SoC RMSE of each experiment over the Mix runs of a temperature, the experiment-2 count above "
            f"{PEAK_LIMIT_PP:.0f} pp and its largest peak, and the reached counts (runs whose error ends inside the "
            "2 pp band; experiment 3 is the S2 value at every prior).", "",
            *md_table(["Prior", "T (degC)", "Runs", "exp1 (pp)", "exp2 (pp)", "exp4 (pp)", "exp2 above 25 pp",
                       "exp2 largest peak (pp)", "exp2 reached", "exp3 low reached", "exp3 high reached",
                       "Marked runs"], rows), ""]


def run_lines(history, by_prior, incumbent_prior):
    exp1 = {prior: frame[frame.experiment == "exp1"].set_index(["folder", "file"]).rmse_pp
            for prior, frame in by_prior.items()}
    rows = []
    for row in history[history.split == "Mix"].itertuples():
        base = exp1[incumbent_prior][(row.folder, row.file)]
        rows.append([row.folder, row.cycle, row.mark, f"{base:.4f}",
                     *[f"{exp1[prior][(row.folder, row.file)] - base:+.4f}" for prior in PRIORS_V]])
    return ["### Experiment 1 per Mix run", "",
            "Experiment-1 SoC RMSE at the S2 value and its change at each prior value, in pp.", "",
            *md_table(["Folder", "Cycle", "Mark", "S2 (pp)", *[f"{1000 * prior:.0f} mV" for prior in PRIORS_V]], rows),
            ""]


def part3_lines(history, by_prior, tables, screens, metrics, deviation):
    incumbent_prior = next(iter(by_prior))
    return ["## Part 3: the branch prior alone on the 40 Mix runs", "",
            f"3RC-D0 under the S2 settings, with every branch voltage started at the prior value when the size of the "
            f"filter's input current on the first used row is below {THRESHOLD_A} A (in experiment 4 with its 0.2 A "
            f"offset) and at the S2 value, {1000 * incumbent_prior:.0f} mV, otherwise. Experiments 1, 2 and 4 run "
            "through the native evaluator of decision 1.50; experiment 3 is the stored S2 trace, because every Mix "
            f"experiment-3 start is above {THRESHOLD_A} A. The S2 rows are scored from the stored Python traces. Before "
            f"any number is used, the native evaluator at the S2 value reproduces the stored Python traces of "
            f"experiments 1, 2 and 4 on all 40 Mix runs within {NATIVE_TOLERANCE:g}: largest difference "
            f"{deviation[0]:.2e} in SoC and {deviation[1]:.2e} V in predicted voltage. The standard runs are not run. "
            "This is a selection on the calibration runs, in sample, and nothing here is a guard.", "", MARKS, "",
            *prescreen_lines(screens, metrics, incumbent_prior),
            *temperature_lines(history[history.split == "Mix"], tables, incumbent_prior),
            *run_lines(history, by_prior, incumbent_prior)]


def report_text(history, cases, by_prior, tables, screens, metrics, deviation):
    return "\n".join([
        "# Starts of the 3RC-D0 filter (S12 step A diagnostic)", "",
        "Generated by `make diagnose-starts`; decision 1.56.", "", DISCLOSURE, "",
        "3RC-D0 (`results/params_3rcd0.csv`) under the S2 settings (`results/ekf_config.json`). No filter equation "
        "changes. Parts 1 and 2 cover all 63 runs under the unchanged filter; part 3 runs the 40 Mix runs only. "
        "Per-case values are in `results/start_cases.csv`.", "",
        *part1_lines(history, cases), *part2_lines(cases),
        *part3_lines(history, by_prior, tables, screens, metrics, deviation)])
