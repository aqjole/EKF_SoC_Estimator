"""OCV(SoC, T): the open-circuit-voltage table and its slope, built from the C/20 discharge halves.

Rule (docs/decisions.md 1.1; docs/model.md C3, C4, C15):

- Source: the discharge half of each temperature's C20DisCh file only. The charge half is not used
  and no average of the two halves is taken, because the halves do not share one Ah axis.
- SoC axis: SoC = 1 - ah_removed / Q_ref, with ah_removed counted from the counter's zero at the
  step start (the loader does this for C20DisCh files, C3). Q_ref is the one value of constants.py.
- Curve: a PCHIP (monotone cubic) through the logged (SoC, V) points, evaluated on the SoC grid.
- Where the discharge does not reach a grid point (it ends above SoC 0 at five of the six
  temperatures, and its first row is a little below SoC 1), the table holds the value at the nearest
  end of the measured range. The measured range is kept per temperature (soc_min, soc_max) so that
  the report can state where the table is measured and where it is held.
- Check: V must rise strictly from each grid point to the next, over the grid points inside the
  measured range. If any temperature fails, the 25 degC row is copied to every temperature
  (the spec's fallback, decisions 1.1).
- dOCV/dSoC: central differences on the grid, one-sided at the two ends. It is computed once here and
  stored as its own table. Python and C interpolate it and never differentiate at run time, so their
  Jacobians are identical. It is exactly 0 on held grid points.
"""

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from ekfsoc.constants import Q_REF_AH


# A row counts as "discharging" when the current is above this (A, loader sign: positive = discharge).
# It is the 50 mA of results/data_checks.md section 11, which found the discharge half the same way.
DISCHARGE_MIN_A = 0.05

# The fallback curve, used at every temperature when a temperature fails the monotonicity check.
FALLBACK_TEMP_DEGC = 25


@dataclass
class OcvTable:
    """The OCV table on the (temperature, SoC) grid.

    soc_grid      SoC axis, fractions, shape (n_soc,)
    t_grid        temperature axis in degC, shape (n_t,), float64
    ocv           open-circuit voltage in V, shape (n_t, n_soc); row = temperature, column = SoC
    docv          slope of ocv over SoC in V per unit SoC, same shape; central differences on the grid
    soc_min       lowest SoC the discharge reached, per temperature, shape (n_t,); the table holds
                  its value at that SoC for the grid points below it
    soc_max       highest SoC the discharge reached (a little below 1), per temperature; the table
                  holds its value for the grid points above it
    monotone      per temperature, True when the curve of that temperature's own discharge passed the
                  strict-rise check on the grid points inside [soc_min, soc_max]
    fallback_used True when some temperature failed the check and the 25 degC row was copied to every
                  temperature; then ocv and docv are the same in every row, and soc_min and soc_max
                  are those of the 25 degC curve (the range where the table is measured), while
                  monotone still shows each temperature's own result
    """

    soc_grid: np.ndarray
    t_grid: np.ndarray
    ocv: np.ndarray
    docv: np.ndarray
    soc_min: np.ndarray
    soc_max: np.ndarray
    monotone: np.ndarray
    fallback_used: bool


def find_discharge_half(i):
    """Return (first, last) rows of the discharge half: the longest run of rows with i above DISCHARGE_MIN_A.

    The C20DisCh file is one long C/20 discharge, a rest, then the charge. The longest run of rows
    with current flowing out is the discharge; the rest and the charge are left out. Raises ValueError
    if no row discharges.
    """
    flowing = np.asarray(i) > DISCHARGE_MIN_A

    best_first = None
    best_last = None
    run_first = None
    for row in range(len(flowing)):
        if flowing[row]:
            if run_first is None:
                run_first = row
            run_last = row
            run_length = run_last - run_first + 1
            if best_first is None or run_length > best_last - best_first + 1:
                best_first = run_first
                best_last = run_last
        else:
            run_first = None

    if best_first is None:
        raise ValueError(f"no row has a discharge current above {DISCHARGE_MIN_A} A")
    return best_first, best_last


def average_equal_x(x, y):
    """Sort the points by x ascending and replace points that share one x by their mean.

    PCHIP needs strictly increasing x. Two rows can share a SoC when the counter has not moved
    between them; their voltages are averaged. Returns (x_unique, y_mean) as float64 arrays.
    """
    order = np.argsort(x, kind="stable")
    x_sorted = np.asarray(x, dtype=np.float64)[order]
    y_sorted = np.asarray(y, dtype=np.float64)[order]

    x_unique = []
    y_mean = []
    group_start = 0
    for k in range(1, len(x_sorted) + 1):
        group_ended = k == len(x_sorted) or x_sorted[k] != x_sorted[group_start]
        if group_ended:
            x_unique.append(x_sorted[group_start])
            y_mean.append(float(np.mean(y_sorted[group_start:k])))
            group_start = k
    return np.array(x_unique, dtype=np.float64), np.array(y_mean, dtype=np.float64)


def discharge_curve(run, q_ref=Q_REF_AH):
    """Return (soc, v) of the run's discharge half, sorted by SoC ascending, equal SoC averaged.

    SoC = 1 - ah_removed / Q_ref (C4). For a C20DisCh run the loader has counted ah_removed from the
    counter's zero at the step start, so the curve is on the same axis as Q_ref.
    """
    first, last = find_discharge_half(run.i)
    ah_removed = run.ah_removed[first:last + 1]
    voltage = run.v[first:last + 1]
    soc = 1.0 - ah_removed / q_ref
    return average_equal_x(soc, voltage)


