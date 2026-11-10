"""Step C's pre-screen of decision 1.56 (s12_prescreen) on synthetic scored rows: one Mix run per temperature."""

import math

import pandas as pd
import pytest

from ekfsoc.constants import T_GRID_DEGC
from run_all import SCORED
from s12_prescreen import prescreen, prior_metric, temperature_table, variant_metric


def scored(changes=None):
    """One run per temperature, every experiment at 1 pp RMSE, peak 10 pp and reached; `changes` maps
    (temperature, experiment) to the column values that differ."""
    changes = changes or {}
    rows = []
    for temp in T_GRID_DEGC:
        for experiment in SCORED:
            row = {"file": f"run_{temp}", "T_degC": temp, "experiment": experiment, "rmse_pp": 1.0,
                   "max_abs_pp": 10.0, "t_conv_s": 100.0}
            rows.append(row | changes.get((temp, experiment), {}))
    return pd.DataFrame(rows)


INCUMBENT = scored({(-20, "exp2"): {"max_abs_pp": 30.0}})


def test_the_incumbent_qualifies_against_itself():
    assert prescreen(INCUMBENT, INCUMBENT)["qualifies"]


def test_an_exp1_rise_of_the_limit_qualifies():
    candidate = scored({(-20, "exp2"): {"max_abs_pp": 30.0}, (0, "exp1"): {"rmse_pp": 1.0999}})
    assert prescreen(candidate, INCUMBENT)["qualifies"]


def test_an_exp1_rise_above_the_limit_at_one_temperature_does_not_qualify():
    candidate = scored({(-20, "exp2"): {"max_abs_pp": 30.0}, (0, "exp1"): {"rmse_pp": 1.11}})
    assert not prescreen(candidate, INCUMBENT)["qualifies"]


def test_more_cases_above_25_pp_do_not_qualify_with_a_lower_peak():
    candidate = scored({(-20, "exp2"): {"max_abs_pp": 26.0}, (-10, "exp3_low"): {"max_abs_pp": 26.0}})
    assert not prescreen(candidate, INCUMBENT)["qualifies"]


def test_a_higher_largest_peak_does_not_qualify_with_the_same_count():
    candidate = scored({(-20, "exp2"): {"max_abs_pp": 31.0}})
    assert not prescreen(candidate, INCUMBENT)["qualifies"]


@pytest.mark.parametrize("experiment", ["exp2", "exp3_low", "exp3_high"])
def test_a_lower_reached_count_of_experiments_2_and_3_does_not_qualify(experiment):
    candidate = scored({(-20, "exp2"): {"max_abs_pp": 30.0}, (10, experiment): {"t_conv_s": math.nan}})
    assert not prescreen(candidate, INCUMBENT)["qualifies"]


@pytest.mark.parametrize("experiment", ["exp1", "exp4"])
def test_the_reached_counts_of_experiments_1_and_4_are_not_screened(experiment):
    candidate = scored({(-20, "exp2"): {"max_abs_pp": 30.0}, (10, experiment): {"t_conv_s": math.nan}})
    assert prescreen(candidate, INCUMBENT)["qualifies"]


def test_the_prior_metric_averages_experiments_1_2_and_4_per_temperature_then_over_temperatures():
    frame = scored({(40, "exp2"): {"rmse_pp": 4.0}, (40, "exp3_low"): {"rmse_pp": 50.0}})
    assert prior_metric(temperature_table(frame)) == pytest.approx(1.0 + 3.0 / 3 / len(T_GRID_DEGC))


def test_the_variant_metric_is_the_experiment_1_mean_over_the_runs():
    frame = scored({(40, "exp1"): {"rmse_pp": 7.0}, (40, "exp2"): {"rmse_pp": 50.0}})
    assert variant_metric(frame) == pytest.approx(1.0 + 6.0 / len(T_GRID_DEGC))
