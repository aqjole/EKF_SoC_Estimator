"""Tests for ekfsoc.ocv: synthetic C20DisCh runs with known curves, and (when data/raw/ exists) the six real files.

The synthetic runs are built directly as loader Runs: a C/20-like discharge (current +0.15 A, loader sign),
then a rest and a charge half with a voltage far from the discharge curve, so a table that wrongly used
those rows would show it. The real-data test compares soc_min with results/data_checks.md section 11.
"""

from pathlib import Path

import numpy as np
import pytest

from ekfsoc.constants import FOLDER_TEMP, Q_REF_AH, RAW_DIR, SOC_GRID, T_GRID_DEGC
from ekfsoc.loader import Run, find_runs, load_run
from ekfsoc.ocv import (
    DISCHARGE_MIN_A,
    OcvTable,
    average_equal_x,
    build_ocv,
    central_differences,
    find_discharge_half,
)

DATA_CHECKS_MD = Path(__file__).resolve().parents[2] / "results" / "data_checks.md"

# Discharge current of the made-up runs (A, loader sign), close to the real C/20 current.
C20_CURRENT_A = 0.15

# A made-up rest and charge after the discharge: 20 rest rows, then 50 charge rows at this voltage (V).
# The voltage is far from any made-up discharge curve below, so a wrongly included row is visible.
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


def make_c20_run(voltage_of_soc, soc_start=1.0, soc_end=0.0, n_discharge=1001, with_rest_and_charge=True):
    """A made-up C20DisCh run in the loader's convention: positive discharge current, ah_removed from the step start.

    The discharge goes from soc_start to soc_end in n_discharge rows. ah_removed = (1 - SoC) * Q_ref, so
    SoC = 1 - ah_removed / Q_ref gives back the SoC that was put in.
    """
    soc = np.linspace(soc_start, soc_end, n_discharge)
    ah_removed = (1.0 - soc) * Q_REF_AH
    i = np.full(n_discharge, C20_CURRENT_A)
    v = voltage_of_soc(soc)

    if with_rest_and_charge:
        n_rest = 20
        n_charge = 50
        ah_end = ah_removed[-1]
        # Rest: no current, the counter stays, the voltage sits at the end value.
        ah_removed = np.concatenate([ah_removed, np.full(n_rest, ah_end)])
        i = np.concatenate([i, np.zeros(n_rest)])
        v = np.concatenate([v, np.full(n_rest, v[-1])])
        # Charge: negative current in the loader sign, the counter falls back, the voltage is far away.
        ah_charge = ah_end - np.linspace(0.0, 1.0, n_charge)
        ah_removed = np.concatenate([ah_removed, ah_charge])
        i = np.concatenate([i, np.full(n_charge, -C20_CURRENT_A)])
        v = np.concatenate([v, np.full(n_charge, CHARGE_HALF_V)])

    n_rows = len(v)
    t = 60.0 * np.arange(n_rows, dtype=np.float64)
    dt = np.zeros(n_rows)
    dt[1:] = 60.0
    meta = {"file": "synthetic_C20DisCh.mat", "test_type": "c20"}
    return Run(
        t=t, i=i, v=v, temp=np.full(n_rows, 25.0), ah_removed=ah_removed, dt=dt, soc0=1.0, meta=meta
    )


def make_runs(voltage_of_soc_by_temp, **kwargs):
    """A dict temperature -> made-up run, one per entry of {temperature: curve function}."""
    return {temp: make_c20_run(curve, **kwargs) for temp, curve in voltage_of_soc_by_temp.items()}


def shifted(curve, offset_v):
    """The same curve shifted up by offset_v, so that the temperatures can be told apart in a table."""
    return lambda soc: curve(soc) + offset_v


def same_curve_at_every_temperature(curve):
    """Curve functions for all six grid temperatures, each shifted by 10 mV per step so the rows differ."""
    return {temp: shifted(curve, 0.01 * k) for k, temp in enumerate(T_GRID_DEGC)}


# --------------------------------------------------------------------------------------------
# Synthetic: the curve, the hold, the monotone check, the fallback, the slope
# --------------------------------------------------------------------------------------------


