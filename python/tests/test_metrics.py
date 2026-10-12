"""Tests for ekfsoc.metrics: the evaluation window, the error measures, the band times, the init-forgetting
time and the coulomb counter (Eq. 3). Everything runs on short made-up arrays, so no raw data is needed.
The expected values are worked out by hand in the comments, not by calling the code under test.
"""

import math

import numpy as np
import pytest

from ekfsoc.metrics import (
    CONV_BAND_PP,
    FORGET_BAND_PP,
    after_conv_mask,
    band_times,
    coulomb_count,
    expected_drift_pp,
    init_forgetting_time,
    max_abs_pp,
    rmse_pp,
    voltage_rmse_mv,
    window_mask,
)


def flags(*indices, n):
    """A boolean array of length n that is True at the given indices."""
    mask = np.zeros(n, dtype=bool)
    mask[list(indices)] = True
    return mask


# --- window_mask ---------------------------------------------------------------------------------

# Reference SoC of a run that ends near empty. Index 5 is exactly 0.10, the last sample at or above it.
SOC_REF_RUN = np.array([1.0, 0.8, 0.6, 0.4, 0.2, 0.10, 0.05, 0.02])


def test_window_mask_runs_from_start_to_the_last_sample_at_or_above_10_percent():
    # The sample at exactly 0.10 is inside (">= 0.10"); 0.05 and 0.02 are not.
    assert window_mask(SOC_REF_RUN, 0).tolist() == [True] * 6 + [False] * 2
    assert window_mask(SOC_REF_RUN, 2).tolist() == [False, False] + [True] * 4 + [False] * 2


def test_window_mask_is_the_whole_run_when_the_reference_never_falls_below_the_limit():
    soc_ref = np.array([1.0, 0.9, 0.8, 0.7, 0.6])
    assert window_mask(soc_ref, 0).all()
    assert window_mask(soc_ref, 3).tolist() == [False, False, False, True, True]


def test_window_mask_keeps_a_dip_below_the_limit_that_regen_recovers_from():
    # The window ends at the LAST sample at or above the limit, so the dip at index 2 is inside.
    soc_ref = np.array([0.5, 0.2, 0.09, 0.12, 0.05])
    assert window_mask(soc_ref, 0).tolist() == [True, True, True, True, False]


def test_window_mask_is_empty_when_start_is_after_the_last_sample_above_the_limit():
    assert not window_mask(SOC_REF_RUN, 6).any()
    assert not window_mask(np.array([0.05, 0.04]), 0).any()


def test_window_mask_takes_another_limit():
    assert window_mask(SOC_REF_RUN, 0, soc_min=0.5).tolist() == [True] * 3 + [False] * 5


# --- rmse_pp, max_abs_pp, voltage_rmse_mv --------------------------------------------------------

def test_rmse_and_max_abs_turn_soc_fractions_into_pp_and_read_only_the_masked_samples():
    # Masked errors 0.03 and -0.04: mean square (9 + 16) / 2 = 12.5 pp^2, so RMSE sqrt(12.5) pp, max 4 pp.
    # The third sample (0.99) and the NaN would ruin both if they were read.
    err = np.array([0.03, -0.04, 0.99, np.nan])
    mask = flags(0, 1, n=4)
    assert rmse_pp(err, mask) == pytest.approx(math.sqrt(12.5), rel=1e-12)
    assert max_abs_pp(err, mask) == pytest.approx(4.0, rel=1e-12)


def test_rmse_and_max_abs_of_an_empty_mask_are_nan():
    err = np.array([0.01, 0.02])
    empty = np.zeros(2, dtype=bool)
    assert math.isnan(rmse_pp(err, empty))
    assert math.isnan(max_abs_pp(err, empty))
    assert math.isnan(voltage_rmse_mv(err, err, empty))


def test_voltage_rmse_is_in_mv_over_the_masked_samples():
    # Differences -3 mV and +4 mV: mean square (9 + 16) / 2 = 12.5 mV^2.
    v_pred = np.array([3.700, 3.600, 0.0])
    v_meas = np.array([3.703, 3.596, 9.0])
    assert voltage_rmse_mv(v_pred, v_meas, flags(0, 1, n=3)) == pytest.approx(math.sqrt(12.5), rel=1e-9)


# --- band_times ----------------------------------------------------------------------------------

def test_band_times_gives_first_entry_and_the_start_of_the_final_stay_in_the_band():
    # A time axis that does not start at 0, to show that the values of t come back, not indices.
    t = 100.0 + 0.5 * np.arange(10)
    #                      0    1    2    3    4    5    6     7     8     9
    err_pp = np.array([5.0, 4.0, 1.5, 3.0, 1.0, 0.5, 2.0, -2.0, -1.0, 0.0])
    # Band 2 pp: inside at 2, then out at 3, then inside from 4 to the end (|+-2.0| counts as inside).
    # First entry is index 2, the last exit is at index 3, so the filter has converged from index 4.
    assert band_times(t, err_pp, np.ones(10, dtype=bool), 2.0) == (101.0, 102.0)


