"""Sections 13 to 19 of results/s0/data_checks.md: the Ah counter, the campaign order, the 10 degC current scaling,
the 2.8 V limit, the segments the mixes share and the sign convention."""

import numpy as np

from dataset.checks_drive import drive_records, find_record
from dataset.checks_hppc import position_median
from dataset.checks_rules import (COUNTER_TOLERANCE_AH, HWFET_SECONDS, MATCH_CORRELATION, RECHARGE_MIN_A, label,
                                  rows_used)
from dataset.common import DRIVE_TYPES, FLOW_CURRENT_A, fmt, runs_of
from ekfsoc import rawio
from ekfsoc.hppc import LOW_LIMIT_V


def start_value_ah(folder, test_type, capacity_files):
    """Counter value the discharge of a capacity file starts from: 0 after a reset, or the carried C/20 end value."""
    if test_type == "dis_0p5c":
        return capacity_files[(folder, "c20")]["ah_last"]
    return 0.0


def start_difference_ah(folders, capacity_files):
    """Largest |start value - counter one interval before the first row| over the C/20, 0.5C and 2C files."""
    return max(abs(start_value_ah(folder, test_type, capacity_files)
                   - capacity_files[(folder, test_type)]["ah_back_one_interval"])
               for folder in folders for test_type in ("c20", "dis_0p5c", "dis_2c"))


def section_counter_starts(folders, capacity_files):
    """Section 13: where the counter of each C20DisCh, Dis_0p5C and Dis_2C file starts, and the capacity both ways."""
    lines = ["## 13. Counter start of the C/20, 0.5C and 2C files", ""]
    lines.append("Source: the C20DisCh, Dis_0p5C and Dis_2C files of every folder, rows as stored. *Back one "
                 "interval*: Ah[0] - I[0] x (Time[1] - Time[0]) / 3600, the counter one logging interval before the "
                 "first row. C20DisCh and Dis_2C files start one interval after a counter reset (back one interval "
                 "= 0); Dis_0p5C files continue the counter of the folder's C20DisCh file (back one interval = that "
                 "file's last Ah). *Capacity from the start value*: start value minus the counter at the end of the "
                 "discharge, where the start value is 0 (C20DisCh, Dis_2C: the step-start zero) or the C20DisCh "
                 "file's last Ah (Dis_0p5C: the carried counter). *Capacity -(Ah_end - Ah[0])*: logged rows only. "
                 "`results/s0/capacity.md` starts from *back one interval* instead; the two start values differ by at "
                 f"most {fmt(1000.0 * start_difference_ah(folders, capacity_files), 2)} mAh here, so its capacities can "
                 "differ from this column in the last digit.")
    lines.append("")
    lines.append("| folder | file | Ah[0] (Ah) | I[0] (A) | first interval (s) | back one interval (Ah) "
                 "| C20DisCh last Ah (Ah) | counter at discharge end (Ah) | capacity from the start value (Ah) "
                 "| capacity -(Ah_end - Ah[0]) (Ah) |")
    lines.append("|---" * 10 + "|")
    for folder in folders:
        c20_last = capacity_files[(folder, "c20")]["ah_last"]
        for test_type in ("c20", "dis_0p5c", "dis_2c"):
            f = capacity_files[(folder, test_type)]
            start_value = start_value_ah(folder, test_type, capacity_files)
            lines.append(f"| {folder} | {label(f['record'])} | {fmt(f['ah_first'], 5)} | {fmt(f['i_first'], 4)} "
                         f"| {fmt(f['interval_s'], 1)} | {fmt(f['ah_back_one_interval'], 5)} "
                         f"| {fmt(c20_last, 5) if test_type == 'dis_0p5c' else 'n/a'} | {fmt(f['ah_dis_end'], 5)} "
                         f"| {fmt(start_value - f['ah_dis_end'], 4)} | {fmt(f['ah_first'] - f['ah_dis_end'], 4)} |")
    lines.append("")
    return lines


