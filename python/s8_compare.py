"""Shared parts of the S8 comparisons (docs/decisions.md 1.32 to 1.35): the open-loop numbers per model, the guards of
1.32 and the report tables, used by compare_r1d.py (step A) and compare_r1c.py (step B).

A model is named by its label ("2RC", "2RC-I", "2RC-Id", "2RC-Ic"); results maps a label to its results frame (the
columns of results/ekf_results.csv), tables maps it to compare_r1i.per_temperature of that frame.
"""

import numpy as np

from compare_r1i import verdict
from ekfsoc.constants import T_GRID_DEGC
from export_params import md_table
from fit_all import GATE_RMSE_MV, GATE_TEMP_DEGC, validate_us06
from fit_r1_current import pooled_rmse_mv


# The guards of decisions 1.32, in pp.
MAX_RUN_HIGHER_PP = 0.50
MAX_CYCLE_HIGHER_PP = 0.25
MAX_EXP4_HIGHER_PP = 0.10
# Decisions 1.35: a guard whose CSV value lies this close to its limit is recomputed from unrounded values.
RECOMPUTE_WITHIN = 1e-4
# The R1 ratio of decisions 1.32: at this current node, over the grid SoC in this range.
RATIO_CURRENT_A = 1.5
RATIO_SOC = (0.5, 0.95)
# Current bands of the open-loop US06 error (decisions 1.33), by the row's own current in A; they do not overlap.
BANDS = (("regen, I <= -0.05", lambda i: i <= -0.05),
         ("rest, abs(I) < 0.05", lambda i: np.abs(i) < 0.05),
         ("0.05 <= I < 1.5", lambda i: (i >= 0.05) & (i < 1.5)),
         ("1.5 <= I < 3", lambda i: (i >= 1.5) & (i < 3.0)),
         ("3 <= I < 6", lambda i: (i >= 3.0) & (i < 6.0)),
         ("I >= 6", lambda i: i >= 6.0))


def exp1_by_run(results):
    """Experiment-1 rows of the evaluation runs, indexed by (folder, file)."""
    rows = results[(results["experiment"] == "exp1") & ~results["is_tuning"]]
    return rows.set_index(["folder", "file"])


def us06_exp1(results):
    """Temperature to the experiment-1 SoC RMSE of the US06 run."""
    rows = exp1_by_run(results)
    return rows[rows["cycle"] == "US06"].set_index("T_degC")["rmse_pp"].to_dict()


def band_errors(us06_run):
    """Mean open-loop error in mV per current band of one validate_us06 result, the row's own current deciding."""
    current, error_mv = us06_run["run"].i, us06_run["error_mv"]
    return [float(error_mv[in_band(current)].mean()) for _, in_band in BANDS]


def r1_ratio(params_2rc, params_ri, temp):
    """Median 2RC-I R1 at RATIO_CURRENT_A over the grid SoC in RATIO_SOC, divided by the median v1.0 R1 there."""
    j = list(params_2rc.t_grid).index(temp)
    q = list(params_ri.i_grid).index(RATIO_CURRENT_A)
    soc = (params_2rc.soc_grid >= RATIO_SOC[0]) & (params_2rc.soc_grid <= RATIO_SOC[1])
    return float(np.median(params_ri.r1_current[j, soc, q]) / np.median(params_2rc.r1[j, soc]))


def open_loop_numbers(params, specs):
    """Per temperature: (US06 RMSE, pooled drive-run RMSE) per model, the US06 band errors and held-negative share,
    and the R1 ratio. params maps a label to its Params and must hold "2RC" and "2RC-I"."""
    open_loop, bands, ratios = {}, {}, {}
    for temp in T_GRID_DEGC:
        here = [spec for spec in specs if spec.nominal_temp_degc == temp]
        us06 = {model: validate_us06(params[model], temp) for model in params}
        open_loop[temp] = {model: (us06[model]["rmse_mv"], pooled_rmse_mv(params[model], here)) for model in params}
        bands[temp] = {model: band_errors(us06[model]) for model in params}
        bands[temp]["held_negative"] = float(np.mean(us06["2RC"]["run"].i[:-1] < 0.0))
        ratios[temp] = r1_ratio(params["2RC"], params["2RC-I"], temp)
    return open_loop, bands, ratios


