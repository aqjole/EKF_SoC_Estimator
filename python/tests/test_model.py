"""Tests for ekfsoc.model: the bilinear lookup (Eq. 4), the 2RC open-loop simulation (Eq. 1, Eq. 2)
and the params.csv round trip. Everything runs on small made-up tables, so no raw data is needed.
The expected values are worked out by hand in the comments, not by calling the code under test.
"""

import math

import numpy as np
import pytest
from scipy.interpolate import RegularGridInterpolator

from ekfsoc.constants import SOC_GRID, T_GRID_DEGC
from ekfsoc.model import CSV_COLUMNS, Params, find_cell, interp2, simulate_2rc_open_loop


# --- interp2 -------------------------------------------------------------------------------------

# A small table on the project's descending temperature order. Rows: 40, 25, 10 degC.
# Columns: SoC 0, 0.5, 1. The values are all different, so a mix-up of rows or columns shows.
SMALL_T = [40.0, 25.0, 10.0]
SMALL_SOC = [0.0, 0.5, 1.0]
SMALL_TABLE = [
    [1.0, 2.0, 4.0],  # 40 degC
    [3.0, 5.0, 9.0],  # 25 degC
    [6.0, 8.0, 16.0],  # 10 degC
]


def test_interp2_on_every_node_returns_the_node_value():
    # Use the real axes (6 temperatures descending, 101 SoC points) with a table that has a
    # different value at every node.
    t_grid = np.array(T_GRID_DEGC, dtype=float)
    table = np.arange(len(t_grid) * len(SOC_GRID), dtype=float).reshape(len(t_grid), len(SOC_GRID)) * 0.001 + 2.5
    for j in range(len(t_grid)):
        for m in range(len(SOC_GRID)):
            value = interp2(table, t_grid, SOC_GRID, t_grid[j], SOC_GRID[m])
            assert value == pytest.approx(table[j, m], rel=1e-12, abs=0.0)


@pytest.mark.parametrize(
    "temp, soc, expected, how",
    [
        # Halfway in both. Row 25 at SoC 0.25 is half way between its columns 0 and 0.5, which hold 3 and 5: 4.
        # Row 10 at SoC 0.25 is half way between 6 and 8: 7. Halfway between the rows 25 and 10: (4 + 7)/2 = 5.5.
        (17.5, 0.25, 5.5, "midpoint of the cell (25..10, 0..0.5)"),
        # SoC 0.75 is halfway between columns 0.5 and 1: row 25 gives (5 + 9)/2 = 7, row 10 gives (8 + 16)/2 = 12.
        # T = 20 is 5 of the 15 degC from 25 to 10: weight 1/3. Result (2/3)*7 + (1/3)*12 = 14/3 + 4.
        (20.0, 0.75, 14.0 / 3.0 + 4.0, "unequal temperature weight, 1/3"),
        # SoC 0.1 is 0.2 of the way from column 0 to 0.5. Row 40: 0.8*1 + 0.2*2 = 1.2. Row 25: 0.8*3 + 0.2*5 = 3.4.
        # T = 37.5 is 2.5 of the 15 degC from 40 to 25: weight 1/6. Result (5/6)*1.2 + (1/6)*3.4 = 1.0 + 0.5666...
        (37.5, 0.1, (5.0 / 6.0) * 1.2 + (1.0 / 6.0) * 3.4, "unequal SoC weight, 0.2, and temperature weight 1/6"),
        # On a temperature node (25) and between SoC nodes: only the SoC interpolation remains: (5 + 9)/2 = 7.
        (25.0, 0.75, 7.0, "on a temperature node"),
        # On a SoC node (0.5) and between temperatures 40 and 25: (2 + 5)/2 = 3.5.
        (32.5, 0.5, 3.5, "on a SoC node"),
    ],
)
def test_interp2_between_nodes_is_the_bilinear_value(temp, soc, expected, how):
    value = interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, temp, soc)
    assert value == pytest.approx(expected, rel=1e-12), how


def test_interp2_works_on_an_ascending_temperature_axis_too():
    # The same table with the rows in the opposite order and the axis ascending gives the same value.
    ascending_t = [10.0, 25.0, 40.0]
    ascending_table = [SMALL_TABLE[2], SMALL_TABLE[1], SMALL_TABLE[0]]
    for temp, soc in [(17.5, 0.25), (20.0, 0.75), (37.5, 0.1), (40.0, 1.0), (10.0, 0.0)]:
        descending = interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, temp, soc)
        ascending = interp2(ascending_table, ascending_t, SMALL_SOC, temp, soc)
        assert ascending == pytest.approx(descending, rel=1e-12)


