"""The rules of S12 step A (decision 1.56) on synthetic inputs: the history class, the separation threshold and the
measures of one wrong-start case. The current rule that chooses the branch prior is the filter's (test_ekf.py)."""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from start_cases import RESTED, UNKNOWN, best_threshold, case_measures, history_class, span_end


def test_a_long_rest_and_a_short_gap_make_a_rested_start():
    assert history_class(3660.0, 2.0) == RESTED


def test_a_rest_shorter_than_600_s_is_unknown():
    assert history_class(599.0, 2.0) == UNKNOWN


def test_a_gap_longer_than_60_s_is_unknown():
    assert history_class(3660.0, 61.0) == UNKNOWN


def test_no_previous_file_is_unknown():
    assert history_class(math.nan, math.nan) == UNKNOWN


def test_the_first_row_at_least_the_span_after_the_start_is_read():
    t = np.arange(0.0, 5.0, 0.5)
    assert span_end(t, 2, 1.0) == 4


def test_a_span_beyond_the_run_reads_its_last_row():
    t = np.arange(0.0, 5.0, 0.5)
    assert span_end(t, 2, 30.0) == 9


def test_a_separating_threshold_misclassifies_nothing():
    values = np.array([0.1, 0.2, 1.5, 1.7])
    assert best_threshold(values, np.array([False, False, True, True])) == (0.85, ">", 0)


def test_a_flag_below_the_threshold_is_found_too():
    values = np.array([0.1, 0.2, 1.5, 1.7])
    assert best_threshold(values, np.array([True, True, False, False])) == (0.85, "<", 0)


def test_overlapping_values_count_the_fewest_misclassified():
    values = np.array([0.1, 0.5, 0.3, 0.9])
    assert best_threshold(values, np.array([False, True, False, False]))[2] == 1


def synthetic_case():
    """Rows 0.5 s apart, a start at row 2, a -30 pp error at row 6, a +20 pp error on the bound at row 8 and a
    -50 pp error before the start."""
    count, start = 20, 2
    run = SimpleNamespace(t=np.arange(count) * 0.5, i=np.linspace(-2.0, 2.0, count), v=np.full(count, 3.7))
    reference = np.full(count, 0.8)
    soc = reference.copy()
    soc[1], soc[6], soc[8] = 0.3, 0.5, 1.0
    result = {"soc": soc, "p_soc": np.full(count, 0.0004), "state": np.zeros((count, 4))}
    return case_measures(run, reference, start, result, result), run


def test_the_peak_is_the_largest_error_after_the_start_with_its_time_since_the_start():
    row, _ = synthetic_case()
    assert (row["peak_error_pp"], row["peak_s"]) == (pytest.approx(-30.0), 2.0)


def test_a_posterior_on_a_soc_bound_is_counted():
    row, _ = synthetic_case()
    assert row["bound_rows_30s"] == 1


def test_the_current_is_averaged_from_the_start_row_to_the_first_row_1_s_later():
    row, run = synthetic_case()
    assert row["mean_abs_i_1s_A"] == pytest.approx(np.abs(run.i[2:5]).mean())


def test_the_start_deviation_is_the_root_of_the_posterior_soc_variance_in_pp():
    row, _ = synthetic_case()
    assert row["soc_std_start_pp"] == pytest.approx(2.0)
