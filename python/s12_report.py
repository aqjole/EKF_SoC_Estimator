"""Text of results/s12/model_compare_3rcd0p.md, the S12 step C comparison (docs/decisions.md 1.57).

frames maps "3RC-D0" (the incumbent under the S2 settings) and then "3RC-D0-P" to its results frame; the split and
experiment-1 tables are those of the S11 A report (s11_report).
"""

import math

import pandas as pd

from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.ekf import RESTED_CURRENT_A
from export_params import md_table
from s10_protocol import DISCLOSURE
from s11_evaluate import WRONG
from s11_report import exp1_lines, split_lines
from s12_prescreen import PEAK_LIMIT_PP


# The name and limit of each guard of decision 1.48, in guard order. The names replace those of
# s11_report.guards, which also writes the S11 step A report and so keeps its own.
GUARDS = (("1. S1 gate", "at most 30 mV (inherited: no table changes)"),
          ("2. Standard-run improvement", "lower at 4 or more of 6 temperatures, higher at none by more than 0.10 pp"),
          ("3. Largest run increase", "no run higher by more than 0.50 pp"),
          ("4. Largest cycle increase", "no cycle mean higher by more than 0.25 pp"),
          ("5. Worst run", "not above the incumbent's worst run"),
          ("6. Experiment-4 means and reached counts",
           "experiment-4 mean higher at no temperature by more than 0.10 pp; no reached count lower"),
          ("7. Wrong-start peaks", f"count above {PEAK_LIMIT_PP:.0f} pp and largest peak not above the incumbent's"),
          ("8. Mix-run means", "Mix experiment-1 mean higher at no temperature by more than 0.10 pp"))
EXPERIMENTS = ("exp1", "exp2", "exp3_low", "exp3_high", "exp3_ref", "exp4")


def number(value, digits):
    return "n/a" if value is None or math.isnan(value) else f"{value:.{digits}f}"


def pair(frames, cell):
    """One table cell holding cell(frame) of each frame, joined in frame order."""
    return " / ".join(cell(frame) for frame in frames.values())


def largest_case(peaks):
    """Text naming the case of the largest peak of a series indexed like peak_lines' frames."""
    _, _, cycle, temp, experiment = peaks.idxmax()
    return f"{cycle} at {temp} degC, {experiment}"


def guard_lines(decided):
    """The guard table with each guard's limit and margin, and the verdict."""
    rows = [[name, value, limit, number(margin, 4) if math.isfinite(margin) else "n/a",
             "PASS" if passed else "FAIL"] for (_, value, passed, margin), (name, limit) in zip(decided, GUARDS)]
    verdict = "ADOPTED" if all(row[2] for row in decided) else "NOT ADOPTED"
    return ["## Guards and verdict", "",
            "The eight guards of decision 1.48 against 3RC-D0 under `results/s2/ekf_config.json`, evaluated as 1.35 amends "
            "1.32: on the values of the results CSVs, recomputed from the unrounded traces where the margin (the "
            "smallest distance of a compared value from its limit, or of two compared values from each other, taken "
            "over the RMSE and peak values, not over the integer counts) is below 1e-4. Guard 2 uses the 23 standard runs, guards 3 to 7 all 63, guard 8 the 40 Mix runs; the "
            "tuning run is scored with the others. Guard 1 is recomputed from the unchanged 3RC-D0 tables.", "",
            *md_table(["Guard", "Value", "Limit", "Margin", "Result"], rows), "", f"**{verdict}.**", ""]


def exp2_lines(frames):
    """Experiment 2 per temperature over the 63 runs, the rule off (3RC-D0) beside the rule on."""
    old, new = frames
    rows = []
    for temp in T_GRID_DEGC:
        here = {name: frame[(frame.T_degC == temp) & (frame.experiment == "exp2")] for name, frame in frames.items()}
        rows.append([str(temp), str(len(here[new])), *[f"{frame.rmse_pp.mean():.4f}" for frame in here.values()],
                     f"{here[new].rmse_pp.mean() - here[old].rmse_pp.mean():+.4f}",
                     pair(here, lambda frame: str(int((frame.max_abs_pp > PEAK_LIMIT_PP).sum()))),
                     pair(here, lambda frame: f"{frame.max_abs_pp.max():.4f}"),
                     pair(here, lambda frame: str(int(frame.t_conv_s.notna().sum()))),
                     pair(here, lambda frame: number(frame.t_conv_s.median(), 1))])
    return ["## Experiment 2: the rule off and on", "",
            f"Start 20 pp below the reference at row 0, all 63 runs. Pairs are {old} / {new} (the rule off / on).", "",
            *md_table(["T (degC)", "Runs", f"{old} RMSE (pp)", f"{new} RMSE (pp)", "Change (pp)",
                       f"Above {PEAK_LIMIT_PP:.0f} pp", "Largest peak (pp)", "Reached", "Median t_conv (s)"], rows), ""]


