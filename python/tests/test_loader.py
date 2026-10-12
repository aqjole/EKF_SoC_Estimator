"""Tests for ekfsoc.loader: sign and unit conventions on the committed fixture, each loader rule on
made-up arrays, and (when data/raw/ exists) the two files that need a cut.

The fixture python/tests/fixtures/lghg2_excerpt.mat is a copy of 25degC/551_Cap_1C (see its README),
a 1C discharge logged every 10 s. The expected numbers in the data tests come from
results/data_checks.md section 4 and results/data_inventory.md.
"""

import datetime
from pathlib import Path

import numpy as np
import pytest

from ekfsoc import rawio
from ekfsoc.constants import FOLDER_TEMP, Q_REF_AH, RAW_DIR
from ekfsoc.loader import Run, build_run, find_runs, load_run, soc_ref

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_PATH = TESTS_DIR / "fixtures" / "lghg2_excerpt.mat"
CAPACITY_MD = TESTS_DIR.parents[1] / "results" / "capacity.md"

# Lowest current counted as "discharging" when the tests look at the discharge segment (A).
FLOW_A = 0.05


@pytest.fixture(scope="module")
def fixture_run():
    """The fixture file loaded once for the whole module."""
    return load_run(FIXTURE_PATH)


def capacity_1c_for_551_cap_1c():
    """Read the 1C capacity of 25degC/551_Cap_1C from results/capacity.md (the cap_1c row of that file)."""
    if not CAPACITY_MD.exists():
        pytest.skip("results/capacity.md is missing")
    for line in CAPACITY_MD.read_text().splitlines():
        if "551_Cap_1C" in line and "cap_1c" in line:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            return float(cells[cells.index("cap_1c") + 1])
    raise AssertionError("no cap_1c row for 551_Cap_1C in results/capacity.md")


# --------------------------------------------------------------------------------------------
# Fixture: sign, units, Ah, dt
# --------------------------------------------------------------------------------------------


def test_fixture_discharge_current_is_positive(fixture_run):
    """The known discharge step: Current goes 0 -> -3.0011 A at Time 60.005 s (chk 19); I must be +3 A."""
    run = fixture_run
    assert run.i.min() >= 0.0  # a Cap_1C file only discharges, and 0.0 - (-0.0) must not give a negative

    first_flow = int(np.flatnonzero(run.i > FLOW_A)[0])
    assert run.t[first_flow] == pytest.approx(60.005, abs=0.01)
    assert run.i[first_flow - 1] == 0.0
    assert run.i[first_flow] == pytest.approx(3.0011, abs=0.001)
    # Voltage falls when the discharge starts: 4.1927 V -> 4.0928 V (chk 19).
    assert run.v[first_flow - 1] == pytest.approx(4.1927, abs=0.0001)
    assert run.v[first_flow] == pytest.approx(4.0928, abs=0.0001)
    assert run.v[first_flow] < run.v[first_flow - 1]


def test_fixture_units_are_plausible(fixture_run):
    """Volts, amps, seconds and degC: the numbers must sit in the ranges the cell and the test can have."""
    run = fixture_run
    assert run.v.min() > 2.5 and run.v.max() < 4.3

    discharging = run.i[run.i > FLOW_A]
    assert np.median(np.abs(discharging)) == pytest.approx(3.0, abs=0.05)  # 1C = 3 A

    assert run.t[0] == 0.0
    assert run.t[-1] == pytest.approx(3921.469, abs=0.01)  # about 65 min, in s
    assert np.median(run.dt[1:]) == pytest.approx(10.0, abs=0.01)  # this test logs every 10 s

    assert 20.0 < run.temp.min() and run.temp.max() < 30.0  # 25 degC chamber
    assert run.meta["test_type"] == "other"  # the fixture's name is not a dataset file name