def ocv_row_on_grid(soc_curve, v_curve, soc_grid):
    """Evaluate one temperature's PCHIP on the SoC grid, holding the end values outside the measured range.

    soc_curve must be strictly increasing (see average_equal_x). A grid point below soc_curve[0] gets
    the value at soc_curve[0]; one above soc_curve[-1] gets the value at soc_curve[-1]. The PCHIP is
    never evaluated outside the measured range, so it does not extrapolate.
    Returns (ocv_row, soc_min, soc_max).
    """
    soc_min = float(soc_curve[0])
    soc_max = float(soc_curve[-1])
    pchip = PchipInterpolator(soc_curve, v_curve)

    ocv_row = np.zeros(len(soc_grid), dtype=np.float64)
    for k in range(len(soc_grid)):
        soc_held = min(max(float(soc_grid[k]), soc_min), soc_max)
        ocv_row[k] = pchip(soc_held)
    return ocv_row, soc_min, soc_max


def rises_strictly_in_range(ocv_row, soc_grid, soc_min, soc_max):
    """True when V rises strictly from each grid point to the next, over the grid points inside [soc_min, soc_max].

    Held points (outside the range) are flat by construction and are not checked. Raises ValueError if
    fewer than two grid points lie inside the range, because nothing can then be checked.
    """
    inside_rows = [k for k in range(len(soc_grid)) if soc_min <= soc_grid[k] <= soc_max]
    if len(inside_rows) < 2:
        raise ValueError(f"fewer than two SoC grid points lie inside the measured range {soc_min} to {soc_max}")

    for k in range(len(inside_rows) - 1):
        step = ocv_row[inside_rows[k + 1]] - ocv_row[inside_rows[k]]
        if not step > 0.0:
            return False
    return True


def central_differences(values, x):
    """Return d(values)/d(x) at every point of a sorted axis: central differences inside, one-sided at the ends.

    Inside:   (values[k+1] - values[k-1]) / (x[k+1] - x[k-1])
    At the ends: (values[1] - values[0]) / (x[1] - x[0]) and the same for the last two points.
    """
    n_points = len(values)
    slope = np.zeros(n_points, dtype=np.float64)
    slope[0] = (values[1] - values[0]) / (x[1] - x[0])
    for k in range(1, n_points - 1):
        slope[k] = (values[k + 1] - values[k - 1]) / (x[k + 1] - x[k - 1])
    slope[n_points - 1] = (values[n_points - 1] - values[n_points - 2]) / (x[n_points - 1] - x[n_points - 2])
    return slope


def build_ocv(c20_runs, soc_grid, t_grid):
    """Build the OCV and dOCV/dSoC tables from the C20DisCh runs, one run per grid temperature.

    c20_runs  dict: nominal temperature in degC -> loader Run of that folder's C20DisCh file
    soc_grid  SoC axis, fractions, ascending
    t_grid    temperature axis in degC; the table rows follow this order
    Raises ValueError if a grid temperature has no run, if a run has no discharge, or if the fallback
    is needed but the 25 degC curve itself fails the check (then there is nothing valid to copy).
    """
    soc_grid = np.asarray(soc_grid, dtype=np.float64)
    t_grid = np.asarray(t_grid, dtype=np.float64)
    n_t = len(t_grid)
    n_soc = len(soc_grid)

    # Temperatures are whole degrees; a dict key of 25 and one of 25.0 are the same key.
    missing = [float(t) for t in t_grid if int(t) not in c20_runs]
    if missing:
        raise ValueError(f"no C20DisCh run for temperature(s) {missing} degC")

    ocv = np.zeros((n_t, n_soc), dtype=np.float64)
    soc_min = np.zeros(n_t, dtype=np.float64)
    soc_max = np.zeros(n_t, dtype=np.float64)
    monotone = np.zeros(n_t, dtype=bool)

    for row in range(n_t):
        temp_degc = int(t_grid[row])
        run = c20_runs[temp_degc]
        soc_curve, v_curve = discharge_curve(run)
        ocv[row, :], soc_min[row], soc_max[row] = ocv_row_on_grid(soc_curve, v_curve, soc_grid)
        monotone[row] = rises_strictly_in_range(ocv[row, :], soc_grid, soc_min[row], soc_max[row])

    # Fallback: one failing temperature puts the 25 degC curve at every temperature (decisions 1.1).
    fallback_used = not bool(np.all(monotone))
    if fallback_used:
        fallback_rows = np.flatnonzero(t_grid == FALLBACK_TEMP_DEGC)
        if len(fallback_rows) != 1:
            raise ValueError(f"the fallback needs exactly one {FALLBACK_TEMP_DEGC} degC row in t_grid")
        fallback_row = int(fallback_rows[0])
        if not monotone[fallback_row]:
            raise ValueError(
                f"the {FALLBACK_TEMP_DEGC} degC curve fails the monotonicity check, so it cannot be the fallback"
            )
        for row in range(n_t):
            ocv[row, :] = ocv[fallback_row, :]
            soc_min[row] = soc_min[fallback_row]
            soc_max[row] = soc_max[fallback_row]

    docv = np.zeros((n_t, n_soc), dtype=np.float64)
    for row in range(n_t):
        docv[row, :] = central_differences(ocv[row, :], soc_grid)

    return OcvTable(
        soc_grid=soc_grid,
        t_grid=t_grid,
        ocv=ocv,
        docv=docv,
        soc_min=soc_min,
        soc_max=soc_max,
        monotone=monotone,
        fallback_used=fallback_used,
    )