def peak_lines(frames):
    """The wrong-start cases above PEAK_LIMIT_PP under either filter, with both peaks."""
    old, new = frames
    keys = ["folder", "file", "cycle", "T_degC", "experiment"]
    wrong = {name: frame[frame.experiment.isin(WRONG)].set_index(keys).max_abs_pp for name, frame in frames.items()}
    both = pd.DataFrame({name: peaks for name, peaks in wrong.items()})
    above = both[(both > PEAK_LIMIT_PP).any(axis=1)].reset_index()
    rows = [[row.folder, row.cycle, row.experiment, f"{row[old]:.4f}", f"{row[new]:.4f}"]
            for _, row in above.iterrows()]
    summary = [[name, str(len(peaks)), str(int((peaks > PEAK_LIMIT_PP).sum())),
                *[str(int((peaks.xs(exp, level="experiment") > PEAK_LIMIT_PP).sum())) for exp in WRONG],
                f"{peaks.max():.4f}", largest_case(peaks)] for name, peaks in wrong.items()]
    return [f"## Wrong-start cases above {PEAK_LIMIT_PP:.0f} pp", "",
            "The 189 wrong-start cases (experiments 2, 3 low and 3 high on the 63 runs), peak absolute SoC error "
            "inside the evaluation window.", "",
            *md_table(["Filter", "Cases", f"Above {PEAK_LIMIT_PP:.0f} pp", *[f"of them {exp}" for exp in WRONG],
                       "Largest (pp)", "Largest case"], summary), "",
            f"Every case above {PEAK_LIMIT_PP:.0f} pp under either filter:", "",
            *md_table(["Folder", "Cycle", "Experiment", f"{old} peak (pp)", f"{new} peak (pp)"], rows), ""]


def prior_lines(priors, rested_v, load_v):
    """Counts of the branch prior each of the 378 cases received, and the cases off the experiment pattern."""
    label = {rested_v: f"{1000 * rested_v:.0f} mV", load_v: f"{1000 * load_v:.0f} mV"}
    rows = [[exp, *[str(int(((priors.experiment == exp) & (priors.prior_V == value)).sum())) for value in label]]
            for exp in EXPERIMENTS]
    restarts = priors[priors.experiment.str.startswith("exp3") & (priors.prior_V == rested_v)]
    row0 = priors[~priors.experiment.str.startswith("exp3") & (priors.prior_V == load_v)]
    listed = lambda frame: [[row.folder, row.cycle, row.experiment, f"{row.current_A:+.4f}"]
                            for row in frame.itertuples()]
    return ["## Branch prior of each case", "",
            f"The candidate's initial branch standard deviation is {label[rested_v]} when the size of the input "
            f"current on the first processed row (row 0 in experiments 1, 2 and 4, with the 0.2 A offset in "
            f"experiment 4; the restart row in experiment 3) is below {RESTED_CURRENT_A} A, and {label[load_v]} "
            "otherwise. Counts over the 63 runs:", "",
            *md_table(["Experiment", *[f"{text} cases" for text in label.values()]], rows), "",
            f"Experiment-3 cases that get {label[rested_v]}:", "",
            *md_table(["Folder", "Cycle", "Experiment", "First current (A)"], listed(restarts)), "",
            f"Row-0 cases (experiments 1, 2 and 4) that keep {label[load_v]}:", "",
            *md_table(["Folder", "Cycle", "Experiment", "First current (A)"], listed(row0)), "",
            f"Every case not listed takes its experiment's default: {label[rested_v]} on row 0 (experiments 1, 2 "
            f"and 4), {label[load_v]} at the restart (experiment 3).", ""]


def restart_lines(restarts, frames):
    """The experiment-3 cases that start below RESTED_CURRENT_A, old against new."""
    rows = []
    for row, values in restarts:
        cells = [row.folder, row.cycle, row.experiment]
        for k, digits in ((0, 4), (1, 4), (2, 1), (3, 1)):
            cells += [" / ".join(number(values[name][k], digits) for name in values)]
        rows.append(cells)
    names = " / ".join(frames)
    return ["## Experiment-3 starts below the threshold", "",
            "The restart cases whose first current is below the threshold, so that the candidate starts them with the "
            f"rested prior although the branches are polarised (decision 1.57). Pairs are {names}. Reached at is "
            "t_conv, the time after the start from which the error stays inside +-2 pp (n/a: never); the forgetting "
            "time is against exp3_ref, which is not scored itself and changes with the rule too.", "",
            *md_table(["Folder", "Cycle", "Experiment", "RMSE (pp)", "Peak (pp)", "Reached at (s)",
                       "Forgetting time (s)"], rows), ""]


def part3_lines(rows):
    return ["## Agreement with step A part 3", "",
            "Mix-run means of experiments 1, 2 and 4 at the rested prior: step A part 3 (`results/s12/start_cases.md`, "
            "the native evaluator) against this run (the Python filter). The script stops if any printed value "
            "differs.", "",
            *md_table(["T (degC)", "Experiment", "Part 3 (pp)", "This run (pp)"], rows), ""]


def report_text(frames, mix, standard, decided, priors, restarts, part3, rested_v):
    old, new = frames
    load_v = float(priors.prior_V.max())
    lines = [f"# {new} against {old} (S12 step C)", "",
             "Generated by `make ekf-3rcd0p` (`python/compare_3rcd0p.py`); decision 1.57.", "",
             DISCLOSURE, "",
             "The standard runs were inspected before this run (decision 1.57 lists the earlier looks), so they serve "
             "here as regression runs, not as independent validation.", "",
             f"{new} is 3RC-D0 under `results/s2/ekf_config.json` with one change (`results/s12/ekf_config_3rcd0p.json`): "
             f"when the size of the filter's input current on the first row it processes is below "
             f"{RESTED_CURRENT_A} A, every branch starts with a standard deviation of {1000 * rested_v:.0f} mV "
             f"instead of {1000 * load_v:.0f} mV. All 378 cases are computed by the Python filter.", "",
             *guard_lines(decided), *exp2_lines(frames), *peak_lines(frames), *prior_lines(priors, rested_v, load_v),
             *restart_lines(restarts, frames), *part3_lines(part3), *split_lines(frames, mix, standard), *exp1_lines(frames)]
    return "\n".join(lines)
