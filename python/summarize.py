"""The scoreboard of every filter model run in all four experiments, results/summary.md, from the committed per-stage
result files (decision 1.59).

Run from the repo root:  .venv/bin/python python/summarize.py   (or: make summary; the US06 check needs data/raw/)

  1. Filter models: one row per model with an experiments CSV, every one of its 63 runs scored the same way (the
     tuning run included): experiment-1 mean SoC RMSE over all runs, the 23 standard and the 40 Mix runs, the worst
     experiment-1 run, the experiment-2 and -4 means and the wrong-start cases above 25 pp.
  2. Experiment 1 by temperature: the experiment-1 mean of each model at each temperature.
  3. Open-loop voltage check: the US06 25 degC open-loop RMSE of each model's committed tables against the S1 gate.
  4. C builds: flash and the equivalence maxima of the 2RC and 3RC-D0 builds, read from the tables of their reports.
MODELS holds the hand-entered status of each model and the decision entries that record it; the fixed sentences of
scoring_section, filter_section and open_loop_section state the scoring conventions and the role of each run set.
"""

import re
from itertools import dropwhile, takewhile

import pandas as pd

import arm_footprint
from compare_3rcd import CANDIDATE_CSV as RESULTS_3RCD_CSV
from compare_3rcd import subset
from compare_3rcd0 import CANDIDATE_CSV as RESULTS_3RCD0_CSV
from compare_3rcd0n import CSV as RESULTS_3RCD0N_CSV
from compare_3rcd0p import CSV as RESULTS_3RCD0P_CSV
from compare_c import EQUIVALENCE_MD
from compare_c_3rcd0 import REPORT_MD as EQUIVALENCE_3RCD0_MD
from compare_r1c import RESULTS_RC_CSV, load_params_rc
from compare_r1d import RESULTS_RD_CSV, load_params_rd
from compare_r1i import RESULTS_RI_CSV, load_params_ri
from compare_r1l import RESULTS_RL_CSV, load_params_rl
from ekfsoc.constants import REPO_DIR, T_GRID_DEGC
from ekfsoc.model import Params
from export_params import PARAMS_CSV, md_table, write_text
from fit_3rc import PARAMS_3RC_CSV
from fit_3rc_rest import PARAMS_REST_CSV
from fit_3rcd import load_params_3rcd
from fit_3rcd0 import load_candidate
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, validate_us06
from run_all import RESULTS_CSV
from s10_protocol import DISCLOSURE, splits
from s11_evaluate import WRONG
from s12_prescreen import PEAK_LIMIT_PP, temperature_table, wrong_start_peaks


SUMMARY_MD = REPO_DIR / "results" / "summary.md"

# (model, experiments CSV, status, decision entries of docs/decisions.md that record the status).
MODELS = (
    ("2RC", RESULTS_CSV, "v1.0 baseline, the default C build", "1.15, 1.55"),
    ("2RC-I", RESULTS_RI_CSV, "adopted, replaced in S10", "1.31, 1.45"),
    ("2RC-Id", RESULTS_RD_CSV, "not adopted", "1.34"),
    ("2RC-Ic", RESULTS_RC_CSV, "not adopted", "1.36"),
    ("2RC-Il", RESULTS_RL_CSV, "not adopted", "1.38"),
    ("3RC-D", RESULTS_3RCD_CSV, "not adopted", "1.43"),
    ("3RC-D0", RESULTS_3RCD0_CSV, "deployment model", "1.45, 1.54, 1.55"),
    ("3RC-D0-N", RESULTS_3RCD0N_CSV, "not adopted", "1.51"),
    ("3RC-D0-P", RESULTS_3RCD0P_CSV, "not adopted", "1.58"),
)

# (tables, the folder of their stage, loader) for the open-loop check; 3RC-D0-N and 3RC-D0-P run the 3RC-D0 tables.
TABLES = (
    ("2RC", "s1", lambda: Params.from_csv(PARAMS_CSV)),
    ("3RC, first fit", "s6", lambda: Params.from_csv(PARAMS_3RC_CSV)),
    ("3RC, second fit", "s6", lambda: Params.from_csv(PARAMS_REST_CSV)),
    ("2RC-I", "s7", load_params_ri),
    ("2RC-Id", "s8", load_params_rd),
    ("2RC-Ic", "s8", load_params_rc),
    ("2RC-Il", "s8", load_params_rl),
    ("3RC-D", "s9", load_params_3rcd),
    ("3RC-D0", "s10", load_candidate),
)