def section_chronology(folders, records):
    """Section 14: first and last TimeStamp per folder, test numbers, and overlapping neighbours."""
    lines = ["## 14. Campaign chronology", ""]
    lines.append("Source: the first and last TimeStamp of every file (`ekfsoc.rawio.parse_timestamp`, which reads "
                 "both TimeStamp formats), shown to the whole second because the fraction is unreliable. Folders in "
                 "campaign order (sorted by their first TimeStamp).")
    lines.append("")
    lines.append("| folder | first TimeStamp | first file | last TimeStamp | last file | test numbers |")
    lines.append("|---|---|---|---|---|---|")
    for folder in folders:
        files = [r for r in records if r["folder"] == folder]
        first = min(files, key=lambda r: r["start"])
        last = max(files, key=lambda r: r["end"])
        numbers = sorted(set(r["test_number"] for r in files if r["test_number"] is not None))
        lines.append(f"| {folder} | {first['start'].isoformat(sep=' ', timespec='seconds')} | {label(first)} "
                     f"| {last['end'].isoformat(sep=' ', timespec='seconds')} | {label(last)} | {numbers[0]} to {numbers[-1]} "
                     f"({', '.join(str(n) for n in numbers)}) |")
    lines.append("")
    overlaps = []
    for r in records:
        previous = r["previous"]
        if previous is None:
            continue
        overlap_s = (previous["end"] - r["start"]).total_seconds()
        if overlap_s > 2.0 and r["end"] > previous["end"]:
            overlaps.append((r, previous, overlap_s))
    for r, previous, overlap_s in overlaps:
        lines.append(f"- **Overlap:** {label(r)} starts at {r['start'].isoformat(sep=' ', timespec='seconds')}, "
                     f"{fmt(overlap_s / 60.0, 1)} min before {label(previous)} ends at "
                     f"{previous['end'].isoformat(sep=' ', timespec='seconds')} (both by TimeStamp; checked for every "
                     "pair of neighbouring files).")
    if not overlaps:
        lines.append("- No neighbouring files overlap.")
    lines.append("")
    return lines


def section_scaling(folders, hppc, c20, capacity_files, records):
    """Section 15: the 10 degC test-575 currents against the other folders."""
    lines = ["## 15. Test currents per folder (the 10 degC test-575 scaling)", ""]
    lines.append("Source: the HPPC, C20DisCh, Dis_0p5C, Dis_2C and Cap_1C files of every folder. Medians in A, "
                 "cycler sign (HPPC values as in section 10, C/20 values as in section 11). *In-file recharge*: "
                 f"median of the rows above {RECHARGE_MIN_A} A in the recharge after the discharge. The last column "
                 "divides the 10 degC value by the 25 degC value.")
    lines.append("")
    rows = []
    for position in ("D1", "D2", "D3", "D4", "C1", "C2", "C3", "C4"):
        rows.append((f"HPPC pulse {position}", {f: position_median(hppc[f], position) for f in folders}))
    rows.append(("HPPC move current", {f: float(np.median([m["median_a"] for m in hppc[f]["moves"]])) for f in folders}))
    rows.append(("HPPC counter at the end of the first move (Ah)", {f: hppc[f]["moves"][0]["end_ah"] for f in folders}))
    rows.append(("HPPC in-file recharge", {f: hppc[f]["recharge_cc_a"] for f in folders}))
    rows.append(("C/20 discharge", {f: c20[f]["dis_median_a"] for f in folders}))
    rows.append(("C/20 charge CC", {f: c20[f]["cc_median_a"] for f in folders}))
    rows.append(("0.5C discharge (Dis_0p5C)", {f: capacity_files[(f, "dis_0p5c")]["dis_median_a"] for f in folders}))
    rows.append(("0.5C in-file recharge", {f: capacity_files[(f, "dis_0p5c")]["recharge_cc_a"] for f in folders}))
    rows.append(("2C discharge (Dis_2C)", {f: capacity_files[(f, "dis_2c")]["dis_median_a"] for f in folders}))
    rows.append(("2C in-file recharge", {f: capacity_files[(f, "dis_2c")]["recharge_cc_a"] for f in folders}))
    one_c = {}
    for f in folders:
        values = [r["median_current_discharge"] for r in records if r["folder"] == f and r["test_type"] == "cap_1c"]
        one_c[f] = float(np.median(values)) if values else float("nan")
    rows.append(("1C discharge (Cap_1C, median over the folder's files)", one_c))
    lines.append("| quantity | " + " | ".join(folders) + " | 10degC / 25degC |")
    lines.append("|---" * (len(folders) + 2) + "|")
    for name, values in rows:
        ratio = values["10degC"] / values["25degC"] if values["25degC"] not in (0.0,) else float("nan")
        lines.append(f"| {name} | " + " | ".join(fmt(values[f], 4) for f in folders) + f" | {fmt(ratio, 3)} |")
    lines.append("")
    lines.append("- 10 degC files of test 575: " + ", ".join(
        label(r) for r in records if r["folder"] == "10degC" and r["test_number"] == 575) + ".")
    lines.append("")
    return lines


