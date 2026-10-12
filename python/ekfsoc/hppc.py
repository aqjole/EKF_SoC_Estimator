"""HPPC segmentation: finds the levels, pulses, moves and rests of one HPPC Run.

Structure of the file (docs/decisions.md 1.2, results/data_checks.md section 10). A *level* is
eight 10 s pulses at one SoC, D1 C1 D2 C2 D3 C3 D4 C4, each followed by a rest (40 s after a
discharge pulse D, 610 s after a charge pulse C). Then comes a *move*, a long discharge at about
0.9 A, and a 1 h rest, and the next level starts. The last move runs to the 2.8 V cutoff.

Everything is found from the current alone, in the loader's sign (positive = discharge, C2):
a row with |I| above FLOW_A is active, any other row is rest. An active stretch of at most
PULSE_MAX_S is a pulse; a longer discharge is a move; a longer charge is the in-file recharge that
follows the pulse train, and the search stops there.

All row ranges are Python slices into the Run's arrays. A pulse's `rows` start at its first row
with current, so the row before `rows.start` is the last rest row, the voltage before the step.
"""

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from ekfsoc.loader import soc_ref

FLOW_A = 0.05           # |I| above this is a pulse or a move, at or below it is rest (as in python/data_checks.py)
PULSE_MAX_S = 12.0      # an active stretch this short or shorter is a pulse; a longer one is a move or the recharge
MIN_PULSE_S = 9.0       # a pulse shorter than this was cut off by a voltage limit
LOW_LIMIT_V = 2.8005    # a discharge pulse with a row at or below this sits at the 2.8 V cutoff
HIGH_LIMIT_V = 4.1995   # a charge pulse with a row at or above this sits at the 4.2 V limit
R0_FRACTION = 0.98      # R0 is read once the current has reached this fraction of the pulse current ...
R0_WINDOW_S = 0.3       # ... within this time of the pulse's first row (decisions 1.12)
PULSE_ORDER = "DCDCDCDC"  # the pulses of every level, in the order they run


class Segment(NamedTuple):
    """A stretch of rows with one kind of current: +1 discharge, -1 charge, 0 rest. `stop` is exclusive."""

    kind: int
    first: int
    stop: int
    duration_s: float  # Time of the first row after the stretch minus Time of its first row


@dataclass
class Pulse:
    """One 10 s pulse and the rest that follows it.

    kind         'D' (discharge, i_cmd > 0) or 'C' (charge, i_cmd < 0)
    number       1 to 4: the position among the level's pulses of the same kind
    i_cmd        median current over the pulse in A, loader sign
    rows         slice of the pulse rows
    rest_rows    slice of the rest that follows, up to the next pulse or move
    cut_by_limit True if the pulse is shorter than MIN_PULSE_S or reached the 2.8 V (D) / 4.2 V (C) limit
    r0_row       index into the Run's arrays of the first row with |i| >= 98 % of |i_cmd| within
                 R0_WINDOW_S of rows.start, or None if there is none
    usable       not cut_by_limit and r0_row is not None
    """

    kind: str
    number: int
    i_cmd: float
    rows: slice
    rest_rows: slice
    cut_by_limit: bool
    r0_row: int | None
    usable: bool


@dataclass
class Level:
    """The pulses at one SoC, and the move and rest that lead to the next level.

    k                1-based level number
    soc_pulses       reference SoC at the first pulse row
    pulses           the eight Pulses in running order
    move             slice of the move rows, or None if the file ends after the pulses
    rest_after_move  slice of the 1 h rest after the move; None for the last level, which has no such rest
    soc_after_move   reference SoC at the last row of the move, or None if there is no move
    """

    k: int
    soc_pulses: float
    pulses: list
    move: slice | None
    rest_after_move: slice | None
    soc_after_move: float | None


def split_by_current(run):
    """Cut the run into Segments of equal current kind, from the first row to the last."""
    kinds = np.where(run.i > FLOW_A, 1, np.where(run.i < -FLOW_A, -1, 0))
    firsts = np.concatenate(([0], np.flatnonzero(np.diff(kinds)) + 1))
    stops = np.append(firsts[1:], len(kinds))

    segments = []
    for first, stop in zip(firsts, stops):
        end_time = run.t[min(stop, len(kinds) - 1)]
        segments.append(Segment(int(kinds[first]), int(first), int(stop), float(end_time - run.t[first])))
    return segments


def find_levels(segments):
    """Group the segments into levels: returns [(pulse segment indices, move segment index or None)].

    Pulses collect until a move closes the level. A long charge ends the search. Pulses left at the
    end with no move after them form a last level without a move.
    """
    levels = []
    pulse_indices = []
    for index, segment in enumerate(segments):
        if segment.kind == 0:
            continue
        if segment.duration_s <= PULSE_MAX_S:
            pulse_indices.append(index)
        elif segment.kind > 0:
            levels.append((pulse_indices, index))
            pulse_indices = []
        else:
            break
    if pulse_indices:
        levels.append((pulse_indices, None))
    return levels


