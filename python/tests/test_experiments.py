"""Tests for ekfsoc.experiments: the evaluation list (needs the raw data) and the experiment cases.

The structure of experiment_runs is tested on a made-up run built with loader.build_run, so no raw
data is needed. The made-up run has 200 rows 10 s apart at 3 A, so the reference SoC falls by
3 * 10 / (3600 * 2.7807) = 0.2997 pp per row, from 1.0 to 0.404. It first reaches 0.70 at row 101
(row 100 is at 0.70029). The expected counts of the evaluation list are those of docs/decisions.md 1.5.
"""

from collections import Counter

import numpy as np
import pytest

from ekfsoc import rawio
from ekfsoc.constants import RAW_DIR, REPO_DIR
from ekfsoc.ekf import EkfConfig
from ekfsoc.experiments import (
    CYCLE_NAMES,
    EXCLUDED,
    OFFSET_A,
    TUNING_RUN,
    evaluation_runs,
    experiment_runs,
)
from ekfsoc.loader import build_run, find_runs
from ekfsoc.model import Params

# Row of the made-up run where the reference first reaches 0.70 (see the module docstring).
MADE_UP_EXP3_START = 101

# Noise settings for the structure tests; the values are made up and no result depends on them.
MADE_UP_CFG = EkfConfig(q_soc=1e-7, q_v=1e-6, r=1e-3)


def made_up_run():
    """A 25degC discharge of 200 rows 10 s apart at a constant 3 A, with a linearly falling voltage."""
    n = 200
    time = 10.0 * np.arange(n)
    fields = {
        "Time": time,
        "Voltage": np.linspace(4.15, 3.70, n),
        "Current": np.full(n, -3.0),  # the cycler writes discharge as negative current
        "Ah": -3.0 * time / 3600.0,
        "Battery_Temp_degC": np.full(n, 25.0),
    }
    return build_run(fields, file="made_up.mat", folder="25degC", test_type="us06")


@pytest.fixture(scope="module")
def params():
    return Params.from_csv(REPO_DIR / "results" / "s1" / "params.csv")


@pytest.fixture(scope="module")
def made_up_cases(params):
    return experiment_runs(made_up_run(), params, MADE_UP_CFG)


# --------------------------------------------------------------------------------------------
# experiment_runs on a made-up run
# --------------------------------------------------------------------------------------------


def test_experiment_names_and_keys(made_up_cases):
    assert list(made_up_cases) == ["exp1", "exp2", "exp3_low", "exp3_high", "exp3_ref", "exp4"]
    for name, case in made_up_cases.items():
        expected = {"soc", "v_pred", "cc", "start", "soc0"} | ({"expected_drift_pp"} if name == "exp4" else set())
        assert set(case) == expected, name


def test_starts_and_initial_soc(made_up_cases):
    """Experiment 1 starts at the reference, 2 is 20 pp low, 3 starts at row 101 with 50 / 90 / 70 %, 4 is 1."""
    expected = {
        "exp1": (0, 1.0),
        "exp2": (0, 0.8),
        "exp3_low": (MADE_UP_EXP3_START, 0.5),
        "exp3_high": (MADE_UP_EXP3_START, 0.9),
        "exp3_ref": (MADE_UP_EXP3_START, 0.7),
        "exp4": (0, 1.0),
    }
    for name, (start, soc0) in expected.items():
        case = made_up_cases[name]
        assert case["start"] == start, name
        assert case["soc0"] == pytest.approx(soc0, abs=1e-12), name
        assert case["cc"][start] == case["soc0"], name


def test_traces_are_nan_before_the_start_and_finite_after(made_up_cases):
    for name, case in made_up_cases.items():
        start = case["start"]
        for trace in ("soc", "v_pred", "cc"):
            assert np.all(np.isnan(case[trace][:start])), (name, trace)
            assert np.all(np.isfinite(case[trace][start:])), (name, trace)
            assert len(case[trace]) == 200


