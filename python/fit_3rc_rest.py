"""Stage S6, the second 3RC fit: the middle branch alone on the whole HPPC pulse train (docs/decisions.md 1.26).

Run from the repo root:  .venv/bin/python python/fit_3rc_rest.py   (or: make fit-3rc-rest; needs make fit)

  1. Every 2RC table of results/params.csv stays as it is. Per HPPC level, R3, tau3 and one offset are fitted
     on the rest rows of the level's pulse train, from 20 s after each pulse, with the model simulated from
     the start of the previous level's move (level 1: the first row of the file) with every branch at 0.
     A level with a discharge pulse cut at 2.8 V is left out.
  2. results/fit_levels_3rc_rest.csv holds the level fits. results/params_3rc_rest.csv is results/params.csv
     with R3 and tau3 added, resampled onto the SoC grid by the rule of fit_all.py.
  3. results/model_fit_3rc_rest.md reports the level fits, the levels where the v1.0 tau2 is close to the
     tau3 bound, the open-loop US06 check with the S1 gate, and the open-loop error pooled over every drive
     run next to the 2RC value and the ceiling of decisions 1.25.
  4. results/plots/s6/params_3rc_rest.png draws R3 and tau3 against SoC (decisions 1.14).
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.fit import rc_voltage, solve
from ekfsoc.hppc import segment_hppc
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.model import Params, simulate_open_loop
from ekfsoc.plots import plot_params
from export_params import PARAMS_CSV, md_table, write_text
from fit_3rc import drive_run_ceiling, grid_best, on_bound
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, load_test, resample, validate_us06


LEVELS_CSV = REPO_DIR / "results" / "fit_levels_3rc_rest.csv"
PARAMS_REST_CSV = REPO_DIR / "results" / "params_3rc_rest.csv"
REPORT_MD = REPO_DIR / "results" / "model_fit_3rc_rest.md"
PARAMS_PNG = REPO_DIR / "results" / "plots" / "s6" / "params_3rc_rest.png"
V1_LEVELS_CSV = REPO_DIR / "results" / "fit_levels.csv"

# The rules of decisions 1.26.
REST_SKIP_S = 20.0                 # cost rows start this long after the last row of a pulse
START = (0.01, 30.0, 0.0)          # R3 in Ohm, tau3 in s, offset in V
LOWER = (0.0, 10.0, -np.inf)
UPPER = (0.5, 100.0, np.inf)
TAU3_BOUNDS_S = (LOWER[1], UPPER[1])
NEAR_TAU2_S = 150.0                # a v1.0 tau2 below this lies close to the upper tau3 bound; such levels are listed

LEVEL_COLUMNS = ("T_degC", "level", "soc_pulses", "left_out_cut", "fit_ok", "R3_ohm", "tau3_s", "offset_mV",
                 "rmse_rest_mV", "n_cost_rows")
FITTED_TABLES_REST = (("r3", "soc_pulses", "R3_ohm"), ("tau3", "soc_pulses", "tau3_s"))


def fit_middle_branch(params_2rc, current, voltage, temp, soc, dt, cost):
    """R3, tau3 and the offset of one level by bounded least squares (decisions 1.26), or None if it fails.

    The arrays run from the simulation start to the end of the pulse train; `cost` marks the rows that enter
    the cost. A branch with constant R3 and tau3 is linear in its own state, so the model voltage is the 2RC
    voltage minus R3 times the voltage of a 1 Ohm branch (Eq. 1): one 2RC simulation serves every iteration.
    """
    model_2rc = simulate_open_loop(params_2rc, current, temp, soc, dt)

    def residuals(x):
        r3, tau3, offset = x
        model = model_2rc - r3 * rc_voltage(current, dt, 1.0, tau3)
        return (voltage - model - offset)[cost]  # measured minus model

    result = solve(residuals, START, LOWER, UPPER)
    if result is None:
        return None
    r3, tau3, offset = result.x
    return {"R3_ohm": float(r3), "tau3_s": float(tau3), "offset_mV": 1000.0 * float(offset),
            "rmse_rest_mV": 1000.0 * float(np.sqrt(np.mean(result.fun ** 2)))}


def fit_level(params_2rc, run, reference_soc, levels, index):
    """The row of results/fit_levels_3rc_rest.csv for levels[index] of one HPPC run."""
    level = levels[index]
    row = {"T_degC": None, "level": level.k, "soc_pulses": level.soc_pulses, "fit_ok": False, "R3_ohm": None,
           "tau3_s": None, "offset_mV": None, "rmse_rest_mV": None, "n_cost_rows": 0,
           "left_out_cut": any(pulse.kind == "D" and pulse.cut_by_limit for pulse in level.pulses)}
    if row["left_out_cut"]:
        return row

    start = 0 if index == 0 else levels[index - 1].move.start
    stop = level.move.start if level.move is not None else level.pulses[-1].rest_rows.stop
    cost = np.zeros(stop - start, dtype=bool)
    for pulse in level.pulses:
        rest = np.arange(pulse.rest_rows.start, pulse.rest_rows.stop)
        late = run.t[rest] >= run.t[pulse.rows.stop - 1] + REST_SKIP_S
        cost[rest[late] - start] = True

    rows = slice(start, stop)
    fit = fit_middle_branch(params_2rc, run.i[rows], run.v[rows], run.temp[rows], reference_soc[rows],
                            run.dt[rows], cost)
    row["n_cost_rows"] = int(cost.sum())
    if fit is not None:
        row.update(fit, fit_ok=True)
    return row


def fit_temperature(params_2rc, temp):
    """The level rows of one temperature's HPPC file."""
    run = load_test(temp, "hppc")
    reference_soc = soc_ref(run)
    levels = segment_hppc(run)
    rows = [fit_level(params_2rc, run, reference_soc, levels, index) for index in range(len(levels))]
    for row in rows:
        row["T_degC"] = temp
    return rows


