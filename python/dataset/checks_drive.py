"""Sections 1 to 4 of results/s0/data_checks.md: steps, duplicate rows, long steps and the special drive files."""

import numpy as np

from dataset.checks_rules import (DT_BAND_S, LONG_STEP_S, NUMERIC_FIELDS, ONLY_ROWS_DATED, label, rows_used, run_key,
                                  run_role, stored_rows_text)
from dataset.common import DRIVE_TYPES, fmt, longest_run
from ekfsoc import rawio
from ekfsoc.loader import GAP_S


def drive_records(records, folder=None):
    """Drive files (UDDS, HWFET, LA92, US06, Mixed1-8), optionally of one folder."""
    return [r for r in records if r["test_type"] in DRIVE_TYPES and (folder is None or r["folder"] == folder)]


def previous_file(record, records):
    """The file of the same folder whose first TimeStamp comes last before this file's first TimeStamp."""
    earlier = [r for r in records if r["folder"] == record["folder"] and r["start"] < record["start"]]
    return max(earlier, key=lambda r: r["start"]) if earlier else None


def section_steps(folders, records):
    """Section 1: drive-cycle step statistics per folder and in total."""
    drives = drive_records(records)
    lines = ["## 1. Drive-cycle sampling steps", ""]
    lines.append(f"Source: all {len(drives)} drive files (UDDS, HWFET, LA92, US06, Mixed1 to Mixed8; names in "
                 "section 7), every row as stored. A step is Time[k] - Time[k-1]. The median and the 1st and 99th "
                 "percentiles are taken over the steps with dt > 0, as in `results/s0/data_inventory.md`.")
    lines.append("")
    lines.append(f"| folder | drive files | steps | steps in {DT_BAND_S[0]} to {DT_BAND_S[1]} s (%) | dt = 0 | dt < 0 "
                 f"| dt > {LONG_STEP_S} s | dt > {GAP_S:.0f} s | median dt (s) | 1st percentile (s) "
                 "| 99th percentile (s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for folder in folders + ["all"]:
        files = drives if folder == "all" else drive_records(records, folder)
        steps = np.concatenate([r["steps"] for r in files])
        positive = steps[steps > 0.0]
        in_band = np.sum((steps >= DT_BAND_S[0]) & (steps <= DT_BAND_S[1]))
        lines.append(f"| {folder} | {len(files)} | {len(steps)} | {fmt(100.0 * in_band / len(steps), 3)} "
                     f"| {int(np.sum(steps == 0.0))} | {int(np.sum(steps < 0.0))} | {int(np.sum(steps > LONG_STEP_S))} "
                     f"| {int(np.sum(steps > GAP_S))} | {fmt(np.median(positive), 3)} "
                     f"| {fmt(np.percentile(positive, 1), 3)} | {fmt(np.percentile(positive, 99), 3)} |")
    lines.append("")
    return lines


def section_duplicates(records):
    """Section 2: duplicate-Time rows in every file, per test type, in the HPPC files and at drive-file ends."""
    lines = ["## 2. Duplicate Time rows", ""]
    lines.append("Source: all files, every row as stored. A duplicate is a row whose Time equals the previous "
                 "row's Time (the *dup* column of `results/s0/data_inventory.md`). A duplicate pair *differs* when "
                 "the two rows have different Current or Voltage; pairs with a NaN are counted apart.")
    lines.append("")
    with_duplicates = [r for r in records if r["n_duplicates"] > 0]
    total = sum(r["n_duplicates"] for r in records)
    lines.append(f"- **Total:** {total} duplicate rows in {len(with_duplicates)} of {len(records)} files.")
    pairs = [(r, pair) for r in records for pair in r["differing_pairs"]]
    nan_pairs = sum(r["n_nan_pairs"] for r in records)
    files_with_pairs = [r for r in records if r["differing_pairs"]]
    lines.append(f"- **Pairs that differ, all files:** {len(pairs)} in {len(files_with_pairs)} files (" +
                 ", ".join(f"{label(r)} {len(r['differing_pairs'])}" for r in files_with_pairs) + "); the largest "
                 f"difference is {fmt(1000.0 * max(p[1] for _, p in pairs), 2)} mA in Current and "
                 f"{fmt(1000.0 * max(p[2] for _, p in pairs), 3)} mV in Voltage. Pairs with a NaN: {nan_pairs} "
                 "(`10degC/582_LA92`, section 4).")
    stall = find_record(records, "n10degC", "602_Mixed4")
    lines.append(f"- **{label(stall)}** holds {stall['n_duplicates']} of the "
                 f"{sum(r['n_duplicates'] for r in drive_records(records))} duplicate rows in drive files: "
                 f"{stall['longest_same_time_rows'] - 1} in its frozen block of {stall['longest_same_time_rows']} rows "
                 f"(section 4c) and {stall['n_duplicates'] - stall['longest_same_time_rows'] + 1} elsewhere.")
    drives = drive_records(records)
    ends = [r for r in drives if r["ends_on_duplicate"]]
    ends_zero = [r for r in drives if r["ends_on_duplicate_zero"]]
    lines.append(f"- **Drive files that end on a duplicated row:** {len(ends)} of {len(drives)}; in "
                 f"{len(ends_zero)} of them both rows have Current = 0 A.")
    lines.append("")

    lines.append("Per test type:")
    lines.append("")
    lines.append("| test type | files | files with duplicates | duplicate rows | min / max per file "
                 "| differing pairs |")
    lines.append("|---|---|---|---|---|---|")
    groups = {}
    for r in records:
        group = "drive (UDDS, HWFET, LA92, US06, Mixed1-8)" if r["test_type"] in DRIVE_TYPES else r["test_type"]
        groups.setdefault(group, []).append(r)
    for group in sorted(groups):
        files = groups[group]
        counts = [r["n_duplicates"] for r in files]
        lines.append(f"| {group} | {len(files)} | {sum(1 for c in counts if c > 0)} | {sum(counts)} "
                     f"| {min(counts)} / {max(counts)} | {sum(len(r['differing_pairs']) for r in files)} |")
    lines.append("")

    lines.append("HPPC files. *At a step end*: the pair carries |I| >= 50 mA and the next row has |I| < 50 mA, "
                 "i.e. the pair is the last sample of a current step.")
    lines.append("")
    lines.append("| file | duplicate rows | pairs that differ | of those, at a step end | rows of the other pairs "
                 "| largest dI (mA) | largest dV (mV) |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in [r for r in records if r["test_type"] == "hppc"]:
        pairs = r["differing_pairs"]
        others = [p[0] for p in pairs if not p[3]]
        lines.append(f"| {label(r)} | {r['n_duplicates']} | {len(pairs)} | {sum(1 for p in pairs if p[3])} "
                     f"| {', '.join(str(k) for k in others) if others else 'none'} "
                     f"| {fmt(1000.0 * max(p[1] for p in pairs), 2)} | {fmt(1000.0 * max(p[2] for p in pairs), 3)} |")
    lines.append("")
    return lines


def section_long_steps(records, q_ref):
    """Section 3: steps longer than 1 s inside drive files, as stored and in the rows the loader keeps."""
    lines = ["## 3. Steps longer than 1 s inside drive files", ""]
    lines.append(f"Source: the drive files listed below (the other drive files have no step above {GAP_S:.0f} s). "
                 "*As stored*: every row. *Rows used*: after the loader rules (legend). Step lengths are in s, "
                 "in file order; a row number k is the row that ends the step from row k-1 (or from the previous "
                 "kept row).")
    lines.append("")
    lines.append("| file | role | steps > 1 s as stored | largest (s) | step lengths as stored (s) "
                 "| steps > 1 s in the rows used | step lengths in the rows used (s) |")
    lines.append("|---|---|---|---|---|---|---|")
    drives = drive_records(records)
    for r in drives:
        if not r["long_steps"] and not r["used_long_steps"]:
            continue
        stored = ", ".join(fmt(dt, 3) for _, dt in r["long_steps"])
        used = ", ".join(fmt(step["dt"], 3) for step in r["used_long_steps"])
        lines.append(f"| {label(r)} | {run_role(r)} | {len(r['long_steps'])} "
                     f"| {fmt(max(dt for _, dt in r['long_steps']), 3)} | {stored} | {len(r['used_long_steps'])} "
                     f"| {used if used else 'none'} |")
    lines.append("")

    evaluated = [r for r in drives if run_role(r) == "evaluation"]
    with_long = [r for r in evaluated if r["used_long_steps"]]
    all_steps = [step for r in with_long for step in r["used_long_steps"]]
    lines.append(f"- **Evaluation runs with steps > {GAP_S:.0f} s (rows used):** {len(with_long)} "
                 f"({', '.join(label(r) for r in with_long)}); {len(all_steps)} steps of "
                 f"{fmt(min(s['dt'] for s in all_steps), 3)} to {fmt(max(s['dt'] for s in all_steps), 3)} s.")
    longest = max(all_steps, key=lambda s: s["dt"])
    regen_a = max(r["used_i_max"] for r in evaluated)
    discharge_a = -min(r["used_i_min"] for r in evaluated)
    lines.append(f"- **Bound on the charge error of one such step:** the longest step, {fmt(longest['dt'], 3)} s, "
                 f"with the largest charging (regen) current in the evaluation runs, {fmt(regen_a, 2)} A, held "
                 f"over it gives {fmt(100.0 * regen_a * longest['dt'] / 3600.0 / q_ref, 3)} pp of Q_ref; with the "
                 f"largest discharge current, {fmt(discharge_a, 2)} A, it gives "
                 f"{fmt(100.0 * discharge_a * longest['dt'] / 3600.0 / q_ref, 3)} pp.")
    worst = max(all_steps, key=lambda s: abs(s["error_pp"]))
    lines.append(f"- **Measured charge error across these steps:** the current held over each step (previous kept "
                 f"row, zero-order hold) against the counter's change over the same step, table below. The largest "
                 f"difference is {fmt(worst['error_pp'], 4)} pp; the held current is at most "
                 f"{fmt(1000.0 * max(abs(s['i_before']) for s in all_steps), 1)} mA at these steps.")
    lines.append("")
    lines.append("| file | row | Time before (s) | dt (s) | I before (A) | I after (A) | held charge removed (mAh) "
                 "| counter removed (mAh) | held minus counter (pp) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in with_long:
        for step in r["used_long_steps"]:
            lines.append(f"| {label(r)} | {step['row']} | {fmt(step['time_before'], 3)} | {fmt(step['dt'], 3)} "
                         f"| {fmt(step['i_before'], 4)} | {fmt(step['i_after'], 4)} | {fmt(step['held_mah'], 4)} "
                         f"| {fmt(step['counter_mah'], 4)} | {fmt(step['error_pp'], 5)} |")
    lines.append("")
    return lines


def find_record(records, folder, key):
    """The record of one folder whose run key (test number and first descriptor word) is key."""
    found = [r for r in records if r["folder"] == folder and run_key(r) == key]
    if len(found) != 1:
        raise ValueError(f"expected one file {folder}/{key}, found {len(found)}")
    return found[0]


def section_special_files(records, q_ref):
    """Section 4: the evidence behind the three per-file rules (571_Mixed6, 582_LA92, 602_Mixed4)."""
    lines = ["## 4. The three damaged drive files", ""]

    # 571_Mixed6: hidden pause between two rows.
    r = find_record(records, "10degC", "571_Mixed6")
    data = rawio.load_mat(r["path"])
    t, v, i, ah, temp, stamps = (data["Time"], data["Voltage"], data["Current"], data["Ah"],
                                 data["Battery_Temp_degC"], data["TimeStamp"])
    stamp_jumps = [(rawio.parse_timestamp(stamps[k]) - rawio.parse_timestamp(stamps[k - 1])).total_seconds()
                   for k in range(1, len(stamps))]
    k = int(np.argmax(stamp_jumps)) + 1                          # first row after the largest TimeStamp jump
    removed_before = -(ah[k] - ah[0])
    lines.append(f"### 4a. {label(r)}")
    lines.append("")
    lines.append(f"Source: `data/raw/10degC/{r['file']}`.")
    lines.append("")
    lines.append(f"- **Hidden pause:** the largest TimeStamp jump is between rows {k - 1} and {k}: "
                 f"{fmt(stamp_jumps[k - 1], 3)} s ({fmt(stamp_jumps[k - 1] / 3600.0, 2)} h; TimeStamps "
                 f"`{stamps[k - 1]}` and `{stamps[k]}`), while Time advances {fmt(t[k] - t[k - 1], 3)} s.")
    lines.append(f"- **Row {k - 1}:** Time {fmt(t[k - 1], 3)} s, V {fmt(v[k - 1], 4)} V, I {fmt(i[k - 1], 5)} A, "
                 f"Ah {fmt(ah[k - 1], 5)} Ah, T {fmt(temp[k - 1], 2)} degC.")
    lines.append(f"- **Row {k}:** Time {fmt(t[k], 3)} s, V {fmt(v[k], 4)} V, I {fmt(i[k], 5)} A, "
                 f"Ah {fmt(ah[k], 5)} Ah, T {fmt(temp[k], 2)} degC. Row 0 has Ah {fmt(ah[0], 5)} Ah.")
    lines.append(f"- **SoC0 when the run starts at row {k}:** 1 - Ah_removed / Q_ref with Ah_removed = -(Ah[{k}] - "
                 f"Ah[0]) = {fmt(removed_before, 5)} Ah, so SoC0 = {fmt(1.0 - removed_before / q_ref, 5)}.")
    lines.append("")

    # 582_LA92: false start spliced in front of the real run.
    r = find_record(records, "10degC", "582_LA92")
    data = rawio.load_mat(r["path"])
    t, v, i, ah, stamps = data["Time"], data["Voltage"], data["Current"], data["Ah"], data["TimeStamp"]
    dates = [rawio.parse_timestamp(stamp).date() for stamp in stamps]
    year, month, day = ONLY_ROWS_DATED["582_LA92"]
    real = np.array([(d.year, d.month, d.day) == (year, month, day) for d in dates])
    first_real = int(np.where(real)[0][0])
    stray = [k for k in range(first_real, len(t)) if not real[k]]
    false_start = np.arange(first_real)
    lowest = int(false_start[np.nanargmin(ah[:first_real])])
    backward = [(k, float(t[k] - t[k - 1])) for k in range(1, len(t)) if t[k] - t[k - 1] < 0.0]
    used = rows_used(r, data)
    removed_before = -(ah[first_real] - ah[0])
    date_counts = {}
    for d in dates:
        date_counts[d] = date_counts.get(d, 0) + 1
    lines.append(f"### 4b. {label(r)}")
    lines.append("")
    lines.append(f"Source: `data/raw/10degC/{r['file']}`.")
    lines.append("")
    lines.append("- **Rows per TimeStamp date:** " +
                 ", ".join(f"{d:%d/%m/%Y}: {n}" for d, n in sorted(date_counts.items())) + f" (of {len(t)} rows).")
    lines.append(f"- **False start:** rows 0 to {first_real - 1}, Time {fmt(t[0], 3)} to {fmt(t[first_real - 1], 3)} s. "
                 f"Its counter is lowest at row {lowest} ({fmt(ah[lowest], 5)} Ah) and ends at "
                 f"{fmt(ah[first_real - 1], 5)} Ah at row {first_real - 1}, which is at {fmt(v[first_real - 1], 4)} V "
                 f"and {fmt(i[first_real - 1], 4)} A.")
    jump = (rawio.parse_timestamp(stamps[first_real]) - rawio.parse_timestamp(stamps[first_real - 1])).total_seconds()
    lines.append(f"- **Pause before the real run:** TimeStamp jumps {fmt(jump, 3)} s ({fmt(jump / 3600.0, 2)} h) "
                 f"between rows {first_real - 1} and {first_real}; Time advances {fmt(t[first_real] - t[first_real - 1], 3)} s.")
    lines.append(f"- **First row of the real run:** row {first_real} (`{stamps[first_real]}`), Time "
                 f"{fmt(t[first_real], 3)} s, V {fmt(v[first_real], 5)} V, I {fmt(i[first_real], 4)} A, Ah "
                 f"{fmt(ah[first_real], 5)} Ah. Row 0 has Ah {fmt(ah[0], 5)} Ah, so Ah_removed before the run = "
                 f"{fmt(removed_before, 5)} Ah and SoC0 = 1 - {fmt(removed_before, 5)} / Q_ref = "
                 f"{fmt(1.0 - removed_before / q_ref, 5)}.")
    lines.append(f"- **Rows dated {stamps[0].split()[0]} inside the real run (row {first_real} onward):** "
                 f"{stored_rows_text(stray)}.")
    nan_text = "; ".join(f"row {k}: {', '.join(fields)}" for k, fields in r["nan_rows"])
    lines.append(f"- **NaN rows:** {nan_text}.")
    lines.append("- **Backward Time steps:** " + "; ".join(
        f"rows {k - 1} to {k}: {fmt(step, 3)} s (dates {dates[k - 1]:%d/%m} and {dates[k]:%d/%m})"
        for k, step in backward) + ".")
    used_steps = np.diff(t[used])
    lines.append(f"- **Rows used (only rows dated {day:02d}/{month:02d}/{year}, then the general loader rules):** "
                 f"{len(used)} rows, Time {fmt(t[used[0]], 3)} to {fmt(t[used[-1]], 3)} s, smallest step "
                 f"{fmt(np.min(used_steps), 3)} s, {int(np.sum(used_steps > GAP_S))} steps above {GAP_S:.0f} s "
                 "(section 3).")
    lines.append("")

    # 602_Mixed4: frozen rows, then an unlogged interval.
    r = find_record(records, "n10degC", "602_Mixed4")
    data = rawio.load_mat(r["path"])
    t, v, i, ah, temp, stamps = (data["Time"], data["Voltage"], data["Current"], data["Ah"],
                                 data["Battery_Temp_degC"], data["TimeStamp"])
    same_as_previous = np.concatenate(([False], t[1:] == t[:-1]))
    first_dup, last_dup = longest_run(same_as_previous)
    block_first = first_dup - 1                       # the row the duplicates repeat
    block_last = last_dup
    identical = all(np.all(data[name][block_first:block_last + 1] == data[name][block_first])
                    for name in NUMERIC_FIELDS)
    stamps_identical = len(set(stamps[block_first:block_last + 1])) == 1
    after = block_last + 1
    gap_s = float(t[after] - t[block_last])
    stamp_gap_s = (rawio.parse_timestamp(stamps[after]) - rawio.parse_timestamp(stamps[block_last])).total_seconds()
    counter_removed = -(ah[after] - ah[block_last])
    held_previous = -i[block_last] * gap_s / 3600.0
    held_next = -i[after] * gap_s / 3600.0
    lines.append(f"### 4c. {label(r)}")
    lines.append("")
    lines.append(f"Source: `data/raw/n10degC/{r['file']}`.")
    lines.append("")
    lines.append(f"- **Frozen rows:** rows {block_first} to {block_last} ({block_last - block_first + 1} rows, i.e. "
                 f"{block_last - block_first} duplicate rows of the file's {r['n_duplicates']}) all have "
                 f"Time {fmt(t[block_first], 3)} s; every numeric field is identical across them: "
                 f"{'yes' if identical else 'no'}; the TimeStamp is identical too: {'yes' if stamps_identical else 'no'} "
                 f"(`{stamps[block_first]}`). The frozen sample: V {fmt(v[block_first], 5)} V, I "
                 f"{fmt(i[block_first], 5)} A, Ah {fmt(ah[block_first], 5)} Ah, T {fmt(temp[block_first], 2)} degC.")
    lines.append(f"- **Gap after the frozen rows:** rows {block_last} to {after}: Time step {fmt(gap_s, 3)} s, "
                 f"TimeStamp step {fmt(stamp_gap_s, 3)} s, so the interval is unlogged rather than hidden.")
    lines.append(f"- **Counter across the gap:** {fmt(ah[block_last], 5)} to {fmt(ah[after], 5)} Ah, i.e. "
                 f"{fmt(counter_removed, 5)} Ah removed = {fmt(100.0 * counter_removed / q_ref, 3)} pp of Q_ref.")
    lines.append(f"- **Current on the rows before and after the gap:** {fmt(i[block_last], 5)} A (row {block_last}) "
                 f"and {fmt(i[after], 5)} A (row {after}). Held over the {fmt(gap_s, 3)} s step (zero-order hold), "
                 f"the row before moves SoC by {fmt(-100.0 * held_previous / q_ref, 2)} pp "
                 f"({fmt(-held_previous, 5)} Ah charged) and the row after by {fmt(-100.0 * held_next / q_ref, 2)} pp "
                 f"({fmt(held_next, 5)} Ah removed); the counter moves SoC_ref by "
                 f"{fmt(-100.0 * counter_removed / q_ref, 2)} pp.")
    lines.append(f"- **Over the whole run (rows used):** the held-current coulomb counter ends "
                 f"{fmt(r['cc_minus_ref_end_pp'], 2)} pp away from the counter-based reference (section 7).")
    lines.append("")
    return lines