def section_counter_per_type(records):
    """Extra 16: the Ah counter on the first row and its resets, per test type."""
    lines = ["## 16. Ah counter: first row and resets, per test type", ""]
    lines.append("Source: all files, rows as stored. A *reset* is a row where Ah is exactly 0 while the previous "
                 "row's Ah is not, by more than the current on either row could change the counter over that step "
                 f"(+{COUNTER_TOLERANCE_AH * 1000:.2f} mAh). This leaves out a counter that only passes through 0, as "
                 "it does under regen early in some drive cycles.")
    lines.append("")
    lines.append("| test type | files | Ah at the first row, min / max (Ah) | files with a reset | resets on the "
                 "last row | resets on the second-to-last row | resets on other rows |")
    lines.append("|---|---|---|---|---|---|---|")
    groups = {}
    for r in records:
        group = "drive (UDDS, HWFET, LA92, US06, Mixed1-8)" if r["test_type"] in DRIVE_TYPES else r["test_type"]
        groups.setdefault(group, []).append(r)
    for group in sorted(groups):
        files = groups[group]
        first = [r["ah_first"] for r in files]
        last = sum(1 for r in files for k in r["reset_rows"] if k == r["n_rows"] - 1)
        second = sum(1 for r in files for k in r["reset_rows"] if k == r["n_rows"] - 2)
        other = sum(1 for r in files for k in r["reset_rows"] if k < r["n_rows"] - 2)
        lines.append(f"| {group} | {len(files)} | {fmt(min(first), 5)} / {fmt(max(first), 5)} "
                     f"| {sum(1 for r in files if r['reset_rows'])} | {last} | {second} | {other} |")
    lines.append("")
    return lines


def section_low_limit(folders, records):
    """Extra 17: drive files that reach the 2.8 V cutoff."""
    lines = ["## 17. Drive files at the 2.8 V cutoff", ""]
    lines.append(f"Source: the drive files of every folder, rows as stored. A row is *at the cutoff* when "
                 f"0 < V <= {LOW_LIMIT_V} V. *Earliest*: the smallest Time of such a row in any of the folder's files.")
    lines.append("")
    lines.append("| folder | drive files with current | files with rows at the cutoff | rows at the cutoff "
                 "| earliest (s), file |")
    lines.append("|---|---|---|---|---|")
    for folder in folders:
        files = [r for r in drive_records(records, folder) if r["has_current"]]
        hit = [r for r in files if r["low_limit_rows"] > 0]
        earliest = min(hit, key=lambda r: r["low_limit_first_s"]) if hit else None
        earliest_text = f"{fmt(earliest['low_limit_first_s'], 1)}, {label(earliest)}" if earliest else "none"
        lines.append(f"| {folder} | {len(files)} | {len(hit)} | {sum(r['low_limit_rows'] for r in hit)} "
                     f"| {earliest_text} |")
    lines.append("")
    return lines


