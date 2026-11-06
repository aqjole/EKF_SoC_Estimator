"""Stage S8, step C: R1 at and below the smallest discharge pulse, scaled on the PausCycl files (docs/decisions.md 1.37).

Run from the repo root:  .venv/bin/python python/fit_r1_low.py   (or: make fit-r1l; needs make fit and make fit-r1i)

  1. The pulse fits of the 2RC-I model are recomputed unrounded, as fit_r1_current.py computes them.
  2. The 2RC-Il table is the 2RC-I table with each level's values scaled by s(I): one factor r_T at and below the
     level's smallest pulse current, a ramp to 1 at its second pulse, 1 above. r_T = 1 at 40 and 25 degC.
  3. The four factors r_10, r_0, r_-10 and r_-20 are fitted jointly by linear least squares on the open-loop voltage
     of the four PausCycl files, every row, one free offset per file. The model voltage is affine in the factors, so
     five simulations per file give the fit exactly: all factors at 1, and each in turn at 0.
  4. The table goes to results/r1_low.csv; results/model_fit_r1l.md gives the factors, the PausCycl RMSE per file,
     the open-loop US06 RMSE with the S1 gate and the open-loop error pooled over every drive run.
"""

import sys
from dataclasses import replace

import numpy as np

from compare_r1i import load_params_ri
from ekfsoc.constants import RAW_DIR, REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import evaluation_runs
from ekfsoc.hppc import segment_hppc
from ekfsoc.loader import soc_ref
from ekfsoc.model import Params, simulate_open_loop
from ekfsoc.r1_current import read_r1_current, write_r1_table
from export_params import PARAMS_CSV, md_table, write_text
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, load_ocv_inputs, load_test, validate_us06
from fit_r1_current import I_GRID_A, R1_CURRENT_CSV, fit_level_pulses, level_nodes, pooled_rmse_mv, r1_table


R1_LOW_CSV = REPO_DIR / "results" / "r1_low.csv"
REPORT_MD = REPO_DIR / "results" / "model_fit_r1l.md"

FIT_TEMPS_DEGC = (10, 0, -10, -20)  # the temperatures with a usable PausCycl file (decisions 1.37)
FACTOR_LIMITS = (0.0, 2.0)  # a fitted factor outside (low, high] is a failed fit


def scaled_level_nodes(factors):
    """level_values for r1_table: a level's R1 on the nodes (level_nodes of 1.28) times s(I) of decisions 1.37.

    s = r_T at and below the level's smallest pulse current in the fit, linear in current to 1 at its second pulse,
    1 above; a level with one pulse in the fit is scaled by r_T at every current. factors maps a temperature to r_T;
    a temperature without one keeps r_T = 1.
    """
    def level_values(pulse_rows, nodes):
        currents = sorted(row["I_A"] for row in pulse_rows if row["used"])
        factor = factors.get(pulse_rows[0]["T_degC"], 1.0)
        if len(currents) == 1:
            scale = np.full(len(nodes), factor)
        else:
            scale = np.interp(nodes, currents[:2], [factor, 1.0])
        return level_nodes(pulse_rows, nodes) * scale
    return level_values


def low_params(params_2rc, pulse_rows, factors):
    """The 2RC-Il tables with the unrounded R1 table of these factors."""
    table = r1_table(pulse_rows, I_GRID_A, scaled_level_nodes(factors))
    return replace(params_2rc, i_grid=np.array(I_GRID_A), r1_current=table)


