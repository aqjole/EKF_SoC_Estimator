"""Tests for ekfsoc.ocv: synthetic C20DisCh runs with known curves, and (when data/raw/ exists) the six real files.

The synthetic runs are built directly as loader Runs: a C/20-like discharge (current +0.15 A, loader sign),
then a rest and a charge half with a voltage far from the discharge curve, so a table that wrongly used
those rows would show it. The real-data tests compare with results/s0/data_checks.md section 11.
"""

import numpy as np
import pytest

from ekfsoc.constants import FOLDER_TEMP, Q_REF_AH, RAW_DIR, SOC_GRID, T_GRID_DEGC
from ekfsoc.hppc import rest_points, segment_hppc
from ekfsoc.loader import Run, find_runs, load_run
from ekfsoc.ocv import (
    DISCHARGE_MIN_A,
    OcvTable,
    average_equal_x,
    build_ocv,
    central_differences,
    discharge_curve,
    find_discharge_half,
    rest_offsets,
)

# Discharge current of the made-up runs (A, loader sign), close to the real C/20 current.
C20_CURRENT_A = 0.15

# The made-up rest (20 rows) and charge (50 rows) after the discharge sit at this voltage (V), far from
# every made-up discharge curve below, so a wrongly included row is visible.
CHARGE_HALF_V = 4.5


# --------------------------------------------------------------------------------------------
# Helpers that build made-up runs
# --------------------------------------------------------------------------------------------


def linear_curve(soc):
    """V = 3.0 + 1.2 * SoC: rising, and PCHIP reproduces a straight line exactly."""
    return 3.0 + 1.2 * soc


def quadratic_curve(soc):
    """V = 3.0 + 1.0 * SoC + 0.4 * SoC^2: strictly rising on 0 to 1, with a slope that changes."""
    return 3.0 + 1.0 * soc + 0.4 * soc * soc


def dipping_curve(soc):
    """A curve whose slope changes sign (0.8 + 1.5 cos(30 SoC) goes negative), so it is not monotone."""
    return 3.2 + 0.8 * soc + 0.05 * np.sin(30.0 * soc)


def make_c20_run(voltage_of_soc, soc_start=1.0, soc_end=0.0, n_discharge=1001):
    """A made-up C20DisCh run in the loader's convention: positive discharge current, ah_removed from the step start.

    The discharge goes from soc_start to soc_end in n_discharge rows. ah_removed = (1 - SoC) * Q_ref, so
    SoC = 1 - ah_removed / Q_ref gives back the SoC that was put in. A rest and a charge half follow.
    """
    soc = np.linspace(soc_start, soc_end, n_discharge)
    ah_end = (1.0 - soc_end) * Q_REF_AH
    n_rest, n_charge = 20, 50
    # Rest: no current, the counter stays. Charge: negative current, the counter falls back.
    ah_removed = np.concatenate([(1.0 - soc) * Q_REF_AH, np.full(n_rest, ah_end), ah_end - np.linspace(0.0, 1.0, n_charge)])
    i = np.concatenate([np.full(n_discharge, C20_CURRENT_A), np.zeros(n_rest), np.full(n_charge, -C20_CURRENT_A)])
    v = np.concatenate([voltage_of_soc(soc), np.full(n_rest + n_charge, CHARGE_HALF_V)])

    n_rows = len(v)
    dt = np.full(n_rows, 60.0)
    dt[0] = 0.0
    return Run(
        t=60.0 * np.arange(n_rows), i=i, v=v, temp=np.full(n_rows, 25.0), ah_removed=ah_removed, dt=dt, soc0=1.0,
        meta={"file": "synthetic_C20DisCh.mat", "test_type": "c20"},
    )


def make_runs(curve_by_temp, **kwargs):
    """A dict temperature -> made-up run, one per entry of {temperature: curve function}."""
    return {temp: make_c20_run(curve, **kwargs) for temp, curve in curve_by_temp.items()}


OFFSETS_V = 0.01 * np.arange(6)  # the shift of each temperature row, 10 mV per step, so the rows differ


def shifted(curve, offset_v):
    """The same curve shifted up by offset_v."""
    return lambda soc: curve(soc) + offset_v


