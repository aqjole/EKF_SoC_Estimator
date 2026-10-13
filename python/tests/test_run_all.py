"""Smoke test of python/run_all.py on the committed fixture (one short run, no raw data), with a temporary cache folder.

The fixture is a 397-row 1C discharge at 25 degC (python/tests/fixtures/README.md). It is scored as a US06 run:
the cycle name only labels the rows. process_run is called in this process, as a pool worker would call it.
"""

import os

import numpy as np
import pytest

import run_all
from ekfsoc.constants import REPO_DIR
from ekfsoc.experiments import RunSpec

FIXTURE = REPO_DIR / "python" / "tests" / "fixtures" / "lghg2_excerpt.mat"
TRACES_NAME = "25degC__lghg2_excerpt.npz"


@pytest.fixture
def spec():
    return RunSpec(FIXTURE, "25degC", 25, "US06", False)


def test_process_run_scores_every_experiment(spec, tmp_path):
    rows = run_all.process_run(spec, tmp_path)

    assert [row["experiment"] for row in rows] == list(run_all.SCORED)
    exp1, exp2, exp3_low, exp3_high, exp4 = rows
    # exp1 starts at the reference, so its start is the first row; exp3 starts later, where the reference reaches 70 %.
    assert exp1["start_s"] == 0.0
    assert exp3_low["start_s"] > 0.0
    assert exp3_low["start_s"] == exp3_high["start_s"]
    assert exp2["soc0"] == pytest.approx(exp1["soc0"] - 0.20)
    # Only exp4 has an expected drift, and a positive offset (extra discharge) makes it negative.
    assert exp4["expected_drift_pp"] < 0.0
    assert all(np.isnan(row["expected_drift_pp"]) for row in rows[:4])


def test_process_run_saves_the_traces_and_one_plot_per_experiment(spec, tmp_path):
    run_all.process_run(spec, tmp_path)

    assert (tmp_path / TRACES_NAME).is_file()
    assert sorted(path.name for path in (tmp_path / "plots").iterdir()) == sorted(
        run_all.trace_name(experiment, spec) for experiment in run_all.SCORED)


def test_a_fresh_run_is_read_from_its_traces_and_gives_the_same_rows(spec, tmp_path):
    first = run_all.process_run(spec, tmp_path)
    traces = tmp_path / TRACES_NAME
    modified = traces.stat().st_mtime_ns

    again = run_all.process_run(spec, tmp_path)

    assert traces.stat().st_mtime_ns == modified  # not computed again
    assert repr(again) == repr(first)


def test_a_run_older_than_its_dependencies_is_computed_again(spec, tmp_path):
    run_all.process_run(spec, tmp_path)
    traces = tmp_path / TRACES_NAME
    old = run_all.DEPENDENCIES[0].stat().st_mtime_ns - 10**9
    os.utime(traces, ns=(old, old))

    run_all.process_run(spec, tmp_path)

    assert traces.stat().st_mtime_ns > old


def test_trace_name_of_the_example_runs():
    cold_mix = RunSpec(FIXTURE, "n20degC", -20, "Mix 1", False)
    assert run_all.trace_name("exp2", cold_mix) == "trace_exp2_Mix1_n20degC.png"
    assert run_all.trace_name("exp1", RunSpec(FIXTURE, "25degC", 25, "US06", False)) == "trace_exp1_US06_25degC.png"