def fit_factors(params_2rc, pulse_rows, runs):
    """(factors, offsets in V) by the joint linear least squares of decisions 1.37 on the PausCycl runs.

    With s_T = 1 - r_T the model voltage is v_base + sum_T s_T * a_T, where a_T = v(r_T = 0) - v_base, so the
    unknowns are the s_T and one offset per run, and the fit is a single linear least-squares solve.
    """
    ones = {temp: 1.0 for temp in FIT_TEMPS_DEGC}
    variants = [low_params(params_2rc, pulse_rows, ones)]
    variants += [low_params(params_2rc, pulse_rows, {**ones, temp: 0.0}) for temp in FIT_TEMPS_DEGC]
    blocks, targets = [], []
    for index, run in enumerate(runs):
        voltages = [simulate_open_loop(params, run.i, run.temp, soc_ref(run), run.dt) for params in variants]
        offsets = np.zeros((len(run.v), len(runs)))
        offsets[:, index] = 1.0
        blocks.append(np.column_stack([voltage - voltages[0] for voltage in voltages[1:]] + [offsets]))
        targets.append(run.v - voltages[0])
    solution, *_ = np.linalg.lstsq(np.vstack(blocks), np.concatenate(targets), rcond=None)
    factors = {temp: 1.0 - float(s) for temp, s in zip(FIT_TEMPS_DEGC, solution)}
    return factors, solution[len(FIT_TEMPS_DEGC):]


def own_offset_rmse_mv(params, run):
    """Open-loop RMSE in mV over a run, model minus measured, after removing its mean (the run's own offset)."""
    error = simulate_open_loop(params, run.i, run.temp, soc_ref(run), run.dt) - run.v
    return 1000.0 * float(np.sqrt(np.mean((error - error.mean()) ** 2)))


def factor_section(factors, offsets, runs, params_ri, params_rl):
    """Lines of the fitted factors and the PausCycl RMSE per file."""
    rows = [[str(temp), f"{factors[temp]:.4f}", f"{1000.0 * offset:+.1f}", f"{own_offset_rmse_mv(params_ri, run):.2f}",
             f"{own_offset_rmse_mv(params_rl, run):.2f}"]
            for temp, offset, run in zip(FIT_TEMPS_DEGC, offsets, runs)]
    lines = ["## Factors", "",
             "r_T scales R1 at and below each level's smallest discharge pulse current and ramps back to 1 at its second "
             "pulse (docs/decisions.md 1.37); r_T = 1 at 40 and 25 degC. The four factors are fitted jointly on the "
             "PausCycl files, with one free offset per file. The RMSE columns are the open-loop voltage error over the "
             "whole file, each model with its own mean removed; they decide nothing.", ""]
    lines += md_table(["T (degC)", "r_T", "fit offset (mV)", "PausCycl 2RC-I (mV)", "PausCycl 2RC-Il (mV)"], rows)
    return lines


def us06_section(results_ri, results_rl):
    """Lines of the open-loop US06 RMSE of 2RC-I and 2RC-Il, with the S1 gate (guard 1 of decisions 1.32)."""
    rows = [[str(old["temp"]), f"{old['rmse_mv']:.2f}", f"{new['rmse_mv']:.2f}"]
            for old, new in zip(results_ri, results_rl)]
    gate = next(result["rmse_mv"] for result in results_rl if result["temp"] == GATE_TEMP_DEGC)
    verdict = "PASS" if gate <= GATE_RMSE_MV else "FAIL"
    lines = ["## Open-loop US06", "", "Model minus measured voltage over the whole US06 run.", ""]
    lines += md_table(["T (degC)", "2RC-I (mV)", "2RC-Il (mV)"], rows)
    lines += ["", f"S1 gate: 2RC-Il at {GATE_TEMP_DEGC} degC {gate:.4f} mV against {GATE_RMSE_MV:.0f} mV. "
                  f"**{verdict}.**"]
    return lines