def same_curve_at_every_temperature(curve):
    """Curve functions for all six grid temperatures, each shifted by its OFFSETS_V."""
    return {temp: shifted(curve, offset) for temp, offset in zip(T_GRID_DEGC, OFFSETS_V)}


# --------------------------------------------------------------------------------------------
# Synthetic: the curve, the hold, the monotone check, the fallback, the slope
# --------------------------------------------------------------------------------------------


def test_linear_curve_reproduces_itself_exactly_on_the_grid():
    """A straight line comes back unchanged at every temperature; the rest and charge half at 4.5 V do not enter."""
    table = build_ocv(make_runs(same_curve_at_every_temperature(linear_curve)), SOC_GRID, T_GRID_DEGC)

    assert isinstance(table, OcvTable)
    assert list(table.t_grid) == T_GRID_DEGC
    assert np.array_equal(table.soc_grid, SOC_GRID)
    for row, offset in enumerate(OFFSETS_V):
        assert table.ocv[row] == pytest.approx(linear_curve(SOC_GRID) + offset, abs=1e-12)

    assert table.monotone.tolist() == [True] * 6
    assert table.fallback_used is False
    assert table.soc_min == pytest.approx(np.zeros(6), abs=1e-12)
    assert table.soc_max == pytest.approx(np.ones(6), abs=1e-12)


def test_smooth_monotone_curve_reproduces_itself_to_within_pchip_error():
    """A curved, strictly rising input is reproduced by the table to a few microvolts when sampled finely."""
    table = build_ocv(make_runs(same_curve_at_every_temperature(quadratic_curve)), SOC_GRID, T_GRID_DEGC)
    for row, offset in enumerate(OFFSETS_V):
        assert table.ocv[row] == pytest.approx(quadratic_curve(SOC_GRID) + offset, abs=1e-5)
    assert table.monotone.all() and not table.fallback_used


def test_discharge_half_is_the_longest_run_above_the_threshold():
    """Short blips of current elsewhere do not move the discharge half; the threshold is 50 mA."""
    i = np.zeros(40)
    i[2:5] = 1.0  # a short blip
    i[10:30] = 0.2  # the long run: the discharge half
    i[35:37] = 3.0
    assert find_discharge_half(i) == (10, 29)

    i[30] = DISCHARGE_MIN_A  # a current at or below the threshold is a rest, so it does not extend the run
    assert find_discharge_half(i) == (10, 29)

    with pytest.raises(ValueError):
        find_discharge_half(np.zeros(10))


def test_grid_points_outside_the_measured_range_hold_the_end_values():
    """A discharge from SoC 0.999 down to 0.2 gives a flat table below 0.2 and above 0.999, and records both ends."""
    runs = make_runs(same_curve_at_every_temperature(linear_curve), soc_start=0.999, soc_end=0.2)
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)

    assert table.soc_min == pytest.approx(np.full(6, 0.2), abs=1e-9)
    assert table.soc_max == pytest.approx(np.full(6, 0.999), abs=1e-9)
    below = SOC_GRID < 0.2 - 1e-9
    assert below.sum() == 20
    for row, offset in enumerate(OFFSETS_V):
        assert table.ocv[row, below] == pytest.approx(np.full(20, linear_curve(0.2) + offset), abs=1e-9)
        assert table.ocv[row, 100] == pytest.approx(linear_curve(0.999) + offset, abs=1e-9)
        assert table.ocv[row, 99] == pytest.approx(linear_curve(0.99) + offset, abs=1e-9)
    assert table.monotone.all()  # held points are not part of the check


def test_non_monotone_curve_sets_monotone_false_and_the_fallback_copies_25_degc():
    """The -20 degC curve dips: monotone is False there, True elsewhere, and 25 degC is copied to all rows."""
    curves = same_curve_at_every_temperature(quadratic_curve)
    curves[-20] = dipping_curve
    table = build_ocv(make_runs(curves), SOC_GRID, T_GRID_DEGC)

    assert table.monotone.tolist() == [True, True, True, True, True, False]
    assert table.fallback_used is True

    row_25 = T_GRID_DEGC.index(25)
    for row in range(6):
        assert table.ocv[row] == pytest.approx(quadratic_curve(SOC_GRID) + OFFSETS_V[row_25], abs=1e-5)
        assert np.array_equal(table.ocv[row], table.ocv[row_25])
        assert np.array_equal(table.docv[row], table.docv[row_25])
        assert table.soc_min[row] == table.soc_min[row_25]