def section_shared_segments(records):
    """Extra 18: where the 40 degC HWFET current reappears inside the 25 degC tuning cycle (Mix 1)."""
    hwfet = find_record(records, "40degC", "556_HWFET")
    mix = find_record(records, "25degC", "551_Mixed1")
    hwfet_data = rawio.load_mat(hwfet["path"])
    mix_data = rawio.load_mat(mix["path"])
    hwfet_rows = rows_used(hwfet, hwfet_data)
    mix_rows = rows_used(mix, mix_data)
    hwfet_t = hwfet_data["Time"][hwfet_rows]
    pattern = hwfet_data["Current"][hwfet_rows][hwfet_t - hwfet_t[0] < HWFET_SECONDS]
    signal = mix_data["Current"][mix_rows]
    mix_t = mix_data["Time"][mix_rows]

    # Pearson correlation of the pattern with every window of the same number of rows in the mix.
    n = len(pattern)
    pattern_centred = pattern - pattern.mean()
    numerator = np.correlate(signal, pattern_centred, mode="valid")
    sums = np.concatenate(([0.0], np.cumsum(signal)))
    squares = np.concatenate(([0.0], np.cumsum(signal ** 2)))
    window_sum = sums[n:] - sums[:-n]
    window_var = squares[n:] - squares[:-n] - window_sum ** 2 / n
    correlation = numerator / np.sqrt(np.maximum(window_var, 1e-12) * np.sum(pattern_centred ** 2))

    matches = []
    for first, last in runs_of(correlation >= MATCH_CORRELATION):
        best = first + int(np.argmax(correlation[first:last + 1]))
        matches.append((best, float(correlation[best])))
    lines = ["## 18. A standard cycle inside a mix", ""]
    lines.append(f"Source: {label(hwfet)} and {label(mix)}, rows used. The current of the first "
                 f"{fmt(HWFET_SECONDS, 0)} s of the HWFET file ({n} rows) is correlated (Pearson) with every window "
                 "of the same number of rows of the mix (rows matched by position; both log at about 0.1 s).")
    lines.append("")
    lines.append(f"- **Windows with correlation >= {MATCH_CORRELATION}:** " + ("; ".join(
        f"starting at Time {fmt(mix_t[k], 1)} s of the mix, correlation {fmt(value, 4)}" for k, value in matches)
        if matches else "none") + f". Highest correlation anywhere: {fmt(float(np.max(correlation)), 4)}.")
    lines.append("")
    return lines


def section_sign(records):
    """Extra 19: the cycler's sign on a known discharge step and a known charge step."""
    lines = ["## 19. Sign of current on known steps", ""]
    cap = find_record(records, "25degC", "551_Cap")
    charge = find_record(records, "25degC", "551_Charge2")
    lines.append(f"Source: {label(cap)} and {label(charge)}, rows as stored. The row before and the row of the first "
                 f"step change of current (|I| crossing {fmt(1000 * FLOW_CURRENT_A, 0)} mA).")
    lines.append("")
    for r in (cap, charge):
        data = rawio.load_mat(r["path"])
        i = data["Current"]
        k = int(np.where(np.abs(i) > FLOW_CURRENT_A)[0][0])
        lines.append(f"- {label(r)}: at Time {fmt(data['Time'][k], 3)} s (row {k}) Current goes from "
                     f"{fmt(i[k - 1], 4)} to {fmt(i[k], 4)} A and Voltage from {fmt(data['Voltage'][k - 1], 4)} to "
                     f"{fmt(data['Voltage'][k], 4)} V; Ah goes from {fmt(data['Ah'][k - 1], 5)} to "
                     f"{fmt(data['Ah'][k + 1], 5)} Ah over the next row.")
    lines.append("- Discharge (voltage falls) shows as negative Current and a falling Ah counter; charge (voltage "
                 "rises) as positive Current. The project sign is I = -Current.")
    lines.append("")
    return lines
