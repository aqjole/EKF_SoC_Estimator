"""The HPPC files for results/s0/data_checks.md (section 10): current segments, logging pattern, pulses and rests."""

import numpy as np

from dataset.checks_rules import (FIRST_SAMPLE_FRACTION, FULL_PULSE_S, ONE_HOUR_REST_S, RECHARGE_MIN_A, RELAX_WINDOW_S,
                                  counter_resets, rows_used)
from dataset.common import FLOW_CURRENT_A, fmt
from ekfsoc.hppc import HIGH_LIMIT_V, LOW_LIMIT_V, PULSE_MAX_S


def current_segments(time_s, current):
    """Split rows into runs of discharge (-1, I < -50 mA), rest (0) and charge (+1, I > +50 mA).

    Returns a list of dicts with first and last (positions in the arrays given),
    kind, and duration_s = Time of the first row after the run minus Time of
    its first row (the step lasted until the next logged row showed otherwise).
    The last run ends at the last row.
    """
    kind = np.where(current < -FLOW_CURRENT_A, -1, np.where(current > FLOW_CURRENT_A, 1, 0))
    boundaries = np.concatenate(([0], np.where(np.diff(kind) != 0)[0] + 1, [len(kind)]))
    segments = []
    for first, end in zip(boundaries[:-1], boundaries[1:]):
        end_time = time_s[end] if end < len(time_s) else time_s[-1]
        segments.append({"first": int(first), "last": int(end - 1), "kind": int(kind[first]),
                         "duration_s": float(end_time - time_s[first])})
    return segments


def dt_class(step_s):
    """Name the logging interval of one step: 0.1, 1, 10 or 60 s."""
    if step_s < 0.5:
        return "0.1 s"
    if step_s < 5.0:
        return "1 s"
    if step_s < 30.0:
        return "10 s"
    return "60 s"


def logging_pattern(time_s, first, after):
    """Logging intervals over a rest, e.g. '0.1 s to 9.9 s, 1 s to 59.9 s, 10 s to 599.9 s'.

    first: position of the rest's first row; after: position of the first row
    after the rest (the next pulse), so the last step into the next pulse
    counts. Each part gives the interval and the elapsed time (from the
    rest's first row) at which that interval stops being used.
    """
    parts = []
    current_class = None
    for k in range(first + 1, after + 1):
        step_class = dt_class(time_s[k] - time_s[k - 1])
        elapsed = time_s[k] - time_s[first]
        if step_class != current_class:
            parts.append([step_class, elapsed])
            current_class = step_class
        else:
            parts[-1][1] = elapsed
    return ", ".join(f"{name} to {fmt(end, 1)} s" for name, end in parts)


def most_common(texts):
    """'<most common text> (n of N)' plus the number of other variants."""
    counts = {}
    for text in texts:
        counts[text] = counts.get(text, 0) + 1
    best = max(sorted(counts), key=lambda text: counts[text])
    result = f"{best} ({counts[best]} of {len(texts)})"
    if len(counts) > 1:
        result += f"; {len(counts) - 1} other pattern{'s' if len(counts) > 2 else ''}"
    return result


