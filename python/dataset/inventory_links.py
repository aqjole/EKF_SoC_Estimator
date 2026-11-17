"""How each file starts: from a full charge, after the previous file, or inside an earlier one."""

import numpy as np

from dataset.common import FULL_VOLTAGE_V, fmt
from dataset.inventory_rules import CV_REACHED_V, LINK_GAP_S, OVERLAP_FLAG_S, REST_CURRENT_A, UNLOGGED_DROP_V, nan_max
from dataset.inventory_table import short_file


def full_charge_start(record, folder_records):
    """Say whether a file starts from a full charge, and on what evidence.

    1. The first sample is above 4.15 V with |I| < 50 mA: the cell sits at its
       full-charge rest voltage when the file starts.
    2. Otherwise: the last sample logged before this file starts, in any other
       file of the same folder, is a rest above 4.15 V that ends at most 300 s
       before the start, and that file reached the 4.2 V CV phase (>= 4.19 V)
       before it. This covers files that open with current already flowing
       straight after a full charge (e.g. the C/20 test, Mixed4 and Mixed8).
    Absolute sample times are the first TimeStamp plus Time, which is right
    for every file except the two whose Time stops during a pause (flagged).
    Rows with Voltage <= 0 (end-of-test sentinel) are not used as evidence.
    """
    v0 = record["voltage"][0]
    i0 = record["current"][0]
    if v0 > FULL_VOLTAGE_V and abs(i0) < REST_CURRENT_A:
        return f"yes: first sample {v0:.3f} V at {fmt(i0, 3)} A"

    start_s = record["abs_time_s"][0]
    best = None   # (time, record, index) of the latest earlier sample in the folder
    for other in folder_records:
        if other is record:
            continue
        times = other["abs_time_s"]
        earlier = np.where((times <= start_s) & (other["voltage"] > 0.0))[0]
        if len(earlier) == 0:
            continue
        k = earlier[np.argmax(times[earlier])]
        if best is None or times[k] > best[0]:
            best = (times[k], other, k)

    earlier_text = "no earlier sample in the folder"
    if best is not None:
        when, other, k = best
        gap_s = start_s - when
        v_rest = other["voltage"][k]
        i_rest = other["current"][k]
        reached_cv = nan_max(other["voltage"][:k + 1]) >= CV_REACHED_V
        if gap_s <= LINK_GAP_S and abs(i_rest) < REST_CURRENT_A and v_rest > FULL_VOLTAGE_V and reached_cv:
            return f"yes: rest at {v_rest:.3f} V ends {gap_s:.0f} s before start ({short_file(other['file'])})"
        earlier_text = (f"last earlier sample: {v_rest:.3f} V at {fmt(i_rest, 3)} A, {gap_s:.0f} s before "
                        f"({short_file(other['file'])})")

    if abs(i0) < REST_CURRENT_A and v0 <= FULL_VOLTAGE_V:
        return f"no: opens at rest at {v0:.3f} V"
    state = "under load" if i0 < 0 else "charging"
    return f"unclear: opens {state} at {v0:.3f} V, {fmt(i0, 3)} A; {earlier_text}"


def check_previous_file(record, previous):
    """Compare a file with the file logged just before it in the same folder.

    Only neighbouring files are compared here.
    - Overlap: the file starts before the previous file ends (by TimeStamp)
      and ends after it, so the two files claim the same wall-clock minutes.
      A file that lies wholly inside an earlier file's span is not an overlap;
      check_inside_earlier() looks for those against every earlier file.
    - Unlogged discharge: the file opens at rest more than UNLOGGED_DROP_V
      below the last voltage of the previous file, so the cell lost charge
      in between without a log.
    Adds flags to record and fills record["overlap"] and ["unlogged_discharge"].
    """
    overlap_s = (previous["end"] - record["start"]).total_seconds()
    if overlap_s > OVERLAP_FLAG_S and record["end"] > previous["end"]:
        record["overlap"] = (previous["file"], overlap_s / 60.0)
        record["flags"].append(f"starts {overlap_s / 60:.1f} min before the previous file "
                               f"({short_file(previous['file'])}) ends, by TimeStamp: the two clocks disagree "
                               "(e.g. a daylight-saving change), so wall-clock gaps across the pair are wrong")

    previous_voltage = previous["voltage"][previous["voltage"] > 0.0]   # drops NaN and the 0 V sentinel
    if len(previous_voltage) == 0:
        return
    v_end = float(previous_voltage[-1])
    v0 = float(record["voltage"][0])
    gap_min = (record["start"] - previous["end"]).total_seconds() / 60.0
    if abs(record["current"][0]) < REST_CURRENT_A and v_end - v0 > UNLOGGED_DROP_V:
        text = (f"opens at rest at {v0:.3f} V, {gap_min:.0f} min after {short_file(previous['file'])} "
                f"ended at {v_end:.3f} V")
        record["unlogged_discharge"] = text
        record["flags"].append(text + ": unlogged discharge in between")


def check_inside_earlier(record, folder_records):
    """Note a file whose [first, last TimeStamp] span lies wholly inside the span of an earlier file.

    Every earlier file of the folder is checked, not only the neighbour,
    because a long Charge file (549_Charge holds four charges) can span
    several tests logged in between. Such a file is not an overlap and is not
    flagged; the legend lists it with the number of samples the earlier file
    logs inside its span (0 means the two files never log at the same time).
    Fills record["inside_earlier"] with the first such earlier file.
    """
    for other in folder_records:
        if other is record or other["start"] >= record["start"]:
            continue
        reaches_into = (other["end"] - record["start"]).total_seconds() > OVERLAP_FLAG_S
        if reaches_into and record["end"] <= other["end"]:
            times = other["abs_time_s"]
            n_inside = int(np.sum((times > record["abs_time_s"][0]) & (times < record["abs_time_s"][-1])))
            record["inside_earlier"] = (other["file"], n_inside)
            return
