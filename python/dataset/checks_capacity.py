"""The C/20 files (sections 11 and 12) and the other capacity files (13, 15) for results/s0/data_checks.md."""

import numpy as np
from scipy.interpolate import PchipInterpolator

from dataset.checks_rules import CV_START_V, RECHARGE_MIN_A, counter_resets, rows_used, value_at
from dataset.common import FLOW_CURRENT_A, longest_run


def analyse_c20(record, data, q_ref):
    """Describe one C20DisCh file: both halves, monotonicity, PCHIP check, alignment gaps.

    q_ref is None while Q_ref itself is being measured (the 25 degC file);
    then the SoC-axis quantities are left out.

    Discharge half: the longest run of rows with I < -50 mA. The file opens
    one 60 s interval into the step, after a counter reset at the step
    start, so Ah removed = -Ah, counted from that zero (docs/decisions.md).
    Charge half: from the first row after the discharge with I > +50 mA to
    the last row with I > 0 (the CV cutoff). The CV phase starts at the
    first charge row at or above 4.1995 V.
    """
    rows = rows_used(record, data)
    t = data["Time"][rows]
    v = data["Voltage"][rows]
    i = data["Current"][rows]
    ah = data["Ah"][rows]
    temp = data["Battery_Temp_degC"][rows]
    positions = np.arange(len(rows))

    dis_first, dis_last = longest_run(i < -FLOW_CURRENT_A)
    charge_first = int(np.where((i > FLOW_CURRENT_A) & (positions > dis_last))[0][0])
    charge_last = int(np.where((i > 0.0) & (positions > dis_last))[0][-1])
    cv_first = int(np.where((v >= CV_START_V) & (positions >= charge_first))[0][0])

    removed = -ah[dis_first:dis_last + 1]                  # counted from the step-start zero
    v_dis = v[dis_first:dis_last + 1]
    q_dis = float(removed[-1])
    added = ah[charge_first:charge_last + 1] - ah[dis_last]
    v_chg = v[charge_first:charge_last + 1]
    q_chg = float(added[-1])

    rises = np.diff(v_dis)
    rebound = v_dis - np.minimum.accumulate(v_dis)
    v_cc = v[charge_first:cv_first]
    falls = np.diff(v_cc)
    dip = np.maximum.accumulate(v_cc) - v_cc if len(v_cc) else np.array([0.0])

    result = {
        "record": record,
        "dis_rows": (int(rows[dis_first]), int(rows[dis_last])),
        "dis_median_a": float(np.median(i[dis_first:dis_last + 1])),
        "dis_end_time_s": float(t[dis_last]),
        "dis_end_v": float(v[dis_last]),
        "dis_end_ah": float(ah[dis_last]),
        "ah_first": float(data["Ah"][0]),
        "q_dis": q_dis,
        "q_chg": q_chg,
        "rest_s": float(t[charge_first] - t[dis_last]),
        "rest_from_first_rest_row_s": float(t[charge_first] - t[dis_last + 1]),
        "cc_median_a": float(np.median(i[charge_first:cv_first])),
        "cv_median_v": float(np.median(v[cv_first:charge_last + 1])),
        "cutoff_a": float(i[charge_last]),
        "cc_s": float(t[cv_first] - t[charge_first]),
        "cv_s": float(t[charge_last] - t[cv_first]),
        "temp_dis": (float(np.min(temp[dis_first:dis_last + 1])), float(np.max(temp[dis_first:dis_last + 1]))),
        "temp_chg": (float(np.min(temp[charge_first:charge_last + 1])),
                     float(np.max(temp[charge_first:charge_last + 1]))),
        "n_dis": len(v_dis),
        "rises": int(np.sum(rises > 0.0)),
        "largest_rise_mv": 1000.0 * float(max(np.max(rises), 0.0)),
        "largest_rebound_mv": 1000.0 * float(np.max(rebound)),
        "n_cc": len(v_cc),
        "falls": int(np.sum(falls < 0.0)),
        "largest_fall_mv": 1000.0 * float(max(-np.min(falls), 0.0)) if len(falls) else 0.0,
        "largest_dip_mv": 1000.0 * float(np.max(dip)),
        "removed_strictly_increasing": bool(np.all(np.diff(removed) > 0.0)),
    }
    if q_ref is None:
        return result

    # PCHIP through the raw discharge half on the Q_ref SoC axis, sampled on the 101-point grid.
    soc_dis = 1.0 - removed / q_ref
    order = np.argsort(soc_dis)
    pchip = PchipInterpolator(soc_dis[order], v_dis[order])
    grid = np.arange(101) / 100.0
    inside = grid[(grid >= soc_dis.min()) & (grid <= soc_dis.max())]
    resampled = pchip(inside)
    result.update({
        "end_soc": 1.0 - q_dis / q_ref,
        "pchip_points": len(inside),
        "pchip_range": (float(inside.min()), float(inside.max())),
        "pchip_monotone": bool(np.all(np.diff(resampled) > 0.0)),
        "pchip_smallest_step_mv": 1000.0 * float(np.min(np.diff(resampled))),
    })

    # Charge-minus-discharge voltage at the same SoC under four ways of placing the charge half.
    soc_a = 1.0 - (q_dis - added) / q_ref          # A: same Ah removed, counted back from the discharge end
    own_dis = 1.0 - removed / q_dis                # B and C: discharge on its own Ah span
    own_chg = added / q_chg                        # B: charge on its own Ah span
    scaled_chg = added / q_dis                     # C: charge Ah from the discharge end, scaled by the discharge Ah
    soc_d = 1.0 - (q_chg - added) / q_ref          # D: charge ends at SoC 1 on the Q_ref axis
    gap = {
        "A50": value_at(soc_a, v_chg, 0.5) - value_at(soc_dis, v_dis, 0.5),
        "B50": value_at(own_chg, v_chg, 0.5) - value_at(own_dis, v_dis, 0.5),
        "C50": value_at(scaled_chg, v_chg, 0.5) - value_at(own_dis, v_dis, 0.5),
        "D50": value_at(soc_d, v_chg, 0.5) - value_at(soc_dis, v_dis, 0.5),
        "A80": value_at(soc_a, v_chg, 0.8) - value_at(soc_dis, v_dis, 0.8),
    }
    result["gap_mv"] = {name: 1000.0 * value for name, value in gap.items()}
    return result


def analyse_capacity_file(record, data):
    """Counter start, discharge end and in-file recharge of a C20DisCh, Dis_0p5C or Dis_2C file (section 13)."""
    time_s = data["Time"]
    current = data["Current"]
    ah = data["Ah"]
    dis_first, dis_last = longest_run(current < -FLOW_CURRENT_A)
    interval_s = float(time_s[1] - time_s[0])
    after = np.where((current > RECHARGE_MIN_A) & (np.arange(len(current)) > dis_last))[0]
    return {
        "record": record,
        "ah_first": float(ah[0]),
        "i_first": float(current[0]),
        "interval_s": interval_s,
        "ah_back_one_interval": float(ah[0] - current[0] * interval_s / 3600.0),
        "ah_dis_end": float(ah[dis_last]),
        "ah_last": float(ah[-1]),
        "dis_median_a": float(np.median(current[dis_first:dis_last + 1])),
        "recharge_cc_a": float(np.median(current[after])) if len(after) else float("nan"),
        "resets": counter_resets(time_s, current, ah),
    }
