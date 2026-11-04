"""Stage S8, step B: the charge-side R1 of the 2RC-Ic model, fitted on the HPPC charge pulses (docs/decisions.md 1.35).

Run from the repo root:  .venv/bin/python python/fit_r1_charge.py   (or: make fit-r1c; needs make fit and make fit-r1i)

  1. Per HPPC level with a successful fit (a), every charge pulse not cut by the 4.2 V limit or shorter than 9 s gets
     one window: the pulse and the first 40 s of its rest, every logged row. The slow-branch decay carried in from
     the pulses before (2RC-I model, simulated from a zero state at the level's first pulse row, current set to zero
     from the window on) is removed, and R1 is the one-line fit of decisions 1.28 with R0 and tau1 held at the
     level's discharge values. Every pulse goes to results/fit_pulses_r1c.csv.
  2. Per level, R1 is interpolated onto the charge current nodes, then resampled over SoC (decisions 1.12), into
     results/r1_charge.csv.
  3. results/model_fit_r1c.md gives the charge R1 per pulse number next to the discharge values, the pulses left out,
     and the open-loop US06 RMSE of 2RC-Ic with the S1 gate; results/plots/s8/r1_charge.png draws the tables.
"""

import numpy as np
import pandas as pd

from compare_r1i import load_params_ri
from ekfsoc.constants import REPO_DIR, T_GRID_DEGC
from ekfsoc.fit import fit_level_fast, step_r0, window
from ekfsoc.hppc import segment_hppc
from ekfsoc.loader import soc_ref
from ekfsoc.model import R1Reader, interp2, simulate_open_loop
from ekfsoc.plots import plot_r1_charge
from ekfsoc.r1_current import read_r1_charge, write_r1_table
from export_params import md_table, write_text
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, load_ocv_inputs, validate_us06
from fit_r1_current import r1_table, window_r1


PULSES_CSV = REPO_DIR / "results" / "fit_pulses_r1c.csv"
R1_CHARGE_CSV = REPO_DIR / "results" / "r1_charge.csv"
REPORT_MD = REPO_DIR / "results" / "model_fit_r1c.md"
R1_PNG = REPO_DIR / "results" / "plots" / "s8" / "r1_charge.png"

I_GRID_CHARGE_A = (0.375, 0.75, 1.5, 3.0, 6.0)  # the charge current nodes of decisions 1.35
REST_WINDOW_S = 40.0  # a charge window keeps the rest rows with t - t(first rest row) <= this
PULSE_COLUMNS = ("T_degC", "level", "soc_pulses", "pulse", "I_A", "R1_ohm", "used", "left_out", "misses_0p3s",
                 "R1_uncorrected_ohm", "R1_dt_weighted_ohm", "rmse_window_mV", "R0_level_ohm", "R0_step_ohm",
                 "tau1_level_s", "R1_level_ohm", "R1_discharge_ohm")


def charge_window_rows(run, pulse):
    """The rows of one charge window: the pulse and the rest rows with t - t(first rest row) <= REST_WINDOW_S."""
    rest_start = pulse.rest_rows.start
    stop = rest_start
    while stop < pulse.rest_rows.stop and run.t[stop] - run.t[rest_start] <= REST_WINDOW_S:
        stop += 1
    return slice(pulse.rows.start, stop)


def carried_decay(run, level, rows, params_ri):
    """V1 + V2 in V over the window rows: the free decay of the state the 2RC-I model carries into the window.

    The model runs open loop from a zero state at the level's first pulse row; from the window's first row on its
    current is zero, so its terminal voltage is OCV - V1 - V2 there (Eq. 2) and V1 + V2 = OCV - v_model.
    """
    first = level.pulses[0].rows.start
    span = slice(first, rows.stop)
    current = run.i[span].copy()
    current[rows.start - first:] = 0.0
    dt = run.dt[span].copy()
    dt[0] = 0.0
    temp = np.full(len(current), float(run.meta["nominal_temp_degc"]))
    soc = soc_ref(run)[span]
    v_model = simulate_open_loop(params_ri, current, temp, soc, dt)
    ocv_table, t_grid, soc_grid = params_ri.ocv.tolist(), params_ri.t_grid.tolist(), params_ri.soc_grid.tolist()
    ocv = np.array([interp2(ocv_table, t_grid, soc_grid, temp[0], s) for s in soc])
    return (ocv - v_model)[rows.start - first:]


