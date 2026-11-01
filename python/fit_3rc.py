"""Stage S6, step 3: fit the 3RC model and check it open-loop on US06 beside the 2RC model.

Run from the repo root:  .venv/bin/python python/fit_3rc.py   (or: make fit-3rc; needs make fit)

  1. The OCV table is built as in fit_all.py, so the 3RC fits see the OCV the 2RC fits saw.
  2. The six HPPC files are fitted with the 3RC bounds of docs/decisions.md 1.21 (fit.py, model "3rc").
  3. results/fit_levels_3rc.csv holds the level fits. results/params_3rc.csv is results/params.csv with
     OCV, dOCV/dSoC and R0 unchanged, R1, tau1, R2, tau2 replaced and R3, tau3 added, each resampled
     onto the SoC grid by the rule of fit_all.py.
  4. Both models run open-loop on US06 (decisions 1.4) from their CSV tables. results/model_fit_3rc.md
     compares them, counts failed fits and time constants that end on a bound, and applies the 25 degC
     gate of S1 to the 3RC model.
  5. results/plots/s6/params_3rc.png draws the 3RC tables (decisions 1.14).
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from ekfsoc.constants import REPO_DIR, T_GRID_DEGC
from ekfsoc.fit import FIT_BOUNDS, FITTED_TABLES_3RC, fit_hppc_run
from ekfsoc.model import Params
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


def model_fit_3rc_text(results_2rc, results_3rc, level_rows):
    """Return the text of results/model_fit_3rc.md. Every number comes from the arguments."""
    lines = ["# Model fit, 3RC (S6)", "", "Written by `python/fit_3rc.py` (`make fit-3rc`). Do not edit by hand."]
    for section in (comparison_section(results_2rc, results_3rc), fit_section(level_rows)):
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

    write_text(MODEL_FIT_3RC_MD, model_fit_3rc_text(results_2rc, results_3rc, level_rows))
    print(f"wrote {MODEL_FIT_3RC_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
