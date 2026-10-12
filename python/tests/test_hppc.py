"""Tests for ekfsoc.hppc.

Synthetic: a made-up HPPC current profile at 0.1 s with two levels and a recharge, built through
loader.build_run, checks the pulse detector. Data (needs data/raw/): the six real HPPC files are
segmented and compared with the table "Voltage limits and the R0 rule" and the level table of
results/data_checks.md section 10.
"""

from pathlib import Path

import numpy as np
import pytest

from ekfsoc.constants import FOLDER_TEMP, Q_REF_AH, RAW_DIR
from ekfsoc.hppc import rest_points, segment_hppc
from ekfsoc.loader import build_run, find_runs, load_run, soc_ref

DATA_CHECKS_MD = Path(__file__).resolve().parents[2] / "results" / "data_checks.md"
DT = 0.1
V_REST = 3.7


def make_run(blocks):
    """Build an HPPC-like Run at 0.1 s steps from blocks (current in A, loader sign, seconds[, volts]).

    The cycler's Current is the negative of the loader's, and its Ah falls on discharge.
    """
    current, voltage = [], []
    for block in blocks:
        amps, seconds = block[0], block[1]
        volts = block[2] if len(block) > 2 else V_REST
        n_rows = round(seconds / DT)
        current += [-amps] * n_rows
        voltage += [volts] * n_rows
    current = np.array(current)
    fields = {
        "Time": np.arange(len(current)) * DT,
        "Voltage": np.array(voltage),
        "Current": current,
        "Ah": np.cumsum(current * DT) / 3600.0,
        "Battery_Temp_degC": np.full(len(current), 25.0),
    }
    return build_run(fields, "synthetic_hppc", "25degC", "hppc")


def level_blocks(d_blocks=None):
    """One level: D1 C1 D2 C2 D3 C3 D4 C4, 10 s pulses, 4 s rest after D and 6 s after C.

    d_blocks maps a D number (1 to 4) to the list of blocks that replaces its plain 10 s pulse.
    """
    d_blocks = d_blocks or {}
    d_amps = {1: 3.0, 2: 6.0, 3: 12.0, 4: 18.0}
    blocks = []
    for number in (1, 2, 3, 4):
        blocks += d_blocks.get(number, [(d_amps[number], 10.0)])
        blocks += [(0.0, 4.0), (-1.5 * number, 10.0), (0.0, 6.0)]
    return blocks


MOVE = [(0.9, 100.0)]
HOUR_REST = [(0.0, 200.0)]
LEVEL_1_START = 50  # first pulse row: after the 5 s opening rest
LEVEL_SECONDS = 4 * (10 + 4 + 10 + 6)


@pytest.fixture(scope="module")
def synthetic():
    """Two levels, then the recharge. Level 2 has four odd pulses: D1 ramps within 0.2 s, D2 ramps
    for 0.4 s, D3 touches 2.8 V on its last row, D4 lasts only 5 s."""
    odd_d_pulses = {
        1: [(1.0, 0.1), (3.0, 9.9)],
        2: [(1.0, 0.4), (6.0, 9.6)],
        3: [(12.0, 9.9), (12.0, 0.1, 2.8)],
        4: [(18.0, 5.0)],
    }
    blocks = [(0.0, 5.0)] + level_blocks() + MOVE + HOUR_REST + level_blocks(odd_d_pulses) + MOVE
    blocks += [(0.0, 50.0), (-3.0, 200.0), (0.0, 50.0)]
    run = make_run(blocks)
    return run, segment_hppc(run)


def test_synthetic_finds_two_levels_and_ignores_the_recharge(synthetic):
    _, levels = synthetic
    assert [level.k for level in levels] == [1, 2]


def test_synthetic_pulses_run_d_c_and_are_numbered_within_their_kind(synthetic):
    _, levels = synthetic
    labels = [f"{pulse.kind}{pulse.number}" for pulse in levels[0].pulses]
    assert labels == ["D1", "C1", "D2", "C2", "D3", "C3", "D4", "C4"]


def test_synthetic_pulse_current_is_signed_like_the_loader(synthetic):
    _, levels = synthetic
    assert [pulse.i_cmd for pulse in levels[0].pulses[:2]] == pytest.approx([3.0, -1.5])


def test_synthetic_pulse_rows_start_at_the_first_row_with_current(synthetic):
    _, levels = synthetic
    assert levels[0].pulses[0].rows == slice(LEVEL_1_START, LEVEL_1_START + 100)