def fit_level_charge(run, level, ocv_table, params_ri, temp):
    """The rows of results/fit_pulses_r1c.csv for one level: one per charge pulse, used or with its reason."""
    fast = fit_level_fast(run, level, ocv_table)
    read_discharge_r1 = R1Reader(params_ri)
    soc = soc_ref(run)
    rows = []
    for pulse in [pulse for pulse in level.pulses if pulse.kind == "C"]:
        row = {"T_degC": temp, "level": level.k, "soc_pulses": level.soc_pulses, "pulse": pulse.number,
               "I_A": abs(pulse.i_cmd), "misses_0p3s": pulse.r0_row is None, "used": False,
               "left_out": "4.2 V limit or short" if pulse.cut_by_limit else "fit (a) failed"}
        if pulse.cut_by_limit or not fast["fast_ok"]:
            rows.append(row)
            continue
        window_rows = charge_window_rows(run, pulse)
        current, dt, z = window(run, soc, window_rows, fast["R0_ohm"], ocv_table)
        corrected = z + carried_decay(run, level, window_rows, params_ri)
        r1, rmse = window_r1(current, dt, corrected, fast["tau1_s"])
        row.update(R1_ohm=r1, used=r1 > 0.0, left_out="" if r1 > 0.0 else "R1 <= 0", rmse_window_mV=rmse,
                   R1_uncorrected_ohm=window_r1(current, dt, z, fast["tau1_s"])[0],
                   R1_dt_weighted_ohm=window_r1(current, dt, corrected, fast["tau1_s"], weights=dt)[0],
                   R0_level_ohm=fast["R0_ohm"], tau1_level_s=fast["tau1_s"], R1_level_ohm=fast["R1_ohm"],
                   R0_step_ohm=np.nan if pulse.r0_row is None else step_r0(run, pulse),
                   R1_discharge_ohm=read_discharge_r1(float(temp), level.soc_pulses, abs(pulse.i_cmd)))
        rows.append(row)
    return rows


def pulse_section(pulses):
    """Lines of the per-pulse table: per temperature and pulse number, medians over the pulses in the fit."""
    used = pulses[pulses["used"]]
    rows = []
    for temp in T_GRID_DEGC:
        for number in range(1, 5):
            here = used[(used["T_degC"] == temp) & (used["pulse"] == number)]
            if here.empty:
                rows.append([str(temp), f"C{number}", "0"] + ["-"] * 9)
                continue
            mohm = lambda column: f"{1000.0 * here[column].median():.2f}"
            r0_diff = 1000.0 * (here["R0_step_ohm"] - here["R0_level_ohm"]).dropna()
            rows.append([str(temp), f"C{number}", str(len(here)), f"{here['I_A'].median():.3f}", mohm("R1_ohm"),
                         mohm("R1_uncorrected_ohm"), mohm("R1_dt_weighted_ohm"),
                         f"{r0_diff.median():+.2f} ({len(r0_diff)})" if len(r0_diff) else "-",
                         mohm("R1_level_ohm"), mohm("R1_discharge_ohm"),
                         f"{1000.0 * (here['R0_level_ohm'] + here['R1_ohm']).median():.2f}",
                         f"{1000.0 * (here['R0_level_ohm'] + here['R1_discharge_ohm']).median():.2f}"])
    lines = ["## Charge R1 per pulse", "",
             "Medians over the charge pulses in the fit, per temperature and pulse number. R1 is the fitted value "
             "(carried-in decay removed, rows unweighted); the uncorrected and dt-weighted columns are the sensitivity "
             "checks of docs/decisions.md 1.35 and do not enter the table. The fit holds R0 at the level's discharge "
             "value, so the charge R1 takes up any charge-discharge difference in R0: the step-rule column gives the "
             "charge pulse's step-rule R0 minus the level's R0, over the pulses that have one (pulses that miss the 0.3 s "
             "rule have none); the count of pulses with one is in brackets. v1.0 R1 is the level's fit (a) value; the 2RC-I discharge R1 is read from "
             "`results/r1_current.csv` at the pulse's current and the level's SoC. The R0 + R1 columns compare charge "
             "and discharge as the model reads them, both with the level's R0. Pulse numbers mix SoC levels, because "
             "the pulses in the fit differ by level.", ""]
    lines += md_table(["T (degC)", "pulse", "pulses", "median I (A)", "R1 (mOhm)", "uncorrected (mOhm)",
                       "dt-weighted (mOhm)", "step-rule R0 - level R0 (mOhm)", "v1.0 R1 (mOhm)",
                       "2RC-I discharge R1 (mOhm)", "charge R0 + R1 (mOhm)", "discharge R0 + R1 (mOhm)"], rows)
    return lines


