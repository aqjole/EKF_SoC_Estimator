"""The verdict of python/compare_c.py on small hand-made tables; the C builds and the raw data are not needed."""

import numpy as np
import pandas as pd
import pytest

import compare_c


def table(float_max, double_max):
    """One row per run with the four statistics; the RMS columns are half the max, tests 551, 552, ..."""
    return pd.DataFrame([{"folder": "25degC", "cycle": "US06", "test": 551 + k, "float_max_pp": f, "float_rms_pp": f / 2,
                          "double_max_pp": d, "double_rms_pp": d / 2} for k, (f, d) in enumerate(zip(float_max, double_max))])


def test_a_run_with_a_non_finite_delta_is_an_error_that_names_it():
    with pytest.raises(RuntimeError, match="25degC/US06 test 552"):
        compare_c.check_finite(table([1e-3, np.nan], [1e-6, 1e-6]), compare_c.C_IMPLEMENTATIONS)


def test_no_build_fails_below_its_thresholds():
    assert compare_c.failed_builds(table([1e-3, 0.09], [1e-6, 9e-4]), compare_c.C_IMPLEMENTATIONS) == []


def test_a_build_fails_when_its_worst_run_reaches_the_threshold():
    assert compare_c.failed_builds(table([1e-3, 0.1], [1e-6, 1e-6]), compare_c.C_IMPLEMENTATIONS) == ["float"]
