"""The notes under the capacity tables of results/s0/capacity.md: extrapolation, the 1C runs, the current scaling and
the C/20 ratio."""

import numpy as np

from dataset.common import FOLDER_TEMPS_DEGC, fmt
from dataset.inventory_rules import NOMINAL_1C_A, RATE_FLAG, TEMP_FLAG_DEGC, fmt_pair
from dataset.inventory_table import short_file


def extrapolation_check(capacity_records):
    """Sentence that checks the one-interval extrapolation of the discharge start against the data.

    If the first logged sample really is one interval into the step, the
    extrapolated start is 0 where the cycler reset the counter (C/20, 2C) and
    equals the last Ah of the preceding C/20 file where it did not (0.5C).
    """
    reset_starts = [abs(r["capacity"]["ah_start"]) for r in capacity_records
                    if r["test_type"] in ("c20", "dis_2c") and r["capacity"]["start_note"].startswith("file opens")]
    carried = []
    for r in capacity_records:
        if r["test_type"] != "dis_0p5c" or not r["capacity"]["start_note"].startswith("file opens"):
            continue
        c20 = [x for x in capacity_records if x["folder"] == r["folder"] and x["test_type"] == "c20"]
        if c20:
            carried.append(r["capacity"]["ah_start"] - c20[0]["ah_end"])
    parts = []
    if reset_starts:
        parts.append(f"check: for the {len(reset_starts)} C/20 and 2C files this gives |Ah at start| <= "
                     f"{max(reset_starts):.5f} Ah (counter reset at the step start)")
    if carried:
        parts.append(f"for the {len(carried)} 0.5C files it gives the last Ah value of that folder's C20DisCh "
                     f"file to within {max(abs(x) for x in carried):.5f} Ah (counter not reset)")
    return "; ".join(parts) + "." if parts else "no file needed this."


def at_folder_temperature(r):
    """True if a capacity test's discharge started within TEMP_FLAG_DEGC of its folder temperature."""
    folder_temp = FOLDER_TEMPS_DEGC.get(r["folder"])
    if folder_temp is None:
        return True
    return abs(r["capacity"]["temp_start"] - folder_temp) <= TEMP_FLAG_DEGC


def one_c_runs(records):
    """Return (first run, second run) of a folder's 1C tests; None where the data has no file.

    records: the folder's records in time order. The readme puts the first 1C
    test before UDDS and the second before Mix 3. With two 1C files they are
    taken in the order they ran. With one, it is the first run if it started
    before the folder's UDDS file, otherwise the second.
    """
    one_c = [r for r in records if r["test_type"] == "cap_1c" and r["capacity"] is not None]
    if len(one_c) >= 2:
        return one_c[0], one_c[1]
    if len(one_c) == 0:
        return None, None
    udds = [r for r in records if r["test_type"] == "udds"]
    if udds and one_c[0]["start"] > udds[0]["start"]:
        return None, one_c[0]
    return one_c[0], None


def one_c_note(r):
    """Short note for a 1C test that ran off its folder temperature or whose name gives another one ('' if neither)."""
    folder_temp = FOLDER_TEMPS_DEGC.get(r["folder"])
    if folder_temp is None:
        return ""
    if not at_folder_temperature(r):
        return f"**off-temperature**, not a {folder_temp:.0f} degC capacity"
    if r["descriptor_temp"] is not None and r["descriptor_temp"] != folder_temp:
        return f"named {r['descriptor_temp']:.0f} degC, valid as {folder_temp:.0f} degC"
    return ""


def one_c_notes(folders, records_by_folder):
    """Bullets under the per-folder table: which 1C run is missing, and which 1C test to read with care."""
    notes = []
    for folder in folders:
        records = records_by_folder[folder]
        first, second = one_c_runs(records)
        udds = [r for r in records if r["test_type"] == "udds"]
        udds_text = f"`{short_file(udds[0]['file'])}`" if udds else "no UDDS file in the data"
        if first is None and second is None:
            notes.append(f"{folder}: no 1C file.")
        elif first is None:
            text = (f"{folder}: the only 1C file, `{short_file(second['file'])}`, started after the folder's UDDS "
                    f"({udds_text}), so it is the second run; the first run is missing.")
            before_udds = [r for r in records if r["unlogged_discharge"] and udds and r["start"] <= udds[0]["start"]]
            if before_udds:
                text += (" Before UDDS, where the readme puts the first 1C test, the data shows an unlogged discharge: "
                         + "; ".join(f"`{short_file(r['file'])}` {r['unlogged_discharge']}" for r in before_udds) + ".")
            notes.append(text)
        elif second is None:
            notes.append(f"{folder}: the only 1C file, `{short_file(first['file'])}`, started before the folder's UDDS "
                         f"({udds_text}), so it is the first run; the second run is missing.")

        for r in (first, second):
            if r is None or not one_c_note(r):
                continue
            c = r["capacity"]
            folder_temp = FOLDER_TEMPS_DEGC[folder]
            text = (f"`{folder}/{short_file(r['file'])}`: cell at {c['temp_start']:.1f} degC when the discharge "
                    f"starts, {fmt_pair(c['temp_min'], c['temp_max'], 1)} degC min / max over it; "
                    f"folder {folder_temp:.0f} degC.")
            if not at_folder_temperature(r):
                text += f" Not a {folder_temp:.0f} degC capacity."
            else:
                text += (f" The name says {r['descriptor_temp']:.0f} degC, but this is the {folder_temp:.0f} degC "
                         "1C test.")
            notes.append(text)
    return notes


