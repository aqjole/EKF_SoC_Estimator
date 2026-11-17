"""Sections 10 to 12 of results/s0/data_checks.md: the HPPC test, the C/20 test and the Q_ref row."""

import numpy as np

from dataset.checks_hppc import position_median
from dataset.checks_rules import (CV_START_V, FIRST_SAMPLE_FRACTION, FIRST_SAMPLE_WINDOW_S, FULL_PULSE_S,
                                  RELAX_WINDOW_S, SHORT_PULSE_S, fmt_range, label, stored_rows_text)
from dataset.common import FLOW_CURRENT_A, fmt
from ekfsoc.hppc import HIGH_LIMIT_V, LOW_LIMIT_V, PULSE_MAX_S


def section_hppc(folders, hppc):
    """Section 10: HPPC structure, currents, rests, logging, limits, first-sample rule, relaxation, resets."""
    lines = ["## 10. HPPC structure", ""]
    lines.append("Source: the six HPPC files (`*_HPPC_*.mat`, one per folder), rows used (legend). A *pulse* is a "
                 f"current step (|I| > {fmt(1000 * FLOW_CURRENT_A, 0)} mA) of at most {PULSE_MAX_S:.0f} s; a *move* is "
                 "a longer discharge before the final recharge; a *level* is the group of pulses between two moves. "
                 "Within a level the discharge pulses are D1 to D4 and the charge pulses C1 to C4, in the order "
                 "they run (D1, C1, D2, C2, ...). Durations run from a step's first row to the first row after it. "
                 "Currents are in the cycler's sign.")
    lines.append("")
    lines.append("| folder | file | levels | D pulses | C pulses | moves | move current, median (A) "
                 "| counter at the end of each move (Ah) | V at the end of the last move (V) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for folder in folders:
        h = hppc[folder]
        n_d = sum(1 for p in h["pulses"] if p["kind"] == -1)
        n_c = sum(1 for p in h["pulses"] if p["kind"] == 1)
        moves = h["moves"]
        lines.append(f"| {folder} | {label(h['record'])} | {h['levels']} | {n_d} | {n_c} | {len(moves)} "
                     f"| {fmt(np.median([m['median_a'] for m in moves]), 4)} "
                     f"| {', '.join(fmt(m['end_ah'], 4) for m in moves)} | {fmt(moves[-1]['end_v'], 4)} |")
    lines.append("")
    lines.append("Pulse currents: median command current (the median current over a pulse) of the full-length "
                 f"pulses at each position, in A. A pulse is full-length when it lasts at least {FULL_PULSE_S} s and "
                 "reaches neither 2.8 V nor 4.2 V.")
    lines.append("")
    positions = ("D1", "D2", "D3", "D4", "C1", "C2", "C3", "C4")
    lines.append("| folder | " + " | ".join(positions) + " | full-length pulses | full-length duration, median (s) |")
    lines.append("|---" * (len(positions) + 3) + "|")
    for folder in folders:
        h = hppc[folder]
        full = [p for p in h["pulses"] if p["full"]]
        lines.append(f"| {folder} | " + " | ".join(fmt(position_median(h, pos), 4) for pos in positions) +
                     f" | {len(full)} of {len(h['pulses'])} | {fmt(np.median([p['duration_s'] for p in full]), 3)} |")
    lines.append("")
    lines.append("Rest lengths (s), min / median / max. *1 h rests*: the rests after a move that lead into the "
                 "next level's pulses; their length is the spec's t_rest (`docs/decisions.md`). *Final rest*: the rest after the last move.")
    lines.append("")
    lines.append("| folder | after D pulses | after C pulses | 1 h rests | final rest |")
    lines.append("|---|---|---|---|---|")

    def three(values):
        return (f"{fmt(min(values), 3)} / {fmt(np.median(values), 3)} / {fmt(max(values), 3)}"
                if values else "none")

    for folder in folders:
        h = hppc[folder]
        lines.append(f"| {folder} | {three(h['d_rest_s'])} | {three(h['c_rest_s'])} | {three(h['hour_rest_s'])} "
                     f"| {three(h['final_rest_s'])} |")
    lines.append("")
    lines.append("Logging inside the rests: the interval used and the elapsed time (from the rest's first row) up "
                 "to which it is used, ending at the next pulse's first row; the most common pattern and how many "
                 "rests follow it. *D pulse + rest*: every step from a discharge pulse's first row to the end of "
                 "its 40 s rest.")
    lines.append("")
    lines.append("| folder | D pulse + rest: dt median / 99th percentile / max (s) | rests after D pulses "
                 "| rests after C pulses | 1 h rests | final rest |")
    lines.append("|---|---|---|---|---|---|")
    for folder in folders:
        h = hppc[folder]
        steps = h["pulse_steps"]
        lines.append(f"| {folder} | {fmt(np.median(steps), 3)} / {fmt(np.percentile(steps, 99), 3)} / "
                     f"{fmt(np.max(steps), 3)} | {h['d_rest_pattern']} | {h['c_rest_pattern']} "
                     f"| {h['hour_rest_pattern']} | {h['final_rest_pattern']} |")
    lines.append("")
    lines.append(f"Voltage limits and the R0 rule. *At 2.8 V*: a D pulse with a row at or below {LOW_LIMIT_V} V "
                 f"(in brackets: how many of them end before {SHORT_PULSE_S} s). *At 4.2 V*: a C pulse with a row at or "
                 f"above {HIGH_LIMIT_V} V. *First row*: the D pulse's first row reaches "
                 f"{fmt(100 * FIRST_SAMPLE_FRACTION, 0)} % of its command current. *Within 0.3 s*: the first row that "
                 f"reaches it comes at most {FIRST_SAMPLE_WINDOW_S} s after the reference, counted either from the "
                 "last row before the pulse (the step happened after it) or from the pulse's first row (the step "
                 "happened before it); the true step time lies between the two. *Usable for R0*: within 0.3 s of the "
                 "pulse's first row with current (the rule fixed for S1; the column counted from the last row before "
                 "is the stricter alternative, shown for information) and not at 2.8 V. "
                 "*Residual relaxation*: V at the last row of a rest "
                 f"minus V {fmt(RELAX_WINDOW_S, 0)} s earlier (interpolated), in mV.")
    lines.append("")
    lines.append("| folder | D pulses | D at 2.8 V | C pulses at 4.2 V | D first row >= 98 % "
                 "| D within 0.3 s of the last row before | D within 0.3 s of the first pulse row "
                 "| latest time to 98 %, from the last row before / from the first pulse row (s) | D usable for R0 "
                 "| 1 h rests: relaxation median / max (mV) | final rest relaxation (mV) |")
    lines.append("|---" * 11 + "|")
    late_notes = []
    for folder in folders:
        h = hppc[folder]
        d_pulses = [p for p in h["pulses"] if p["kind"] == -1]
        c_pulses = [p for p in h["pulses"] if p["kind"] == 1]
        low = [p for p in d_pulses if p["low_limited"]]
        short = [p for p in low if p["duration_s"] < SHORT_PULSE_S]
        first_ok = [p for p in d_pulses if p["first_sample_ok"]]
        within_before = [p for p in d_pulses if p["reach_s"] <= FIRST_SAMPLE_WINDOW_S]
        within_first = [p for p in d_pulses if p["reach_from_first_s"] <= FIRST_SAMPLE_WINDOW_S]
        usable = [p for p in within_first if not p["low_limited"]]
        not_low = [p for p in d_pulses if not p["low_limited"]]
        relax = h["relax_mv"]
        final = h["final_relax_mv"]
        n_d = len(d_pulses)
        lines.append(f"| {folder} | {n_d} | {len(low)} ({len(short)}) "
                     f"| {sum(1 for p in c_pulses if p['high_limited'])} "
                     f"| {len(first_ok)} ({fmt(100.0 * len(first_ok) / n_d, 1)} %) "
                     f"| {len(within_before)} ({fmt(100.0 * len(within_before) / n_d, 1)} %) "
                     f"| {len(within_first)} ({fmt(100.0 * len(within_first) / n_d, 1)} %) "
                     f"| {fmt(max(p['reach_s'] for p in not_low), 3)} / "
                     f"{fmt(max(p['reach_from_first_s'] for p in not_low), 3)} "
                     f"| {len(usable)} | {fmt(np.median(relax), 2)} / {fmt(max(relax), 2)} "
                     f"| {', '.join(fmt(x, 2) for x in final) if final else 'none'} |")
        late = [p for p in d_pulses if not p["first_sample_ok"]]
        if late:
            positions = sorted(set(p["position"] for p in late))
            late_notes.append(
                f"{folder}: {len(late)} D pulses ({', '.join(positions)}, command "
                f"{fmt_range([p['command_a'] for p in late], 4)} A, levels "
                f"{stored_rows_text(sorted(p['level'] for p in late))}) reach 98 % on pulse row "
                f"{fmt_range([p['reach_row'] for p in late], 0)}, {fmt_range([p['reach_s'] for p in late], 3)} s after "
                f"the last row before the pulse ({fmt_range([p['reach_from_first_s'] for p in late], 3)} s after the "
                "pulse's first row)")
    lines.append("")
    lines.append("- **D pulses whose first row is below 98 % of the command:** " +
                 ("; ".join(late_notes) if late_notes else "none") + ".")
    lines.append("")
    lines.append("Ah counter resets inside the HPPC files (rows as stored; the reset rule of section 16) and the "
                 "in-file recharge after the pulse train:")
    lines.append("")
    lines.append("| folder | counter resets: row (Time, h) | recharge starts: row (Time, h) "
                 "| recharge CC current, median (A) | rows in the file |")
    lines.append("|---|---|---|---|---|")
    for folder in folders:
        h = hppc[folder]
        resets = ", ".join(f"{row} ({fmt(time_s / 3600.0, 2)} h)" for row, time_s in h["resets"]) or "none"
        recharge = (f"{h['recharge_row']} ({fmt(h['recharge_time_s'] / 3600.0, 2)} h)"
                    if h["recharge_row"] is not None else "none")
        lines.append(f"| {folder} | {resets} | {recharge} | {fmt(h['recharge_cc_a'], 4)} | {h['record']['n_rows']} |")
    lines.append("")
    return lines


def section_c20(folders, c20):
    """Section 11: C/20 discharge and charge halves per folder."""
    lines = ["## 11. C/20 tests", ""]
    lines.append("Source: the six C20DisCh files (`*_C20DisCh_*.mat`), rows used (legend). *Discharge half*: the "
                 f"longest run of rows with I < -{fmt(1000 * FLOW_CURRENT_A, 0)} mA; Ah removed = -Ah, counted from "
                 "the counter's zero at the step start (the file opens one 60 s interval after it). *Charge half*: "
                 f"from the first row after the discharge with I > +{fmt(1000 * FLOW_CURRENT_A, 0)} mA to the last row "
                 f"with I > 0 (the CV cutoff); CV starts at the first charge row at or above {CV_START_V} V. Ah "
                 "returned = counter at the last charge row minus counter at the last discharge row. Durations are "
                 "differences of logged Times; at 60 s logging each boundary is known to within 60 s. Rest = Time "
                 "of the first charge row minus Time of the last discharge row, or of the first rest row after it. "
                 "End-of-discharge SoC = 1 - Ah removed / Q_ref. Currents in the cycler's sign.")
    lines.append("")
    lines.append("| folder | file | discharge I, median (A) | charge CC I, median (A) | CV voltage, median (V) "
                 "| cutoff I (A) | CC time (s) | CV time (s) | rest between halves, from the last discharge row / "
                 "from the first rest row (s) | Ah removed (Ah) "
                 "| Ah returned (Ah) | returned / removed | end-of-discharge SoC (%) | cell T discharge, min / max (degC) "
                 "| cell T charge, min / max (degC) |")
    lines.append("|---" * 15 + "|")
    for folder in folders:
        c = c20[folder]
        lines.append(f"| {folder} | {label(c['record'])} | {fmt(c['dis_median_a'], 5)} | {fmt(c['cc_median_a'], 5)} "
                     f"| {fmt(c['cv_median_v'], 5)} | {fmt(c['cutoff_a'], 5)} | {fmt(c['cc_s'], 1)} | {fmt(c['cv_s'], 1)} "
                     f"| {fmt(c['rest_s'], 1)} / {fmt(c['rest_from_first_rest_row_s'], 1)} | {fmt(c['q_dis'], 5)} "
                     f"| {fmt(c['q_chg'], 5)} "
                     f"| {fmt(c['q_chg'] / c['q_dis'], 4)} | {fmt(100.0 * c['end_soc'], 2)} "
                     f"| {fmt(c['temp_dis'][0], 2)} / {fmt(c['temp_dis'][1], 2)} "
                     f"| {fmt(c['temp_chg'][0], 2)} / {fmt(c['temp_chg'][1], 2)} |")
    lines.append("")
    lines.append("Monotonicity. Discharge half: *rises* = rows where V is above the previous row's V; *rebound* = "
                 "the largest V above the lowest V so far. Charge half, CC part only (before CV): *falls* and *dip* "
                 "likewise. *PCHIP*: a PCHIP through the raw discharge half (V against SoC = 1 - Ah removed / Q_ref), "
                 "evaluated at the points of the 101-point SoC grid (0, 0.01, ..., 1) that lie inside the measured "
                 "SoC range; *monotone* means V rises strictly from each grid point to the next.")
    lines.append("")
    lines.append("| folder | discharge rows | rises | largest rise (mV) | largest rebound (mV) | CC rows | falls "
                 "| largest fall (mV) | largest dip (mV) | PCHIP grid points (SoC range) | PCHIP monotone "
                 "| smallest PCHIP step (mV) |")
    lines.append("|---" * 12 + "|")
    for folder in folders:
        c = c20[folder]
        lines.append(f"| {folder} | {c['n_dis']} | {c['rises']} | {fmt(c['largest_rise_mv'], 2)} "
                     f"| {fmt(c['largest_rebound_mv'], 2)} | {c['n_cc']} | {c['falls']} | {fmt(c['largest_fall_mv'], 2)} "
                     f"| {fmt(c['largest_dip_mv'], 2)} | {c['pchip_points']} ({fmt(c['pchip_range'][0], 2)} to "
                     f"{fmt(c['pchip_range'][1], 2)}) | {'yes' if c['pchip_monotone'] else 'no'} "
                     f"| {fmt(c['pchip_smallest_step_mv'], 2)} |")
    lines.append("")
    lines.append("Charge-minus-discharge voltage (mV) at the same SoC, by how the charge half is placed against "
                 "the discharge half (linear interpolation in both halves):")
    lines.append("")
    lines.append("- **A**: same Ah removed. The charge half's Ah removed is the discharge's Ah removed minus the Ah "
                 "returned so far, measured from the discharge end; both halves on SoC = 1 - Ah removed / Q_ref.")
    lines.append("- **B**: each half normalised to its own Ah span: discharge at 1 - Ah removed / (Ah removed in "
                 "total), charge at Ah returned / (Ah returned in total).")
    lines.append("- **C**: charge Ah counted from the discharge end but scaled by the discharge Ah: discharge as in "
                 "B, charge at Ah returned / (Ah removed in total).")
    lines.append("- **D**: Q_ref axis with the charge half ending at SoC 1: charge at 1 - (Ah returned in total - Ah "
                 "returned so far) / Q_ref; discharge as in A.")
    lines.append("")
    lines.append("| folder | A at 50 % | B at 50 % | C at 50 % | D at 50 % | A at 80 % |")
    lines.append("|---|---|---|---|---|---|")
    for folder in folders:
        gap = c20[folder]["gap_mv"]
        lines.append(f"| {folder} | {fmt(gap['A50'], 1)} | {fmt(gap['B50'], 1)} | {fmt(gap['C50'], 1)} "
                     f"| {fmt(gap['D50'], 1)} | {fmt(gap['A80'], 1)} |")
    lines.append("")
    return lines


def section_qref(c20_25, q_ref):
    """Section 12: where Q_ref comes from."""
    r = c20_25["record"]
    first_row, last_row = c20_25["dis_rows"]
    lines = ["## 12. Q_ref provenance", ""]
    lines.append(f"Source: `data/raw/{r['folder']}/{r['file']}`.")
    lines.append("")
    lines.append(f"- **Discharge half:** rows {first_row} to {last_row}, median current "
                 f"{fmt(c20_25['dis_median_a'], 5)} A.")
    lines.append(f"- **Last discharge row:** row {last_row}, Time {fmt(c20_25['dis_end_time_s'], 2)} s "
                 f"({fmt(c20_25['dis_end_time_s'] / 3600.0, 2)} h after the first row), Voltage "
                 f"{fmt(c20_25['dis_end_v'], 5)} V, counter Ah {fmt(c20_25['dis_end_ah'], 5)} Ah.")
    lines.append(f"- **Q_ref** = -Ah at that row = **{fmt(q_ref, 5)} Ah** (counted from the counter's zero at the "
                 "step start).")
    lines.append(f"- **First row:** Ah[0] = {fmt(c20_25['ah_first'], 5)} Ah (the file opens one 60 s interval into the "
                 f"discharge). The alternative -(Ah - Ah[0]) = {fmt(-(c20_25['dis_end_ah'] - c20_25['ah_first']), 5)} Ah "
                 f"leaves out that first interval ({fmt(100.0 * c20_25['ah_first'] / -q_ref, 3)} % of Q_ref).")
    lines.append("")
    return lines
