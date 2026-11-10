"""Step C's pre-screen of decision 1.56, one rule for both S12 diagnostics: step A screens branch-prior values with
it, step B Jacobian variants.

Over the 40 Mix runs, a setting *qualifies* against the incumbent when its experiment-1 mean is higher at no
temperature by more than EXP1_LIMIT_PP, its count of wrong-start cases above PEAK_LIMIT_PP is not higher, its largest
wrong-start peak is not higher, and its reached counts are lower at no temperature. Reached counts are those of
experiments 2 and 3, as guard 6 of 1.48 counts them (compare_r1i.per_temperature).
"""

import numpy as np

from compare_r1i import per_temperature
from ekfsoc.constants import T_GRID_DEGC
from s11_evaluate import WRONG


PEAK_LIMIT_PP = 25.0  # guard 7 of decision 1.48
EXP1_LIMIT_PP = 0.10  # the largest allowed rise of a temperature's experiment-1 Mix mean
SCREEN_HEADER = [*[f"exp1 change {temp} degC" for temp in T_GRID_DEGC], f"Cases above {PEAK_LIMIT_PP:.0f} pp",
                 "Largest peak (pp)", "Fewer reached", "Metric (pp)", "Qualifies"]


def temperature_table(frame):
    """Per temperature, from scored rows: compare_r1i.per_temperature (experiment-1 and -4 means, reached counts of
    experiments 2 and 3) and the experiment-2 mean, which the selection metric of kind (i) reads."""
    table = per_temperature(frame.assign(is_tuning=False))
    for temp in T_GRID_DEGC:
        table[temp]["exp2_mean"] = frame[(frame.T_degC == temp) & (frame.experiment == "exp2")].rmse_pp.mean()
    return table


def wrong_start_peaks(frame):
    """The count of wrong-start cases (experiments 2, 3 low and 3 high) above PEAK_LIMIT_PP, and their largest peak."""
    peaks = frame[frame.experiment.isin(WRONG)].max_abs_pp
    return int((peaks > PEAK_LIMIT_PP).sum()), float(peaks.max())


def prescreen(frame, incumbent):
    """The pre-screen quantities of one setting's scored rows against the incumbent's, and whether it qualifies."""
    new, old = temperature_table(frame), temperature_table(incumbent)
    change = {temp: new[temp]["exp1"] - old[temp]["exp1"] for temp in T_GRID_DEGC}
    above, peak = wrong_start_peaks(frame)
    old_above, old_peak = wrong_start_peaks(incumbent)
    fewer = [f"{name} at {temp} degC ({old[temp][name]} to {new[temp][name]})"
             for temp in T_GRID_DEGC for name in WRONG if new[temp][name] < old[temp][name]]
    qualifies = max(change.values()) <= EXP1_LIMIT_PP and above <= old_above and peak <= old_peak and not fewer
    return {"exp1_change": change, "above": above, "peak": peak, "fewer_reached": fewer, "qualifies": qualifies}


def prior_metric(table):
    """Kind (i): the mean over the six temperatures of the mean of the experiment-1, -2 and -4 Mix RMSEs."""
    return float(np.mean([(table[temp]["exp1"] + table[temp]["exp2_mean"] + table[temp]["exp4"]) / 3
                          for temp in T_GRID_DEGC]))


def variant_metric(frame):
    """Kind (ii): the experiment-1 mean over the Mix runs."""
    return float(frame[frame.experiment == "exp1"].rmse_pp.mean())


def screen_cells(screen, metric):
    """One row of the pre-screen tables of both reports, in the order of SCREEN_HEADER."""
    return [*[f"{screen['exp1_change'][temp]:+.4f}" for temp in T_GRID_DEGC], str(screen["above"]),
            f"{screen['peak']:.4f}", ", ".join(screen["fewer_reached"]) or "none", f"{metric:.4f}",
            "yes" if screen["qualifies"] else "no"]