def test_interp2_clamps_beyond_both_ends_of_both_axes():
    # Beyond the 40 degC end the first row is used, beyond the 10 degC end the last row.
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, 100.0, 0.25) == pytest.approx(interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, 40.0, 0.25))
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, -50.0, 0.25) == pytest.approx(interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, 10.0, 0.25))
    # Beyond SoC 0 and SoC 1.
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, 25.0, -0.3) == pytest.approx(3.0)
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, 25.0, 1.7) == pytest.approx(9.0)
    # All four corners, each beyond both axes at once: the corner node values 1, 4, 6, 16.
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, 99.0, -1.0) == pytest.approx(1.0)
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, 99.0, 2.0) == pytest.approx(4.0)
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, -99.0, -1.0) == pytest.approx(6.0)
    assert interp2(SMALL_TABLE, SMALL_T, SMALL_SOC, -99.0, 2.0) == pytest.approx(16.0)


def test_interp2_agrees_with_scipy_on_random_queries_including_out_of_range():
    # Independent check of the rule: scipy's bilinear interpolator needs ascending axes, so flip the
    # temperature axis for it, and clamp the queries the same way before asking it.
    rng = np.random.default_rng(7)
    t_grid = np.array(T_GRID_DEGC, dtype=float)
    soc_grid = np.linspace(0.0, 1.0, 11)
    table = rng.normal(size=(len(t_grid), len(soc_grid)))
    scipy_interp = RegularGridInterpolator((t_grid[::-1], soc_grid), table[::-1, :], method="linear")
    for _ in range(300):
        temp = rng.uniform(-35.0, 55.0)
        soc = rng.uniform(-0.2, 1.2)
        point = [min(max(temp, -20.0), 40.0), min(max(soc, 0.0), 1.0)]
        assert interp2(table, t_grid, soc_grid, temp, soc) == pytest.approx(float(scipy_interp(point)[0]), abs=1e-12)


def test_find_cell_returns_the_last_cell_with_weight_one_at_the_last_node():
    # Descending axis: the last node (-20) is in the last cell, at its far end.
    assert find_cell(T_GRID_DEGC, -20.0) == (len(T_GRID_DEGC) - 2, 1.0)
    # The first node starts the first cell.
    assert find_cell(T_GRID_DEGC, 40.0) == (0, 0.0)
    # 5 degC lies between 10 and 0, which is cell 2 (nodes 10 and 0), half way.
    assert find_cell(T_GRID_DEGC, 5.0) == (2, 0.5)


# --- simulate_2rc_open_loop -----------------------------------------------------------------------


def constant_params(ocv, r0, r1, tau1, r2, tau2):
    """Params whose seven tables are the same number at every node of a small 2 x 2 grid (docv = 0)."""
    shape = (2, 2)
    return Params(
        t_grid=[25.0, 0.0],
        soc_grid=[0.0, 1.0],
        ocv=np.full(shape, ocv),
        docv=np.zeros(shape),
        r0=np.full(shape, r0),
        r1=np.full(shape, r1),
        tau1=np.full(shape, tau1),
        r2=np.full(shape, r2),
        tau2=np.full(shape, tau2),
    )


def test_constant_current_reproduces_the_closed_form_rc_step_response():
    ocv, r0, r1, tau1, r2, tau2 = 3.7, 0.030, 0.012, 4.0, 0.020, 200.0
    params = constant_params(ocv, r0, r1, tau1, r2, tau2)
    current = 5.0
    step = 0.5
    n = 400
    i = np.full(n, current)
    temp = np.full(n, 12.0)
    soc = np.full(n, 0.6)
    dt = np.full(n, step)
    dt[0] = 0.0

    v_model = simulate_2rc_open_loop(params, i, temp, soc, dt)

    # Closed form for a current switched on at k = 0: V_i(t) = R_i * I * (1 - exp(-t / tau_i)), t = k * step.
    for k in range(n):
        t = k * step
        v1 = r1 * current * (1.0 - math.exp(-t / tau1))
        v2 = r2 * current * (1.0 - math.exp(-t / tau2))
        expected = ocv - v1 - v2 - r0 * current
        assert v_model[k] == pytest.approx(expected, abs=1e-12)