def coverage_section(pulses):
    """Lines of the pulses left out by reason, the 0.3 s misses kept, and the SoC span of the levels in the fit."""
    rows = []
    for temp in T_GRID_DEGC:
        here = pulses[pulses["T_degC"] == temp]
        used = here[here["used"]]
        count = lambda reason: str(int((here["left_out"] == reason).sum()))
        rows.append([str(temp), str(len(here)), str(len(used)), count("4.2 V limit or short"), count("fit (a) failed"),
                     count("R1 <= 0"), str(int(used["misses_0p3s"].sum())),
                     f"{used['soc_pulses'].min():.2f} to {used['soc_pulses'].max():.2f}"])
    lines = ["## Pulses in the fit", "",
             "Charge pulses per temperature: in the fit, and left out by reason. Pulses that miss the 0.3 s rule of "
             "decisions 1.12 are kept (1.35). Beyond the SoC span of the levels with a pulse in the fit, the table holds "
             "the end values.", ""]
    lines += md_table(["T (degC)", "charge pulses", "in the fit", "4.2 V limit or short", "fit (a) failed",
                       "R1 <= 0", "0.3 s misses kept", "SoC span of the levels"], rows)
    return lines


def us06_section(results_ri, results_rc):
    """Lines of the open-loop US06 RMSE of 2RC-I and 2RC-Ic, with the S1 gate (guard 1 of decisions 1.32)."""
    rows = [[str(old["temp"]), f"{old['rmse_mv']:.2f}", f"{new['rmse_mv']:.2f}"]
            for old, new in zip(results_ri, results_rc)]
    gate = next(result["rmse_mv"] for result in results_rc if result["temp"] == GATE_TEMP_DEGC)
    verdict = "PASS" if gate <= GATE_RMSE_MV else "FAIL"
    lines = ["## Open-loop US06", "", "Model minus measured voltage over the whole US06 run.", ""]
    lines += md_table(["T (degC)", "2RC-I (mV)", "2RC-Ic (mV)"], rows)
    lines += ["", f"S1 gate: 2RC-Ic at {GATE_TEMP_DEGC} degC {gate:.4f} mV against {GATE_RMSE_MV:.0f} mV. "
                  f"**{verdict}.**"]
    return lines


def main():
    _, hppc_runs, _, ocv_table = load_ocv_inputs()
    params_ri = load_params_ri()
    pulse_rows = [row for temp in T_GRID_DEGC for level in segment_hppc(hppc_runs[temp])
                  for row in fit_level_charge(hppc_runs[temp], level, ocv_table, params_ri, temp)]
    pd.DataFrame(pulse_rows, columns=PULSE_COLUMNS).to_csv(PULSES_CSV, index=False, float_format="%.6g",
                                                          lineterminator="\n")
    write_r1_table(params_ri, I_GRID_CHARGE_A, r1_table(pulse_rows, I_GRID_CHARGE_A), R1_CHARGE_CSV)
    params_rc = read_r1_charge(params_ri, R1_CHARGE_CSV)
    plot_r1_charge(params_rc, R1_PNG)

    results_ri = [validate_us06(params_ri, temp) for temp in T_GRID_DEGC]
    results_rc = [validate_us06(params_rc, temp) for temp in T_GRID_DEGC]
    pulses = pd.read_csv(PULSES_CSV, keep_default_na=False, na_values=[""])
    pulses["left_out"] = pulses["left_out"].fillna("")
    lines = ["# Model fit, 2RC-Ic (S8, step B)", "",
             "Written by `python/fit_r1_charge.py` (`make fit-r1c`). Do not edit by hand.", "",
             "The charge-side R1 of the 2RC-Ic model (docs/decisions.md 1.35), read under a negative held current; "
             "the discharge side is the 2RC-I table of `results/r1_current.csv`."]
    for section in (pulse_section(pulses), coverage_section(pulses), us06_section(results_ri, results_rc)):
        lines += ["", *section]
    write_text(REPORT_MD, "\n".join(lines) + "\n")
    print(f"wrote {REPORT_MD.relative_to(REPO_DIR)}")
    print(lines[-1])


if __name__ == "__main__":
    main()
