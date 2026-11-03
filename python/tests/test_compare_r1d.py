"""Tests for python/compare_r1d.py (S8 step A, docs/decisions.md 1.32 and 1.33): the current bands and the test for
step B. All inputs are synthetic; no raw data is needed."""

import numpy as np
import pandas as pd

import compare_r1d


def test_every_current_falls_in_exactly_one_band():
    current = np.concatenate([np.linspace(-20.0, 20.0, 40001), [-0.05, 0.05, 1.5, 3.0, 6.0]])
    hits = sum(in_band(current).astype(int) for _, in_band in compare_r1d.BANDS)
    assert np.all(hits == 1)


def us06_results(rmse_by_temp):
    """A results frame with one experiment-1 US06 evaluation run per temperature."""
    return pd.DataFrame([{"folder": f"{temp}degC", "file": f"us06_{temp}.mat", "cycle": "US06", "T_degC": temp,
                          "is_tuning": False, "experiment": "exp1", "rmse_pp": rmse}
                         for temp, rmse in rmse_by_temp.items()])


def test_step_b_needs_a_drop_of_at_least_the_margin_at_every_test_temperature():
    """Drops of 0.20, 0.50 and 0.09 pp: the last one falls short, so the test is not met."""
    old = us06_results({10: 2.0, 0: 3.0, -10: 6.0, -20: 5.0})
    new = us06_results({10: 2.5, 0: 2.8, -10: 5.5, -20: 4.91})
    passes, _ = compare_r1d.b_test({"2RC-I": old, "2RC-Id": new})
    assert not passes
