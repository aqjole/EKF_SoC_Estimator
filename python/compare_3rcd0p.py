"""S12 step C: 3RC-D0-P against 3RC-D0 under the S2 settings on all 63 runs (docs/decisions.md 1.57).

Run from the repo root:  .venv/bin/python python/compare_3rcd0p.py
(or: make ekf-3rcd0p; needs ekf-3rcd0 and diagnose-starts)

  1. results/s12/ekf_config_3rcd0p.json is the S2 settings of results/s2/ekf_config.json plus p0_v_std_rested = 0.010 V:
     a filter whose first processed row has an input current below 0.5 A starts its branches at 10 mV
     (ekfsoc.ekf.branch_std).
  2. Every case of experiments.experiment_runs (378 on the 63 runs) is computed by the Python filter; traces go to
     results/runs/3rcd0p/ and are reused while fresh. The incumbent is read from results/s10/ekf_results_3rcd0.csv and
     results/runs/3rcd0/, after checking that the two agree.
  3. results/s12/ekf_results_3rcd0p.csv has the rows and columns of results/s10/ekf_results_3rcd0.csv; as there, the tuning
     run keeps its flag and every guard and table scores it with the others. results/s12/model_compare_3rcd0p.md gives
     the eight guards of 1.48, decided as 1.35 amends 1.32, the verdict and the tables 1.57 lists;
     results/plots/s12/model_compare_3rcd0p.png draws the experiment-1 means.
  4. The Mix-run means of experiments 1, 2 and 4 must repeat step A part 3 (results/s12/start_cases.md) to the printed
     precision, or the script stops.
"""

import argparse
from dataclasses import replace
from multiprocessing import Pool

import pandas as pd

from compare_3rcd import subset
from compare_3rcd0 import RUNS_DIR as RUNS_3RCD0
from compare_3rcd0n import verify_incumbent
from compare_r1c import scored_frame
from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.ekf import EkfConfig, branch_std
from ekfsoc.experiments import experiment_cases
from ekfsoc.loader import load_run
from ekfsoc.metrics import CONV_BAND_PP, PP, band_times, max_abs_pp, rmse_pp, window_mask
from export_params import write_text
from fit_3rcd0 import load_candidate
from fit_all import validate_us06
from run_all import CONFIG_JSON, load_traces
from s10_protocol import RESULTS, splits, verify_baseline
from s11_evaluate import evaluate, trace_path
from s11_report import OLD, guards, plot
from s12_prescreen import temperature_table
from s12_report import GUARDS, report_text
from s8_compare import decided_guards
from start_report import prior_label


NEW = "3RC-D0-P"
RESTED_PRIOR_V = 0.010  # decision 1.57: the qualifying value of lowest metric in step A part 3
CONFIG = RESULTS / "s12" / "ekf_config_3rcd0p.json"
RUNS = RESULTS / "runs" / "3rcd0p"
CSV = RESULTS / "s12" / "ekf_results_3rcd0p.csv"
COMPARISON = RESULTS / "s12" / "model_compare_3rcd0p.md"
PLOT = RESULTS / "plots" / "s12" / "model_compare_3rcd0p.png"
START_CASES_MD = RESULTS / "s12" / "start_cases.md"
PART3_COLUMNS = {"exp1": "exp1", "exp2": "exp2_mean", "exp4": "exp4"}  # part 3 column -> temperature_table key


def write_config():
    """The S2 settings plus the rested branch prior."""
    replace(EkfConfig.from_json(CONFIG_JSON), p0_v_std_rested=RESTED_PRIOR_V).to_json(CONFIG)


def run_priors(spec):
    """One row per experiment of one run: the input current on its first processed row (offset included) and the
    branch prior the candidate filter takes from it."""
    run, cfg = load_run(spec.path), EkfConfig.from_json(CONFIG)
    rows = []
    for name, (_, start, offset) in experiment_cases(run).items():
        current = float(run.i[start] + offset)
        rows.append({"folder": spec.folder, "file": spec.path.name, "cycle": spec.cycle_name,
                     "T_degC": spec.nominal_temp_degc, "experiment": name, "start": start,
                     "current_A": current, "prior_V": branch_std(cfg, current)})
    return rows


def evaluate_run(spec):
    """Scored rows of the incumbent and the candidate, and the candidate's priors, for one run."""
    return evaluate(spec, CONFIG, RUNS), run_priors(spec)


