"""Stage S1 driver: build the model tables from the raw data and check them open-loop on US06.

Run from the repo root:  .venv/bin/python python/fit_all.py   (or: make fit)

  1. OCV(SoC, T) and dOCV/dSoC from the six C/20 discharge halves, corrected onto the voltages at the
     end of the HPPC rests (ocv.py, hppc.py; docs/decisions.md 1.1). The correction at every rest point
     is written to results/ocv_correction.csv.
  2. The six HPPC files are segmented and fitted level by level (hppc.py, fit.py; rules in
     docs/decisions.md 1.12), on the corrected OCV.
  3. Each level fit is resampled onto the 101-point SoC grid: linear in SoC, the first and last level
     value held beyond the measured range. R0, R1, tau1 sit at the SoC of the level's pulses,
     R2, tau2 at the SoC where the move ended.
  4. results/params.csv and results/fit_levels.csv are written, then export_params.py makes
     results/params.md (with the correction table) and the C source and header from them.
  5. The tables are read back from params.csv, so the validation uses the same 6-digit numbers as the
     C file, and the 2RC model runs open-loop on US06 at each temperature (decisions 1.4): measured
     current and temperature, reference SoC. results/model_fit.md and results/plots/s1/model_fit_<folder>.png
     report the voltage error.
  6. results/plots/s1/ocv.png, docv.png and params.png draw the three tables (plots.py; decisions 1.14).

Nothing is tuned: the validation files are not used in any fit.
"""

import numpy as np
import pandas as pd

from ekfsoc.constants import FOLDER_TEMP, RAW_DIR, REPO_DIR, SOC_GRID, T_GRID_DEGC
from ekfsoc.fit import FITTED_TABLES, fit_hppc_run
from ekfsoc.hppc import rest_points, segment_hppc
from ekfsoc.loader import find_runs, load_run, soc_ref
from ekfsoc.model import Params, simulate_2rc_open_loop
from ekfsoc.ocv import build_ocv, discharge_curve, rest_offsets
from ekfsoc.plots import plot_docv, plot_model_fit, plot_ocv, plot_params
from export_params import LEVELS_CSV, OCV_CORRECTION_CSV, PARAMS_CSV, export_params, md_table


MODEL_FIT_MD = REPO_DIR / "results" / "model_fit.md"
PLOTS_DIR = REPO_DIR / "results" / "plots" / "s1"

FOLDER_OF = {temp: folder for folder, temp in FOLDER_TEMP.items()}

# Sanity gate of the stage: the open-loop voltage RMSE at 25 degC must stay below this (mV).
GATE_TEMP_DEGC = 25
GATE_RMSE_MV = 30.0

# The evaluation window of the EKF experiments (docs/model.md C14): rows up to the last one with reference SoC at or above this.
WINDOW_MIN_SOC = 0.10

# Columns of results/fit_levels.csv, the keys of fit_hppc_run in this order.
LEVEL_COLUMNS = ("T_degC", "level", "soc_pulses", "R0_ohm", "R1_ohm", "tau1_s", "rmse_fast_mV", "n_pulses_used",
                 "soc_rest", "R2_ohm", "tau2_s", "rmse_slow_mV", "fast_ok", "slow_ok")


# --- fit and resample ----------------------------------------------------------------------------


def load_test(folder, test_type):
    """Load the one file of a test type in a temperature folder (each folder has one c20, hppc and us06)."""
    paths = find_runs(RAW_DIR, test_type=test_type, folder=folder)
    if len(paths) != 1:
        raise ValueError(f"{folder}: expected one {test_type} file, found {len(paths)}")
    return load_run(paths[0])


