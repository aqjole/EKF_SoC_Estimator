"""Sections 5 to 9 of results/s0/data_checks.md: bad rows, temperatures, run lengths, the full charge and the
charges."""

import numpy as np

from dataset.checks_drive import drive_records
from dataset.checks_rules import (CC_CURRENT_A, CV_PHASE_V, EXP3_START_SOC, FULL_CURRENT_A, LINK_GAP_S, OFFSETS_A,
                                  OFFSET_GUARD_PP, OFFSET_STEP_A, REST_START_CURRENT_A, WINDOW_SOC, fmt_range, label,
                                  round_up, run_key, run_role, stored_rows_text)
from dataset.common import FLOW_CURRENT_A, FOLDER_TEMPS_DEGC, FULL_VOLTAGE_V, fmt


def section_bad_rows(records):
    """Section 5: rows with Voltage <= 0 and rows with NaN."""
    lines = ["## 5. Rows with Voltage <= 0 and rows with NaN", ""]
    lines.append("Source: all files, every row as stored. Row numbers count from 0.")
    lines.append("")
    lines.append("| file | rows | Voltage <= 0 | rows in the file |")
    lines.append("|---|---|---|---|")
    for r in records:
        if r["zero_voltage_rows"]:
            rows = [k for k, _ in r["zero_voltage_rows"]]
            values = sorted(set(fmt(value, 3) for _, value in r["zero_voltage_rows"]))
            lines.append(f"| {label(r)} | {stored_rows_text(rows)} | {', '.join(values)} V | {r['n_rows']} |")
    lines.append("")
    lines.append("| file | row | fields that are NaN |")
    lines.append("|---|---|---|")
    for r in records:
        for k, fields in r["nan_rows"]:
            lines.append(f"| {label(r)} | {k} | {', '.join(fields)} |")
    lines.append("")
    n_zero = sum(1 for r in records if r["zero_voltage_rows"])
    n_nan = sum(1 for r in records if r["nan_rows"])
    lines.append(f"- Files with rows at Voltage <= 0: {n_zero}. Files with NaN rows: {n_nan}. No other file has either.")
    lines.append("")
    return lines


def temperature_text(values):
    """'median (5th to 95th percentile)' of temperatures in degC."""
    return (f"{fmt(np.median(values), 2)} ({fmt(np.percentile(values, 5), 2)} to "
            f"{fmt(np.percentile(values, 95), 2)})")


def section_temperatures(folders, records):
    """Section 6: pooled cell temperature during drive cycles per folder."""
    lines = ["## 6. Cell temperature during drive cycles", ""]
    lines.append("Source: the drive files of each folder, field Battery_Temp_degC, pooled over samples. "
                 "Values are median (5th to 95th percentile) in degC. *All drive files*: every row with a finite "
                 "temperature. *Without 562_Mixed4-8*: the same, leaving out the five partial 40 degC runs. "
                 "*Evaluation set*: the 62 evaluation runs, rows used (legend).")
    lines.append("")
    lines.append("| folder | grid node (degC) | all drive files | without 562_Mixed4-8 | evaluation set, rows used |")
    lines.append("|---|---|---|---|---|")
    for folder in folders:
        files = drive_records(records, folder)
        all_temps = np.concatenate([r["temp_all"] for r in files])
        without = np.concatenate([r["temp_all"] for r in files if not run_key(r).startswith("562_Mixed")])
        evaluated = np.concatenate([r["temp_used"] for r in files if run_role(r) == "evaluation"])
        lines.append(f"| {folder} | {fmt(FOLDER_TEMPS_DEGC[folder], 0)} | {temperature_text(all_temps)} "
                     f"| {temperature_text(without)} | {temperature_text(evaluated)} |")
    lines.append("")
    partial = [r for r in drive_records(records) if run_key(r).startswith("562_Mixed")]
    partial_temps = np.concatenate([r["temp_all"] for r in partial])
    lines.append(f"- The five 562 partial runs alone ({', '.join(label(r) for r in partial)}): "
                 f"{temperature_text(partial_temps)} degC, min / max {fmt(np.min(partial_temps), 2)} / "
                 f"{fmt(np.max(partial_temps), 2)} degC.")
    lines.append("")
    return lines


