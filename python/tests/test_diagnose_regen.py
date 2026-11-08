"""The limit-interval rule of decision 1.48 on synthetic rows."""

import numpy as np

from diagnose_regen import limit_intervals


T = np.arange(10) * 0.5


def test_charge_at_the_limit_is_not_a_limit_row():
    v = np.full(10, 4.2)
    assert limit_intervals(T, v, np.full(10, 1.0)) == []


def test_rows_up_to_one_second_apart_form_one_interval():
    v = np.where(np.isin(np.arange(10), [2, 4, 6]), 4.2, 4.1)
    assert limit_intervals(T, v, np.full(10, -1.0)) == [(2, 6)]


def test_a_longer_gap_starts_a_new_interval():
    v = np.where(np.isin(np.arange(10), [1, 2, 6]), 4.2, 4.1)
    assert limit_intervals(T, v, np.full(10, -1.0)) == [(1, 2), (6, 6)]


def test_the_voltage_threshold_is_inclusive():
    v = np.where(np.arange(10) == 3, 4.1995, 4.1994)
    assert limit_intervals(T, v, np.full(10, -1.0)) == [(3, 3)]