def count_pulses(run):
    """Count what happens to the pulses of one HPPC run (decisions 1.12).

    A discharge pulse is left out of the fits when it is cut by the limit (shorter than 9 s or at 2.8 V),
    or, if it is not cut, when the current never reaches 98 % of the command within 0.3 s. Charge pulses
    are never fitted; those cut by the 4.2 V limit are counted because decisions 1.12 asks for them.
    """
    levels = segment_hppc(run)
    pulses = [pulse for level in levels for pulse in level.pulses]
    discharge = [pulse for pulse in pulses if pulse.kind == "D"]
    charge = [pulse for pulse in pulses if pulse.kind == "C"]
    return {
        "levels": len(levels),
        "discharge": len(discharge),
        "discharge_cut": sum(pulse.cut_by_limit for pulse in discharge),
        "discharge_rule": sum(not pulse.cut_by_limit and pulse.r0_row is None for pulse in discharge),
        "charge_cut": sum(pulse.cut_by_limit for pulse in charge),
    }


def resample(level_rows, soc_key, value_key):
    """Linear interpolation of one fitted value over SoC onto SOC_GRID, end values held outside the levels.

    Levels whose fit failed have no value and are skipped. np.interp needs ascending SoC and holds the
    first and last value beyond the ends, which is the rule of decisions 1.12.
    """
    nodes = sorted((row[soc_key], row[value_key]) for row in level_rows if row[value_key] is not None)
    if not nodes:
        raise ValueError(f"no level has a fitted {value_key}")
    soc_nodes, values = zip(*nodes)
    return np.interp(SOC_GRID, soc_nodes, values)


def build_params(ocv_table, level_rows):
    """Params from the OCV table and the level fits (level_rows: temperature -> list of fit_hppc_run rows)."""
    tables = {"ocv": ocv_table.ocv, "docv": ocv_table.docv}
    for name, soc_key, value_key in FITTED_TABLES:
        tables[name] = np.array([resample(level_rows[temp], soc_key, value_key) for temp in T_GRID_DEGC])
    return Params(t_grid=T_GRID_DEGC, soc_grid=SOC_GRID, **tables)


def write_levels_csv(level_rows):
    """Write results/fit_levels.csv: one row per HPPC level, 6 significant digits, empty cell = no value."""
    rows = [row for temp in T_GRID_DEGC for row in level_rows[temp]]
    table = pd.DataFrame(rows, columns=LEVEL_COLUMNS)
    table.to_csv(LEVELS_CSV, index=False, float_format="%.6g", lineterminator="\n")


def write_ocv_correction_csv(c20_runs, rest_points_by_temp):
    """Write results/ocv_correction.csv: one row per HPPC rest point, SoC falling within a temperature (decisions 1.1)."""
    frames = []
    for temp in T_GRID_DEGC:
        soc_curve, v_curve = discharge_curve(c20_runs[temp])
        soc_rest, v_rest = np.array(rest_points_by_temp[temp]).T
        v_c20, delta = rest_offsets(soc_curve, v_curve, soc_rest, v_rest)
        frames.append(pd.DataFrame({"T_degC": temp, "soc": soc_rest, "v_rest_V": v_rest, "v_c20_V": v_c20,
                                    "delta_mV": 1000.0 * delta}))
    pd.concat(frames).to_csv(OCV_CORRECTION_CSV, index=False, float_format="%.6g", lineterminator="\n")


# --- open-loop validation ------------------------------------------------------------------------


def rms(values):
    """Root mean square of an array."""
    return float(np.sqrt(np.mean(values**2)))


def validate_us06(params, temp):
    """Run the model open-loop on the US06 file of one temperature (docs/model.md Eq. 1, 2).

    Inputs: measured current and cell temperature, reference SoC from the cycler's counter (Eq. 3).
    Returns a result dict; "error_mv" is model minus measured voltage per row, and "rmse_window_mv" is
    the RMSE over the evaluation window of C14 (information only; the gate uses "rmse_mv").
    """
    run = load_test(FOLDER_OF[temp], "us06")
    reference_soc = soc_ref(run)
    v_model = simulate_2rc_open_loop(params, run.i, run.temp, reference_soc, run.dt)
    error_mv = 1000.0 * (v_model - run.v)
    n_window = np.flatnonzero(reference_soc >= WINDOW_MIN_SOC)[-1] + 1
    return {
        "temp": temp,
        "run": run,
        "v_model": v_model,
        "error_mv": error_mv,
        "rmse_mv": rms(error_mv),
        "rmse_window_mv": rms(error_mv[:n_window]),
        "max_abs_mv": float(np.max(np.abs(error_mv))),
    }


