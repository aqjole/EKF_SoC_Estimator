"""Stage S6, step 3: fit the 3RC model and check it open-loop on US06 beside the 2RC model.

Run from the repo root:  .venv/bin/python python/fit_3rc.py   (or: make fit-3rc; needs make fit)

  1. The OCV table is built as in fit_all.py, so the 3RC fits see the OCV the 2RC fits saw.
  2. The six HPPC files are fitted with the 3RC bounds of docs/decisions.md 1.21 (fit.py, model "3rc").
  3. results/fit_levels_3rc.csv holds the level fits. results/params_3rc.csv is results/params.csv with
     OCV, dOCV/dSoC and R0 unchanged, R1, tau1, R2, tau2 replaced and R3, tau3 added, each resampled
     onto the SoC grid by the rule of fit_all.py.
  4. Both models run open-loop on US06 (decisions 1.4) from their CSV tables. results/model_fit_3rc.md
     compares them, counts failed fits and time constants that end on a bound, and applies the 25 degC
     gate of S1 to the 3RC model. It also gives the ceiling of decisions 1.24: the best open-loop RMSE
     when a constant third branch from a small grid is added to the unchanged 2RC tables. Decisions 1.25
     repeats that ceiling on every drive run of experiments.evaluation_runs, pooled per temperature.
  5. results/plots/s6/params_3rc.png draws the 3RC tables (decisions 1.14).
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.fit import FIT_BOUNDS, FITTED_TABLES_3RC, fit_hppc_run, rc_voltage
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.model import Params, simulate_open_loop
from ekfsoc.plots import plot_params
from export_params import PARAMS_CSV, md_table, write_text
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, LEVEL_COLUMNS, load_ocv_inputs, resample, validate_us06


LEVELS_3RC_CSV = REPO_DIR / "results" / "fit_levels_3rc.csv"
PARAMS_3RC_CSV = REPO_DIR / "results" / "params_3rc.csv"
MODEL_FIT_3RC_MD = REPO_DIR / "results" / "model_fit_3rc.md"
PARAMS_3RC_PNG = REPO_DIR / "results" / "plots" / "s6" / "params_3rc.png"

# Columns of results/fit_levels_3rc.csv: those of fit_levels.csv with R3 and tau3 after tau1.
LEVEL_COLUMNS_3RC = LEVEL_COLUMNS[:6] + ("R3_ohm", "tau3_s") + LEVEL_COLUMNS[6:]

# A fitted time constant within this fraction of an end of its bounds counts as on the bound.
ON_BOUND_REL = 1e-3

# The grid of the ceiling diagnostic (decisions 1.24): constant R3 and tau3 added to the 2RC tables.
CEILING_R3_OHM = (0.002, 0.005, 0.01, 0.02)
CEILING_TAU3_S = (10.0, 20.0, 30.0, 50.0)

# The grid of the pooled ceiling (decisions 1.25): the grid above with larger R3 and a longer tau3 added,
# because on the grid above the -20 degC best lies on its upper edge.
POOLED_R3_OHM = CEILING_R3_OHM + (0.035, 0.05, 0.07, 0.1)
POOLED_TAU3_S = CEILING_TAU3_S + (100.0,)

# A run counts as helped by a third branch when its own best one lowers its RMSE by more than this fraction.
HELPED_FRACTION = 0.10


def build_params_3rc(level_rows):
    """results/params.csv with every fitted table but R0 taken from the 3RC level fits (decisions 1.21)."""
    fitted = {name: np.array([resample(level_rows[temp], soc_key, value_key) for temp in T_GRID_DEGC])
              for name, soc_key, value_key in FITTED_TABLES_3RC if name != "r0"}
    return replace(Params.from_csv(PARAMS_CSV), **fitted)


def on_bound(value, bounds):
    """True when a fitted time constant lies within ON_BOUND_REL of either end of its bounds."""
    return value is not None and any(abs(value - end) <= ON_BOUND_REL * end for end in bounds)


def comparison_section(results_2rc, results_3rc):
    """Lines of the open-loop comparison on US06, with the gate on the 3RC model."""
    rows = []
    for old, new in zip(results_2rc, results_3rc):
        rows.append([str(old["temp"]), f"{old['rmse_mv']:.2f}", f"{new['rmse_mv']:.2f}",
                     f"{new['rmse_mv'] - old['rmse_mv']:+.2f}", f"{old['rmse_window_mv']:.2f}",
                     f"{new['rmse_window_mv']:.2f}"])
    gate = next(result for result in results_3rc if result["temp"] == GATE_TEMP_DEGC)
    verdict = "PASS" if gate["rmse_mv"] <= GATE_RMSE_MV else "FAIL"
    lines = [
        "## Open-loop voltage error on US06, 2RC and 3RC",
        "",
        "Both models run without feedback on the US06 file of each temperature, as in `results/model_fit.md`: measured "
        "current and temperature, reference SoC, every branch voltage 0 at the first row, the tables of "
        "`results/params.csv` (2RC) and `results/params_3rc.csv` (3RC). Error = model minus measured voltage. "
        "The window columns run up to the last row with reference SoC >= 10 % (docs/model.md C14).",
        "",
    ]
    lines += md_table(["T (degC)", "2RC RMSE (mV)", "3RC RMSE (mV)", "3RC - 2RC (mV)",
                       "2RC RMSE, SoC_ref >= 10 % (mV)", "3RC RMSE, SoC_ref >= 10 % (mV)"], rows)
    lines += [
        "",
        f"Gate: the 3RC open-loop RMSE at {GATE_TEMP_DEGC} degC is {gate['rmse_mv']:.2f} mV against the sanity limit of "
        f"{GATE_RMSE_MV:.0f} mV. **{verdict}.** The limit is a bug check, not a published target.",
    ]
    return lines


def fit_section(level_rows):
    """Lines of the section on the 3RC level fits: failures, time constants on a bound, typical middle branch."""
    fast_bounds, tau2_bounds = FIT_BOUNDS["3rc"]["fast"], FIT_BOUNDS["3rc"]["tau2"]
    rows = []
    for temp in T_GRID_DEGC:
        levels = level_rows[temp]
        with_rest = [row for row in levels if row["slow_ok"] is not None]
        fitted = [row for row in levels if row["fast_ok"]]
        cells = [
            temp, len(levels), sum(not row["fast_ok"] for row in levels), sum(row["slow_ok"] is False for row in levels),
            sum(on_bound(row["tau1_s"], fast_bounds[0]) for row in levels),
            sum(on_bound(row["tau3_s"], fast_bounds[1]) for row in levels),
            sum(on_bound(row["tau2_s"], tau2_bounds) for row in with_rest),
            f"{np.median([row['tau3_s'] for row in fitted]):.1f}",
            f"{1000.0 * np.median([row['R3_ohm'] for row in fitted]):.2f}",
        ]
        rows.append([str(cell) for cell in cells])
    lines = [
        "## 3RC level fits",
        "",
        "Fit (a) gives R1, tau1, R3 and tau3 from the discharge pulses with tau1 in [0.5, 10] s and "
        "tau3 in [10, 50] s; fit (b) gives R2 and tau2 from the 1 h rest with tau2 in [50, 3600] s; "
        "R0 is that of `results/params.csv` "
        f"(docs/decisions.md 1.21). A time constant within {100 * ON_BOUND_REL:g} % of an end of its bounds counts as on "
        "the bound; tau2 is counted over the levels with a 1 h rest. Every level fit is in `results/fit_levels_3rc.csv`.",
        "",
    ]
    lines += md_table(["T (degC)", "levels", "failed fast fits", "failed slow fits", "tau1 on a bound",
                       "tau3 on a bound", "tau2 on a bound", "median tau3 (s)", "median R3 (mOhm)"], rows)
    lines += ["", "Plot: `results/plots/s6/params_3rc.png`, the seven fitted tables against SoC, as `params.png` of S1."]
    return lines


def best_added_branch(params_2rc, temp):
    """(rmse_mv, r3_ohm, tau3_s): the lowest US06 open-loop RMSE on the grid, with a third branch added to the 2RC tables.

    It is scored on the validation file itself, so it bounds from above what a middle branch adds to the
    2RC model while R1, tau1, R2 and tau2 stay as fitted; it is not a fit.
    """
    shape = params_2rc.ocv.shape
    best = None
    for tau3 in CEILING_TAU3_S:
        for r3 in CEILING_R3_OHM:
            params = replace(params_2rc, r3=np.full(shape, r3), tau3=np.full(shape, tau3))
            rmse = validate_us06(params, temp)["rmse_mv"]
            if best is None or rmse < best[0]:
                best = (rmse, r3, tau3)
    return best


def ceiling_section(results_2rc, ceilings):
    """Lines of the ceiling diagnostic: per temperature the 2RC RMSE and the best one with a third branch added."""
    rows = []
    for result, (rmse, r3, tau3) in zip(results_2rc, ceilings):
        rows.append([str(result["temp"]), f"{result['rmse_mv']:.2f}", f"{rmse:.2f}",
                     f"{rmse - result['rmse_mv']:+.2f}", f"{1000.0 * r3:g}", f"{tau3:g}"])
    r3_grid = ", ".join(f"{1000.0 * r3:g}" for r3 in CEILING_R3_OHM)
    tau3_grid = ", ".join(f"{tau3:g}" for tau3 in CEILING_TAU3_S)
    lines = [
        "## Ceiling: a third branch added to the 2RC model",
        "",
        f"A constant third branch, R3 in {{{r3_grid}}} mOhm and tau3 in {{{tau3_grid}}} s, is added to the unchanged "
        "2RC tables, and the lowest open-loop US06 RMSE is kept (docs/decisions.md 1.24). It is chosen on the "
        "validation file itself, so it bounds from above what a middle branch adds while R1, tau1, R2 and tau2 "
        "stay as fitted; it is not a fit.",
        "",
    ]
    lines += md_table(["T (degC)", "2RC RMSE (mV)", "best with a third branch (mV)", "change (mV)", "R3 (mOhm)",
                       "tau3 (s)"], rows)
    return lines


def branch_sse(error_mv, current, dt):
    """Squared-error sums in mV^2, shape (tau3, R3) over the pooled grid, of one run with a third branch added.

    error_mv is the run's 2RC open-loop error, model minus measured. A branch with constant R3 and tau3 is
    linear in its own state, so with it the model voltage falls by R3 times the voltage of a 1 Ohm branch of
    the same tau3 (Eq. 1). One 2RC simulation per run therefore serves the whole grid.
    """
    sse = np.zeros((len(POOLED_TAU3_S), len(POOLED_R3_OHM)))
    for a, tau3 in enumerate(POOLED_TAU3_S):
        unit_mv = 1000.0 * rc_voltage(current, dt, 1.0, tau3)
        for b, r3 in enumerate(POOLED_R3_OHM):
            sse[a, b] = np.sum((error_mv - r3 * unit_mv) ** 2)
    return sse


def open_loop_error_mv(params, run):
    """The open-loop error of a drive run in mV, model minus measured over the whole run (decisions 1.25)."""
    return 1000.0 * (simulate_open_loop(params, run.i, run.temp, soc_ref(run), run.dt) - run.v)


def drive_run_sse(params, spec):
    """(rows, sum of squared open-loop errors in mV^2) of one drive run: the pooled score of decisions 1.25."""
    error_mv = open_loop_error_mv(params, load_run(spec.path))
    return len(error_mv), float(np.sum(error_mv ** 2))


def drive_run_ceiling(params_2rc, spec):
    """One drive run of the pooled ceiling: its 2RC open-loop error summed for scoring, and its branch_sse grid."""
    run = load_run(spec.path)
    error_mv = open_loop_error_mv(params_2rc, run)
    return {"temp": spec.nominal_temp_degc, "cycle": spec.cycle_name, "rows": len(error_mv),
            "mean_error_mv": float(np.mean(error_mv)), "sse_2rc": float(np.sum(error_mv ** 2)),
            "sse": branch_sse(error_mv, run.i, run.dt)}


def grid_best(sse, rows):
    """(rmse_mv, r3_ohm, tau3_s) of the smallest squared-error sum on the pooled grid; ties go to the first."""
    a, b = np.unravel_index(np.argmin(sse), sse.shape)
    return float(np.sqrt(sse[a, b] / rows)), POOLED_R3_OHM[b], POOLED_TAU3_S[a]


def pooled_ceiling_sections(drive_runs):
    """Lines of the ceiling of decisions 1.25: pooled per temperature over its drive runs, then run by run."""
    pooled_rows, run_rows = [], []
    for temp in T_GRID_DEGC:
        runs = [run for run in drive_runs if run["temp"] == temp]
        helped = 0
        for run in runs:
            rmse_2rc = np.sqrt(run["sse_2rc"] / run["rows"])
            rmse, r3, tau3 = grid_best(run["sse"], run["rows"])
            helped += rmse < (1.0 - HELPED_FRACTION) * rmse_2rc
            run_rows.append([str(temp), run["cycle"], f"{rmse_2rc:.2f}", f"{run['mean_error_mv']:+.1f}", f"{rmse:.2f}",
                             f"{1000.0 * r3:g}", f"{tau3:g}"])
        rows = sum(run["rows"] for run in runs)
        rmse_2rc = np.sqrt(sum(run["sse_2rc"] for run in runs) / rows)
        rmse, r3, tau3 = grid_best(sum(run["sse"] for run in runs), rows)
        pooled_rows.append([str(temp), str(len(runs)), f"{rmse_2rc:.2f}", f"{rmse:.2f}",
                            f"{100.0 * (rmse / rmse_2rc - 1.0):+.1f}", f"{1000.0 * r3:g}", f"{tau3:g}", str(helped)])

    r3_grid = ", ".join(f"{1000.0 * r3:g}" for r3 in POOLED_R3_OHM)
    tau3_grid = ", ".join(f"{tau3:g}" for tau3 in POOLED_TAU3_S)
    lines = [
        "## Ceiling over every drive cycle",
        "",
        "The ceiling above, repeated on every run of the evaluation set and the tuning cycle and pooled per "
        f"temperature (docs/decisions.md 1.25). R3 in {{{r3_grid}}} mOhm and tau3 in {{{tau3_grid}}} s. The pooled "
        "RMSE is over all rows of a temperature's runs together, error = model minus measured voltage over the whole "
        "run, as for US06 above. Like the ceiling above it is chosen on the data it is scored on; it is not a fit. "
        f"A run is helped when its own best branch lowers its RMSE by more than {100 * HELPED_FRACTION:g} %.",
        "",
    ]
    lines += md_table(["T (degC)", "runs", "2RC pooled RMSE (mV)", "best with a third branch (mV)", "change (%)",
                       "R3 (mOhm)", "tau3 (s)", "runs helped"], pooled_rows)
    lines += [
        "",
        "## Ceiling per drive run",
        "",
        "Each run with its own best third branch on the same grid. Mean error = model minus measured voltage, "
        "averaged over the run; a positive mean is a model that drops too little voltage.",
        "",
    ]
    lines += md_table(["T (degC)", "cycle", "2RC RMSE (mV)", "mean error (mV)", "best with a third branch (mV)",
                       "R3 (mOhm)", "tau3 (s)"], run_rows)
    return lines


def model_fit_3rc_text(results_2rc, results_3rc, level_rows, ceilings, drive_runs):
    """Return the text of results/model_fit_3rc.md. Every number comes from the arguments."""
    lines = ["# Model fit, 3RC (S6)", "", "Written by `python/fit_3rc.py` (`make fit-3rc`). Do not edit by hand."]
    sections = (comparison_section(results_2rc, results_3rc), fit_section(level_rows),
                ceiling_section(results_2rc, ceilings), pooled_ceiling_sections(drive_runs))
    for section in sections:
        lines += ["", *section]
    return "\n".join(lines) + "\n"


def main():
    _, hppc_runs, _, ocv_table = load_ocv_inputs()
    level_rows = {temp: fit_hppc_run(hppc_runs[temp], ocv_table, "3rc") for temp in T_GRID_DEGC}

    rows = [row for temp in T_GRID_DEGC for row in level_rows[temp]]
    pd.DataFrame(rows, columns=LEVEL_COLUMNS_3RC).to_csv(LEVELS_3RC_CSV, index=False, float_format="%.6g",
                                                         lineterminator="\n")
    build_params_3rc(level_rows).to_csv(PARAMS_3RC_CSV)

    params_2rc = Params.from_csv(PARAMS_CSV)
    params_3rc = Params.from_csv(PARAMS_3RC_CSV)
    plot_params(pd.read_csv(LEVELS_3RC_CSV), params_3rc, PARAMS_3RC_PNG, FITTED_TABLES_3RC)

    results_2rc = [validate_us06(params_2rc, temp) for temp in T_GRID_DEGC]
    results_3rc = [validate_us06(params_3rc, temp) for temp in T_GRID_DEGC]
    for old, new in zip(results_2rc, results_3rc):
        print(f"US06 {new['temp']:>4} degC: RMSE 2RC {old['rmse_mv']:.2f} mV, 3RC {new['rmse_mv']:.2f} mV")

    ceilings = [best_added_branch(params_2rc, temp) for temp in T_GRID_DEGC]
    drive_runs = [drive_run_ceiling(params_2rc, spec) for spec in evaluation_runs(RAW_DIR)]
    write_text(MODEL_FIT_3RC_MD, model_fit_3rc_text(results_2rc, results_3rc, level_rows, ceilings, drive_runs))
    print(f"wrote {MODEL_FIT_3RC_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
