"""results/s0/capacity.md: every capacity test in campaign order, the capacities per folder and the drive-cycle stop
rule."""

from dataset.capacity_notes import (at_folder_temperature, c20_ratio_note, current_scaling_notes, extrapolation_check,
                                    one_c_note, one_c_notes, one_c_runs)
from dataset.common import DRIVE_TYPES, FLOW_CURRENT_A, fmt
from dataset.inventory_rules import STOP_RULE_FRACTION, STOP_RULE_TOLERANCE, TEMP_FLAG_DEGC, fmt_pair
from dataset.inventory_table import short_file


def drive_groups(folders, records_by_folder):
    """Drive cycles grouped by folder and cycler test number, with the 1C tests to compare them with.

    Returns a list of dicts in campaign order with keys:
        folder, number
        cycles: drive-cycle records of the group that have current
        dead: test types of the group whose file has no current
        removed: Ah removed by each cycle (first Ah minus last Ah, positive)
        same_test: the 1C record with the same test number, or None
        reference: the first 1C record of the folder that ran at the folder temperature, or None
    """
    groups = []
    for folder in folders:
        records = records_by_folder[folder]
        at_temperature = [r for r in records if r["test_type"] == "cap_1c" and r["capacity"] is not None
                          and at_folder_temperature(r)]
        numbers = []
        for r in records:
            if r["test_type"] in DRIVE_TYPES and r["test_number"] not in numbers:
                numbers.append(r["test_number"])
        for number in numbers:
            cycles = [r for r in records if r["test_type"] in DRIVE_TYPES and r["test_number"] == number
                      and not r["no_current"]]
            dead = [r["test_type"] for r in records if r["test_type"] in DRIVE_TYPES
                    and r["test_number"] == number and r["no_current"]]
            if not cycles:
                continue
            same_test = [r for r in records if r["test_type"] == "cap_1c" and r["test_number"] == number
                         and r["capacity"] is not None]
            groups.append({
                "folder": folder,
                "number": number,
                "cycles": cycles,
                "dead": dead,
                "removed": [r["ah_first"] - r["ah_end"] for r in cycles],
                "same_test": same_test[0] if same_test else None,
                "reference": at_temperature[0] if at_temperature else None,
            })
    return groups


def percent_range(low, high):
    """'97.4 %' or '93.2 to 94.1 %' for two fractions."""
    if f"{low * 100:.1f}" == f"{high * 100:.1f}":
        return f"{low * 100:.1f} %"
    return f"{low * 100:.1f} to {high * 100:.1f} %"


def stop_rule_verdict(groups):
    """Anomaly bullet: does every drive cycle stop at 95 % of a 1C capacity?

    A group is compared with its same-number 1C test when the data has one,
    otherwise with the first 1C test that ran at the folder temperature. It
    fits when every cycle is within STOP_RULE_TOLERANCE of 95 %. A group that
    removed less than half of what the folder's largest group removed is a
    partial run.
    """
    matched_ratios = []
    off_temperature_matches = []
    fits_without_match = []
    misses = []
    unchecked = []
    partial = []
    for g in groups:
        folder_most = max(max(other["removed"]) for other in groups if other["folder"] == g["folder"])
        if max(g["removed"]) < 0.5 * folder_most:
            partial.append(f"{g['number']} ({g['folder']}: {', '.join(r['test_type'] for r in g['cycles'])}) "
                           f"removed only {max(g['removed']):.2f} Ah per cycle")
            continue
        one_c = g["same_test"] if g["same_test"] is not None else g["reference"]
        if one_c is None:
            unchecked.append(f"{g['number']} ({g['folder']})")
            continue
        capacity = one_c["capacity"]["ah_removed"]
        ratios = [x / capacity for x in g["removed"]]
        fits = all(abs(x - STOP_RULE_FRACTION) <= STOP_RULE_TOLERANCE for x in ratios)
        if g["same_test"] is not None:
            matched_ratios += ratios
            if not at_folder_temperature(g["same_test"]):
                off_temperature_matches.append(str(g["number"]))
        if fits and g["same_test"] is None:
            fits_without_match.append(f"{g['number']} ({g['folder']})")
        if not fits:
            misses.append(f"{g['number']} ({g['folder']}) removed {percent_range(min(ratios), max(ratios))} of "
                          f"{one_c['test_number']}'s 1C capacity")

    if not misses and not unchecked and not partial:
        verdict = "yes"
    elif matched_ratios or fits_without_match:
        verdict = "partly"
    else:
        verdict = "no"
    text = f"- **Drive-cycle stop rule ({STOP_RULE_FRACTION * 100:.0f} % of the 1C capacity): {verdict}.**"
    if matched_ratios:
        text += (f" In all {len(matched_ratios)} drive cycles that share a cycler test number with a 1C test, Ah "
                 f"removed / that 1C capacity is {min(matched_ratios):.4f} to {max(matched_ratios):.4f}")
        if off_temperature_matches:
            text += f", even where that 1C test ran off-temperature (tests {', '.join(off_temperature_matches)})"
        text += "."
    text += (" Groups without a same-number 1C test are compared with the first 1C test that ran at the folder "
             "temperature.")
    if fits_without_match:
        text += f" Fit: {', '.join(fits_without_match)}."
    if misses:
        text += f" Do not fit: {'; '.join(misses)}."
    if unchecked:
        text += f" Cannot be checked (no 1C test at the folder temperature): {', '.join(unchecked)}."
    if partial:
        text += f" Partial runs: {'; '.join(partial)}."
    return text