# --- results/model_fit.md ------------------------------------------------------------------------


def model_fit_text(results, counts, level_rows, ocv_table):
    """Return the text of results/model_fit.md. Every number comes from the arguments."""
    gate = next(result for result in results if result["temp"] == GATE_TEMP_DEGC)
    gate_passed = gate["rmse_mv"] <= GATE_RMSE_MV

    validation_rows = []
    for result in results:
        run = result["run"]
        validation_rows.append([
            f"{result['temp']}", f"`{run.meta['folder']}/{run.meta['file']}`", f"{run.meta['n_rows_used']}",
            f"{run.t[-1] - run.t[0]:.1f}", f"{result['rmse_mv']:.2f}", f"{result['max_abs_mv']:.2f}",
            f"{result['rmse_window_mv']:.2f}",
        ])

    pulse_rows = []
    for temp in T_GRID_DEGC:
        count = counts[temp]
        rows = level_rows[temp]
        left_out = count["discharge_cut"] + count["discharge_rule"]
        pulse_rows.append([
            f"{temp}", f"{count['levels']}", f"{count['discharge']}", f"{count['discharge_cut']}",
            f"{count['discharge_rule']}", f"{left_out}", f"{count['discharge'] - left_out}",
            f"{count['charge_cut']}", f"{sum(not row['fast_ok'] for row in rows)}",
            f"{sum(row['slow_ok'] is False for row in rows)}",
        ])

    lines = [
        "# Model fit",
        "",
        "Written by `python/fit_all.py` (`make fit`). Do not edit by hand.",
        "",
        "## Open-loop voltage error on US06",
        "",
        "The 2RC model (docs/model.md Eq. 1 and Eq. 2) runs without any feedback on the US06 file of each "
        "temperature (docs/decisions.md 1.4). No fit uses these files.",
        "",
        "What drives the simulation:",
        "",
        "- the measured current (positive = discharge) and the measured cell temperature of every row;",
        "- the reference SoC from the cycler's Ah counter, `SoC0 - Ah_removed / Q_ref` (Eq. 3, C13), "
        "so only the voltage model is under test, not the SoC estimate;",
        "- the tables of `results/params.csv` (the numbers the C file holds), read with the clamped bilinear lookup of Eq. 4;",
        "- V1 = V2 = 0 at the first row: the model starts relaxed.",
        "",
        "Error = model voltage minus measured voltage. RMSE and max |error| run over all rows used after the loader rules, "
        "and the gate uses this RMSE (docs/decisions.md 1.1). The last column is the RMSE over the rows up to the last one with "
        "reference SoC >= 10 % (the evaluation window of the EKF experiments, docs/model.md C14), for information only: "
        "no window is chosen to pass the gate. Duration is the last Time minus the first Time of the rows used.",
        "",
    ]
    lines += md_table(["T (degC)", "file", "rows used", "duration (s)", "RMSE (mV)", "max abs error (mV)",
                       "RMSE over SoC_ref >= 10 % (mV)"], validation_rows)
    lines += [
        "",
        f"Gate: the open-loop RMSE at {GATE_TEMP_DEGC} degC is {gate['rmse_mv']:.2f} mV against the sanity limit of "
        f"{GATE_RMSE_MV:.0f} mV. **{'PASS' if gate_passed else 'FAIL'}.** The limit is a bug check, not a published target.",
        "",
        "Plots: `results/plots/s1/model_fit_<folder>.png`, measured and model voltage over time with the error below.",
        "",
        "## HPPC pulses left out of the fits",
        "",
        "The fits use discharge pulses only (docs/decisions.md 1.12). A discharge pulse is left out when it is cut by the "
        "limit (shorter than 9 s, or at 2.8 V), or, if it is not cut, when its current never reaches 98 % of the command "
        "within 0.3 s of the pulse's first row with current (the 98 % rule). Charge pulses are never fitted; "
        "the table counts those cut by the 4.2 V limit. A fit that did not converge is counted per level: "
        "the fast fit gives R0, R1 and tau1, the slow fit gives R2 and tau2 (the last level has none).",
        "",
    ]
    lines += md_table(
        ["T (degC)", "levels", "discharge pulses", "cut by limit", "98 % rule not met", "left out", "used",
         "charge pulses cut at 4.2 V", "failed fast fits", "failed slow fits"],
        pulse_rows,
    )
    lines += [
        "",
        "Plot: `results/plots/s1/params.png`, R0, R1, tau1, R2 and tau2 against SoC, the HPPC level fits (dots) and the "
        "table on the SoC grid (dashed), one colour per temperature.",
        "",
        "## OCV",
        "",
        "The OCV table is the C/20 discharge curve plus a correction onto the HPPC rest voltages "
        "(docs/decisions.md 1.1; the correction at every rest point is in `results/ocv_correction.csv`). "
        f"OCV fallback (the 25 degC curve used at every temperature): {'yes' if ocv_table.fallback_used else 'no'}. "
        f"Monotone on the measured range at {int(np.sum(ocv_table.monotone))} of {len(ocv_table.monotone)} temperatures. "
        "The valid SoC range per temperature is in `results/params.md`.",
        "",
        "Plots: `results/plots/s1/ocv.png`, the C/20 curve (dashed), the corrected OCV (solid) and the HPPC rest voltages "
        "(dots) with the correction in mV below; `results/plots/s1/docv.png`, dOCV/dSoC on the SoC grid.",
    ]
    return "\n".join(lines) + "\n"


