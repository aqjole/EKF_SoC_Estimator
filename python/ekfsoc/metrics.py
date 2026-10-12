"""The S2 metrics, defined here before any run (the spec, S2 "Metrics"; docs/model.md C14).

Every function is a pure function on numpy arrays. Time is in s and SoC is a fraction from 0 to 1.
The error of an estimate is `estimate - reference`. Results are in pp (percentage points of SoC) or mV.
Where a function takes `err`, it is a difference of SoC fractions; band_times takes `err_pp`, already in pp.

Evaluation window (C14)
    From the filter start to the last sample where the reference SoC is at least 10 %, inclusive.
    A run that ends near empty is where the model is worst, so that end is left out of every metric.
    Every function below takes the window as a boolean `mask`; samples outside it are never read.

SoC RMSE and max |error| (pp)
    rmse_pp and max_abs_pp over the window, and again "after convergence": over the part of the window
    from t_conv on (after_conv_mask). When convergence is not reached that part is empty and both
    return NaN, which the tables print as n/a.

Convergence time t_conv and first entry t_first (s)
    The band is +-2 pp around the reference (CONV_BAND_PP). t_first is the first window sample inside
    the band. t_conv is the first window sample from which the error stays inside the band to the end
    of the window, i.e. the sample after the last exit from the band (the first window sample, if the
    error never leaves it). If the error is outside the band at the last window sample, there is no
    such sample: t_conv is None, "not reached". t_first is None only if the error is never inside.
    Both are values of the time axis passed in; pass t - t[start] for seconds since the filter start.

Init-forgetting time (s)
    The same last-exit time, for the difference between two runs of the filter, in a +-1 pp band
    (FORGET_BAND_PP). The runs are experiment 2 against experiment 1, and experiments 3 (low and high)
    against the restart with correct init. This separates the effect of the initial error from the
    model error, which both runs share.

Terminal-voltage RMSE (mV)
    voltage_rmse_mv compares the voltage the filter predicted before each update (Eq. 8) with the
    measured voltage over the window. It is a diagnostic.

Coulomb counting (the baseline) and its expected drift
    coulomb_count is Eq. 3 on the logged current with the same dt and hold rule as the filter (C11),
    and no clamping. expected_drift_pp is what a constant current offset does to it (experiment 4).
"""

import math

import numpy as np


# Evaluation window: the last sample the reference SoC is at least this high (C14).
SOC_MIN = 0.10

# The bands of the convergence time and of the init-forgetting time, in pp.
CONV_BAND_PP = 2.0
FORGET_BAND_PP = 1.0

# SoC fraction to pp, and V to mV.
PP = 100.0
MV = 1000.0


def window_mask(soc_ref, start, soc_min=SOC_MIN):
    """Return the evaluation window: True from index `start` to the last index with soc_ref >= soc_min.

    The window is empty if the reference is below soc_min from `start` on.
    """
    at_or_above = np.flatnonzero(soc_ref >= soc_min)
    mask = np.zeros(len(soc_ref), dtype=bool)
    if len(at_or_above) > 0:
        mask[start:at_or_above[-1] + 1] = True
    return mask


def rms(x):
    """Root mean square of an array; NaN for an empty one."""
    return math.sqrt(np.mean(x ** 2)) if len(x) > 0 else math.nan


def rmse_pp(err, mask):
    """SoC RMSE in pp over the masked samples; err is a difference of SoC fractions. NaN for an empty mask."""
    return PP * rms(err[mask])


def max_abs_pp(err, mask):
    """Largest |err| in pp over the masked samples; err is a difference of SoC fractions. NaN for an empty mask."""
    return PP * float(np.max(np.abs(err[mask]))) if mask.any() else math.nan


def band_times(t, err_pp, mask, band_pp):
    """Return (t_first, t_conv) of the error trace err_pp (pp) in the band +-band_pp, over the masked samples.

    t_first is the time of the first masked sample with |err_pp| <= band_pp, None if there is none.
    t_conv is the time of the first masked sample from which |err_pp| <= band_pp holds to the last masked
    sample, None ("not reached") if |err_pp| > band_pp at the last masked sample. Both are values of t.
    An empty mask gives (None, None).
    """
    t_window = t[mask]
    inside = np.abs(err_pp[mask]) <= band_pp
    if not inside.any():
        return None, None
    t_first = float(t_window[np.argmax(inside)])
    if not inside[-1]:
        return t_first, None
    exits = np.flatnonzero(~inside)
    first_kept = exits[-1] + 1 if len(exits) > 0 else 0
    return t_first, float(t_window[first_kept])


def after_conv_mask(mask, t, t_conv):
    """Return the part of the window from t_conv on; it is empty if t_conv is None (not reached)."""
    if t_conv is None:
        return np.zeros(len(mask), dtype=bool)
    return mask & (t >= t_conv)


def init_forgetting_time(t, soc_a, soc_b, mask, band_pp=FORGET_BAND_PP):
    """Return the last-exit time of |soc_a - soc_b| (SoC fractions) from the band +-band_pp, over the masked samples.

    It is the t_conv of band_times for the difference of two runs; None if the runs are still apart
    at the last masked sample.
    """
    return band_times(t, PP * (soc_a - soc_b), mask, band_pp)[1]


def voltage_rmse_mv(v_pred, v_meas, mask):
    """RMSE in mV between the predicted and the measured terminal voltage (V) over the masked samples."""
    return MV * rms(v_pred[mask] - v_meas[mask])


def coulomb_count(i, dt, soc0, q_ref, start=0, current_offset=0.0):
    """Return the coulomb-counted SoC by Eq. 3, with eta = 1 and no clamping.

        soc[start] = soc0
        soc[k]     = soc[k-1] - (i[k-1] + current_offset) * dt[k] / (3600 * q_ref)        k > start

    The current held over step k is the previous kept sample's current (C11). i is in A (positive =
    discharge), dt in s, q_ref in Ah. Samples before `start` are NaN.
    """
    soc = np.full(len(i), np.nan)
    removed = np.cumsum((i[start:-1] + current_offset) * dt[start + 1:]) / (3600.0 * q_ref)
    soc[start] = soc0
    soc[start + 1:] = soc0 - removed
    return soc


def expected_drift_pp(offset_a, duration_s, q_ref):
    """Error in pp (estimate - reference) a coulomb counter picks up from a constant current offset.

    offset_a is added to the current (A, positive = discharge) for duration_s seconds, q_ref in Ah.
    A positive offset reads as extra discharge, so the estimate falls and the drift is negative.
    """
    return -PP * offset_a * duration_s / (3600.0 * q_ref)
