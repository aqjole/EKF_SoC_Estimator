"""The scoreboard numbers of summarize.py on synthetic scored rows: two Mix runs and one standard run."""

from pathlib import Path

import pandas as pd
import pytest

from ekfsoc.experiments import RunSpec
from run_all import SCORED
from summarize import MODELS, first_table, model_scores


def spec(name, folder, temp, cycle):
    return RunSpec(Path(f"{name}.mat"), folder, temp, cycle, False)


MIX = [spec("mix_a", "25degC", 25, "Mix 1"), spec("mix_b", "25degC", 25, "Mix 2")]
STANDARD = [spec("us06", "n10degC", -10, "US06")]

# Experiment-1 RMSE per run; every other experiment gets a fixed RMSE and peak unless PEAKS names the case.
EXP1 = {"mix_a": 1.0, "mix_b": 2.0, "us06": 6.0}
OTHER = {"exp2": 3.0, "exp3_low": 1.0, "exp3_high": 1.0, "exp4": 0.5}
PEAKS = {("mix_a", "exp2"): 30.0, ("us06", "exp3_high"): 26.0, ("us06", "exp1"): 40.0, ("mix_b", "exp3_low"): 25.0}


def scored():
    rows = []
    for run in [*MIX, *STANDARD]:
        name = run.path.stem
        for experiment in SCORED:
            rows.append({"folder": run.folder, "file": run.path.name, "cycle": run.cycle_name,
                         "T_degC": run.nominal_temp_degc, "experiment": experiment,
                         "rmse_pp": EXP1[name] if experiment == "exp1" else OTHER[experiment],
                         "max_abs_pp": PEAKS.get((name, experiment), 10.0)})
    return pd.DataFrame(rows)


SCORES = model_scores(scored(), MIX, STANDARD)


def test_experiment_1_mean_over_all_runs():
    assert SCORES["all"] == pytest.approx(3.0)


def test_experiment_1_mean_over_the_standard_runs():
    assert SCORES["standard"] == pytest.approx(6.0)


def test_experiment_1_mean_over_the_mix_runs():
    assert SCORES["mix"] == pytest.approx(1.5)


def test_worst_run_names_its_cycle_and_temperature():
    assert (SCORES["worst"], SCORES["worst_run"]) == (6.0, "US06, -10 degC")


def test_experiment_2_and_4_means():
    assert (SCORES["exp2"], SCORES["exp4"]) == (3.0, 0.5)


def test_wrong_starts_count_only_peaks_above_25_pp_in_experiments_2_and_3():
    assert SCORES["above"] == 2


def test_a_missing_run_stops_the_scoring():
    with pytest.raises(ValueError):
        model_scores(scored().iloc[5:], MIX, STANDARD)


def test_first_table_keeps_escaped_pipes_inside_a_cell(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("# Title\n\nText.\n\n| build | max \\|delta SoC\\| (pp) |\n|---|---|\n| float | 1.85e-02 |\n"
                      "\n| x |\n")
    assert first_table(report) == [{"build": "float", "max \\|delta SoC\\| (pp)": "1.85e-02"}]


def test_every_model_has_its_experiments_csv():
    assert [name for name, path, *_ in MODELS if not path.is_file()] == []