def build_params_rest(params_2rc, level_rows):
    """results/params.csv with R3 and tau3 resampled from the level fits that succeeded."""
    tables = {name: np.array([resample([row for row in level_rows if row["T_degC"] == temp], soc_key, column)
                              for temp in T_GRID_DEGC])
              for name, soc_key, column in FITTED_TABLES_REST}
    return replace(params_2rc, **tables)


def level_section(level_rows):
    """Lines of the level-fit summary per temperature, and of the levels whose v1.0 tau2 is near the bound."""
    rows = []
    for temp in T_GRID_DEGC:
        levels = [row for row in level_rows if row["T_degC"] == temp]
        fitted = [row for row in levels if row["fit_ok"]]
        cells = [temp, len(levels), sum(row["left_out_cut"] for row in levels),
                 sum(not row["fit_ok"] and not row["left_out_cut"] for row in levels),
                 sum(on_bound(row["tau3_s"], (TAU3_BOUNDS_S[0],)) for row in fitted),
                 sum(on_bound(row["tau3_s"], (TAU3_BOUNDS_S[1],)) for row in fitted)]
        for column, fmt in (("R3_ohm", "{:.2f}"), ("tau3_s", "{:.1f}"), ("offset_mV", "{:+.2f}"),
                            ("rmse_rest_mV", "{:.2f}")):
            values = [row[column] * (1000.0 if column == "R3_ohm" else 1.0) for row in fitted]
            cells.append(fmt.format(np.median(values)) if values else "n/a")
        rows.append([str(cell) for cell in cells])
    lines = [
        "## Level fits",
        "",
        "Per HPPC level, R3, tau3 and one offset fitted on the rest rows of the pulse train from "
        f"{REST_SKIP_S:g} s after each pulse, every 2RC table of `results/params.csv` fixed (docs/decisions.md "
        f"1.26). R3 in [{LOWER[0]:g}, {UPPER[0]:g}] Ohm, tau3 in [{TAU3_BOUNDS_S[0]:g}, {TAU3_BOUNDS_S[1]:g}] s. "
        "Left out: levels with a discharge pulse cut at 2.8 V. A tau3 within 0.1 % of an end of its bounds counts "
        "as on the bound. Offset = measured minus model voltage, constant over the train. Every level fit is in "
        "`results/fit_levels_3rc_rest.csv`.",
        "",
    ]
    lines += md_table(["T (degC)", "levels", "left out (cut pulse)", "failed fits", "tau3 on the lower bound",
                       "tau3 on the upper bound", "median R3 (mOhm)", "median tau3 (s)", "median offset (mV)",
                       "median rest RMSE (mV)"], rows)

    v1 = pd.read_csv(V1_LEVELS_CSV)
    near = v1[v1["tau2_s"] < NEAR_TAU2_S]
    by_level = {(row["T_degC"], row["level"]): row for row in level_rows}
    near_rows = []
    for _, v1_row in near.iterrows():
        row = by_level[(int(v1_row["T_degC"]), int(v1_row["level"]))]
        fitted = row["fit_ok"]
        near_rows.append([str(int(v1_row["T_degC"])), str(int(v1_row["level"])), f"{v1_row['tau2_s']:.1f}",
                          f"{1000.0 * row['R3_ohm']:.2f}" if fitted else "n/a",
                          f"{row['tau3_s']:.1f}" if fitted else "n/a"])
    lines += ["", f"## Levels where the v1.0 tau2 is below {NEAR_TAU2_S:g} s", "",
              "There the upper tau3 bound does not keep the middle branch apart from the slow one (docs/decisions.md "
              "1.26).", ""]
    lines += md_table(["T (degC)", "level", "v1.0 tau2 (s)", "R3 (mOhm)", "tau3 (s)"], near_rows)
    return lines