def test_fixture_ah_removed_rises_and_ends_at_the_1c_capacity(fixture_run):
    """ah_removed is 0 at the first row, rises through the discharge and ends at the capacity in results/capacity.md."""
    run = fixture_run
    assert run.ah_removed[0] == 0.0
    assert np.all(np.diff(run.ah_removed) >= 0.0)  # only discharge in this file, so it never falls

    discharge_rows = np.flatnonzero(run.i > FLOW_A)
    assert np.all(np.diff(run.ah_removed[discharge_rows]) > 0.0)  # strictly rising while current flows

    expected = capacity_1c_for_551_cap_1c()
    assert run.ah_removed[-1] == pytest.approx(expected, abs=0.001)


def test_fixture_dt_is_positive_and_comes_from_time(fixture_run):
    """After the rules every step is above 0 and equals the Time difference; the first is 0."""
    run = fixture_run
    assert run.dt[0] == 0.0
    assert np.all(run.dt[1:] > 0.0)
    assert np.array_equal(run.dt[1:], run.t[1:] - run.t[:-1])


def test_fixture_arrays_and_meta(fixture_run):
    """The Run holds 1-D float64 arrays of one length, and the row counts in meta add up."""
    run = fixture_run
    assert isinstance(run, Run)
    for name in ("t", "i", "v", "temp", "ah_removed", "dt"):
        array = getattr(run, name)
        assert array.dtype == np.float64 and array.ndim == 1 and len(array) == len(run.t)
    assert run.soc0 == 1.0

    meta = run.meta
    assert meta["n_rows_used"] == len(run.t)
    assert meta["n_rows_raw"] == (
        meta["n_dropped_rows"] + meta["n_cut_rows"] + meta["n_duplicates_removed"] + meta["n_rows_used"]
    )
    assert meta["cut"] is None
    assert meta["nominal_temp_degc"] is None  # the fixture is not in a temperature folder

    # The duplicates removed are the rows that repeat the Time of the row before, counted on the stored file.
    stored_time = rawio.load_mat(FIXTURE_PATH)["Time"]
    assert meta["n_duplicates_removed"] == int(np.sum(np.diff(stored_time) == 0.0))
    assert meta["n_duplicates_removed"] == 2


def test_fixture_wh_stored_as_uint8_still_loads():
    """Wh is stored as uint8 in this file; the loader must still return float64 arrays (no overflow, no error)."""
    _, details = rawio.load_mat_details(FIXTURE_PATH)
    assert details["dtypes"]["Wh"] == "uint8"


# --------------------------------------------------------------------------------------------
# Synthetic arrays: one test per loader rule
# --------------------------------------------------------------------------------------------


def make_fields(time, voltage, current, ah=None, temp=None):
    """Made-up file contents in the cycler's convention (discharge current negative, Ah falling)."""
    n_rows = len(time)
    if ah is None:
        ah = np.zeros(n_rows)
    if temp is None:
        temp = np.full(n_rows, 25.0)
    return {
        "Time": np.array(time, dtype=np.float64),
        "Voltage": np.array(voltage, dtype=np.float64),
        "Current": np.array(current, dtype=np.float64),
        "Ah": np.array(ah, dtype=np.float64),
        "Battery_Temp_degC": np.array(temp, dtype=np.float64),
    }


def build(fields, test_type="udds", **kwargs):
    """build_run() with the file, folder and test type that do not matter for the rule under test."""
    return build_run(fields, "synthetic.mat", "25degC", test_type, **kwargs)


def test_rule1_voltage_zero_and_negative_rows_are_dropped():
    fields = make_fields(
        time=[0.0, 1.0, 2.0, 3.0, 4.0],
        voltage=[4.1, 0.0, 4.0, -0.3, 3.9],
        current=[0.0, -1.0, -1.0, -1.0, -1.0],
    )
    run = build(fields)
    assert list(run.t) == [0.0, 2.0, 4.0]
    assert list(run.v) == [4.1, 4.0, 3.9]
    assert run.meta["n_dropped_rows"] == 2
    assert run.meta["n_rows_raw"] == 5