def write_capacity(folders, records_by_folder, out_path):
    """Write results/s0/capacity.md."""
    all_records = [r for folder in folders for r in records_by_folder[folder]]
    capacity_records = sorted((r for r in all_records if r["capacity"] is not None), key=lambda r: r["start"])

    lines = []
    lines.append("# Capacity tests (S0)")
    lines.append("")
    lines.append("Generated by `python/dataset/inventory.py` (`make inventory`) from `data/raw/` (LG 18650HG2, "
                 "DOI 10.17632/b5mj79w5w9.2, CC BY 4.0). Do not edit by hand. Every number is measured from the files.")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(f"- The discharge of a test is the longest run of samples with current below -{FLOW_CURRENT_A * 1000:.0f} mA "
                 "(cycler sign). For C20DisCh this is the C/20 discharge part; its charge part is reported separately.")
    lines.append("- *Ah removed* = Ah counter at the start of the discharge minus Ah counter at its last sample. The "
                 "cycler counts discharge as negative Ah, so this is positive.")
    lines.append("- *Ah at start*: the counter at the rest sample just before the discharge. Files that open "
                 "mid-discharge (last column) are extrapolated back one logging interval at the first sample's "
                 "current; " + extrapolation_check(capacity_records))
    lines.append("- *final V*: voltage at the last discharge sample. *mean I*: mean of the logged current over the "
                 "discharge, sign flipped so discharge is positive (the *Anomalies* section uses the median instead). "
                 "*cell T*: Battery_Temp_degC min / max over the discharge.")
    lines.append("- Rows are in campaign order (first TimeStamp of each file), so ageing across the campaign shows "
                 f"down the table. Folder order by first TimeStamp: {', '.join(folders)}. The readme gives the order "
                 "40, 25, 10, 0, -10, -20 degC.")
    lines.append("")

    lines.append("## All capacity tests in campaign order")
    lines.append("")
    lines.append("| # | folder | start (TimeStamp) | file | test | Ah removed (Ah) | Ah at start (Ah) | final V (V) "
                 "| mean I (A) | cell T min / max (degC) | how the start was found |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, r in enumerate(capacity_records, start=1):
        c = r["capacity"]
        lines.append(f"| {k} | {r['folder']} | {r['start']:%Y-%m-%d %H:%M} | `{r['file']}` | {r['test_type']} "
                     f"| {fmt(c['ah_removed'], 4)} | {fmt(c['ah_start'], 4)} | {fmt(c['final_voltage'], 3)} "
                     f"| {fmt(c['mean_current_a'], 3)} | {fmt_pair(c['temp_min'], c['temp_max'], 1)} "
                     f"| {c['start_note']} |")
    lines.append("")

    # The 25 degC C/20 discharge capacity, named explicitly (Q_ref candidate, decided in docs/decisions.md).
    c20_25 = [r for r in capacity_records if r["folder"] == "25degC" and r["test_type"] == "c20"]
    lines.append("## 25 degC C/20 discharge capacity")
    lines.append("")
    if len(c20_25) == 1:
        r = c20_25[0]
        c = r["capacity"]
        lines.append(f"The C/20 discharge capacity at 25 degC is **{c['ah_removed']:.4f} Ah**, measured on the discharge "
                     f"part of `data/raw/25degC/{r['file']}` (started {r['start']:%Y-%m-%d %H:%M}, mean current "
                     f"{c['mean_current_a']:.4f} A, ended at {c['final_voltage']:.3f} V, cell at "
                     f"{c['temp_min']:.1f} to {c['temp_max']:.1f} degC). The spec makes this number `Q_ref`; the "
                     "decision itself belongs in `docs/decisions.md`.")
    else:
        lines.append(f"Expected exactly one C/20 test in 25degC, found {len(c20_25)}.")
    lines.append("")

    lines.append("## C/20 and 1C capacities per folder")
    lines.append("")
    lines.append("The two 1C columns are the folder's first and second 1C run in the order they ran (the readme puts "
                 "the first before UDDS and the second before Mix 3). A folder with only one 1C file has it in the "
                 "first-run column if it started before the folder's UDDS file, otherwise in the second-run column. "
                 "*cell T* is the temperature the cell was actually at (min / max over the discharge). *C/20 charge* "
                 "is the Ah put back by the charge part of the same C20DisCh file (highest counter after the "
                 "discharge minus the counter at the end of the discharge); it is shown for comparison only.")
    lines.append("")
    lines.append("| folder | C/20 discharge (Ah) | C/20 charge, same file (Ah) | charge / discharge "
                 "| 1C first run (Ah) | first run: file, cell T (degC) | 1C second run (Ah) "
                 "| second run: file, cell T (degC) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for folder in folders:
        records = [r for r in capacity_records if r["folder"] == folder]
        c20 = [r for r in records if r["test_type"] == "c20"]
        if c20:
            c = c20[0]["capacity"]
            c20_text = fmt(c["ah_removed"], 4)
            charge_text = fmt(c["charge_after_ah"], 4)
            ratio_text = fmt(c["charge_after_ah"] / c["ah_removed"], 3)
        else:
            c20_text, charge_text, ratio_text = "missing", "n/a", "n/a"
        cells = []
        for r in one_c_runs(records_by_folder[folder]):
            if r is None:
                cells.append("missing")
                cells.append("no file")
                continue
            c = r["capacity"]
            file_text = f"`{short_file(r['file'])}`, {fmt_pair(c['temp_min'], c['temp_max'], 1)}"
            if one_c_note(r):
                file_text += f"; {one_c_note(r)}"
            cells.append(fmt(c["ah_removed"], 4))
            cells.append(file_text)
        lines.append(f"| {folder} | {c20_text} | {charge_text} | {ratio_text} | {' | '.join(cells)} |")
    lines.append("")
    for note in one_c_notes(folders, records_by_folder):
        lines.append(f"- {note}")
    other_off = [r for r in capacity_records if r["test_type"] != "cap_1c" and not at_folder_temperature(r)]
    if other_off:
        lines.append(f"- Other capacity tests whose cell is more than {TEMP_FLAG_DEGC:.0f} degC from the folder "
                     "temperature when the discharge starts: " +
                     "; ".join(f"`{r['folder']}/{short_file(r['file'])}` ({r['capacity']['temp_start']:.1f} degC)"
                               for r in other_off) + ".")
    else:
        lines.append(f"- The C/20, 0.5C and 2C tests all start their discharge within {TEMP_FLAG_DEGC:.0f} degC of "
                     "the folder temperature.")
    lines.append("")

    # Drive-cycle stop rule: readme says drive cycles stop at 95 % of the 1C capacity at that temperature.
    groups = drive_groups(folders, records_by_folder)
    lines.append("## Drive-cycle stop rule")
    lines.append("")
    lines.append(f"The readme says drive cycles repeat until {STOP_RULE_FRACTION * 100:.0f} % of the 1C capacity at "
                 "that temperature is discharged. Drive cycles are grouped by folder and cycler test number; *Ah "
                 "removed* is the first Ah value minus the last one (cycler sign, so positive). Each group is "
                 "compared with the 1C test that has the same test number, if the data has one, and with the first "
                 "1C test of the folder that ran at the folder temperature (cell within "
                 f"{TEMP_FLAG_DEGC:.0f} degC when the discharge starts). *implied 1C* = Ah removed / "
                 f"{STOP_RULE_FRACTION}. PausCycl files are left out (they stop much earlier). The verdict is under "
                 "*Anomalies*.")
    lines.append("")
    lines.append("| folder | test number | drive cycles | Ah removed min / max (Ah) | 1C test with this number (Ah) "
                 "| Ah removed / same-number 1C, min / max | first 1C at the folder temperature (Ah) "
                 "| Ah removed / first at-temperature 1C, min / max | implied 1C min / max (Ah) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for g in groups:
        removed = g["removed"]
        compare_cells = []
        for one_c in (g["same_test"], g["reference"]):
            if one_c is None:
                compare_cells += ["none in the data", "n/a"]
                continue
            capacity = one_c["capacity"]["ah_removed"]
            compare_cells.append(f"{capacity:.4f} (`{short_file(one_c['file'])}`)")
            compare_cells.append(fmt_pair(min(removed) / capacity, max(removed) / capacity, 4))
        implied_text = fmt_pair(min(removed) / STOP_RULE_FRACTION, max(removed) / STOP_RULE_FRACTION, 4)
        types = ", ".join(r["test_type"] for r in g["cycles"])
        if g["dead"]:
            types += " (left out, no current: " + ", ".join(g["dead"]) + ")"
        lines.append(f"| {g['folder']} | {g['number']} | {types} | {fmt_pair(min(removed), max(removed), 4)} "
                     f"| {' | '.join(compare_cells)} | {implied_text} |")
    lines.append("")

    lines.append("## Anomalies")
    lines.append("")
    for note in current_scaling_notes(folders, records_by_folder):
        lines.append(note)
    lines.append(c20_ratio_note(folders, records_by_folder))
    lines.append(stop_rule_verdict(groups))
    lines.append("")

    out_path.write_text("\n".join(lines))