def comparator_scores(path):
    """RMSE (pp), peak (pp) and time to the 2 pp band (s, NaN if never) of the unscored exp3_ref case of a trace."""
    t, _, reference, cases = load_traces(path)
    case = cases["exp3_ref"]
    mask = window_mask(reference, case["start"])
    err = case["soc"] - reference
    _, t_conv = band_times(t - t[case["start"]], PP * err, mask, CONV_BAND_PP)
    return rmse_pp(err, mask), max_abs_pp(err, mask), float("nan") if t_conv is None else t_conv


def restart_cases(frames, priors, specs):
    """The experiment-3 cases whose start gets the rested prior, old and new: RMSE, peak, convergence and forgetting
    times (scored cases from the CSVs, the comparator from the traces)."""
    rows = []
    rested = priors[priors.experiment.str.startswith("exp3") & (priors.prior_V == RESTED_PRIOR_V)]
    by_key = {(spec.folder, spec.path.name): spec for spec in specs}
    for row in rested.itertuples():
        values = {}
        for name, frame in frames.items():
            if row.experiment == "exp3_ref":
                folder = RUNS_3RCD0 if name == OLD else RUNS
                rmse, peak, t_conv = comparator_scores(trace_path(by_key[(row.folder, row.file)], folder))
                values[name] = (rmse, peak, t_conv, float("nan"))
            else:
                here = frame[(frame.folder == row.folder) & (frame.file == row.file)
                             & (frame.experiment == row.experiment)].iloc[0]
                values[name] = (here.rmse_pp, here.max_abs_pp, here.t_conv_s, here.t_forget_s)
        rows.append((row, values))
    return rows


def part3_check(raw, mix):
    """Rows [T, experiment, part 3, this run] of the Mix means of experiments 1, 2 and 4 at the rested prior; raises
    if any differs from step A part 3 (results/s12/start_cases.md) at its printed precision."""
    section = START_CASES_MD.read_text().split("## Part 3", 1)[1].split("### Per temperature", 1)[1]
    section = section.split("\n### ", 1)[0]
    label = prior_label(RESTED_PRIOR_V, EkfConfig.from_json(CONFIG_JSON).p0_v_std)
    printed = {}
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == label:
            printed[int(cells[1])] = dict(zip(PART3_COLUMNS, cells[3:6]))
    if set(printed) != set(T_GRID_DEGC):
        raise ValueError(f"results/s12/start_cases.md has no part-3 row of {label} at every temperature")
    table = temperature_table(subset(raw, mix))
    rows = [[str(temp), name, printed[temp][name], f"{table[temp][key]:.4f}"]
            for temp in T_GRID_DEGC for name, key in PART3_COLUMNS.items()]
    if any(row[2] != row[3] for row in rows):
        raise ValueError("Mix-run means differ from step A part 3 in results/s12/start_cases.md")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    verify_baseline()
    write_config()
    mix, standard = splits()
    specs = mix + standard
    voltage = validate_us06(load_candidate(), 25)["rmse_mv"]
    print("Python evaluation: all 378 cases of the 63 runs", flush=True)
    with Pool(args.workers) as pool:
        results = []
        for i, result in enumerate(pool.imap(evaluate_run, specs, chunksize=1), 1):
            results.append(result)
            if i % 7 == 0:
                print(f"Evaluated {i}/63", flush=True)
    raw = {name: scored_frame([scores[k] for scores, _ in results]) for k, name in enumerate((OLD, NEW))}
    priors = pd.DataFrame([row for _, rows in results for row in rows])
    frozen = pd.read_csv(RESULTS / "s10" / "ekf_results_3rcd0.csv")
    verify_incumbent(raw[OLD], frozen)
    raw[NEW].to_csv(CSV, index=False, float_format="%.4f")
    frames = {OLD: frozen, NEW: pd.read_csv(CSV)}
    decided = decided_guards(guards(frames, mix, standard, voltage), guards(raw, mix, standard, voltage))
    print("Guard result: " + ", ".join(f"{name}={'PASS' if row[2] else 'FAIL'}"
                                       for row, (name, _) in zip(decided, GUARDS)), flush=True)
    part3 = part3_check(raw[NEW], mix)
    write_text(COMPARISON, report_text(frames, mix, standard, decided, priors, restart_cases(frames, priors, specs),
                                       part3, RESTED_PRIOR_V))
    plot(frames, mix, standard, PLOT)
    print(f"{NEW} " + ("ADOPTED" if all(row[2] for row in decided) else "NOT ADOPTED"), flush=True)


if __name__ == "__main__":
    main()
