"""Tests for the resampling in fit_all.py: level fits onto the 101-point SoC grid (decisions 1.12)."""

import pytest

import fit_all


def levels(*pairs):
    """Level rows with the SoC of the pulses and a value, as fit_hppc_run returns them (None = no value)."""
    return [{"soc_pulses": soc, "R0_ohm": value} for soc, value in pairs]


def test_resample_is_linear_between_levels_and_holds_the_end_values():
    # SoC falls from level to level, so the rows come in descending SoC.
    rows = levels((0.9, 1.0), (0.5, 3.0), (0.2, 4.0))
    values = fit_all.resample(rows, "soc_pulses", "R0_ohm")
    assert values[70] == pytest.approx(2.0)          # SoC 0.70 lies halfway between 0.9 and 0.5
    assert values[100] == 1.0                        # above the highest level
    assert values[0] == 4.0                          # below the lowest level


def test_resample_skips_levels_without_a_value():
    rows = levels((0.9, 1.0), (0.5, None), (0.1, 3.0))
    values = fit_all.resample(rows, "soc_pulses", "R0_ohm")
    assert values[50] == pytest.approx(2.0)          # interpolated across the skipped level


def test_resample_without_any_value_raises():
    with pytest.raises(ValueError):
        fit_all.resample(levels((0.9, None)), "soc_pulses", "R0_ohm")