def us06_section(results_2rc, results_rest):
    """Lines of the open-loop US06 comparison with the S1 gate on the second 3RC fit."""
    rows = [[str(old["temp"]), f"{old['rmse_mv']:.2f}", f"{new['rmse_mv']:.2f}", f"{new['rmse_mv'] - old['rmse_mv']:+.2f}"]
            for old, new in zip(results_2rc, results_rest)]
    gate = next(result for result in results_rest if result["temp"] == GATE_TEMP_DEGC)
    verdict = "PASS" if gate["rmse_mv"] <= GATE_RMSE_MV else "FAIL"
    lines = ["## Open-loop voltage error on US06, 2RC and second 3RC fit", "",
             "As in `results/model_fit_3rc.md`: measured current and temperature, reference SoC, every branch "
             "voltage 0 at the first row, error = model minus measured voltage over the whole run.", ""]
    lines += md_table(["T (degC)", "2RC RMSE (mV)", "second 3RC RMSE (mV)", "change (mV)"], rows)
    lines += ["", f"Gate: the second 3RC open-loop RMSE at {GATE_TEMP_DEGC} degC is {gate['rmse_mv']:.2f} mV against "
              f"the sanity limit of {GATE_RMSE_MV:.0f} mV. **{verdict}.**"]
    return lines


def drive_section(params_2rc, params_rest):
    """Lines of the open-loop error pooled over every drive run: 2RC, the ceiling of 1.25 and the second fit."""
    rows = []
    specs = evaluation_runs(RAW_DIR)
    for temp in T_GRID_DEGC:
        runs = [drive_run_ceiling(params_2rc, spec) for spec in specs if spec.nominal_temp_degc == temp]
        sse_rest = 0.0
        for spec in (spec for spec in specs if spec.nominal_temp_degc == temp):
            run = load_run(spec.path)
            error_mv = 1000.0 * (simulate_open_loop(params_rest, run.i, run.temp, soc_ref(run), run.dt) - run.v)
            sse_rest += float(np.sum(error_mv ** 2))
        n = sum(run["rows"] for run in runs)
        rmse_2rc = np.sqrt(sum(run["sse_2rc"] for run in runs) / n)
        ceiling = grid_best(sum(run["sse"] for run in runs), n)[0]
        rmse_rest = np.sqrt(sse_rest / n)
        rows.append([str(temp), str(len(runs)), f"{rmse_2rc:.2f}", f"{ceiling:.2f}", f"{rmse_rest:.2f}",
                     f"{100.0 * (rmse_rest / rmse_2rc - 1.0):+.1f}"])
    lines = ["## Open-loop error over every drive cycle", "",
             "Pooled over all rows of a temperature's runs, scored as in docs/decisions.md 1.25; the ceiling is the "
             "one of `results/model_fit_3rc.md`.", ""]
    lines += md_table(["T (degC)", "runs", "2RC pooled RMSE (mV)", "ceiling of 1.25 (mV)",
                       "second 3RC pooled RMSE (mV)", "second 3RC change (%)"], rows)
    return lines


def main():
    params_2rc = Params.from_csv(PARAMS_CSV)
    level_rows = [row for temp in T_GRID_DEGC for row in fit_temperature(params_2rc, temp)]
    pd.DataFrame(level_rows, columns=LEVEL_COLUMNS).to_csv(LEVELS_CSV, index=False, float_format="%.6g",
                                                           lineterminator="\n")
    build_params_rest(params_2rc, level_rows).to_csv(PARAMS_REST_CSV)
    params_rest = Params.from_csv(PARAMS_REST_CSV)
    plot_params(pd.read_csv(LEVELS_CSV), params_rest, PARAMS_PNG, FITTED_TABLES_REST)

    results_2rc = [validate_us06(params_2rc, temp) for temp in T_GRID_DEGC]
    results_rest = [validate_us06(params_rest, temp) for temp in T_GRID_DEGC]
    for old, new in zip(results_2rc, results_rest):
        print(f"US06 {new['temp']:>4} degC: RMSE 2RC {old['rmse_mv']:.2f} mV, second 3RC {new['rmse_mv']:.2f} mV")

    lines = ["# Model fit, second 3RC fit (S6)", "",
             "Written by `python/fit_3rc_rest.py` (`make fit-3rc-rest`). Do not edit by hand."]
    for section in (level_section(level_rows), us06_section(results_2rc, results_rest),
                    drive_section(params_2rc, params_rest)):
        lines += ["", *section]
    write_text(REPORT_MD, "\n".join(lines) + "\n")
    print(f"wrote {REPORT_MD.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