def test_linear_curve_reproduces_itself_exactly_on_the_grid():
    """A straight line through the whole SoC range comes back unchanged, at every temperature."""
    runs = make_runs(same_curve_at_every_temperature(linear_curve))
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)

    assert isinstance(table, OcvTable)
    assert table.ocv.shape == (6, 101) and table.docv.shape == (6, 101)
    assert list(table.t_grid) == T_GRID_DEGC
    assert np.array_equal(table.soc_grid, SOC_GRID)
    for row, offset in enumerate(0.01 * np.arange(6)):
        expected = linear_curve(SOC_GRID) + offset
        assert table.ocv[row] == pytest.approx(expected, abs=1e-12)

    assert table.monotone.tolist() == [True] * 6
    assert table.fallback_used is False
    assert table.soc_min == pytest.approx(np.zeros(6), abs=1e-12)
    assert table.soc_max == pytest.approx(np.ones(6), abs=1e-12)


def test_smooth_monotone_curve_reproduces_itself_to_within_pchip_error():
    """A curved, strictly rising input is reproduced by the table to a few microvolts when sampled finely."""
    runs = make_runs(same_curve_at_every_temperature(quadratic_curve))
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)
    for row, offset in enumerate(0.01 * np.arange(6)):
        expected = quadratic_curve(SOC_GRID) + offset
        assert table.ocv[row] == pytest.approx(expected, abs=1e-5)
    assert table.monotone.all()
    assert not table.fallback_used


def test_charge_half_and_rest_do_not_enter_the_table():
    """The made-up charge half sits at 4.5 V; if a charge row were used, the table would reach it."""
    runs = make_runs(same_curve_at_every_temperature(linear_curve), with_rest_and_charge=True)
    with_charge = build_ocv(runs, SOC_GRID, T_GRID_DEGC)
    runs_without = make_runs(same_curve_at_every_temperature(linear_curve), with_rest_and_charge=False)
    without_charge = build_ocv(runs_without, SOC_GRID, T_GRID_DEGC)

    assert with_charge.ocv.max() < 4.4
    assert np.array_equal(with_charge.ocv, without_charge.ocv)


def test_discharge_half_is_the_longest_run_above_the_threshold():
    """Short blips of current elsewhere do not move the discharge half; the threshold is 50 mA."""
    i = np.zeros(40)
    i[2:5] = 1.0  # a short blip
    i[10:30] = 0.2  # the long run: the discharge half
    i[35:37] = 3.0
    assert find_discharge_half(i) == (10, 29)

    # A current at or below the threshold is a rest, so it does not extend the run.
    i[30] = DISCHARGE_MIN_A
    assert find_discharge_half(i) == (10, 29)

    with pytest.raises(ValueError):
        find_discharge_half(np.zeros(10))


def test_grid_points_below_the_end_of_discharge_hold_the_last_value():
    """A discharge that stops at SoC 0.2 gives a flat table below 0.2 and records soc_min = 0.2."""
    runs = make_runs(same_curve_at_every_temperature(linear_curve), soc_end=0.2)
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)

    assert table.soc_min == pytest.approx(np.full(6, 0.2), abs=1e-9)
    for row, offset in enumerate(0.01 * np.arange(6)):
        held_value = linear_curve(0.2) + offset
        below = SOC_GRID < 0.2 - 1e-9
        assert below.sum() == 20
        assert table.ocv[row, below] == pytest.approx(np.full(20, held_value), abs=1e-9)
        # Above the end of the discharge the curve is the line.
        above = SOC_GRID >= 0.2 + 1e-9
        assert table.ocv[row, above] == pytest.approx(linear_curve(SOC_GRID[above]) + offset, abs=1e-9)
    assert table.monotone.all()  # held points are not part of the check
    assert not table.fallback_used


def test_grid_points_above_the_first_logged_row_hold_the_first_value():
    """The file opens one log interval into the discharge (SoC 0.999), so SoC 1.0 holds the value at 0.999."""
    runs = make_runs(same_curve_at_every_temperature(linear_curve), soc_start=0.999)
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)

    assert table.soc_max == pytest.approx(np.full(6, 0.999), abs=1e-9)
    for row, offset in enumerate(0.01 * np.arange(6)):
        assert table.ocv[row, 100] == pytest.approx(linear_curve(0.999) + offset, abs=1e-9)
        assert table.ocv[row, 99] == pytest.approx(linear_curve(0.99) + offset, abs=1e-9)