def test_offset_reaches_the_filter_and_the_counter(made_up_cases, params):
    """Experiment 4 differs from experiment 1 only by +0.2 A in the current.

    Counter: after 199 steps of 10 s it has removed an extra 0.2 * 1990 / (3600 Q_ref), which is the drift.
    Filter: at row 0 both have the prior [1, 0, 0], so Eq. 8 differs by R0 * 0.2 A, with R0 read at 25 degC, SoC 1.
    """
    exp1 = made_up_cases["exp1"]
    exp4 = made_up_cases["exp4"]

    counter_difference_pp = 100.0 * (exp4["cc"][-1] - exp1["cc"][-1])
    assert counter_difference_pp == pytest.approx(exp4["expected_drift_pp"], rel=1e-9)
    assert exp4["expected_drift_pp"] < 0.0  # extra discharge: the estimate falls below the reference
    assert exp4["expected_drift_pp"] == pytest.approx(-100.0 * 0.2 * 1990.0 / (3600.0 * 2.7807), rel=1e-9)

    r0_at_25_degc_full = params.r0[1, -1]  # row 1 of the temperature axis is 25 degC, the last SoC node is 1
    assert exp1["v_pred"][0] - exp4["v_pred"][0] == pytest.approx(r0_at_25_degc_full * OFFSET_A, rel=1e-9)


def test_cases_without_offset_do_not_see_it(made_up_cases):
    """exp1 and exp2 have the same current: the counters differ by the 20 pp of initial SoC and nothing else."""
    difference = made_up_cases["exp1"]["cc"] - made_up_cases["exp2"]["cc"]
    assert np.allclose(difference, 0.20, atol=1e-12)


def test_the_run_is_not_changed(params):
    run = made_up_run()
    arrays = {name: getattr(run, name).copy() for name in ("t", "i", "v", "temp", "ah_removed", "dt")}
    experiment_runs(run, params, MADE_UP_CFG)
    for name, before in arrays.items():
        assert np.array_equal(getattr(run, name), before), name


# --------------------------------------------------------------------------------------------
# The evaluation list (needs the raw data)
# --------------------------------------------------------------------------------------------


def file_key(path):
    """(folder, test number, test type) of a data file, the key of EXCLUDED."""
    return (path.parent.name, rawio.parse_filename(path.name)["test_number"], rawio.parse_filename(path.name)["test_type"])


@pytest.fixture(scope="module")
def specs():
    return evaluation_runs(RAW_DIR)


@pytest.mark.needs_data
def test_the_list_has_63_rows_and_one_tuning_run(specs):
    assert len(specs) == 63
    (tuning,) = [spec for spec in specs if spec.is_tuning]
    assert file_key(tuning.path) == TUNING_RUN == ("25degC", 551, "mixed1")
    assert (tuning.folder, tuning.nominal_temp_degc, tuning.cycle_name) == ("25degC", 25, "Mix 1")


@pytest.mark.needs_data
def test_62_evaluation_runs_per_temperature(specs):
    """docs/decisions.md 1.5: 40 degC 7, 25 degC 10, 10 degC 11, 0 degC 11, -10 degC 11, -20 degC 12."""
    counts = Counter(spec.nominal_temp_degc for spec in specs if not spec.is_tuning)
    assert counts == {40: 7, 25: 10, 10: 11, 0: 11, -10: 11, -20: 12}


@pytest.mark.needs_data
def test_excluded_files_are_absent_and_the_rest_are_all_there(specs):
    in_list = {file_key(spec.path) for spec in specs}
    assert len(in_list) == 63
    assert not in_list & set(EXCLUDED)
    assert not any("PausCycl" in spec.path.name for spec in specs)

    all_drive_files = {file_key(path) for test_type in CYCLE_NAMES for path in find_runs(RAW_DIR, test_type)}
    assert len(all_drive_files) == 70
    assert len(EXCLUDED) == 7
    assert all_drive_files == in_list | set(EXCLUDED)  # every excluded key is a real file


@pytest.mark.needs_data
def test_cells_without_a_run(specs):
    """docs/decisions.md 1.5: HWFET at 25, Mix 4 to 8 at 40, Mix 4 at -10, Mix 3 at 10 and 0 degC are n/a."""
    cells = {(spec.cycle_name, spec.nominal_temp_degc) for spec in specs}
    assert len(cells) == 63  # one run per cell
    all_cells = {(name, temp) for name in CYCLE_NAMES.values() for temp in (40, 25, 10, 0, -10, -20)}
    assert all_cells - cells == {
        ("HWFET", 25),
        ("Mix 4", 40), ("Mix 5", 40), ("Mix 6", 40), ("Mix 7", 40), ("Mix 8", 40),
        ("Mix 4", -10),
        ("Mix 3", 10), ("Mix 3", 0),
    }


@pytest.mark.needs_data
def test_the_list_is_grouped_by_temperature_in_table_order(specs):
    temps = [spec.nominal_temp_degc for spec in specs]
    assert [temp for n, temp in enumerate(temps) if n == 0 or temp != temps[n - 1]] == [40, 25, 10, 0, -10, -20]
    assert all(spec.path.parent.name == spec.folder for spec in specs)
    assert all(spec.path.is_file() for spec in specs)