def test_two_hand_computed_zero_order_hold_steps_with_unequal_dt_and_current():
    # OCV 3.7 V, R0 0.05 Ohm, branch 1: R1 0.01 Ohm, tau1 2 s; branch 2: R2 0.02 Ohm, tau2 10 s.
    params = constant_params(3.7, 0.05, 0.01, 2.0, 0.02, 10.0)
    i = np.array([2.0, 4.0, -1.0])
    dt = np.array([0.0, 1.0, 2.0])
    temp = np.zeros(3)
    soc = np.full(3, 0.5)

    v_model = simulate_2rc_open_loop(params, i, temp, soc, dt)

    # Row 0: both states are 0, so only R0 acts: 3.7 - 0.05 * 2 = 3.6 V.
    assert v_model[0] == pytest.approx(3.6, abs=1e-12)

    # Step 0 -> 1: the current of row 0 (2 A) is held over dt[1] = 1 s.
    #   a1 = exp(-1/2) = 0.6065306597, a2 = exp(-1/10) = 0.9048374180
    #   V1 = 0.01 * (1 - 0.6065306597) * 2 = 0.007869386806
    #   V2 = 0.02 * (1 - 0.9048374180) * 2 = 0.003806503280
    # Row 1: 3.7 - V1 - V2 - 0.05 * 4 = 3.7 - 0.007869386806 - 0.003806503280 - 0.2
    assert v_model[1] == pytest.approx(3.488324109914, abs=1e-9)

    # Step 1 -> 2: the current of row 1 (4 A) is held over dt[2] = 2 s.
    #   a1 = exp(-2/2) = 0.3678794412, a2 = exp(-2/10) = 0.8187307531
    #   V1 = 0.3678794412 * 0.007869386806 + 0.01 * (1 - 0.3678794412) * 4 = 0.002894985620 + 0.025284822353
    #      = 0.028179807974
    #   V2 = 0.8187307531 * 0.003806503279 + 0.02 * (1 - 0.8187307531) * 4 = 0.003116501296 + 0.014501539754
    #      = 0.017618041050
    # Row 2 carries a charge current of -1 A (regen): the R0 term adds 0.05 V.
    #   3.7 - 0.028179807974 - 0.017618041050 + 0.05 = 3.704202150976
    v1_row2 = 0.3678794412 * 0.007869386806 + 0.01 * (1.0 - 0.3678794412) * 4.0
    v2_row2 = 0.8187307531 * 0.003806503279 + 0.02 * (1.0 - 0.8187307531) * 4.0
    assert v1_row2 == pytest.approx(0.028179807974, abs=1e-9)
    assert v2_row2 == pytest.approx(0.017618041050, abs=1e-9)
    assert v_model[2] == pytest.approx(3.704202150976, abs=1e-9)


def test_rc_parameters_are_taken_at_the_start_of_the_step_and_ocv_and_r0_at_the_sample():
    # Tables that vary along SoC only, same at both temperatures (columns SoC 0 and 1):
    #   OCV 3.0 -> 4.0 V, R0 0.10 -> 0.20 Ohm, R1 0.01 -> 0.03 Ohm, tau1 = 1 s at both, R2 = 0, tau2 = 100 s.
    # Rows at SoC 0.0 and 1.0 with a 1 A current and dt[1] = 1 s.
    t_grid = [25.0, 0.0]
    soc_grid = [0.0, 1.0]
    two_columns = lambda a, b: np.array([[a, b], [a, b]])
    params = Params(
        t_grid=t_grid,
        soc_grid=soc_grid,
        ocv=two_columns(3.0, 4.0),
        docv=two_columns(0.0, 0.0),
        r0=two_columns(0.10, 0.20),
        r1=two_columns(0.01, 0.03),
        tau1=two_columns(1.0, 1.0),
        r2=two_columns(0.0, 0.0),
        tau2=two_columns(100.0, 100.0),
    )
    i = np.array([1.0, 1.0])
    dt = np.array([0.0, 1.0])
    temp = np.array([10.0, 10.0])
    soc = np.array([0.0, 1.0])

    v_model = simulate_2rc_open_loop(params, i, temp, soc, dt)

    # Row 0 at SoC 0: 3.0 - 0 - 0 - 0.10 * 1 = 2.9 V.
    assert v_model[0] == pytest.approx(2.9, abs=1e-12)
    # The state for row 1 comes from the step that starts at row 0 (SoC 0, R1 = 0.01):
    #   V1 = 0.01 * (1 - exp(-1)) * 1 = 0.006321205588 (with R1 = 0.03 it would be three times larger).
    # Row 1 reads OCV and R0 at SoC 1: 4.0 - V1 - 0.20 * 1.
    assert v_model[1] == pytest.approx(4.0 - 0.01 * (1.0 - math.exp(-1.0)) - 0.20, abs=1e-12)


def test_simulate_rejects_arrays_of_different_length():
    params = constant_params(3.7, 0.05, 0.01, 2.0, 0.02, 10.0)
    with pytest.raises(ValueError):
        simulate_2rc_open_loop(params, np.zeros(3), np.zeros(3), np.zeros(2), np.zeros(3))


# --- Params and results/params.csv ----------------------------------------------------------------