def test_non_monotone_curve_sets_monotone_false_and_the_fallback_copies_25_degc():
    """The -20 degC curve dips: monotone is False there, True elsewhere, and 25 degC is copied to all rows."""
    curves = same_curve_at_every_temperature(quadratic_curve)
    curves[-20] = dipping_curve
    runs = make_runs(curves)
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)

    assert table.monotone.tolist() == [True, True, True, True, True, False]
    assert table.fallback_used is True

    row_25 = T_GRID_DEGC.index(25)
    expected_25 = quadratic_curve(SOC_GRID) + 0.01 * row_25
    for row in range(6):
        assert table.ocv[row] == pytest.approx(expected_25, abs=1e-5)
        assert np.array_equal(table.ocv[row], table.ocv[row_25])
        assert np.array_equal(table.docv[row], table.docv[row_25])
        assert table.soc_min[row] == table.soc_min[row_25]


def test_fallback_is_not_used_when_every_temperature_passes():
    runs = make_runs(same_curve_at_every_temperature(quadratic_curve))
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)
    assert table.fallback_used is False
    assert not np.array_equal(table.ocv[0], table.ocv[1])  # the temperatures keep their own rows


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


def test_docv_of_a_line_is_its_slope_everywhere_including_the_ends():
    runs = make_runs(same_curve_at_every_temperature(linear_curve))
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)
    assert table.docv == pytest.approx(np.full((6, 101), 1.2), abs=1e-9)


def test_docv_is_positive_for_a_rising_curve_and_matches_central_differences():
    """Inside: (V[k+1] - V[k-1]) / (2 * 0.01). At the ends: the one-sided difference over one grid step."""
    runs = make_runs(same_curve_at_every_temperature(quadratic_curve))
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)

    assert np.all(table.docv > 0.0)
    for row in range(6):
        ocv = table.ocv[row]
        for k in range(1, 100):
            expected = (ocv[k + 1] - ocv[k - 1]) / 0.02
            assert table.docv[row, k] == pytest.approx(expected, rel=1e-9)
        assert table.docv[row, 0] == pytest.approx((ocv[1] - ocv[0]) / 0.01, rel=1e-9)
        assert table.docv[row, 100] == pytest.approx((ocv[100] - ocv[99]) / 0.01, rel=1e-9)
        # numpy's gradient (first-order ends) is the same operation, as an independent check.
        assert table.docv[row] == pytest.approx(np.gradient(ocv, SOC_GRID), rel=1e-9)
        # And the slope is the derivative of the made-up curve: 1 + 0.8 SoC, to within the grid and PCHIP error.
        assert table.docv[row, 10:90] == pytest.approx(1.0 + 0.8 * SOC_GRID[10:90], abs=2e-4)


def test_docv_is_zero_on_held_points_and_half_a_slope_at_the_kink():
    runs = make_runs(same_curve_at_every_temperature(linear_curve), soc_end=0.2)
    table = build_ocv(runs, SOC_GRID, T_GRID_DEGC)
    for row in range(6):
        assert np.all(table.docv[row, :20] == pytest.approx(0.0, abs=1e-9))
        assert table.docv[row, 20] == pytest.approx(0.6, abs=1e-9)  # half of 1.2: one side flat, one side rising
        assert table.docv[row, 21] == pytest.approx(1.2, abs=1e-9)
    assert np.all(table.docv >= 0.0)


def test_central_differences_on_a_nonuniform_axis():
    x = np.array([0.0, 1.0, 3.0, 4.0])
    values = x * x
    slope = central_differences(values, x)
    assert slope[0] == pytest.approx(1.0)  # (1 - 0) / (1 - 0)
    assert slope[1] == pytest.approx((9.0 - 0.0) / 3.0)
    assert slope[2] == pytest.approx((16.0 - 1.0) / 3.0)
    assert slope[3] == pytest.approx((16.0 - 9.0) / 1.0)


def test_equal_soc_rows_are_averaged_and_the_axis_is_sorted():
    soc = np.array([0.9, 0.5, 0.5, 0.1, 0.9, 0.9])
    v = np.array([4.0, 3.6, 3.8, 3.2, 4.2, 4.1])
    soc_unique, v_mean = average_equal_x(soc, v)
    assert soc_unique.tolist() == [0.1, 0.5, 0.9]
    assert v_mean == pytest.approx([3.2, 3.7, 4.1])


def test_equal_soc_rows_in_a_run_do_not_break_the_pchip():
    """Two rows with the same counter value would make PCHIP fail without the averaging."""
    run = make_c20_run(linear_curve)
    run.ah_removed[500] = run.ah_removed[499]  # the counter did not move between rows 499 and 500
    table = build_ocv({temp: run for temp in T_GRID_DEGC}, SOC_GRID, T_GRID_DEGC)
    assert np.all(np.isfinite(table.ocv))
    assert table.monotone.all()