def test_25_degc_failing_the_check_is_an_error_not_a_silent_fallback():
    """With no valid 25 degC curve there is nothing to copy; the function must say so."""
    curves = same_curve_at_every_temperature(quadratic_curve)
    curves[25] = dipping_curve
    with pytest.raises(ValueError, match="fallback"):
        build_ocv(make_runs(curves), SOC_GRID, T_GRID_DEGC)


def test_a_missing_temperature_is_an_error():
    curves = same_curve_at_every_temperature(quadratic_curve)
    del curves[0]
    with pytest.raises(ValueError, match="no C20DisCh run"):
        build_ocv(make_runs(curves), SOC_GRID, T_GRID_DEGC)


def test_central_differences_on_a_nonuniform_axis():
    """Central differences inside, one-sided over the first and the last step."""
    x = np.array([0.0, 1.0, 3.0, 4.0])
    slope = central_differences(x * x, x)
    assert slope == pytest.approx([1.0, 9.0 / 3.0, 15.0 / 3.0, 7.0])


def test_docv_is_zero_on_held_points_and_half_a_slope_at_the_kink():
    """A line of slope 1.2 that stops at SoC 0.2: zero below, half the slope at the kink, the slope above (Eq. 5)."""
    runs = make_runs(same_curve_at_every_temperature(linear_curve), soc_end=0.2)
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)
    assert table.docv[:, :20] == pytest.approx(0.0, abs=1e-9)
    assert table.docv[:, 20] == pytest.approx(0.6, abs=1e-9)
    assert table.docv[:, 21:] == pytest.approx(1.2, abs=1e-9)


def test_rest_point_correction_adds_the_offsets_at_the_rest_socs_and_holds_flat_outside():
    """A made-up C/20 line plus known rest offsets: curve + offset at the rest SoCs, flat beyond the first and last."""
    curves = same_curve_at_every_temperature(linear_curve)
    runs = make_runs(curves)
    plain = build_ocv(runs, SOC_GRID, T_GRID_DEGC)

    # Rest points as hppc.rest_points returns them: SoC falling, the offset growing towards low SoC.
    rest_rows = [80, 50, 20]
    offsets_v = np.array([0.010, 0.030, 0.060])
    rest_socs = SOC_GRID[rest_rows]
    points = {temp: list(zip(rest_socs, curves[temp](rest_socs) + offsets_v)) for temp in T_GRID_DEGC}
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC, points)

    # Without rest points there is no correction; with them the uncorrected curve is the plain table.
    assert np.all(plain.delta_v == 0.0)
    assert np.array_equal(plain.ocv, plain.ocv_c20)
    assert np.array_equal(table.ocv_c20, plain.ocv)
    assert table.ocv == pytest.approx(table.ocv_c20 + table.delta_v, abs=1e-15)
    assert table.monotone.all() and not table.fallback_used
    for row in range(6):
        assert table.delta_v[row, rest_rows] == pytest.approx(offsets_v, abs=1e-12)
        assert table.ocv[row, rest_rows] == pytest.approx(plain.ocv[row, rest_rows] + offsets_v, abs=1e-12)
        assert table.delta_v[row, :20] == pytest.approx(np.full(20, 0.060), abs=1e-12)
        assert table.delta_v[row, 81:] == pytest.approx(np.full(20, 0.010), abs=1e-12)
        assert table.docv[row] == pytest.approx(central_differences(table.ocv[row], SOC_GRID), abs=1e-12)  # of the corrected table


def test_rest_offsets_are_taken_from_the_uncorrected_curve_held_beyond_its_range():
    """A rest point below the end of the discharge is compared with the held end value of the C/20 curve."""
    soc_curve, v_curve = discharge_curve(make_c20_run(linear_curve, soc_end=0.2))
    v_c20, delta = rest_offsets(soc_curve, v_curve, np.array([0.5, 0.1]), np.array([3.7, 3.4]))
    assert v_c20 == pytest.approx([linear_curve(0.5), linear_curve(0.2)], abs=1e-9)
    assert delta == pytest.approx([3.7 - linear_curve(0.5), 3.4 - linear_curve(0.2)], abs=1e-9)


