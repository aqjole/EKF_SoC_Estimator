"""Stage S7, step 3: R1 that depends on current, the 2RC-I model (docs/decisions.md 1.28).

Run from the repo root:  .venv/bin/python python/fit_r1_current.py   (or: make fit-r1i; needs make fit)

  1. The OCV table is built as in fit_all.py. Per HPPC level, fit (a) gives R0 and tau1 (fit_level_fast); per
     usable discharge pulse, R1 is then the least-squares solution in that pulse's window of fit (a), with
     that R0 and tau1 held. Every pulse fit goes to results/fit_pulses_r1i.csv.
  2. Per level, the pulse values are interpolated linearly in current onto the nodes of I_GRID_A and held
     beyond the level's smallest and largest pulse; per node they are resampled over SoC by the rule of
     fit_all.py. The table goes to results/r1_current.csv; every other table stays that of results/params.csv.
  3. results/model_fit_r1i.md gives R1 per pulse and temperature, the open-loop US06 check with the S1 gate,
     and the open-loop error pooled over every drive run, 2RC next to 2RC-I.
  4. results/plots/s7/r1_current.png draws R1 against current per temperature (decisions 1.14).
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.fit import fit_level_fast, pulse_windows, rc_voltage
from ekfsoc.hppc import segment_hppc
from ekfsoc.model import Params
from ekfsoc.plots import plot_r1_current
from ekfsoc.r1_current import read_r1_current, write_r1_current
from export_params import PARAMS_CSV, md_table, write_text
from fit_3rc import drive_run_sse
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, load_ocv_inputs, resample, validate_us06


PULSES_CSV = REPO_DIR / "results" / "fit_pulses_r1i.csv"
R1_CURRENT_CSV = REPO_DIR / "results" / "r1_current.csv"
REPORT_MD = REPO_DIR / "results" / "model_fit_r1i.md"
R1_PNG = REPO_DIR / "results" / "plots" / "s7" / "r1_current.png"

# The current axis of decisions 1.28: the discharge pulse currents of the campaign, in A.
I_GRID_A = (0.75, 1.5, 3.0, 6.0, 12.0, 18.0)

PULSE_COLUMNS = ("T_degC", "level", "soc_pulses", "pulse", "I_A", "R1_ohm", "used", "rmse_window_mV",
                 "R0_level_ohm", "tau1_level_s", "R1_level_ohm")


def window_r1(current, dt, z, tau1):
    """(R1 in Ohm, RMSE in mV) of one window of fit (a) with tau1 held.

    z = c - R1 * u - (slow part), with u the voltage of a 1 Ohm branch (Eq. 1), so after removing the window
    means z' = -R1 * u' and R1 is the least-squares slope of one line; no iteration, no start value.
    """
    u = rc_voltage(current, dt, 1.0, tau1)
    u_centred = u - u.mean()
    z_centred = z - z.mean()
    r1 = -float(np.sum(z_centred * u_centred) / np.sum(u_centred ** 2))
    residual = z_centred + r1 * u_centred
    return r1, 1000.0 * float(np.sqrt(np.mean(residual ** 2)))


def fit_level_pulses(run, level, ocv_table, temp):
    """The rows of results/fit_pulses_r1i.csv for one level: one per usable discharge pulse."""
    fast = fit_level_fast(run, level, ocv_table)
    if not fast["fast_ok"]:
        return []
    pulses = [pulse for pulse in level.pulses if pulse.kind == "D" and pulse.usable]
    rows = []
    for pulse, (current, dt, z) in zip(pulses, pulse_windows(run, pulses, fast["R0_ohm"], ocv_table)):
        r1, rmse = window_r1(current, dt, z, fast["tau1_s"])
        rows.append({"T_degC": temp, "level": level.k, "soc_pulses": level.soc_pulses, "pulse": pulse.number,
                     "I_A": pulse.i_cmd, "R1_ohm": r1, "used": r1 > 0.0, "rmse_window_mV": rmse,
                     "R0_level_ohm": fast["R0_ohm"], "tau1_level_s": fast["tau1_s"], "R1_level_ohm": fast["R1_ohm"]})
    return rows


def level_nodes(pulse_rows):
    """R1 of one level on the current nodes: linear in current between its used pulses, held beyond them."""
    currents, values = zip(*sorted((row["I_A"], row["R1_ohm"]) for row in pulse_rows if row["used"]))
    return np.interp(I_GRID_A, currents, values)


def r1_table(pulse_rows):
    """The R1 table over (T, SoC, I), shape (n_t, n_soc, n_i), from the pulse fits."""
    slices = []
    for temp in T_GRID_DEGC:
        level_rows = []
        for k in sorted({row["level"] for row in pulse_rows if row["T_degC"] == temp}):
            rows = [row for row in pulse_rows if row["T_degC"] == temp and row["level"] == k]
            if any(row["used"] for row in rows):
                level_rows.append({"soc_pulses": rows[0]["soc_pulses"], **dict(enumerate(level_nodes(rows)))})
        slices.append(np.stack([resample(level_rows, "soc_pulses", q) for q in range(len(I_GRID_A))], axis=1))
    return np.array(slices)


def pulse_section(pulses):
    """Lines of the R1-per-pulse table: per temperature the median current and R1 of D1 to D4."""
    rows = []
    for temp in T_GRID_DEGC:
        here = pulses[pulses["T_degC"] == temp]
        used = here[here["used"]]
        cells = [str(temp), f"{1000.0 * here.groupby('level')['R1_level_ohm'].first().median():.2f}"]
        for number in (1, 2, 3, 4):
            of_pulse = used[used["pulse"] == number]
            cells += [f"{of_pulse['I_A'].median():.2f}", f"{1000.0 * of_pulse['R1_ohm'].median():.2f}"]
        cells += [str(len(used)), str(len(here) - len(used))]
        rows.append(cells)
    lines = [
        "## R1 per pulse",
        "",
        "Per usable HPPC discharge pulse, R1 in the window of fit (a) (the pulse and its 40 s rest, one free constant) "
        "with R0 and tau1 held at the level's fit (a) values (docs/decisions.md 1.28). Medians over the levels; "
        "v1.0 R1 is the level fit of S1. D1 is the smallest current and also the only pulse that follows the move and "
        "its 1 h rest, so a current effect and a history effect on D1 cannot be told apart. Left out: pulses with "
        "R1 at or below 0. Every pulse fit is in `results/fit_pulses_r1i.csv`.",
        "",
    ]
    header = ["T (degC)", "v1.0 R1 (mOhm)"]
    for number in (1, 2, 3, 4):
        header += [f"D{number} I (A)", f"D{number} R1 (mOhm)"]
    lines += md_table(header + ["pulses used", "left out"], rows)
    return lines


def us06_section(results_2rc, results_ri):
    """Lines of the open-loop US06 comparison with the S1 gate on the 2RC-I model."""
    rows = [[str(old["temp"]), f"{old['rmse_mv']:.2f}", f"{new['rmse_mv']:.2f}", f"{new['rmse_mv'] - old['rmse_mv']:+.2f}"]
            for old, new in zip(results_2rc, results_ri)]
    gate = next(result for result in results_ri if result["temp"] == GATE_TEMP_DEGC)
    verdict = "PASS" if gate["rmse_mv"] <= GATE_RMSE_MV else "FAIL"
    lines = ["## Open-loop voltage error on US06, 2RC and 2RC-I", "",
             "As in `results/model_fit.md`: measured current and temperature, reference SoC, every branch voltage 0 "
             "at the first row, error = model minus measured voltage over the whole run.", ""]
    lines += md_table(["T (degC)", "2RC RMSE (mV)", "2RC-I RMSE (mV)", "change (mV)"], rows)
    lines += ["", f"Gate: the 2RC-I open-loop RMSE at {GATE_TEMP_DEGC} degC is {gate['rmse_mv']:.2f} mV against the "
              f"sanity limit of {GATE_RMSE_MV:.0f} mV. **{verdict}.**"]
    return lines


def pooled_rmse_mv(params, specs):
    """The open-loop RMSE in mV pooled over all rows of the drive runs `specs` (decisions 1.25)."""
    sums = [drive_run_sse(params, spec) for spec in specs]
    return float(np.sqrt(sum(sse for _, sse in sums) / sum(rows for rows, _ in sums)))


def drive_section(params_2rc, params_ri):
    """Lines of the open-loop error pooled over every drive run, 2RC next to 2RC-I (scored as in decisions 1.25)."""
    specs = evaluation_runs(RAW_DIR)
    rows = []
    for temp in T_GRID_DEGC:
        here = [spec for spec in specs if spec.nominal_temp_degc == temp]
        pooled = [pooled_rmse_mv(params, here) for params in (params_2rc, params_ri)]
        rows.append([str(temp), str(len(here)), f"{pooled[0]:.2f}", f"{pooled[1]:.2f}",
                     f"{100.0 * (pooled[1] / pooled[0] - 1.0):+.1f}"])
    lines = ["## Open-loop error over every drive cycle", "",
             "Pooled over all rows of a temperature's runs, scored as in docs/decisions.md 1.25.", ""]
    lines += md_table(["T (degC)", "runs", "2RC pooled RMSE (mV)", "2RC-I pooled RMSE (mV)", "change (%)"], rows)
    return lines


def main():
    _, hppc_runs, _, ocv_table = load_ocv_inputs()
    pulse_rows = [row for temp in T_GRID_DEGC for level in segment_hppc(hppc_runs[temp])
                  for row in fit_level_pulses(hppc_runs[temp], level, ocv_table, temp)]
    pd.DataFrame(pulse_rows, columns=PULSE_COLUMNS).to_csv(PULSES_CSV, index=False, float_format="%.6g",
                                                          lineterminator="\n")

    params_2rc = Params.from_csv(PARAMS_CSV)
    write_r1_current(replace(params_2rc, i_grid=I_GRID_A, r1_current=r1_table(pulse_rows)), R1_CURRENT_CSV)
    params_ri = read_r1_current(params_2rc, R1_CURRENT_CSV)
    pulses = pd.read_csv(PULSES_CSV)
    plot_r1_current(pulses, R1_PNG)

    results_2rc = [validate_us06(params_2rc, temp) for temp in T_GRID_DEGC]
    results_ri = [validate_us06(params_ri, temp) for temp in T_GRID_DEGC]
    for old, new in zip(results_2rc, results_ri):
        print(f"US06 {new['temp']:>4} degC: RMSE 2RC {old['rmse_mv']:.2f} mV, 2RC-I {new['rmse_mv']:.2f} mV")

    lines = ["# Model fit, 2RC-I (S7)", "", "Written by `python/fit_r1_current.py` (`make fit-r1i`). Do not edit by hand."]
    for section in (pulse_section(pulses), us06_section(results_2rc, results_ri), drive_section(params_2rc, params_ri)):
        lines += ["", *section]
    write_text(REPORT_MD, "\n".join(lines) + "\n")
    print(f"wrote {REPORT_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