# --------------------------------------------------------------------------------------------
# Real data
# --------------------------------------------------------------------------------------------


def section_table_column(section_number, column_name):
    """Read one column of the first table in a section of results/data_checks.md that has that column.

    Returns {folder name: text of the cell} for the rows whose first cell is a data folder name.
    """
    if not DATA_CHECKS_MD.exists():
        pytest.skip("results/data_checks.md is missing")

    in_section = False
    column_index = None
    cells_by_folder = {}
    for line in DATA_CHECKS_MD.read_text().splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.startswith(f"## {section_number}. ")
            continue
        if not in_section or not line.startswith("|"):
            if column_index is not None and cells_by_folder:
                break  # the table ended
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if column_index is None and column_name in cells and cells[0] == "folder":
            column_index = cells.index(column_name)
        elif column_index is not None and cells[0] in FOLDER_TEMP:
            cells_by_folder[cells[0]] = cells[column_index]
    assert cells_by_folder, f"no column {column_name!r} in section {section_number} of results/data_checks.md"
    return cells_by_folder


@pytest.fixture(scope="module")
def real_c20_runs():
    """The six C20DisCh files loaded, keyed by nominal temperature in degC."""
    paths = find_runs(RAW_DIR, test_type="c20")
    runs = {}
    for path in paths:
        run = load_run(path)
        runs[run.meta["nominal_temp_degc"]] = run
    return runs


@pytest.fixture(scope="module")
def real_table(real_c20_runs):
    return build_ocv(real_c20_runs, SOC_GRID, T_GRID_DEGC)


@pytest.mark.needs_data
def test_real_runs_are_the_six_c20_files(real_c20_runs):
    assert sorted(real_c20_runs) == sorted(T_GRID_DEGC)
    for temp, run in real_c20_runs.items():
        assert run.meta["test_type"] == "c20"
        assert FOLDER_TEMP[run.meta["folder"]] == temp


@pytest.mark.needs_data
def test_real_discharge_halves_have_the_row_counts_of_data_checks(real_c20_runs):
    """Section 11 finds the discharge half the same way (longest run above 50 mA) and counts its rows."""
    rows_by_folder = section_table_column(11, "discharge rows")
    for folder, text in rows_by_folder.items():
        run = real_c20_runs[FOLDER_TEMP[folder]]
        first, last = find_discharge_half(run.i)
        assert last - first + 1 == int(text), folder
        assert first == 0, folder  # the file opens inside the discharge


@pytest.mark.needs_data
def test_real_soc_min_matches_data_checks_within_half_a_pp(real_table):
    """soc_min per temperature against the end-of-discharge SoC (%) of results/data_checks.md section 11."""
    end_soc_pct = section_table_column(11, "end-of-discharge SoC (%)")
    assert len(end_soc_pct) == 6
    for folder, text in end_soc_pct.items():
        row = T_GRID_DEGC.index(FOLDER_TEMP[folder])
        soc_min_pp = 100.0 * real_table.soc_min[row]
        assert soc_min_pp == pytest.approx(float(text), abs=0.5), folder


@pytest.mark.needs_data
def test_real_table_needs_no_fallback_and_is_monotone(real_table):
    assert real_table.monotone.tolist() == [True] * 6
    assert real_table.fallback_used is False
    # Each temperature has its own curve: the rows are not copies of one another.
    for row in range(1, 6):
        assert not np.array_equal(real_table.ocv[row], real_table.ocv[0])


@pytest.mark.needs_data
def test_real_table_is_physically_plausible(real_table):
    """Voltages of an NMC cell between empty and full, rising with SoC, slope never negative."""
    assert real_table.ocv.min() > 2.7 and real_table.ocv.max() < 4.25
    assert np.all(real_table.docv >= 0.0)
    for row in range(6):
        valid = (SOC_GRID >= real_table.soc_min[row]) & (SOC_GRID <= real_table.soc_max[row])
        assert np.all(np.diff(real_table.ocv[row, valid]) > 0.0)
        assert real_table.ocv[row, 100] > real_table.ocv[row, 50] > real_table.ocv[row, 0]
        assert real_table.soc_max[row] > 0.99  # the file opens one log interval into the discharge
