"""The fixture check of python/compare_octave.py with stand-in runners; Octave is needed only where marked."""

import shutil

import numpy as np
import pandas as pd
import pytest

import compare_octave
from compare_c import frozen_config


def expected_soc(path, cfg, soc0):
    return pd.read_csv(path)["soc_expected"].to_numpy()


def test_a_runner_that_reproduces_soc_expected_passes():
    assert compare_octave.check_fixtures(expected_soc, frozen_config())


def test_a_runner_off_by_more_than_the_threshold_fails():
    def shifted(path, cfg, soc0):
        return expected_soc(path, cfg, soc0) + 2e-5  # 2e-3 pp
    assert not compare_octave.check_fixtures(shifted, frozen_config())


def test_a_runner_with_a_nan_fails():
    def with_nan(path, cfg, soc0):
        soc = expected_soc(path, cfg, soc0).copy()
        soc[-1] = np.nan
        return soc
    assert not compare_octave.check_fixtures(with_nan, frozen_config())


def test_the_runner_gets_the_soc0_ctest_passes():
    soc0s = []

    def recording(path, cfg, soc0):
        soc0s.append(soc0)
        return expected_soc(path, cfg, soc0)
    compare_octave.check_fixtures(recording, frozen_config())
    assert soc0s == [1.0, 1.0, 1.0]


@pytest.mark.skipif(shutil.which("octave-cli") is None or not compare_octave.OCTAVE_SCRIPT.exists(),
                    reason="needs octave-cli on PATH and octave/ekf_run_csv.m")
def test_the_octave_filter_reproduces_the_fixtures():
    assert compare_octave.check_fixtures(compare_octave.run_octave, frozen_config())