def test_equal_soc_rows_are_averaged_and_the_axis_is_sorted():
    """PCHIP needs a strictly increasing axis: rows that share a SoC give one point at their mean voltage."""
    soc = np.array([0.9, 0.5, 0.5, 0.1, 0.9, 0.9])
    v = np.array([4.0, 3.6, 3.8, 3.2, 4.2, 4.1])
    soc_unique, v_mean = average_equal_x(soc, v)
    assert soc_unique.tolist() == [0.1, 0.5, 0.9]
    assert v_mean == pytest.approx([3.2, 3.7, 4.1])


# --------------------------------------------------------------------------------------------
# Real data
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_c20_runs():
    """The six C20DisCh files loaded, keyed by nominal temperature in degC."""
    runs = [load_run(path) for path in find_runs(RAW_DIR, test_type="c20")]
    return {run.meta["nominal_temp_degc"]: run for run in runs}


@pytest.fixture(scope="module")
def real_table(real_c20_runs):
    return build_ocv(real_c20_runs, SOC_GRID, T_GRID_DEGC)


@pytest.fixture(scope="module")
def real_rest_points():
    """The HPPC rest points of the six folders, keyed by nominal temperature in degC."""
    runs = [load_run(path) for path in find_runs(RAW_DIR, test_type="hppc")]
    return {run.meta["nominal_temp_degc"]: rest_points(run, segment_hppc(run)) for run in runs}


@pytest.mark.needs_data
def test_real_discharge_halves_have_the_row_counts_of_data_checks(real_c20_runs, data_checks_table):
    """Section 11 finds the discharge half the same way (longest run above 50 mA) and counts its rows."""
    for folder, cells in data_checks_table(11, "discharge rows").items():
        first, last = find_discharge_half(real_c20_runs[FOLDER_TEMP[folder]].i)
        assert last - first + 1 == int(cells["discharge rows"]), folder
        assert first == 0, folder  # the file opens inside the discharge


@pytest.mark.needs_data
def test_real_soc_min_matches_data_checks_within_half_a_pp(real_table, data_checks_table):
    """soc_min per temperature against the end-of-discharge SoC (%) of results/s0/data_checks.md section 11."""
    column = "end-of-discharge SoC (%)"
    for folder, cells in data_checks_table(11, column).items():
        soc_min_pp = 100.0 * real_table.soc_min[T_GRID_DEGC.index(FOLDER_TEMP[folder])]
        assert soc_min_pp == pytest.approx(float(cells[column]), abs=0.5), folder


@pytest.mark.needs_data
def test_real_table_is_monotone_without_fallback_and_plausible(real_table):
    """Each temperature keeps its own curve, rising over its measured range; voltages of an NMC cell, slope never negative."""
    assert real_table.monotone.all() and not real_table.fallback_used
    assert real_table.ocv.min() > 2.7 and real_table.ocv.max() < 4.25
    assert np.all(real_table.docv >= 0.0)
    assert np.all(real_table.soc_max > 0.99)  # the file opens one log interval into the discharge


@pytest.mark.needs_data
def test_real_correction_at_25_degc_is_positive_and_the_corrected_table_is_monotone(
    real_table, real_c20_runs, real_rest_points
):
    """The relaxed rest voltage lies above the C/20 discharge curve at every rest point (decisions 1.1)."""
    soc_curve, v_curve = discharge_curve(real_c20_runs[25])
    soc_rest, v_rest = np.array(real_rest_points[25]).T
    _, delta = rest_offsets(soc_curve, v_curve, soc_rest, v_rest)
    assert len(delta) == 12 and np.all(delta > 0.0)

    corrected = build_ocv(real_c20_runs, SOC_GRID, T_GRID_DEGC, real_rest_points)
    row = T_GRID_DEGC.index(25)
    assert np.all(corrected.delta_v[row] > 0.0)
    assert corrected.ocv[row] == pytest.approx(corrected.ocv_c20[row] + corrected.delta_v[row], abs=1e-15)
    assert corrected.monotone.all() and not corrected.fallback_used