def test_synthetic_rest_rows_follow_the_pulse_up_to_the_next_pulse(synthetic):
    _, levels = synthetic
    assert levels[0].pulses[0].rest_rows == slice(LEVEL_1_START + 100, LEVEL_1_START + 140)


def test_synthetic_move_rows_and_rest_after_the_move(synthetic):
    _, levels = synthetic
    move_start = LEVEL_1_START + 10 * LEVEL_SECONDS
    assert levels[0].move == slice(move_start, move_start + 1000)
    assert levels[0].rest_after_move == slice(move_start + 1000, move_start + 3000)


def test_synthetic_last_level_has_a_move_but_no_rest_after_it(synthetic):
    _, levels = synthetic
    assert levels[1].move is not None
    assert levels[1].rest_after_move is None


def test_synthetic_soc_is_read_at_the_first_pulse_row_and_the_last_move_row(synthetic):
    run, levels = synthetic
    soc = soc_ref(run)
    level = levels[0]
    assert level.soc_pulses == soc[level.pulses[0].rows.start]
    assert level.soc_after_move == soc[level.move.stop - 1]


def test_synthetic_plain_pulse_is_usable_at_its_first_row(synthetic):
    _, levels = synthetic
    pulse = levels[0].pulses[0]
    assert (pulse.cut_by_limit, pulse.r0_row, pulse.usable) == (False, pulse.rows.start, True)


def test_synthetic_ramp_inside_the_window_gives_the_second_row(synthetic):
    _, levels = synthetic
    pulse = levels[1].pulses[0]
    assert pulse.r0_row == pulse.rows.start + 1
    assert pulse.usable


def test_synthetic_ramp_longer_than_the_window_has_no_r0_row(synthetic):
    _, levels = synthetic
    pulse = levels[1].pulses[2]
    assert pulse.r0_row is None
    assert not pulse.cut_by_limit
    assert not pulse.usable


def test_synthetic_full_length_pulse_that_touches_2p8_v_is_cut(synthetic):
    _, levels = synthetic
    pulse = levels[1].pulses[4]
    assert pulse.cut_by_limit
    assert not pulse.usable


def test_synthetic_pulse_shorter_than_9_s_is_cut(synthetic):
    _, levels = synthetic
    pulse = levels[1].pulses[6]
    assert pulse.cut_by_limit
    assert not pulse.usable


def test_synthetic_rest_points_are_the_level_1_rest_and_the_rest_after_each_move_with_a_rest(synthetic):
    """Two levels: the point before D1 of level 1, then the rest after level 1's move. Level 2 has no rest after its move."""
    run, levels = synthetic
    points = rest_points(run, levels)
    assert points == [(levels[0].soc_pulses, V_REST), (levels[0].soc_after_move, V_REST)]
    assert points[0][0] > points[1][0]


def test_a_level_without_its_last_charge_pulse_is_refused():
    blocks = [(0.0, 5.0)] + level_blocks()[:-2] + MOVE + HOUR_REST
    with pytest.raises(ValueError, match="level 1"):
        segment_hppc(make_run(blocks))


# --------------------------------------------------------------------------------------------
# Real files
# --------------------------------------------------------------------------------------------


def table_in_section_10(header_text):
    """Return {folder: {column: cell text}} for the section 10 table whose header line holds header_text."""
    text = DATA_CHECKS_MD.read_text()
    section = text.split("## 10. HPPC structure")[1].split("\n## 11.")[0]
    lines = section.splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith("| folder |") and header_text in line)
    header = [cell.strip() for cell in lines[start].strip().strip("|").split("|")]
    rows = {}
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows[cells[0]] = dict(zip(header, cells))
    return rows


@pytest.fixture(scope="module")
def hppc_levels():
    """{folder: (Run, levels)}, filled on first use so each file is loaded and segmented once."""
    cache = {}

    def get(folder):
        if folder not in cache:
            (path,) = find_runs(RAW_DIR, test_type="hppc", folder=folder)
            run = load_run(path)
            cache[folder] = (run, segment_hppc(run))
        return cache[folder]

    return get


def pulses_of_kind(levels, kind):
    return [pulse for level in levels for pulse in level.pulses if pulse.kind == kind]


def rest_seconds(run, rest_rows):
    """Time from the rest's first row to the first row after it."""
    return run.t[rest_rows.stop] - run.t[rest_rows.start]