def analyse_hppc(record, data):
    """Describe one HPPC file: levels, pulses, moves, rests, limits, first-sample rule, relaxation, resets.

    The rows used are the loader's (keep-last, no NaN, V > 0). A pulse is a
    current step of at most 12 s; a move is a longer discharge before the
    final recharge; a level is the group of pulses between two moves.
    Inside a level the discharge pulses are numbered D1-D4 and the charge
    pulses C1-C4 in the order they occur.
    """
    rows = rows_used(record, data)
    t = data["Time"][rows]
    v = data["Voltage"][rows]
    i = data["Current"][rows]
    ah = data["Ah"][rows]
    segments = current_segments(t, i)

    long_charges = [s for s in segments if s["kind"] == 1 and s["duration_s"] > PULSE_MAX_S]
    recharge_first = long_charges[0]["first"] if long_charges else len(t)

    levels = []           # list of lists of pulse segments
    moves = []
    current_level = []
    for index, s in enumerate(segments):
        s["index"] = index
        if s["kind"] != 0 and s["duration_s"] <= PULSE_MAX_S and s["first"] < recharge_first:
            current_level.append(s)
        elif s["kind"] != 0:
            if current_level:
                levels.append(current_level)
                current_level = []
            if s["kind"] == -1 and s["first"] < recharge_first:
                moves.append(s)
    if current_level:
        levels.append(current_level)

    def rest_after(s):
        """The rest segment right after s, or None (also when the file ends on its first row)."""
        following = segments[s["index"] + 1] if s["index"] + 1 < len(segments) else None
        if following is None or following["kind"] != 0 or following["duration_s"] <= 0.0:
            return None
        return following

    def next_active(s):
        """The first non-rest segment after s, or None."""
        for later in segments[s["index"] + 1:]:
            if later["kind"] != 0:
                return later
        return None

    pulses = []
    for level_number, level in enumerate(levels, start=1):
        n_d = n_c = 0
        for s in level:
            if s["kind"] == -1:
                n_d += 1
                position = f"D{n_d}"
            else:
                n_c += 1
                position = f"C{n_c}"
            a, b = s["first"], s["last"]
            pulse_v = v[a:b + 1]
            pulse_i = i[a:b + 1]
            command = float(np.median(pulse_i))
            reached = np.where(np.abs(pulse_i) >= FIRST_SAMPLE_FRACTION * abs(command))[0]
            before_time = t[a - 1] if a > 0 else t[a]
            reach_s = float(t[a + reached[0]] - before_time) if len(reached) else float("inf")
            reach_from_first_s = float(t[a + reached[0]] - t[a]) if len(reached) else float("inf")
            reach_row = int(reached[0]) + 1 if len(reached) else None   # 1 = the pulse's first row
            low_limited = s["kind"] == -1 and float(np.min(pulse_v)) <= LOW_LIMIT_V
            high_limited = s["kind"] == 1 and float(np.max(pulse_v)) >= HIGH_LIMIT_V
            pulses.append({
                "level": level_number, "position": position, "kind": s["kind"],
                "duration_s": s["duration_s"], "command_a": command,
                "first_sample_ok": abs(pulse_i[0]) >= FIRST_SAMPLE_FRACTION * abs(command),
                "reach_s": reach_s, "reach_from_first_s": reach_from_first_s, "reach_row": reach_row,
                "low_limited": low_limited, "high_limited": high_limited,
                "full": s["duration_s"] >= FULL_PULSE_S and not low_limited and not high_limited,
                "rest": rest_after(s),
            })

    # Rests and their logging.
    d_rests = [p["rest"] for p in pulses if p["kind"] == -1 and p["rest"] is not None]
    c_rests = [p["rest"] for p in pulses if p["kind"] == 1 and p["rest"] is not None]
    hour_rests = []        # rests after a move that are followed by a pulse level
    final_rests = []       # the rest after the last move (followed by the recharge or the file end)
    for m in moves:
        rest = rest_after(m)
        if rest is None:
            continue
        following = next_active(rest)
        if following is not None and following["duration_s"] <= PULSE_MAX_S:
            hour_rests.append(rest)
        else:
            final_rests.append(rest)

    def pattern_of(rest):
        after = rest["last"] + 1 if rest["last"] + 1 < len(t) else rest["last"]
        return logging_pattern(t, rest["first"], after)

    def relaxation_mv(rest):
        """V at the last row of the rest minus V 600 s earlier (interpolated), in mV."""
        a, b = rest["first"], rest["last"]
        v_earlier = float(np.interp(t[b] - RELAX_WINDOW_S, t[a:b + 1], v[a:b + 1]))
        return 1000.0 * (v[b] - v_earlier)

    # Logging inside the discharge pulses and their 40 s rests.
    pulse_steps = []
    for p_seg, p in zip([s for level in levels for s in level], pulses):
        if p["kind"] == -1 and p["rest"] is not None:
            pulse_steps.append(np.diff(t[p_seg["first"]:p["rest"]["last"] + 2]))
    pulse_steps = np.concatenate(pulse_steps) if pulse_steps else np.array([np.nan])

    # In-file recharge after the pulse train.
    recharge_cc = float("nan")
    recharge_row = None
    if long_charges:
        s = long_charges[0]
        charge_i = i[s["first"]:s["last"] + 1]
        recharge_cc = (float(np.median(charge_i[charge_i > RECHARGE_MIN_A])) if np.any(charge_i > RECHARGE_MIN_A)
                       else float("nan"))
        recharge_row = int(rows[s["first"]])

    stored_t = data["Time"]
    resets = [(k, float(stored_t[k])) for k in counter_resets(stored_t, data["Current"], data["Ah"])]

    return {
        "record": record,
        "levels": len(levels),
        "pulses": pulses,
        "moves": [{"end_ah": float(ah[m["last"]]), "end_v": float(v[m["last"]]),
                   "median_a": float(np.median(i[m["first"]:m["last"] + 1])), "duration_s": m["duration_s"]}
                  for m in moves],
        "d_rest_s": [r["duration_s"] for r in d_rests],
        "c_rest_s": [r["duration_s"] for r in c_rests],
        "hour_rest_s": [r["duration_s"] for r in hour_rests],
        "final_rest_s": [r["duration_s"] for r in final_rests],
        "d_rest_pattern": most_common([pattern_of(r) for r in d_rests]),
        "c_rest_pattern": most_common([pattern_of(r) for r in c_rests]),
        "hour_rest_pattern": most_common([pattern_of(r) for r in hour_rests]),
        "final_rest_pattern": most_common([pattern_of(r) for r in final_rests]) if final_rests else "none",
        "relax_mv": [relaxation_mv(r) for r in hour_rests if r["duration_s"] > ONE_HOUR_REST_S],
        "final_relax_mv": [relaxation_mv(r) for r in final_rests if r["duration_s"] > ONE_HOUR_REST_S],
        "pulse_steps": pulse_steps,
        "recharge_cc_a": recharge_cc,
        "recharge_row": recharge_row,
        "recharge_time_s": float(stored_t[recharge_row]) if recharge_row is not None else float("nan"),
        "resets": resets,
    }


def position_median(hppc, position):
    """Median command current of the full-length pulses at one position (D1..D4, C1..C4), cycler sign."""
    values = [p["command_a"] for p in hppc["pulses"] if p["position"] == position and p["full"]]
    return float(np.median(values)) if values else float("nan")