def find_r0_row(run, rows, i_cmd):
    """Return the first row of the pulse with |i| >= 98 % of |i_cmd| within 0.3 s of rows.start, or None.

    Counting from the pulse's first row with current (and not from the row before it) is the rule of
    decisions 1.12: the first row of some cold pulses is still ramping.
    """
    threshold = R0_FRACTION * abs(i_cmd)
    for k in range(rows.start, rows.stop):
        if run.t[k] - run.t[rows.start] > R0_WINDOW_S:
            break
        if abs(run.i[k]) >= threshold:
            return k
    return None


def make_pulse(run, segment, rest_segment, kind, number):
    """Build a Pulse from its active segment and the rest segment after it."""
    rows = slice(segment.first, segment.stop)
    i_cmd = float(np.median(run.i[rows]))
    if kind == "D":
        at_limit = run.v[rows].min() <= LOW_LIMIT_V
    else:
        at_limit = run.v[rows].max() >= HIGH_LIMIT_V
    cut_by_limit = bool(segment.duration_s < MIN_PULSE_S or at_limit)
    r0_row = find_r0_row(run, rows, i_cmd)
    return Pulse(
        kind=kind,
        number=number,
        i_cmd=i_cmd,
        rows=rows,
        rest_rows=slice(rest_segment.first, rest_segment.stop),
        cut_by_limit=cut_by_limit,
        r0_row=r0_row,
        usable=bool(not cut_by_limit and r0_row is not None),
    )


def make_level(run, segments, soc, k, pulse_indices, move_index, is_last):
    """Build Level k. Raises ValueError if the pulses are not D1 C1 D2 C2 D3 C3 D4 C4, each followed by a rest."""
    kinds = ["D" if segments[index].kind > 0 else "C" for index in pulse_indices]
    if "".join(kinds) != PULSE_ORDER:
        raise ValueError(f"level {k}: pulses are {''.join(kinds) or 'missing'}, expected {PULSE_ORDER}")

    pulses = []
    counts = {"D": 0, "C": 0}
    for index, kind in zip(pulse_indices, kinds):
        counts[kind] += 1
        rest_segment = segments[index + 1] if index + 1 < len(segments) else None
        if rest_segment is None or rest_segment.kind != 0:
            raise ValueError(f"level {k}: {kind}{counts[kind]} is not followed by a rest")
        pulses.append(make_pulse(run, segments[index], rest_segment, kind, counts[kind]))

    move = None
    rest_after_move = None
    soc_after_move = None
    if move_index is not None:
        move_segment = segments[move_index]
        move = slice(move_segment.first, move_segment.stop)
        soc_after_move = float(soc[move_segment.stop - 1])
        if not is_last:
            rest_segment = segments[move_index + 1]
            if rest_segment.kind != 0:
                raise ValueError(f"level {k}: the move is not followed by a rest")
            rest_after_move = slice(rest_segment.first, rest_segment.stop)

    return Level(
        k=k,
        soc_pulses=float(soc[pulses[0].rows.start]),
        pulses=pulses,
        move=move,
        rest_after_move=rest_after_move,
        soc_after_move=soc_after_move,
    )


def segment_hppc(run):
    """Return the Levels of an HPPC Run, in file order.

    Raises ValueError for a level that is not D1 C1 D2 C2 D3 C3 D4 C4 with a rest after each pulse;
    all six dataset files have that structure (results/data_checks.md section 10).
    """
    segments = split_by_current(run)
    soc = soc_ref(run)
    groups = find_levels(segments)
    levels = []
    for k, (pulse_indices, move_index) in enumerate(groups, start=1):
        is_last = k == len(groups)
        levels.append(make_level(run, segments, soc, k, pulse_indices, move_index, is_last))
    return levels


def rest_points(run, levels):
    """Return the rest voltages of an HPPC Run as [(soc, v)], SoC falling (decisions 1.1).

    The first point is the last row before the first discharge pulse of level 1, at the level-1 pulse
    SoC. Then comes one point per level that has a 1 h rest after its move: the last row of that rest, at
    the SoC where the move ended. The last level has no such rest and gives no point.
    """
    first_pulse_row = levels[0].pulses[0].rows.start
    points = [(levels[0].soc_pulses, float(run.v[first_pulse_row - 1]))]
    for level in levels:
        if level.rest_after_move is not None:
            points.append((level.soc_after_move, float(run.v[level.rest_after_move.stop - 1])))
    return points