# (build, footprint report, equivalence report).
C_BUILDS = (
    ("2RC, the default build", arm_footprint.MODELS["2rc"][3], EQUIVALENCE_MD),
    ("3RC-D0, -DEKF_USE_3RCD0=ON", arm_footprint.MODELS["3rcd0"][3], EQUIVALENCE_3RCD0_MD),
)


def stage(path):
    """The stage of a result file, from its folder: results/s7/... is S7."""
    return path.parent.name.upper()


def experiment(frame, name):
    return frame[frame["experiment"] == name]


def model_scores(frame, mix, standard):
    """The scoreboard numbers of one model's scored rows; mix and standard are the run specs of the two splits."""
    first = subset(experiment(frame, "exp1"), [*mix, *standard])
    worst = first.loc[first["rmse_pp"].idxmax()]
    return {"all": first["rmse_pp"].mean(), "standard": subset(first, standard)["rmse_pp"].mean(),
            "mix": subset(first, mix)["rmse_pp"].mean(), "worst": worst["rmse_pp"],
            "worst_run": f"{worst['cycle']}, {worst['T_degC']} degC",
            "exp2": experiment(frame, "exp2")["rmse_pp"].mean(), "exp4": experiment(frame, "exp4")["rmse_pp"].mean(),
            "above": wrong_start_peaks(frame)[0]}


def filter_section(frames, mix, standard):
    runs = len(mix) + len(standard)
    header = ["Model", "Stage", "Status", "Decision", f"Exp 1, {runs} runs", f"Exp 1, {len(standard)} standard",
              f"Exp 1, {len(mix)} Mix", "Exp 1, worst run", "Exp 2", "Exp 4",
              f"Wrong starts above {PEAK_LIMIT_PP:.0f} pp (of {len(WRONG) * runs})"]
    rows = []
    for name, path, status, decision in MODELS:
        score = model_scores(frames[name], mix, standard)
        rows.append([name, stage(path), status, decision,
                     *[f"{score[key]:.2f}" for key in ("all", "standard", "mix")],
                     f"{score['worst']:.2f} ({score['worst_run']})", f"{score['exp2']:.2f}", f"{score['exp4']:.2f}",
                     str(score["above"])])
    return ["## Filter models", "",
            f"Mean SoC RMSE in pp over the {runs} runs of each model's experiments CSV. The Mix and {runs}-run "
            "columns are not validation: 3RC-D and 3RC-D0 are fitted on the Mix runs (decisions 1.41, 1.44), "
            "3RC-D0-N is tuned (1.49) and 3RC-D0-P screened (1.57) on them, and every filter but 3RC-D0-N runs the "
            "noise settings of 1.15, tuned on Mix 1 at 25 degC (3RC-D0-P with a 10 mV branch prior at a start below "
            "0.5 A). The standard runs are a repeatedly inspected "
            "regression set (1.32, 1.44). A status follows its stage's adoption rule, not these means; from S9 on "
            "that rule is judged on the standard runs, with guards on all runs and the Mix runs added in S11 and "
            "S12 (1.48).", "",
            *md_table(header, rows)]


def scoring_section(frame, mix, standard):
    """How every row is scored; frame is any model's rows, which name the tuning run."""
    tuning = experiment(frame[frame["is_tuning"]], "exp1").iloc[0]
    return ["## Scoring", "",
            f"Every model's {len(mix) + len(standard)} runs are scored the same way, the tuning run ({tuning['cycle']} "
            f"at {tuning['T_degC']} degC) included. The stage reports of S2 to S8 score 62 runs and flag the tuning "
            "run, so their means differ slightly from these. The standard runs are the UDDS, HWFET, LA92 and US06 "
            "runs, the Mix runs the others (`fit_3rcd.drive_split`). Experiment 1 starts at the correct SoC, "
            "experiment 2 at a SoC 20 pp too low, experiment 3 restarts at 50 % (low) or 90 % (high) when the "
            "reference is 70 %, and experiment 4 adds a current offset. A wrong start is a case of experiment 2, 3 low "
            f"or 3 high; it counts when its largest SoC error exceeds {PEAK_LIMIT_PP:.0f} pp (guard 7 of decision "
            "1.48). Each status is the one the listed entries of `docs/decisions.md` record."]