@pytest.mark.parametrize("name", ["Time", "Voltage", "Current", "Ah", "Battery_Temp_degC"])
def test_rule1_nan_row_is_dropped_in_each_required_field(name):
    fields = make_fields(
        time=[0.0, 1.0, 2.0, 3.0],
        voltage=[4.1, 4.0, 3.9, 3.8],
        current=[0.0, -1.0, -1.0, -1.0],
    )
    fields[name][2] = np.nan
    run = build(fields)
    assert run.meta["n_dropped_rows"] == 1
    assert run.meta["n_rows_used"] == 3
    assert not np.any(np.isnan(run.t))
    assert not np.any(np.isnan(run.v))
    assert not np.any(np.isnan(run.i))
    assert not np.any(np.isnan(run.ah_removed))
    assert not np.any(np.isnan(run.temp))


def test_rule1_nan_in_wh_or_power_alone_keeps_the_row():
    """Wh and Power are not used, so a NaN in them does not drop a row (C10, row 1943 of 582_LA92)."""
    fields = make_fields(time=[0.0, 1.0, 2.0], voltage=[4.1, 4.0, 3.9], current=[0.0, -1.0, -1.0])
    fields["Wh"] = np.array([0.0, np.nan, 0.0])
    fields["Power"] = np.array([0.0, np.nan, 0.0])
    run = build(fields)
    assert run.meta["n_dropped_rows"] == 0
    assert list(run.t) == [0.0, 1.0, 2.0]


def test_rule3_duplicate_time_keeps_the_last_row():
    """Rows 1 and 2 share Time 1.0 and rows 3, 4 and 5 share Time 2.0; the last row of each group stays."""
    fields = make_fields(
        time=[0.0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0],
        voltage=[4.10, 4.01, 4.02, 3.91, 3.92, 3.93, 3.80],
        current=[0.0, -1.0, -1.1, -1.0, -1.2, -1.3, -1.0],
    )
    run = build(fields)
    assert list(run.t) == [0.0, 1.0, 2.0, 3.0]
    assert list(run.v) == [4.10, 4.02, 3.93, 3.80]
    assert list(run.i) == [0.0, 1.1, 1.3, 1.0]
    assert run.meta["n_duplicates_removed"] == 3


def test_rule3_only_consecutive_rows_count_as_duplicates():
    """Equal Time values that are not neighbours are not merged (and would fail rule 4 instead)."""
    fields = make_fields(time=[0.0, 1.0, 0.5, 1.0], voltage=[4.1] * 4, current=[0.0] * 4)
    with pytest.raises(ValueError):
        build(fields)


def test_rule4_dt_comes_from_time_not_from_timestamp():
    """dt = Time(k) - Time(k-1) in float64, dt[0] = 0. A TimeStamp with other spacing must make no difference."""
    time = [10.0, 10.1, 10.25, 11.75, 11.8]
    fields = make_fields(time=time, voltage=[4.0] * 5, current=[0.0] * 5)
    fields["TimeStamp"] = np.array(["01/01/2018  1:00:00.000 AM"] * 5)  # all the same: useless as a clock
    run = build(fields)
    assert run.dt.dtype == np.float64
    assert run.dt[0] == 0.0
    assert np.allclose(run.dt[1:], np.diff(time), rtol=0.0, atol=1e-12)
    assert list(run.t) == time  # Time is not shifted to start at 0


def test_rule4_long_steps_are_listed_and_kept():
    fields = make_fields(time=[0.0, 0.1, 0.2, 1.7, 1.8, 3.9], voltage=[4.0] * 6, current=[0.0] * 6)
    run = build(fields)
    assert [row for row, _ in run.meta["gaps_over_1s"]] == [3, 5]
    assert run.meta["gaps_over_1s"][0][1] == pytest.approx(1.5)
    assert run.meta["gaps_over_1s"][1][1] == pytest.approx(2.1)
    assert len(run.t) == 6  # the long steps stay in the run