def current_scaling_notes(folders, records_by_folder):
    """Anomaly bullets for folders whose C/20, 0.5C or 2C current differs from the other folders by > RATE_FLAG."""
    test_names = {"c20": "C/20", "dis_0p5c": "0.5C", "dis_2c": "2C"}
    median_current = {}   # (folder, test type) -> median discharge current (A, positive)
    hppc_levels = {}      # folder -> HPPC discharge pulse levels (A, cycler sign)
    for folder in folders:
        for r in records_by_folder[folder]:
            if r["test_type"] in test_names and r["capacity"] is not None:
                median_current[(folder, r["test_type"])] = r["capacity"]["median_current_a"]
            if r["test_type"] == "hppc" and r["pulse_levels"]:
                hppc_levels[folder] = r["pulse_levels"]

    notes = []
    for folder in folders:
        parts = []
        ratios = []
        flagged = False
        for test_type, name in test_names.items():
            others = [median_current[(f, test_type)] for f in folders
                      if f != folder and (f, test_type) in median_current]
            if (folder, test_type) not in median_current or not others:
                continue
            value = median_current[(folder, test_type)]
            reference = float(np.median(others))
            ratio = value / reference
            ratios.append(ratio)
            if abs(ratio - 1.0) > RATE_FLAG:
                flagged = True
            parts.append(f"{name} {value:.3f} A (other folders {reference:.3f} A, ratio {ratio:.3f})")
        if not flagged:
            continue

        records = records_by_folder[folder]
        numbers = sorted(set(str(r["test_number"]) for r in records
                             if r["test_type"] in ("c20", "dis_0p5c", "dis_2c", "hppc")))
        test_word = "test" if len(numbers) == 1 else "tests"
        text = (f"- **{folder} {test_word} {', '.join(numbers)}: currents differ from the other folders.** "
                f"Median discharge current: {', '.join(parts)}.")
        if folder in hppc_levels and "25degC" in hppc_levels and folder != "25degC":
            levels = hppc_levels[folder]
            reference_levels = hppc_levels["25degC"]
            text += (f" HPPC discharge pulses: {' / '.join(fmt(x, 1) for x in levels)} A, against "
                     f"{' / '.join(fmt(x, 1) for x in reference_levels)} A at 25degC")
            if len(levels) == len(reference_levels):
                level_ratios = [a / b for a, b in zip(levels, reference_levels)]
                ratios += level_ratios
                if fmt(min(level_ratios), 3) == fmt(max(level_ratios), 3):
                    text += f" (ratio {fmt(min(level_ratios), 3)} for every level)"
                else:
                    text += f" (ratio {fmt(min(level_ratios), 3)} to {fmt(max(level_ratios), 3)})"
            text += "."
        text += f" Median of these ratios: {float(np.median(ratios)):.3f}."
        if (folder, "dis_0p5c") in median_current and (folder, "dis_2c") in median_current:
            text += (f" Against the {NOMINAL_1C_A:.1f} A 1C basis, the {folder} 0.5C and 2C capacities were therefore "
                     f"measured at {median_current[(folder, 'dis_0p5c')] / NOMINAL_1C_A:.2f}C and "
                     f"{median_current[(folder, 'dis_2c')] / NOMINAL_1C_A:.2f}C.")
        one_c = [r for r in records if r["test_type"] == "cap_1c" and r["capacity"] is not None]
        if one_c:
            text += (" The folder's 1C tests ran at the usual current (mean I: " +
                     ", ".join(f"{r['capacity']['mean_current_a']:.3f} A in {r['test_number']}" for r in one_c) + ").")
        notes.append(text)
    return notes


def c20_ratio_note(folders, records_by_folder):
    """Anomaly bullet: Ah put back by the C/20 charge divided by Ah removed by the C/20 discharge, per folder.

    The ratio is charge Ah over discharge Ah. A coulombic efficiency under 1
    means more charge must go in than came out, so it would put the ratio
    just above 1. The sentence compares the measured ratios with that.
    """
    parts = []
    ratios = []   # (folder, ratio) in campaign order
    for folder in folders:
        c20 = [r for r in records_by_folder[folder] if r["test_type"] == "c20" and r["capacity"] is not None]
        if c20:
            c = c20[0]["capacity"]
            ratio = c["charge_after_ah"] / c["ah_removed"]
            ratios.append((folder, ratio))
            parts.append(f"{fmt(ratio, 3)} ({folder})")
    above = [ratio for _, ratio in ratios if ratio > 1.0]
    below = [(folder, ratio) for folder, ratio in ratios if ratio < 1.0]
    comparison = []
    if above:
        comparison.append(f"the measured ratios above 1 ({fmt(min(above), 3)} to {fmt(max(above), 3)}) are far "
                          "larger than that")
    if below:
        comparison.append(", ".join(folder for folder, _ in below) + " is below 1 (" +
                          ", ".join(fmt(ratio, 3) for _, ratio in below) + ")")
    comparison_text = ""
    if comparison:
        sentence = ", and ".join(comparison)
        comparison_text = sentence[0].upper() + sentence[1:] + ". "
    return ("- **C/20 charge / discharge Ah ratio**, in campaign order: " + ", ".join(parts) + ". With no charge "
            "lost or created the ratio would be 1, or just above 1 for a coulombic efficiency under 1 (more charge "
            "goes in than comes out). " + comparison_text + "The data explains none of them, so all are recorded "
            "as unexplained, and the two halves of a C20DisCh file should not be assumed to share one Ah axis.")