# --- driver --------------------------------------------------------------------------------------


def main():
    c20_runs = {temp: load_test(FOLDER_OF[temp], "c20") for temp in T_GRID_DEGC}
    hppc_runs = {temp: load_test(FOLDER_OF[temp], "hppc") for temp in T_GRID_DEGC}
    rest_points_by_temp = {temp: rest_points(run, segment_hppc(run)) for temp, run in hppc_runs.items()}
    ocv_table = build_ocv(c20_runs, SOC_GRID, T_GRID_DEGC, rest_points_by_temp)

    level_rows = {temp: fit_hppc_run(hppc_runs[temp], ocv_table) for temp in T_GRID_DEGC}
    counts = {temp: count_pulses(hppc_runs[temp]) for temp in T_GRID_DEGC}

    build_params(ocv_table, level_rows).to_csv(PARAMS_CSV)
    write_levels_csv(level_rows)
    write_ocv_correction_csv(c20_runs, rest_points_by_temp)
    export_params()

    params = Params.from_csv(PARAMS_CSV)
    plot_ocv(ocv_table, pd.read_csv(OCV_CORRECTION_CSV), PLOTS_DIR / "ocv.png")
    plot_docv(params, PLOTS_DIR / "docv.png")
    plot_params(pd.read_csv(LEVELS_CSV), params, PLOTS_DIR / "params.png")

    results = [validate_us06(params, temp) for temp in T_GRID_DEGC]
    for result in results:
        plot_model_fit(result, PLOTS_DIR / f"model_fit_{FOLDER_OF[result['temp']]}.png")
        print(f"US06 {result['temp']:>4} degC: RMSE {result['rmse_mv']:.2f} mV, max |error| {result['max_abs_mv']:.2f} mV")

    with open(MODEL_FIT_MD, "w", newline="\n") as handle:
        handle.write(model_fit_text(results, counts, level_rows, ocv_table))
    print(f"wrote {MODEL_FIT_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