def guard_rows(results, tables, us06_rmse, candidate, incumbent):
    """[guard, value, pass, margin] for each guard of decisions 1.32, candidate against incumbent. The margin is the
    smallest distance of a compared value from the limit it is compared with (decisions 1.35)."""
    old, new = exp1_by_run(results[incumbent]), exp1_by_run(results[candidate])
    change = new["rmse_pp"] - old["rmse_pp"]
    over = change[change > MAX_RUN_HIGHER_PP].sort_values(ascending=False)
    over_text = ", ".join(f"{new.loc[run, 'cycle']} at {new.loc[run, 'T_degC']} degC {value:+.4f}"
                          for run, value in over.items()) or "none"
    cycle_change = new.groupby("cycle")["rmse_pp"].mean() - old.groupby("cycle")["rmse_pp"].mean()
    exp1_change = np.array([tables[candidate][temp]["exp1"] - tables[incumbent][temp]["exp1"] for temp in T_GRID_DEGC])
    exp4_change = {temp: tables[candidate][temp]["exp4"] - tables[incumbent][temp]["exp4"] for temp in T_GRID_DEGC}
    fewer = [f"{experiment} at {temp} degC" for temp in T_GRID_DEGC for experiment in ("exp2", "exp3_low", "exp3_high")
             if tables[candidate][temp][experiment] < tables[incumbent][temp][experiment]]
    adopted_by_rule, lower, worse = verdict(tables[incumbent], tables[candidate])
    gate = us06_rmse[candidate][GATE_TEMP_DEGC]
    exp4_largest = max(exp4_change.values())
    return [
        ["1. S1 gate", f"US06 at {GATE_TEMP_DEGC} degC: {gate:.4f} mV (limit {GATE_RMSE_MV:.0f})", gate <= GATE_RMSE_MV,
         np.inf],
        ["2. rule of 1.22", f"lower at {lower} of 6; higher by more than 0.10 pp at "
                            f"{', '.join(f'{temp} degC' for temp in worse) or 'none'}", adopted_by_rule,
         float(min(np.abs(exp1_change).min(), np.abs(exp1_change - 0.10).min()))],
        ["3. run increase", f"largest {change.max():+.4f} pp; above the limit of +{MAX_RUN_HIGHER_PP:.2f}: {over_text}",
         change.max() <= MAX_RUN_HIGHER_PP, float(np.abs(change - MAX_RUN_HIGHER_PP).min())],
        ["4. largest cycle increase", f"{cycle_change.max():+.4f} pp ({cycle_change.idxmax()}, "
                                      f"limit +{MAX_CYCLE_HIGHER_PP:.2f})", cycle_change.max() <= MAX_CYCLE_HIGHER_PP,
         float(np.abs(cycle_change - MAX_CYCLE_HIGHER_PP).min())],
        ["5. worst run", f"{new['rmse_pp'].max():.4f} pp against {old['rmse_pp'].max():.4f} pp",
         new["rmse_pp"].max() <= old["rmse_pp"].max(), float(abs(new["rmse_pp"].max() - old["rmse_pp"].max()))],
        ["6. experiments 2 to 4", f"largest exp4 increase {exp4_largest:+.4f} pp (limit "
                                  f"+{MAX_EXP4_HIGHER_PP:.2f}); fewer reached: {', '.join(fewer) or 'none'}",
         exp4_largest <= MAX_EXP4_HIGHER_PP and not fewer,
         float(min(abs(value - MAX_EXP4_HIGHER_PP) for value in exp4_change.values()))],
    ]


def decided_guards(csv_guards, unrounded_guards):
    """The guards as decisions 1.35 decides them: the CSV value, or the unrounded one where the CSV value lies within
    RECOMPUTE_WITHIN of its limit (marked in the value text)."""
    rows = []
    for csv_row, unrounded_row in zip(csv_guards, unrounded_guards):
        if csv_row[3] < RECOMPUTE_WITHIN:
            rows.append([unrounded_row[0], f"{unrounded_row[1]} (recomputed from unrounded values)",
                         unrounded_row[2], unrounded_row[3]])
        else:
            rows.append(csv_row)
    return rows