@pytest.mark.needs_data
@pytest.mark.parametrize("folder", list(FOLDER_TEMP))
def test_level_count_matches_data_checks(hppc_levels, folder):
    _, levels = hppc_levels(folder)
    expected = int(table_in_section_10("| levels |")[folder]["levels"])
    assert len(levels) == expected


@pytest.mark.needs_data
@pytest.mark.parametrize("folder", list(FOLDER_TEMP))
def test_discharge_pulses_cut_by_the_limit_match_data_checks(hppc_levels, folder):
    _, levels = hppc_levels(folder)
    cell = table_in_section_10("D at 2.8 V")[folder]["D at 2.8 V"]
    expected = int(cell.split()[0])
    assert sum(pulse.cut_by_limit for pulse in pulses_of_kind(levels, "D")) == expected


@pytest.mark.needs_data
@pytest.mark.parametrize("folder", list(FOLDER_TEMP))
def test_charge_pulses_cut_by_the_limit_match_data_checks(hppc_levels, folder):
    _, levels = hppc_levels(folder)
    expected = int(table_in_section_10("D at 2.8 V")[folder]["C pulses at 4.2 V"])
    assert sum(pulse.cut_by_limit for pulse in pulses_of_kind(levels, "C")) == expected


@pytest.mark.needs_data
@pytest.mark.parametrize("folder", list(FOLDER_TEMP))
def test_usable_discharge_pulses_match_data_checks(hppc_levels, folder):
    _, levels = hppc_levels(folder)
    expected = int(table_in_section_10("D at 2.8 V")[folder]["D usable for R0"])
    assert sum(pulse.usable for pulse in pulses_of_kind(levels, "D")) == expected


@pytest.mark.needs_data
def test_25degc_every_level_has_four_discharge_and_four_charge_pulses(hppc_levels):
    _, levels = hppc_levels("25degC")
    kinds = [[pulse.kind for pulse in level.pulses] for level in levels]
    assert all(level_kinds == list("DCDCDCDC") for level_kinds in kinds)


@pytest.mark.needs_data
def test_25degc_discharge_pulse_currents_are_3_6_12_18_a(hppc_levels):
    _, levels = hppc_levels("25degC")
    medians = [np.median([p.i_cmd for p in pulses_of_kind(levels, "D") if p.number == n]) for n in (1, 2, 3, 4)]
    assert medians == pytest.approx([3.0, 6.0, 12.0, 18.0], abs=0.02)


@pytest.mark.needs_data
def test_25degc_rest_after_a_discharge_pulse_is_about_40_s(hppc_levels):
    run, levels = hppc_levels("25degC")
    seconds = [rest_seconds(run, pulse.rest_rows) for pulse in pulses_of_kind(levels, "D")]
    assert seconds == pytest.approx([40.0] * len(seconds), abs=0.1)


@pytest.mark.needs_data
def test_25degc_rest_after_a_move_is_about_3600_s_except_after_the_last(hppc_levels):
    run, levels = hppc_levels("25degC")
    assert levels[-1].rest_after_move is None
    seconds = [rest_seconds(run, level.rest_after_move) for level in levels[:-1]]
    assert seconds == pytest.approx([3600.1] * len(seconds), abs=0.1)


@pytest.mark.needs_data
def test_25degc_levels_sit_at_the_counter_values_where_the_moves_end(hppc_levels):
    """Level 1 starts at counter 0 and level k+1 where move k ended (docs/decisions.md 1.2)."""
    _, levels = hppc_levels("25degC")
    counters_ah = [0.0, 0.15, 0.30, 0.60, 0.90, 1.20, 1.50, 1.80, 2.10, 2.40, 2.55, 2.70]
    expected = [1.0 - counter / Q_REF_AH for counter in counters_ah]
    assert [level.soc_pulses for level in levels] == pytest.approx(expected, abs=2e-4)


@pytest.mark.needs_data
def test_25degc_rest_points_are_the_level_1_point_and_the_eleven_rests_with_soc_falling(hppc_levels):
    run, levels = hppc_levels("25degC")
    points = rest_points(run, levels)
    socs = [soc for soc, _ in points]
    assert len(points) == 12
    assert all(later < earlier for earlier, later in zip(socs, socs[1:]))
    # The first point is the row before D1 of level 1; the others are the last rows of the 1 h rests.
    assert points[0] == (levels[0].soc_pulses, run.v[levels[0].pulses[0].rows.start - 1])
    for point, level in zip(points[1:], levels[:-1]):
        assert point == (level.soc_after_move, run.v[level.rest_after_move.stop - 1])
    assert all(3.0 < voltage < 4.2 for _, voltage in points)