def drive_section(params_ri, params_rl):
    """Lines of the open-loop error pooled over every drive run, 2RC-I next to 2RC-Il (scored as in decisions 1.25)."""
    specs = evaluation_runs(RAW_DIR)
    rows = []
    for temp in T_GRID_DEGC:
        here = [spec for spec in specs if spec.nominal_temp_degc == temp]
        pooled = [pooled_rmse_mv(params, here) for params in (params_ri, params_rl)]
        rows.append([str(temp), str(len(here)), f"{pooled[0]:.2f}", f"{pooled[1]:.2f}",
                     f"{100.0 * (pooled[1] / pooled[0] - 1.0):+.1f}"])
    lines = ["## Open-loop error over every drive cycle", "",
             "Pooled over all rows of a temperature's runs, scored as in docs/decisions.md 1.25.", ""]
    lines += md_table(["T (degC)", "runs", "2RC-I pooled RMSE (mV)", "2RC-Il pooled RMSE (mV)", "change (%)"], rows)
    return lines


def unchanged_slices(params_ri, params_rl):
    """True if the 40 and 25 degC slices of the 2RC-Il table equal those of the 2RC-I table exactly (decisions 1.37)."""
    rows = [list(params_ri.t_grid).index(temp) for temp in T_GRID_DEGC if temp not in FIT_TEMPS_DEGC]
    return bool(np.array_equal(params_ri.r1_current[rows], params_rl.r1_current[rows]))


def main():
    _, hppc_runs, _, ocv_table = load_ocv_inputs()
    pulse_rows = [row for temp in T_GRID_DEGC for level in segment_hppc(hppc_runs[temp])
                  for row in fit_level_pulses(hppc_runs[temp], level, ocv_table, temp)]
    params_2rc = Params.from_csv(PARAMS_CSV)
    runs = [load_test(temp, "pauscycl") for temp in FIT_TEMPS_DEGC]
    factors, offsets = fit_factors(params_2rc, pulse_rows, runs)
    for temp in FIT_TEMPS_DEGC:
        print(f"r at {temp:>4} degC: {factors[temp]:.4f}")

    header = ["# Model fit, 2RC-Il (S8, step C)", "",
              "Written by `python/fit_r1_low.py` (`make fit-r1l`). Do not edit by hand.", "",
              "The R1 table of the 2RC-Il model (docs/decisions.md 1.37): the 2RC-I table of `results/r1_current.csv` "
              "scaled at low current by factors fitted on the PausCycl files, which are not in the evaluation set."]
    failed = [temp for temp, factor in factors.items() if not FACTOR_LIMITS[0] < factor <= FACTOR_LIMITS[1]]
    if failed:
        lines = header + ["", f"**Failed fit:** factors outside ({FACTOR_LIMITS[0]:g}, {FACTOR_LIMITS[1]:g}] at "
                          + ", ".join(f"{temp} degC ({factors[temp]:.4f})" for temp in failed)
                          + ". No table is written and the evaluation does not run (1.37)."]
        write_text(REPORT_MD, "\n".join(lines) + "\n")
        sys.exit(f"fit_r1_low: failed fit at {failed}")

    write_r1_table(params_2rc, I_GRID_A, low_params(params_2rc, pulse_rows, factors).r1_current, R1_LOW_CSV)
    params_ri = load_params_ri()
    params_rl = read_r1_current(params_2rc, R1_LOW_CSV)
    results_ri = [validate_us06(params_ri, temp) for temp in T_GRID_DEGC]
    results_rl = [validate_us06(params_rl, temp) for temp in T_GRID_DEGC]
    same = "yes" if unchanged_slices(params_ri, params_rl) else "NO"
    lines = header + ["", f"The 40 and 25 degC slices equal those of `results/r1_current.csv`: {same}."]
    for section in (factor_section(factors, offsets, runs, params_ri, params_rl), us06_section(results_ri, results_rl),
                    drive_section(params_ri, params_rl)):
        lines += ["", *section]
    write_text(REPORT_MD, "\n".join(lines) + "\n")
    print(f"wrote {R1_LOW_CSV.relative_to(REPO_DIR)} and {REPORT_MD.relative_to(REPO_DIR)}")
    print(next(line for line in lines if line.startswith("S1 gate")))


if __name__ == "__main__":
    main()