def test_band_times_never_leaving_the_band_converges_at_the_first_masked_sample():
    t = 10.0 + np.arange(4)
    err_pp = np.array([9.0, 1.0, -1.0, 0.0])
    assert band_times(t, err_pp, flags(1, 2, 3, n=4), 2.0) == (11.0, 11.0)


def test_band_times_reads_only_the_masked_samples():
    t = np.arange(8, dtype=float)
    #                      0    1    2    3    4    5     6     7
    err_pp = np.array([0.0, 0.0, 3.0, 1.0, 0.0, 1.0, 50.0, 50.0])
    # In the window (2 to 5) the samples are 3, 1, 0, 1. The zeros before it would make t_first 0,
    # and the 50 after it (the near-empty end of a run) would make t_conv "not reached".
    assert band_times(t, err_pp, flags(2, 3, 4, 5, n=8), 2.0) == (3.0, 3.0)


def test_band_times_not_reached_when_the_last_masked_sample_is_outside_the_band():
    t = np.arange(4, dtype=float)
    err_pp = np.array([0.0, 1.0, 1.0, 3.0])
    # It was inside twice, so t_first exists, but the error is out of the band at the end of the window.
    assert band_times(t, err_pp, np.ones(4, dtype=bool), 2.0) == (0.0, None)


def test_band_times_never_inside_gives_none_for_both():
    t = np.arange(3, dtype=float)
    err_pp = np.array([5.0, 4.0, 3.0])
    assert band_times(t, err_pp, np.ones(3, dtype=bool), 2.0) == (None, None)
    assert band_times(t, err_pp, np.zeros(3, dtype=bool), 2.0) == (None, None)


def test_band_times_returns_plain_floats():
    t_first, t_conv = band_times(np.arange(3, dtype=float), np.zeros(3), np.ones(3, dtype=bool), 2.0)
    assert type(t_first) is float and type(t_conv) is float


def test_the_bands_are_2_pp_for_convergence_and_1_pp_for_init_forgetting():
    assert CONV_BAND_PP == 2.0
    assert FORGET_BAND_PP == 1.0


# --- after_conv_mask -----------------------------------------------------------------------------

def test_after_conv_mask_is_the_part_of_the_window_from_t_conv_on():
    t = np.arange(6, dtype=float)
    assert after_conv_mask(flags(1, 2, 3, 4, 5, n=6), t, 3.0).tolist() == [False, False, False, True, True, True]
    # The window end is kept: nothing after the window comes back.
    assert after_conv_mask(flags(0, 1, 2, 3, n=6), t, 2.0).tolist() == [False, False, True, True, False, False]


def test_after_conv_mask_is_empty_when_not_reached_so_the_rmse_after_convergence_is_nan():
    t = np.arange(4, dtype=float)
    mask = np.ones(4, dtype=bool)
    after = after_conv_mask(mask, t, None)
    assert not after.any()
    assert math.isnan(rmse_pp(np.full(4, 0.01), after))


def test_rmse_after_convergence_skips_the_transient():
    # Error 20, 10, then 1, -1 pp: over the whole window the RMSE is large, after t_conv = 2 it is 1 pp.
    t = np.arange(4, dtype=float)
    err = np.array([0.20, 0.10, 0.01, -0.01])
    mask = np.ones(4, dtype=bool)
    t_first, t_conv = band_times(t, 100.0 * err, mask, 2.0)
    assert (t_first, t_conv) == (2.0, 2.0)
    assert rmse_pp(err, after_conv_mask(mask, t, t_conv)) == pytest.approx(1.0, rel=1e-12)


# --- init_forgetting_time ------------------------------------------------------------------------

def forgetting_case():
    """Two runs that start apart and come together; NaN before the filter start at index 2."""
    gap_pp = np.array([np.nan, np.nan, 1.5, 0.9, 1.2, 0.8, 0.4, 0.2])
    soc_b = np.full(8, 0.5)
    soc_a = soc_b + gap_pp / 100.0
    t = 7.0 + 0.1 * np.arange(8)
    return t, soc_a, soc_b, np.arange(8) >= 2