def synthetic_params():
    """A 3 x 4 table (temperatures 40, 0, -20 degC; SoC 0, 0.25, 0.5, 1) with a different value everywhere."""
    t_grid = [40.0, 0.0, -20.0]
    soc_grid = [0.0, 0.25, 0.5, 1.0]
    rng = np.random.default_rng(3)
    shape = (3, 4)
    return Params(
        t_grid=t_grid,
        soc_grid=soc_grid,
        ocv=3.0 + rng.random(shape),
        docv=rng.random(shape),
        r0=0.01 + 0.1 * rng.random(shape),
        r1=0.005 + 0.05 * rng.random(shape),
        tau1=0.5 + 29.0 * rng.random(shape),
        r2=0.005 + 0.05 * rng.random(shape),
        tau2=30.0 + 3500.0 * rng.random(shape),
    )


def test_params_round_trip_through_csv(tmp_path):
    original = synthetic_params()
    path = tmp_path / "params.csv"
    original.to_csv(path)
    reloaded = Params.from_csv(path)

    assert reloaded.t_grid.tolist() == original.t_grid.tolist()
    assert reloaded.soc_grid.tolist() == original.soc_grid.tolist()
    for name in ("ocv", "docv", "r0", "r1", "tau1", "r2", "tau2"):
        assert getattr(reloaded, name).shape == (3, 4)
        # 6 significant digits are kept, so the round trip is exact to about 1e-6 relative.
        assert np.allclose(getattr(reloaded, name), getattr(original, name), rtol=1e-5, atol=0.0), name


def test_csv_layout_header_row_count_and_order(tmp_path):
    params = synthetic_params()
    path = tmp_path / "params.csv"
    params.to_csv(path)
    lines = path.read_text().splitlines()

    assert lines[0] == "T_degC,soc,ocv_V,docv_V_per_soc,R0_ohm,R1_ohm,tau1_s,R2_ohm,tau2_s"
    assert tuple(lines[0].split(",")) == CSV_COLUMNS
    assert len(lines) == 1 + 3 * 4
    # T-major: the first four data rows are the first temperature (40 degC) at SoC 0, 0.25, 0.5, 1.
    first_block = [line.split(",")[:2] for line in lines[1:5]]
    assert first_block == [["40", "0"], ["40", "0.25"], ["40", "0.5"], ["40", "1"]]
    assert lines[5].split(",")[:2] == ["0", "0"]
    # Row 6 of the file is (T=0, soc=0.25): its OCV column holds the table value of row index 1, column 1.
    cells = lines[6].split(",")
    assert float(cells[2]) == pytest.approx(params.ocv[1, 1], rel=1e-5)
    assert float(cells[8]) == pytest.approx(params.tau2[1, 1], rel=1e-5)


def test_csv_is_written_with_six_significant_digits_and_regenerates_byte_identical(tmp_path):
    params = synthetic_params()
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    params.to_csv(first)
    Params.from_csv(first).to_csv(second)
    for line in first.read_text().splitlines()[1:]:
        for cell in line.split(","):
            digits = cell.replace("-", "").replace(".", "").lstrip("0")
            digits = digits.split("e")[0]
            assert len(digits) <= 6, cell
    # Writing, reading and writing again gives the same bytes: the 6-digit text is its own fixed point.
    assert first.read_bytes() == second.read_bytes()


def test_params_rejects_a_table_of_the_wrong_shape():
    good = synthetic_params()
    with pytest.raises(ValueError):
        Params(
            t_grid=good.t_grid,
            soc_grid=good.soc_grid,
            ocv=np.zeros((3, 3)),
            docv=good.docv,
            r0=good.r0,
            r1=good.r1,
            tau1=good.tau1,
            r2=good.r2,
            tau2=good.tau2,
        )


def test_from_csv_rejects_a_wrong_header_and_a_changed_axis_value(tmp_path):
    params = synthetic_params()
    path = tmp_path / "params.csv"
    params.to_csv(path)
    lines = path.read_text().splitlines()

    bad_header = tmp_path / "bad_header.csv"
    bad_header.write_text("\n".join(["T,soc,ocv"] + lines[1:]) + "\n")
    with pytest.raises(ValueError):
        Params.from_csv(bad_header)

    # Second block repeats SoC 0, 0.25, 0.5, 1 in the first block; change one SoC value in it.
    changed = list(lines)
    cells = changed[7].split(",")
    cells[1] = "0.4"
    changed[7] = ",".join(cells)
    bad_axis = tmp_path / "bad_axis.csv"
    bad_axis.write_text("\n".join(changed) + "\n")
    with pytest.raises(ValueError):
        Params.from_csv(bad_axis)