def comparison_lines(results, tables, open_loop, bands, ratios, models, candidate, incumbent):
    """The report sections from "## Open loop" to the band tables, for the models in table order."""
    runs = {model: exp1_by_run(results[model]) for model in models}
    us06 = {model: us06_exp1(results[model]) for model in models}
    open_rows = [[str(temp)] + [f"{open_loop[temp][model][0]:.2f}" for model in models]
                 + [f"{open_loop[temp][model][1]:.2f}" for model in models] for temp in T_GRID_DEGC]
    exp1_rows, other_rows, us06_rows = [], [], []
    for temp in T_GRID_DEGC:
        t = {model: tables[model][temp] for model in models}
        lower = int((t[candidate]["exp1_by_run"] < t[incumbent]["exp1_by_run"]).sum())
        exp1_rows.append([str(temp), str(t["2RC"]["runs"])] + [f"{t[model]['exp1']:.2f}" for model in models]
                         + [f"{t[candidate]['exp1'] - t[incumbent]['exp1']:+.2f}",
                            f"{t[incumbent]['exp1_median']:.2f}", f"{t[candidate]['exp1_median']:.2f}",
                            f"{lower} of {t['2RC']['runs']}"])
        other_rows.append([str(temp)] + [f"{t[model]['exp4']:.2f}" for model in models]
                          + [" / ".join(str(t[model][experiment]) for model in models)
                             for experiment in ("exp2", "exp3_low", "exp3_high")])
        us06_rows.append([str(temp)] + [f"{us06[model][temp]:.2f}" for model in models]
                         + [f"{us06[candidate][temp] - us06[incumbent][temp]:+.2f}"])
    cycle_rows = []
    for cycle in sorted(runs["2RC"]["cycle"].unique()):
        means = {model: runs[model][runs[model]["cycle"] == cycle]["rmse_pp"].mean() for model in models}
        count = int((runs["2RC"]["cycle"] == cycle).sum())
        cycle_rows.append([cycle, str(count)] + [f"{means[model]:.2f}" for model in models]
                          + [f"{means[candidate] - means[incumbent]:+.2f}"])
    band_rows = [[str(temp), name] + [f"{bands[temp][model][index]:+.1f}" for model in models]
                 for temp in T_GRID_DEGC for index, (name, _) in enumerate(BANDS)]
    share_rows = [[str(temp), f"{100.0 * bands[temp]['held_negative']:.1f}", f"{ratios[temp]:.2f}"]
                  for temp in T_GRID_DEGC]

    lines = ["## Open loop", "",
             "The US06 RMSE and the RMSE pooled over every drive run, model minus measured voltage (docs/decisions.md "
             "1.25).", ""]
    lines += md_table(["T (degC)"] + [f"US06 {model} (mV)" for model in models]
                      + [f"pooled {model} (mV)" for model in models], open_rows)
    lines += ["", "## Experiment 1", "",
              f"SoC RMSE with the correct initial SoC; change and runs lower are {candidate} against {incumbent}.", ""]
    lines += md_table(["T (degC)", "evaluation runs"] + [f"mean {model} (pp)" for model in models]
                      + ["mean change (pp)", f"median {incumbent} (pp)", f"median {candidate} (pp)",
                         f"runs lower with {candidate}"], exp1_rows)
    lines += ["", "### Per drive cycle", "", "Experiment-1 mean SoC RMSE over the cycle's evaluation runs.", ""]
    lines += md_table(["cycle", "runs"] + [f"{model} (pp)" for model in models] + ["change (pp)"], cycle_rows)
    lines += ["", "### US06", "", "Experiment-1 SoC RMSE of the US06 run.", ""]
    lines += md_table(["T (degC)"] + [f"{model} (pp)" for model in models] + ["change (pp)"], us06_rows)
    lines += ["", "## Experiments 2 to 4", "",
              "Experiment 4: mean SoC RMSE with the current offset. Reached: evaluation runs whose error stays within "
              f"+-2 pp from some time on, {' / '.join(models)}.", ""]
    lines += md_table(["T (degC)"] + [f"exp4 {model} (pp)" for model in models]
                      + ["exp2 reached", "exp3 low reached", "exp3 high reached"], other_rows)
    lines += ["", "## Open-loop US06 error by current band", "",
              "Mean error in mV, model minus measured. A row's band is set by its own current, the current at the "
              "voltage sample (docs/decisions.md 1.33). The branch states carry over between rows, so a band's error "
              "also holds what the rows before it left in the branches.", ""]
    lines += md_table(["T (degC)", "band (A)"] + [f"{model} (mV)" for model in models], band_rows)
    lines += ["", f"Steps whose held current is negative (the steps where {candidate} switches R1), and the R1 ratio "
              f"of docs/decisions.md 1.32: the median 2RC-I R1 at {RATIO_CURRENT_A} A over the grid SoC "
              f"{RATIO_SOC[0]} to {RATIO_SOC[1]}, divided by the median v1.0 R1 there.", ""]
    lines += md_table(["T (degC)", "US06 steps with held I < 0 (%)", "R1 ratio"], share_rows)
    return lines


def guard_table(guards):
    """Lines of the guard table."""
    return md_table(["guard", "value", "result"], [[name, value, "pass" if passed else "FAIL"]
                                                   for name, value, passed, _ in guards])