def guard_threshold_a(duration_s, q_ref):
    """Smallest offset (A) whose coulomb-counting drift over duration_s reaches the 5 pp guard."""
    return OFFSET_GUARD_PP * 3600.0 * q_ref / (100.0 * duration_s)


def drift_pp(offset_a, duration_s, q_ref):
    """Coulomb-counting drift in pp after duration_s with a constant offset: 100 * dI * t / (3600 * Q_ref)."""
    return 100.0 * offset_a * duration_s / (3600.0 * q_ref)


def section_runs(folders, records, q_ref):
    """Section 7: run durations, reference SoC at the end, coulomb counter against the reference, offset guard."""
    lines = ["## 7. Run durations, reference SoC and the offset guard", ""]
    lines.append("Source: the drive files below and the six PausCycl files. *Duration as stored*: last Time minus "
                 "first Time. *Rows used*: after the loader rules (legend). *Window*: Time from the first row used "
                 f"to the last row with SoC_ref >= {fmt(100 * WINDOW_SOC, 0)} % (the spec's evaluation window). "
                 "SoC_ref follows the cycler's counter: SoC_ref = SoC0 - Ah_removed / Q_ref with Ah_removed = "
                 "-(Ah - Ah at the first row used), and SoC0 = 1 - (Ah the counter removed before the first row "
                 "used) / Q_ref. *CC - ref*: the coulomb-counting baseline (the project-sign current of the previous "
                 "kept row held over the actual dt) minus SoC_ref, at the end and the largest absolute difference "
                 "over the run, in pp.")
    lines.append("")
    lines.append("| file | role | duration as stored (s) | first row used | duration, rows used (s) | window (s) "
                 "| SoC0 | SoC_ref at end (%) | CC - ref at end (pp) | max abs(CC - ref) (pp) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for folder in folders:
        for r in sorted(drive_records(records, folder), key=lambda r: r["start"]):
            lines.append(f"| {label(r)} | {run_role(r)} | {fmt(r['stored_duration_s'], 1)} | {r['first_row_used']} "
                         f"| {fmt(r['used_duration_s'], 1)} | {fmt(r['window_s'], 1)} | {fmt(r['soc0'], 5)} "
                         f"| {fmt(100.0 * r['soc_end'], 2)} | {fmt(r['cc_minus_ref_end_pp'], 3)} "
                         f"| {fmt(r['cc_minus_ref_max_pp'], 3)} |")
    lines.append("")

    evaluated = [r for r in drive_records(records) if run_role(r) == "evaluation"]
    lines.append(f"Evaluation set ({len(evaluated)} runs) per folder. *Travel after a start level L*: L minus "
                 f"max(SoC_ref at end, {fmt(100 * WINDOW_SOC, 0)} %), the SoC range inside the window after an "
                 "experiment-3 start at L; min / max over the folder's runs.")
    lines.append("")
    lines.append("| folder | runs | shortest run (s) | longest run (s) | SoC_ref at end, min / max (%) "
                 + "".join(f"| travel after {fmt(100 * level, 0)} %, min / max (pp) " for level in EXP3_START_SOC)
                 + "| largest max abs(CC - ref) (pp) |")
    lines.append("|---" * (6 + len(EXP3_START_SOC)) + "|")
    for folder in folders:
        runs = [r for r in evaluated if r["folder"] == folder]
        shortest = min(runs, key=lambda r: r["used_duration_s"])
        longest = max(runs, key=lambda r: r["used_duration_s"])
        ends = [100.0 * r["soc_end"] for r in runs]
        travel_cells = ""
        for level in EXP3_START_SOC:
            travel = [100.0 * (level - max(r["soc_end"], WINDOW_SOC)) for r in runs]
            travel_cells += f"| {fmt(min(travel), 2)} / {fmt(max(travel), 2)} "
        worst = max(runs, key=lambda r: r["cc_minus_ref_max_pp"])
        lines.append(f"| {folder} | {len(runs)} | {fmt(shortest['used_duration_s'], 1)} ({label(shortest)}) "
                     f"| {fmt(longest['used_duration_s'], 1)} ({label(longest)}) | {fmt(min(ends), 2)} / "
                     f"{fmt(max(ends), 2)} {travel_cells}| {fmt(worst['cc_minus_ref_max_pp'], 3)} ({label(worst)}) |")
    lines.append("")

    shortest = min(evaluated, key=lambda r: r["used_duration_s"])
    shortest_window = min(evaluated, key=lambda r: r["window_s"])
    worst = max(evaluated, key=lambda r: r["cc_minus_ref_max_pp"])
    lines.append(f"- **Coulomb counting against the reference, evaluation set:** the largest |CC - ref| over a run "
                 f"is {fmt(worst['cc_minus_ref_max_pp'], 3)} pp ({label(worst)}).")
    duration = shortest["used_duration_s"]
    lines.append(f"- **Offset guard (the spec):** drift_pp = 100 x offset x duration / (3600 x Q_ref) at the end of "
                 f"the shortest evaluation run, {label(shortest)}, {fmt(duration, 1)} s (its window is "
                 f"{fmt(shortest['window_s'], 1)} s; the shortest window is {label(shortest_window)}, "
                 f"{fmt(shortest_window['window_s'], 1)} s). " +
                 "; ".join(f"{fmt(1000 * offset, 0)} mA gives {fmt(drift_pp(offset, duration, q_ref), 3)} pp"
                           for offset in OFFSETS_A) +
                 f". The threshold for {fmt(OFFSET_GUARD_PP, 0)} pp is {fmt(1000 * guard_threshold_a(duration, q_ref), 1)} "
                 f"mA; the smallest multiple of {fmt(1000 * OFFSET_STEP_A, 0)} mA that meets it is "
                 f"{fmt(1000 * round_up(guard_threshold_a(duration, q_ref), OFFSET_STEP_A), 0)} mA.")

    paus = sorted([r for r in records if r["test_type"] == "pauscycl"], key=lambda r: r["used_duration_s"])
    partial = sorted([r for r in drive_records(records) if run_key(r).startswith("562_Mixed")],
                     key=lambda r: r["used_duration_s"])
    for name, extra in (("the six PausCycl files", paus), ("the 562 partial runs (562_Mixed4-8)", partial),
                        ("both", paus + partial)):
        candidate = min(evaluated + extra, key=lambda r: r["used_duration_s"])
        threshold = guard_threshold_a(candidate["used_duration_s"], q_ref)
        lines.append(f"- **Hypothetical, if {name} were in the set:** shortest run {label(candidate)}, "
                     f"{fmt(candidate['used_duration_s'], 1)} s; threshold {fmt(1000 * threshold, 1)} mA, so "
                     f"{fmt(1000 * round_up(threshold, OFFSET_STEP_A), 0)} mA.")
    lines.append("")
    lines.append("PausCycl files (not drive cycles; not in the evaluation set):")
    lines.append("")
    lines.append("| file | duration, rows used (s) | Ah at the last row (Ah) |")
    lines.append("|---|---|---|")
    for r in sorted(paus, key=lambda r: r["start"]):
        lines.append(f"| {label(r)} | {fmt(r['used_duration_s'], 1)} | {fmt(r['ah_last'], 5)} |")
    lines.append("")
    return lines


def charge_kind(record):
    """Short description of a Charge file for the drive-file table: CC-CV, top-up or no current."""
    charge = record.get("charge")
    if charge is None:
        return "no current"
    if charge["has_cc"]:
        return "CC-CV charge (CC above 2.9 A)"
    return f"no CC phase (peak {fmt(charge['peak_a'], 3)} A)"


def section_full_charge(folders, records):
    """Section 8: how each drive file opens, and what was logged just before it."""
    lines = ["## 8. Full-charge start of the drive files", ""]
    lines.append("Source: the 70 drive files and, for each, the previous file of its folder (by first TimeStamp). "
                 f"*Rule*: first V > {FULL_VOLTAGE_V} V and |I| < {fmt(1000 * FULL_CURRENT_A, 0)} mA on the first row. "
                 "*Gap*: first TimeStamp of the drive file minus last TimeStamp of the previous file (1 s resolution). "
                 "*Previous file's last row*: the last row with V > 0.")
    lines.append("")
    lines.append("| file | role | first row: V (V), I (A) | meets the rule | first row used: row, V (V), I (A) "
                 "| previous file | its last row: V (V), I (A) | gap (s) | previous file is |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    drives = []
    for folder in folders:
        drives += sorted(drive_records(records, folder), key=lambda r: r["start"])
    for r in drives:
        previous = r["previous"]
        meets = r["first_v"] > FULL_VOLTAGE_V and abs(r["first_i"]) < FULL_CURRENT_A
        r["meets_full_rule"] = meets
        used_text = "row 0" if r["first_row_used"] == 0 else (
            f"row {r['first_row_used']}: {fmt(r['first_used_v'], 4)}, {fmt(r['first_used_i'], 4)}")
        if previous is None:
            previous_cells = "none in the folder | n/a | n/a | n/a"
        else:
            gap = r["previous_gap_s"]
            kind = charge_kind(previous) if previous["test_type"] == "charge" else f"a {previous['test_type']} file"
            previous_cells = (f"{label(previous)} | {fmt(previous['last_valid_v'], 4)}, "
                              f"{fmt(previous['last_valid_i'], 4)} | {fmt(gap, 0)} | {kind}")
        lines.append(f"| {label(r)} | {run_role(r)} | {fmt(r['first_v'], 4)}, {fmt(r['first_i'], 4)} "
                     f"| {'yes' if meets else 'no'} | {used_text} | {previous_cells} |")
    lines.append("")

    with_current = [r for r in drives if r["has_current"]]
    meeting = [r for r in drives if r["meets_full_rule"]]
    at_rest = [r for r in with_current if abs(r["first_i"]) < REST_START_CURRENT_A]
    rest_not_rule = [r for r in at_rest if not r["meets_full_rule"]]
    under_load = [r for r in with_current if abs(r["first_i"]) >= REST_START_CURRENT_A]
    linked = []
    unlinked = []
    for r in under_load:
        previous = r["previous"]
        ok = (previous is not None and previous["test_type"] == "charge" and r["previous_gap_s"] <= LINK_GAP_S
              and previous["last_valid_v"] > FULL_VOLTAGE_V and abs(previous["last_valid_i"]) < FULL_CURRENT_A)
        (linked if ok else unlinked).append(r)
    lines.append(f"- **Meet the rule (first row):** {len(meeting)} of {len(drives)} drive files.")
    lines.append(f"- **Open at rest** (|I| < {fmt(1000 * REST_START_CURRENT_A, 0)} mA on the first row; the "
                 f"{len(with_current)} drive files with current): {len(at_rest)}, at "
                 f"{fmt_range([r['first_v'] for r in at_rest], 4)} V and {fmt_range([r['first_i'] for r in at_rest], 4)} A. "
                 f"{len(rest_not_rule)} of them miss the rule only on current: " +
                 ", ".join(f"{label(r)} ({fmt(r['first_i'], 4)} A)" for r in rest_not_rule) + ".")
    lines.append(f"- **Open under load** (|I| >= {fmt(1000 * REST_START_CURRENT_A, 0)} mA): {len(under_load)}, at "
                 f"{fmt_range([r['first_v'] for r in under_load], 4)} V and {fmt_range([r['first_i'] for r in under_load], 4)} A. "
                 f"{len(linked)} of them start at most {fmt(LINK_GAP_S, 0)} s after a Charge file whose last row is a "
                 f"rest above {FULL_VOLTAGE_V} V. The other {len(unlinked)}: " +
                 "; ".join(f"{label(r)} (opens at {fmt(r['first_v'], 4)} V, {fmt(r['first_i'], 4)} A; previous file "
                           f"{label(r['previous'])}, {charge_kind(r['previous'])}, ends at "
                           f"{fmt(r['previous']['last_valid_v'], 4)} V, {fmt(r['previous_gap_s'], 0)} s earlier)"
                           for r in unlinked) + ".")
    special = [r for r in drives if r["first_row_used"] != 0]
    lines.append("- **First row used where the loader cuts the file:** " + "; ".join(
        f"{label(r)} row {r['first_row_used']}: {fmt(r['first_used_v'], 5)} V, {fmt(r['first_used_i'], 4)} A, "
        f"meets the rule: {'yes' if r['first_used_v'] > FULL_VOLTAGE_V and abs(r['first_used_i']) < FULL_CURRENT_A else 'no'}"
        for r in special) + ".")
    no_previous_charge = [r for r in drives if r["previous"] is None or r["previous"]["test_type"] != "charge"]
    lines.append("- **Drive files whose previous file is not a Charge file:** " + "; ".join(
        f"{label(r)} (" + ("first file of its folder" if r["previous"] is None else
                           f"after {label(r['previous'])}, gap {fmt(r['previous_gap_s'], 0)} s") + ")"
        for r in no_previous_charge) + ".")
    lines.append("")
    return lines


def section_charges(records):
    """Section 9: the charge procedure in the Charge files."""
    charges = [r for r in records if r["test_type"] == "charge"]
    with_current = [r for r in charges if r["charge"] is not None]
    with_cc = [r for r in with_current if r["charge"]["has_cc"]]
    without_cc = [r for r in with_current if not r["charge"]["has_cc"]]
    multi = [r for r in with_current if r["charge_runs"] > 1]
    lines = ["## 9. Charge files", ""]
    lines.append(f"Source: the {len(charges)} Charge files (`*_Charge*.mat` in every folder). A row is *charging* "
                 f"when Current > {fmt(1000 * FLOW_CURRENT_A, 0)} mA. *CC phase*: Current above {CC_CURRENT_A} A. "
                 f"*CV voltage*: median Voltage over rows with Current > 0 and Voltage >= {CV_PHASE_V} V. "
                 "*Last charge current*: Current on the last row with Current > 0. *Rest before*: first charging row "
                 "minus the first row; *rest after*: last row with V > 0 minus the last row with Current > 0 (Time, s).")
    lines.append("")
    empty = [r for r in charges if r["charge"] is None]
    lines.append(f"- **Charge files with current:** {len(with_current)} of {len(charges)}; without: "
                 + ", ".join(label(r) for r in empty) + ".")
    lines.append(f"- **With a CC phase above {CC_CURRENT_A} A:** {len(with_cc)}; without: {len(without_cc)} (table "
                 "below). Files with more than one charge (runs of charging rows): " +
                 ", ".join(f"{label(r)} ({r['charge_runs']} charges)" for r in multi) + ".")
    cc = [r["charge"]["cc_median_a"] for r in with_cc]
    lines.append(f"- **CC current:** per-file median {fmt_range(cc, 4)} A (median over files {fmt(np.median(cc), 4)} A); "
                 f"largest sample {fmt(max(r['charge']['peak_a'] for r in with_cc), 4)} A.")
    lines.append(f"- **CV voltage:** per-file median {fmt_range([r['charge']['cv_median_v'] for r in with_current], 4)} V; "
                 f"highest sample {fmt(max(r['charge']['v_max'] for r in with_current), 4)} V.")
    lines.append(f"- **Last charge current (cutoff):** {fmt_range([r['charge']['last_current_a'] for r in with_current], 4)} A "
                 f"in all {len(with_current)} files.")
    lines.append(f"- **Rest before the charge:** {fmt_range([r['charge']['rest_before_s'] for r in with_current], 1)} s; "
                 f"**rest after:** {fmt_range([r['charge']['rest_after_s'] for r in with_current], 1)} s.")
    lines.append(f"- **Cell temperature at the first charging row:** "
                 f"{fmt_range([r['charge']['temp_at_start'] for r in with_current], 2)} degC; over all charging rows "
                 f"{fmt(min(r['charge']['temp_min'] for r in with_current), 2)} to "
                 f"{fmt(max(r['charge']['temp_max'] for r in with_current), 2)} degC.")
    lines.append("")
    lines.append(f"Charge files with current but no CC phase above {CC_CURRENT_A} A, and the file logged next in the "
                 "folder:")
    lines.append("")
    lines.append("| file | peak current (A) | Ah charged (Ah) | charging time (s) | next file |")
    lines.append("|---|---|---|---|---|")
    for r in sorted(without_cc, key=lambda r: (r["folder"], r["start"])):
        later = [x for x in records if x["folder"] == r["folder"] and x["start"] > r["start"]]
        following = min(later, key=lambda x: x["start"]) if later else None
        lines.append(f"| {label(r)} | {fmt(r['charge']['peak_a'], 3)} | {fmt(r['charge']['ah_charged'], 4)} "
                     f"| {fmt(r['charge']['charge_s'], 0)} | {label(following) if following else 'none'} |")
    lines.append("")
    after_top_up = [r for r in drive_records(records)
                    if r["previous"] is not None and r["previous"]["test_type"] == "charge"
                    and r["previous"]["charge"] is not None and not r["previous"]["charge"]["has_cc"]]
    lines.append(f"- **Drive files that follow a Charge file without a CC phase:** " + "; ".join(
        f"{label(r)} after {label(r['previous'])} ({run_role(r)})" for r in after_top_up) + ".")
    lines.append("")
    return lines