def test_rules_run_in_the_documented_order():
    """Rule 1 comes before rule 3: a 0 V row that shares Time with a good row is dropped first, so the good row stays.

    If duplicates were removed first, the 0 V row (the last of the pair) would be the one kept and then dropped,
    and no row at Time 1.0 would be left.
    """
    fields = make_fields(
        time=[0.0, 1.0, 1.0, 2.0],
        voltage=[4.1, 4.0, 0.0, 3.9],
        current=[0.0, -1.0, 0.0, -1.0],
    )
    run = build(fields)
    assert list(run.t) == [0.0, 1.0, 2.0]
    assert run.v[1] == 4.0
    assert run.meta["n_dropped_rows"] == 1
    assert run.meta["n_duplicates_removed"] == 0


def test_time_that_still_goes_backwards_is_an_error():
    fields = make_fields(time=[0.0, 5.0, 3.0, 6.0], voltage=[4.0] * 4, current=[0.0] * 4)
    with pytest.raises(ValueError, match="Time does not increase"):
        build(fields)


def test_all_rows_dropped_is_an_error():
    fields = make_fields(time=[0.0, 1.0], voltage=[0.0, 0.0], current=[0.0, 0.0])
    with pytest.raises(ValueError):
        build(fields)


def test_sign_of_current_and_counter():
    """I = -Current (discharge positive); ah_removed = -(Ah - Ah at the first row), 0 at the first row, rising on discharge."""
    fields = make_fields(
        time=[0.0, 1.0, 2.0, 3.0, 4.0],
        voltage=[4.1, 4.0, 3.9, 3.95, 3.95],
        current=[0.0, -2.0, -2.0, 1.0, 0.0],  # discharge, discharge, then regen
        ah=[-0.00004, -0.5, -1.0, -0.75, -0.75],
    )
    run = build(fields)
    assert list(run.i) == [0.0, 2.0, 2.0, -1.0, 0.0]
    assert not np.signbit(run.i[0])  # +0.0, not -0.0
    assert run.ah_removed[0] == 0.0 and not np.signbit(run.ah_removed[0])
    assert run.ah_removed[1:] == pytest.approx([0.49996, 0.99996, 0.74996, 0.74996])


@pytest.mark.parametrize("test_type", ["c20", "dis_2c"])
def test_c20_and_dis_2c_count_from_the_step_start_zero(test_type):
    """These files open after a counter reset: ah_removed = -Ah, so the first row is not 0 (C3)."""
    fields = make_fields(
        time=[0.0, 60.0, 120.0],
        voltage=[4.1, 4.09, 4.08],
        current=[-0.15, -0.15, -0.15],
        ah=[-0.0025, -0.005, -0.0075],
    )
    run = build(fields, test_type=test_type)
    assert run.ah_removed == pytest.approx([0.0025, 0.005, 0.0075])
    # The same arrays as any other file type count from the first row.
    other = build(fields, test_type="hppc")
    assert other.ah_removed == pytest.approx([0.0, 0.0025, 0.005])


def test_cut_by_start_row_counts_stored_rows_not_kept_rows():
    """The cut keeps stored rows >= 391 in the real file. Here: start row 3, and a dropped row 1 does not shift it."""
    fields = make_fields(
        time=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        voltage=[4.1, 0.0, 4.0, 3.9, 3.8, 3.7],
        current=[0.0] * 6,
        ah=[0.0, 0.0, -0.1, -0.2, -0.3, -0.4],
    )
    run = build(fields, cut=("start_row", 3))
    assert list(run.t) == [3.0, 4.0, 5.0]
    assert run.ah_removed[0] == 0.0  # counted from the first row used
    assert run.meta["n_dropped_rows"] == 1
    assert run.meta["n_cut_rows"] == 2
    assert "3" in run.meta["cut"]


def test_cut_by_date_keeps_only_that_date():
    """The 582_LA92 rule: keep only the rows whose TimeStamp is dated 26/11/2018 (day first)."""
    stamps = [
        "25/11/2018  8:59:00.000 PM",
        "25/11/2018  9:00:00.000 PM",
        "26/11/2018  10:11:10.937 AM",
        "25/11/2018  10:11:11.100 AM",  # a stray 25/11 row inside the real run
        "26/11/2018  10:11:11.200 AM",
    ]
    fields = make_fields(time=[0.0, 1.0, 2.0, 3.0, 4.0], voltage=[4.0] * 5, current=[0.0] * 5)
    fields["TimeStamp"] = np.array(stamps)
    run = build(fields, cut=("date", datetime.date(2018, 11, 26)))
    assert list(run.t) == [2.0, 4.0]
    assert run.meta["n_cut_rows"] == 3
    assert "26/11/2018" in run.meta["cut"]