def temperature_section(frames):
    tables = {name: temperature_table(frames[name]) for name, *_ in MODELS}
    runs = tables[MODELS[0][0]]
    header = ["Model", *[f"{temp} degC, {runs[temp]['runs']} runs (pp)" for temp in T_GRID_DEGC]]
    rows = [[name, *[f"{tables[name][temp]['exp1']:.2f}" for temp in T_GRID_DEGC]] for name, *_ in MODELS]
    return ["## Experiment 1 by temperature", "", "Mean experiment-1 SoC RMSE over every run at each temperature.", "",
            *md_table(header, rows)]


def open_loop_section():
    rows = []
    for name, folder, load in TABLES:
        rmse = validate_us06(load(), GATE_TEMP_DEGC)["rmse_mv"]
        rows.append([name, folder.upper(), f"{rmse:.2f}", "pass" if rmse <= GATE_RMSE_MV else "fail"])
    return ["## Open-loop voltage check", "",
            f"US06 at {GATE_TEMP_DEGC} degC, open-loop RMSE over all rows, recomputed from each model's committed "
            f"tables with `fit_all.validate_us06`; the S1 gate is {GATE_RMSE_MV:.0f} mV, a bug check rather than a "
            "target. 3RC-D0-N and 3RC-D0-P change only filter settings and run on the 3RC-D0 tables.", "",
            *md_table(["Tables", "Stage", "RMSE (mV)", f"Gate ({GATE_RMSE_MV:.0f} mV)"], rows)]


def first_table(path):
    """The first markdown table of a result file, one dict per body row keyed by the header cells."""
    lines = path.read_text().splitlines()
    table = list(takewhile(lambda line: line.startswith("|"), dropwhile(lambda line: not line.startswith("|"), lines)))
    header, _, *body = [[cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]] for line in table]
    return [dict(zip(header, row)) for row in body]


def c_section():
    maximum = r"max \|delta SoC\| (pp)"
    rows = []
    for build, footprint_md, equivalence_md in C_BUILDS:
        total = next(row for row in first_table(footprint_md) if row["object"] == "total")
        builds = {row["build"]: row[maximum] for row in first_table(equivalence_md)}
        reports = ", ".join(f"[`{path.relative_to(SUMMARY_MD.parent)}`]({path.relative_to(SUMMARY_MD.parent)})"
                            for path in (footprint_md, equivalence_md))
        flash = int(total[".text"]) + int(total[".data"])
        rows.append([build, f"{flash:,}", builds["float"], builds["double"], reports])
    return ["## C builds", "",
            "Flash is .text plus .data of the library objects on a Cortex-M4, from the total row of each footprint "
            "report; the maxima are the float and double rows of each equivalence report's result table, which states "
            "the cases it compares. The state of one filter, sizeof(ekf_t), is given in the text of the footprint "
            "reports and is not copied here.", "",
            *md_table(["Build", "Flash (B)", "Float: max \\|delta SoC\\| (pp)", "Double: max \\|delta SoC\\| (pp)",
                       "Reports"], rows)]


def summary_text(frames, mix, standard):
    lines = ["# Scoreboard of the filter models", "",
             "Generated by `python/summarize.py` (`make summary`) from the committed result files; do not edit. "
             "What every result file holds and which script writes it: [`results/README.md`](README.md).",
             DISCLOSURE, "",
             *scoring_section(frames[MODELS[0][0]], mix, standard), "",
             *filter_section(frames, mix, standard), "",
             *temperature_section(frames), "",
             *open_loop_section(), "",
             *c_section()]
    return "\n".join(lines) + "\n"


def main():
    mix, standard = splits()
    frames = {name: pd.read_csv(path) for name, path, *_ in MODELS}
    write_text(SUMMARY_MD, summary_text(frames, mix, standard))
    print(f"wrote {SUMMARY_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