def test_init_forgetting_time_is_the_last_exit_from_the_1_pp_band():
    t, soc_a, soc_b, mask = forgetting_case()
    # Window gaps 1.5, 0.9, 1.2, 0.8, 0.4, 0.2: the last sample outside 1 pp is 1.2 (index 4), so from index 5.
    assert init_forgetting_time(t, soc_a, soc_b, mask) == pytest.approx(t[5])
    # Which run is on top does not matter.
    assert init_forgetting_time(t, soc_b, soc_a, mask) == pytest.approx(t[5])


def test_init_forgetting_time_takes_another_band():
    t, soc_a, soc_b, mask = forgetting_case()
    # Inside 0.5 pp only at 0.4 and 0.2 (indices 6 and 7).
    assert init_forgetting_time(t, soc_a, soc_b, mask, band_pp=0.5) == pytest.approx(t[6])


def test_init_forgetting_time_is_none_while_the_runs_are_still_apart_at_the_end():
    t, soc_a, soc_b, mask = forgetting_case()
    assert init_forgetting_time(t, soc_a, soc_b, mask, band_pp=0.1) is None


# --- coulomb_count -------------------------------------------------------------------------------

# q_ref = 10 Ah is 36000 A s. Currents in A (positive = discharge), dt in s.
# The current at index 3 is never held over a step, so it must not change any result.
I_CC = np.array([3.6, 7.2, -3.6, 99.0])
DT_CC = np.array([0.0, 1000.0, 500.0, 100.0])
Q_REF_CC = 10.0


def test_coulomb_count_is_eq_3_with_the_previous_current_held_over_each_step():
    # k=1: 3.6 A * 1000 s / 36000 = 0.10;  k=2: 7.2 * 500 / 36000 = 0.10;  k=3: -3.6 * 100 / 36000 = -0.01.
    soc = coulomb_count(I_CC, DT_CC, 0.9, Q_REF_CC)
    assert soc == pytest.approx([0.9, 0.8, 0.7, 0.71], abs=1e-12)


def test_coulomb_count_adds_the_offset_to_the_held_current():
    # k=1: (3.6 + 3.6) * 1000 / 36000 = 0.20;  k=2: (7.2 + 3.6) * 500 / 36000 = 0.15;  k=3: (-3.6 + 3.6) * 100 = 0.
    soc = coulomb_count(I_CC, DT_CC, 0.9, Q_REF_CC, current_offset=3.6)
    assert soc == pytest.approx([0.9, 0.7, 0.55, 0.55], abs=1e-12)


def test_coulomb_count_starts_at_start_and_is_nan_before_it():
    # k=2: 7.2 * 500 / 36000 = 0.10;  k=3: -3.6 * 100 / 36000 = -0.01.
    soc = coulomb_count(I_CC, DT_CC, 0.9, Q_REF_CC, start=1)
    assert np.isnan(soc[0])
    assert soc[1:] == pytest.approx([0.9, 0.8, 0.81], abs=1e-12)


def test_coulomb_count_is_not_clamped():
    # 36 A for 1000 s is 1.0 of SoC at 10 Ah.
    assert coulomb_count(np.array([36.0, 36.0, 0.0]), np.array([0.0, 1000.0, 1000.0]), 0.05, Q_REF_CC) \
        == pytest.approx([0.05, -0.95, -1.95], abs=1e-12)
    assert coulomb_count(np.array([-36.0, -36.0, 0.0]), np.array([0.0, 1000.0, 1000.0]), 0.95, Q_REF_CC) \
        == pytest.approx([0.95, 1.95, 2.95], abs=1e-12)


def test_coulomb_count_of_a_single_sample_is_soc0():
    assert coulomb_count(np.array([5.0]), np.array([0.0]), 0.7, Q_REF_CC).tolist() == [0.7]


# --- expected_drift_pp ---------------------------------------------------------------------------

def test_expected_drift_is_the_offset_charge_over_the_capacity_in_pp():
    # 0.2 A for 3600 s is 0.2 Ah; at q_ref = 2 Ah that is 10 pp. A positive offset reads as discharge, so it is -10 pp.
    assert expected_drift_pp(0.2, 3600.0, 2.0) == pytest.approx(-10.0, rel=1e-12)
    assert expected_drift_pp(-0.2, 3600.0, 2.0) == pytest.approx(10.0, rel=1e-12)
    assert expected_drift_pp(0.0, 3600.0, 2.0) == 0.0


def test_expected_drift_matches_what_the_coulomb_counter_does_to_a_zero_current():
    n, step, q_ref = 1001, 0.1, 2.7807
    i = np.zeros(n)
    dt = np.full(n, step)
    dt[0] = 0.0
    soc = coulomb_count(i, dt, 0.6, q_ref, current_offset=0.2)
    drift_pp = 100.0 * (soc[-1] - 0.6)
    assert drift_pp == pytest.approx(expected_drift_pp(0.2, dt.sum(), q_ref), rel=1e-9)