def test_soc_ref_follows_the_counter():
    """SoC_ref = SoC0 - Ah_removed / Q_ref (C4, C13)."""
    run = Run(
        t=np.array([0.0, 1.0]),
        i=np.zeros(2),
        v=np.zeros(2),
        temp=np.zeros(2),
        ah_removed=np.array([0.0, Q_REF_AH / 2.0]),
        dt=np.array([0.0, 1.0]),
        soc0=0.99638,
        meta={},
    )
    assert soc_ref(run) == pytest.approx([0.99638, 0.99638 - 0.5])


def test_find_runs_filters_by_test_type_and_folder_and_sorts(tmp_path):
    """find_runs uses only the file names, so empty files with dataset-style names are enough."""
    names = {
        "25degC": [
            "10-26-18_09.29 549_C20DisCh_25degC_LGHG2.mat",
            "10-25-18_07.39 549_HPPC_25degC_LGHG2.mat",
            "10-29-18_10.08 551_US06_25degC_LGHG2.mat",
            "10-25-18_04.09 549_Charge.mat",
        ],
        "n10degC": [
            "12-01-18_10.00 593_HPPC_n10degC_LGHG2.mat",
            "12-05-18_10.00 596_US06_n10degC_LGHG2.mat",
        ],
    }
    for folder, folder_names in names.items():
        (tmp_path / folder).mkdir()
        for name in folder_names:
            (tmp_path / folder / name).touch()
    (tmp_path / "25degC" / "notes.txt").touch()

    all_paths = find_runs(tmp_path)
    assert len(all_paths) == 6
    assert all_paths == sorted(all_paths)

    hppc = find_runs(tmp_path, test_type="hppc")
    assert [path.parent.name for path in hppc] == ["25degC", "n10degC"]
    assert all(isinstance(path, Path) for path in hppc)

    assert [p.name for p in find_runs(tmp_path, test_type="us06", folder="n10degC")] == [
        "12-05-18_10.00 596_US06_n10degC_LGHG2.mat"
    ]
    assert len(find_runs(tmp_path, folder="25degC")) == 4
    with pytest.raises(FileNotFoundError):
        find_runs(tmp_path / "missing")
    with pytest.raises(FileNotFoundError):
        find_runs(tmp_path, folder="40degC")


# --------------------------------------------------------------------------------------------
# Real data (skipped when data/raw/ is missing)
# --------------------------------------------------------------------------------------------


@pytest.mark.needs_data
def test_find_runs_on_the_dataset_counts_the_files():
    assert len(find_runs(RAW_DIR)) == 206
    assert len(find_runs(RAW_DIR, test_type="hppc")) == 6
    assert len(find_runs(RAW_DIR, test_type="c20")) == 6
    assert len(find_runs(RAW_DIR, test_type="us06")) == 6
    assert len(find_runs(RAW_DIR, test_type="hppc", folder="n20degC")) == 1
    assert set(path.parent.name for path in find_runs(RAW_DIR)) == set(FOLDER_TEMP)


@pytest.mark.needs_data
def test_c20_25degc_counts_from_the_step_start_zero():
    """25degC/549_C20DisCh: Ah[0] = -0.00254 Ah after the reset, so ah_removed[0] is 0.00254 and the discharge ends at Q_ref (C3, C4).

    The file continues with the charge half, so the end of the discharge is where ah_removed peaks (row 1096, 2.79993 V).
    """
    paths = find_runs(RAW_DIR, test_type="c20", folder="25degC")
    assert len(paths) == 1
    run = load_run(paths[0])
    assert run.meta["nominal_temp_degc"] == 25
    assert run.ah_removed[0] == pytest.approx(0.00254, abs=0.00001)

    end_of_discharge = int(np.argmax(run.ah_removed))
    assert run.ah_removed[end_of_discharge] == pytest.approx(2.78074, abs=0.00001)
    assert run.ah_removed[end_of_discharge] == pytest.approx(Q_REF_AH, abs=0.0001)
    assert run.v[end_of_discharge] == pytest.approx(2.79993, abs=0.00001)
    assert soc_ref(run)[end_of_discharge] == pytest.approx(0.0, abs=0.0001)  # the 25 degC OCV axis ends at SoC 0


