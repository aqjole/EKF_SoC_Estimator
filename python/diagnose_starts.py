"""S12 step A diagnostic (decision 1.56): the history before each run, the 189 wrong-start cases of 3RC-D0 under the
S2 settings, and the branch prior alone on the 40 Mix runs. No filter equation changes, and no standard run is
filtered under a changed setting.

Writes results/start_cases.csv (one row per wrong-start case, with its run's history), results/start_cases.md and
results/plots/s12/start_cases.png. `start_cases.py` holds parts 1 and 2, `start_prior.py` part 3, `start_report.py`
the report text.
"""

from multiprocessing import Pool

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data_checks import file_records
from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.ekf import EkfConfig
from ekfsoc.plots import DOTS, MODEL_COLORS, TEMP_COLORS, save
from export_params import write_text
from run_all import CONFIG_JSON
from s10_protocol import RESULTS, splits
from s11_evaluate import WRONG
from s11_native import build
from s12_prescreen import EXP1_LIMIT_PP, PEAK_LIMIT_PP, prescreen, prior_metric
from start_cases import IN_RUN, UNKNOWN, replay_run, run_history, scan_record
from start_prior import NATIVE_TOLERANCE, PRIORS_V, THRESHOLD_A, prior_frame, prior_run, prior_table
from start_report import report_text


CSV = RESULTS / "start_cases.csv"
REPORT = RESULTS / "start_cases.md"
PLOT = RESULTS / "plots" / "s12" / "start_cases.png"
STORED_RESULTS = RESULTS / "ekf_results_3rcd0.csv"


def history_frame(specs, splits_of, records):
    """Part 1: one row per run, marked L when its first current is at or above THRESHOLD_A and U when unknown."""
    rows = []
    for spec in specs:
        row = {"split": splits_of[spec.path.name], "folder": spec.folder, "file": spec.path.name,
               "cycle": spec.cycle_name, "T_degC": spec.nominal_temp_degc, **run_history(spec, records)}
        marks = []
        if abs(row["i_first_A"]) >= THRESHOLD_A:
            marks.append("L")
        if row["run_class"] == UNKNOWN:
            marks.append("U")
        rows.append(row | {"mark": ", ".join(marks)})
    return pd.DataFrame(rows)


def case_frame(history, replays):
    """Part 2: the 189 cases with their run's history; an experiment-3 start is in-run by construction."""
    cases = history.merge(pd.DataFrame([row for rows in replays for row in rows]),
                          on=["folder", "file", "cycle", "T_degC"], validate="one_to_many")
    cases.insert(cases.columns.get_loc("run_class") + 1, "start_class",
                 np.where(cases.experiment == "exp2", cases.run_class, IN_RUN))
    return cases


def check_guard7(cases):
    """The cases above PEAK_LIMIT_PP must be those of results/ekf_results_3rcd0.csv, whose peaks they reproduce."""
    stored = pd.read_csv(STORED_RESULTS)
    stored = stored[stored.experiment.isin(WRONG)].merge(cases, on=["folder", "file", "experiment"])
    if len(stored) != len(cases) or not np.allclose(stored.max_abs_pp, stored.peak_abs_pp, rtol=0, atol=5.01e-5):
        raise ValueError("the replayed peaks differ from results/ekf_results_3rcd0.csv; rerun make ekf-3rcd0")
    if not (stored.max_abs_pp > PEAK_LIMIT_PP).equals(stored.peak_abs_pp > PEAK_LIMIT_PP):
        raise ValueError("the guard-7 cases differ from those of results/ekf_results_3rcd0.csv")


def plot(cases, tables, screens, metrics):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for name, color in zip(WRONG, MODEL_COLORS[1:]):
        here = cases[cases.experiment == name]
        axes[0, 0].plot(here.mean_abs_i_1s_A, here.peak_abs_pp, color=color, label=name, **DOTS)
    axes[0, 0].axhline(PEAK_LIMIT_PP, color="black", linewidth=0.5)
    axes[0, 0].set(xlabel="mean |I| over the first 1 s (A)", ylabel="peak |SoC error| in the window (pp)",
                   title="189 wrong starts, 3RC-D0 under S2")
    axes[0, 0].legend(frameon=False)
    s2 = next(iter(tables))
    priors_mv = [1000 * prior for prior in PRIORS_V]
    for temp in T_GRID_DEGC:
        color = TEMP_COLORS[temp]
        axes[0, 1].plot(priors_mv, [tables[p][temp]["exp2_mean"] for p in PRIORS_V], color=color, marker="o",
                        label=f"{temp} degC")
        axes[0, 1].axhline(tables[s2][temp]["exp2_mean"], color=color, linestyle="--", linewidth=0.8)
        axes[1, 0].plot(priors_mv, [screens[p]["exp1_change"][temp] for p in PRIORS_V], color=color, marker="o")
    axes[0, 1].set(xlabel="branch prior below 0.5 A (mV)", ylabel="experiment 2, Mix mean SoC RMSE (pp)",
                   title="40 Mix runs; dashed: S2 value")
    axes[0, 1].legend(frameon=False, fontsize=8)
    axes[1, 0].axhline(EXP1_LIMIT_PP, color="black", linewidth=0.5)
    axes[1, 0].set(xlabel="branch prior below 0.5 A (mV)", ylabel="experiment 1, Mix mean change vs S2 (pp)")
    axes[1, 1].plot(priors_mv, [metrics[p] for p in PRIORS_V], color=MODEL_COLORS[0], marker="o")
    axes[1, 1].axhline(metrics[s2], color=MODEL_COLORS[0], linestyle="--", linewidth=0.8)
    axes[1, 1].set(xlabel="branch prior below 0.5 A (mV)", ylabel="mean of the exp 1, 2, 4 Mix means (pp)")
    save(fig, PLOT)


def main():
    mix, standard = splits()
    specs = mix + standard
    splits_of = {spec.path.name: label for label, group in (("Mix", mix), ("standard", standard)) for spec in group}
    build()  # the native evaluator of 1.50, compiled once before the workers load it
    with Pool() as pool:
        records = pool.map(scan_record, file_records(), chunksize=1)
        replays = pool.map(replay_run, specs, chunksize=1)
        priors = pool.map(prior_run, mix, chunksize=1)
    history = history_frame(specs, splits_of, records)
    cases = case_frame(history, replays)
    check_guard7(cases)
    frame, deviation = prior_frame(priors)
    if deviation.max() > NATIVE_TOLERANCE:
        raise ValueError(f"the native evaluator differs from the stored Python traces by {deviation.max():.3g}")
    incumbent_prior = EkfConfig.from_json(CONFIG_JSON).p0_v_std
    by_prior = {prior: frame[frame.prior_V == prior] for prior in (incumbent_prior, *PRIORS_V)}
    tables = {prior: prior_table(here) for prior, here in by_prior.items()}
    screens = {prior: prescreen(here, by_prior[incumbent_prior]) for prior, here in by_prior.items()}
    metrics = {prior: prior_metric(table) for prior, table in tables.items()}
    cases.to_csv(CSV, index=False, float_format="%.4f")
    write_text(REPORT, report_text(history, cases, by_prior, tables, screens, metrics, deviation))
    plot(cases, tables, screens, metrics)


if __name__ == "__main__":
    main()