@pytest.mark.needs_data
def test_571_mixed6_starts_at_row_391_with_soc0_below_one():
    """results/data_checks.md 4a: the run starts at stored row 391 (Time 38.957 s, 4.1657 V, 0 A), SoC0 = 0.99638."""
    paths = [p for p in find_runs(RAW_DIR, test_type="mixed6", folder="10degC") if "571_Mixed6" in p.name]
    assert len(paths) == 1
    run = load_run(paths[0])
    stored = rawio.load_mat(paths[0])

    assert run.soc0 == 0.99638
    assert run.soc0 == pytest.approx(1.0 + stored["Ah"][391] / Q_REF_AH, abs=0.00001)  # 1 - 0.01008 Ah / Q_ref

    assert run.meta["cut"] is not None and "391" in run.meta["cut"]
    assert run.meta["n_rows_raw"] == 73921  # results/data_inventory.md
    assert run.meta["n_dropped_rows"] == 0
    assert run.meta["n_cut_rows"] == 391
    assert run.meta["n_rows_used"] == run.meta["n_rows_raw"] - 391 - run.meta["n_duplicates_removed"]

    assert run.t[0] == pytest.approx(38.957, abs=0.0005)
    assert run.v[0] == pytest.approx(4.1657, abs=0.00005)
    assert run.i[0] == 0.0
    assert run.ah_removed[0] == 0.0
    assert run.t[-1] - run.t[0] == pytest.approx(7352.7, abs=0.05)  # data_checks section 7, rows used
    assert soc_ref(run)[-1] == pytest.approx(0.1510, abs=0.0001)  # data_checks section 7, SoC_ref at end 15.10 %


@pytest.mark.needs_data
def test_582_la92_keeps_only_the_rows_dated_26_11_2018():
    """results/data_checks.md 4b: 89701 rows used, Time 102.937 to 9082.415 s, 5 steps above 1 s, SoC0 = 0.99484."""
    paths = [p for p in find_runs(RAW_DIR, test_type="la92", folder="10degC") if "582_LA92" in p.name]
    assert len(paths) == 1
    run = load_run(paths[0])
    stored = rawio.load_mat(paths[0])

    assert run.soc0 == 0.99484
    assert run.soc0 == pytest.approx(1.0 + stored["Ah"][1031] / Q_REF_AH, abs=0.00001)  # 1 - 0.01436 Ah / Q_ref

    assert run.meta["cut"] is not None and "26/11/2018" in run.meta["cut"]
    assert run.meta["n_rows_raw"] == 90740
    assert run.meta["n_dropped_rows"] == 3  # rows 1491, 1492, 1944; row 1943 is NaN in Wh only
    assert run.meta["n_cut_rows"] == 1035  # the 1038 rows dated 25/11 minus those 3
    assert run.meta["n_duplicates_removed"] == 1
    assert run.meta["n_rows_used"] == 89701

    assert run.t[0] == pytest.approx(102.937, abs=0.0005)
    assert run.t[-1] == pytest.approx(9082.415, abs=0.0005)
    assert np.all(run.dt[1:] > 0.0)  # the four backward Time steps are all cut away

    gap_steps = [dt for _, dt in run.meta["gaps_over_1s"]]
    assert len(gap_steps) == 5
    assert min(gap_steps) == pytest.approx(1.641, abs=0.001)
    assert max(gap_steps) == pytest.approx(2.056, abs=0.001)

    assert run.ah_removed[0] == 0.0
    assert soc_ref(run)[-1] == pytest.approx(0.1315, abs=0.0001)  # data_checks section 7, SoC_ref at end 13.15 %
