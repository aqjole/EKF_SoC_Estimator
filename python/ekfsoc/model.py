"""The 2RC model: parameter tables, table lookup and the open-loop voltage simulation.

Equation numbers ("Eq. n") are those of the Equations section of docs/model.md:

- Eq. 1  2RC state update with an exact zero-order hold (rc_step, used by simulate_2rc_open_loop)
- Eq. 2  terminal voltage (simulate_2rc_open_loop)
- Eq. 3  coulomb-counting SoC update (not run here: the simulation takes the reference SoC as input)
- Eq. 4  bilinear table lookup with clamping (find_cell, interp2)
- Eq. 5  dOCV/dSoC by central differences (computed in ocv.py, stored as the table `docv`)

All seven tables share the two axes of docs/model.md C15: the temperature axis is stored in the
order 40, 25, 10, 0, -10, -20 degC (descending) and the SoC axis from 0 to 1 (ascending).
Table row j is temperature t_grid[j] and column m is SoC soc_grid[m].
The C port (c/src/) repeats find_cell and interp2 with the same operation order.
"""

import csv
import math
from dataclasses import dataclass

import numpy as np


# The seven tables of Params, in CSV column order (after T_degC and soc).
TABLE_NAMES = ("ocv", "docv", "r0", "r1", "tau1", "r2", "tau2")

# Column order of results/params.csv: the two axes, then the tables in the order of TABLE_NAMES.
CSV_COLUMNS = ("T_degC", "soc", "ocv_V", "docv_V_per_soc", "R0_ohm", "R1_ohm", "tau1_s", "R2_ohm", "tau2_s")


def find_cell(axis, x):
    """Return (j, weight): the grid cell that holds x and how far x lies into it (Eq. 4, steps 1 to 3).

    `axis` is a list or array of at least two nodes that is strictly ascending or strictly
    descending (the temperature axis is stored descending: 40 down to -20 degC).

    Operation order:
      1. direction = +1 for an ascending axis, -1 for a descending one; lowest and highest are
         the smaller and the larger of the two end nodes.
      2. x_clamped = min(max(x, lowest), highest). A query beyond either end of the axis is
         moved to that end, so a table is never extrapolated.
      3. j = the largest index in 0 .. n-2 with direction * (x_clamped - axis[j]) >= 0. It is
         found by bisection: low starts at 0 and high at n-1, and the loop keeps
         "low is at or before x_clamped, high is after it" until high = low + 1.
         At the last node this gives j = n-2.
      4. weight = (x_clamped - axis[j]) / (axis[j+1] - axis[j]), from 0 at node j to 1 at node j+1.
         The signs of numerator and denominator are equal on a descending axis, so the weight
         is in [0, 1] for either direction.
    """
    n = len(axis)
    first = axis[0]
    last = axis[n - 1]
    if last > first:
        direction = 1.0
        lowest = first
        highest = last
    else:
        direction = -1.0
        lowest = last
        highest = first

    x_clamped = min(max(x, lowest), highest)

    low = 0
    high = n - 1
    while high - low > 1:
        mid = (low + high) // 2
        if direction * (x_clamped - axis[mid]) >= 0.0:
            low = mid
        else:
            high = mid

    weight = (x_clamped - axis[low]) / (axis[low + 1] - axis[low])
    return low, weight


def interp2(table, t_grid, soc_grid, temp, soc):
    """Bilinear interpolation of one table at (temp, soc) with clamping to the axis ranges (Eq. 4).

    `table[j][m]` holds the value at temperature t_grid[j] and SoC soc_grid[m]. Operation order,
    which the C port repeats:
      1. (j, weight_t) = find_cell(t_grid, temp) and (m, weight_s) = find_cell(soc_grid, soc).
         find_cell clamps first, so temp and soc beyond the axis ends take the edge value.
      2. Along SoC at the two bracketing temperatures:
           value_j  = (1 - weight_s) * table[j][m]   + weight_s * table[j][m+1]
           value_j1 = (1 - weight_s) * table[j+1][m] + weight_s * table[j+1][m+1]
      3. Along temperature:
           result = (1 - weight_t) * value_j + weight_t * value_j1
    The weighted form is used instead of a + w * (b - a), so a query exactly on a node returns
    that node's value with no rounding.
    """
    j, weight_t = find_cell(t_grid, temp)
    m, weight_s = find_cell(soc_grid, soc)

    value_j = (1.0 - weight_s) * table[j][m] + weight_s * table[j][m + 1]
    value_j1 = (1.0 - weight_s) * table[j + 1][m] + weight_s * table[j + 1][m + 1]
    return float((1.0 - weight_t) * value_j + weight_t * value_j1)


@dataclass(eq=False)
class Params:
    """The two axes and the seven parameter tables of the model (docs/model.md C15, Symbols).

    t_grid    temperature axis in degC, length n_t (descending: 40 ... -20)
    soc_grid  SoC axis as a fraction, length n_soc (ascending: 0 ... 1)
    ocv       OCV in V
    docv      dOCV/dSoC in V per unit SoC (Eq. 5)
    r0        R0 in Ohm
    r1, tau1  RC branch 1 (fast): R1 in Ohm, tau1 in s
    r2, tau2  RC branch 2 (slow): R2 in Ohm, tau2 in s
    Every table has shape (n_t, n_soc). The arrays are copied to float64 on creation.
    """

    t_grid: np.ndarray
    soc_grid: np.ndarray
    ocv: np.ndarray
    docv: np.ndarray
    r0: np.ndarray
    r1: np.ndarray
    tau1: np.ndarray
    r2: np.ndarray
    tau2: np.ndarray

    def __post_init__(self):
        """Convert to float64 arrays and check the axes and table shapes, so a bad table fails at once."""
        self.t_grid = np.array(self.t_grid, dtype=np.float64)
        self.soc_grid = np.array(self.soc_grid, dtype=np.float64)
        for axis_name in ("t_grid", "soc_grid"):
            axis = getattr(self, axis_name)
            if axis.ndim != 1 or len(axis) < 2:
                raise ValueError(f"{axis_name} must be a 1-D axis with at least 2 nodes")
            steps = np.diff(axis)
            if not (np.all(steps > 0.0) or np.all(steps < 0.0)):
                raise ValueError(f"{axis_name} must be strictly ascending or strictly descending")

        expected_shape = (len(self.t_grid), len(self.soc_grid))
        for name in TABLE_NAMES:
            table = np.array(getattr(self, name), dtype=np.float64)
            if table.shape != expected_shape:
                raise ValueError(f"table {name} has shape {table.shape}, expected {expected_shape}")
            setattr(self, name, table)

    @classmethod
    def from_csv(cls, path):
        """Read results/params.csv: one row per (T, soc), T-major (all SoC of the first T, then the next T).

        The axes are rebuilt from the first column (one value per block) and from the SoC column of
        the first block. A wrong header, a ragged block or an axis value that changes in a later
        block raises ValueError.
        """
        with open(path, newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None or tuple(header) != CSV_COLUMNS:
                raise ValueError(f"{path}: header is {header}, expected {list(CSV_COLUMNS)}")
            rows = [[float(cell) for cell in line] for line in reader if line]

        if not rows or any(len(row) != len(CSV_COLUMNS) for row in rows):
            raise ValueError(f"{path}: expected at least one data row, each of {len(CSV_COLUMNS)} cells")
        data = np.array(rows)

        n_soc = int(np.count_nonzero(data[:, 0] == data[0, 0]))  # rows of the first T block
        if len(data) % n_soc != 0:
            raise ValueError(f"{path}: {len(data)} rows is not a whole number of blocks of {n_soc}")
        blocks = data.reshape(-1, n_soc, len(CSV_COLUMNS))  # blocks[j, m] is the row of T j and SoC m

        t_grid = blocks[:, 0, 0]
        soc_grid = blocks[0, :, 1]
        if not (np.all(blocks[:, :, 0] == t_grid[:, None]) and np.all(blocks[:, :, 1] == soc_grid)):
            raise ValueError(f"{path}: the T and soc columns do not form the same grid in every block")

        tables = {name: blocks[:, :, 2 + column] for column, name in enumerate(TABLE_NAMES)}
        return cls(t_grid=t_grid, soc_grid=soc_grid, **tables)

    def to_csv(self, path):
        """Write the CSV that from_csv reads: header CSV_COLUMNS, then one row per (T, soc), T-major.

        Every number has 6 significant digits, so writing the same Params twice gives the same
        bytes, and a round trip returns the values to about 1e-6 relative.
        """
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(CSV_COLUMNS)
            for j, temp in enumerate(self.t_grid):
                for m, soc in enumerate(self.soc_grid):
                    cells = [temp, soc] + [getattr(self, name)[j, m] for name in TABLE_NAMES]
                    writer.writerow([f"{cell:.6g}" for cell in cells])


def rc_step(v, r, tau, current, dt):
    """Advance one RC branch voltage v over a step of dt s with `current` held over it (Eq. 1)."""
    a = math.exp(-dt / tau)
    return a * v + r * (1.0 - a) * current


def simulate_2rc_open_loop(params, i, temp, soc, dt):
    """Run the 2RC model over a run with the SoC given, and return the model voltage in V (Eq. 1, Eq. 2).

    Inputs are 1-D arrays of the same length: i in A (positive = discharge), temp in degC,
    soc as a fraction (the reference SoC in S1, so only the voltage model is tested) and dt in s
    with dt[0] = 0 and dt[k] = t[k] - t[k-1], as in the loader's Run.

    Plain per-sample loop. V1 = V2 = 0 at k = 0 (the model starts relaxed). For each row k:
      1. Look up ocv, r0, r1, tau1, r2, tau2 at (temp[k], soc[k]) with interp2 (Eq. 4).
      2. Terminal voltage (Eq. 2): v_model[k] = ocv - V1 - V2 - r0 * i[k].
      3. Move the two RC states on to row k+1 with rc_step (Eq. 1), under the zero-order hold the
         loader rules fix (docs/model.md C11): the current of row k is held over the step dt[k+1],
         and R_i and tau_i are those at the start of the step, looked up in step 1.
    So row k's own current enters the voltage at once through R0 (Eq. 2) and enters the RC
    states only from row k+1 on.
    """
    n = len(i)
    for name, array in (("temp", temp), ("soc", soc), ("dt", dt)):
        if len(array) != n:
            raise ValueError(f"{name} has {len(array)} samples, i has {n}")

    # Plain Python lists make the element access in the loop fast; interp2 works on them unchanged.
    currents = np.asarray(i, dtype=np.float64).tolist()
    temps = np.asarray(temp, dtype=np.float64).tolist()
    socs = np.asarray(soc, dtype=np.float64).tolist()
    dts = np.asarray(dt, dtype=np.float64).tolist()
    t_grid = params.t_grid.tolist()
    soc_grid = params.soc_grid.tolist()
    ocv_table = params.ocv.tolist()
    r0_table = params.r0.tolist()
    r1_table = params.r1.tolist()
    tau1_table = params.tau1.tolist()
    r2_table = params.r2.tolist()
    tau2_table = params.tau2.tolist()

    v_model = np.zeros(n)
    v1 = 0.0
    v2 = 0.0
    for k in range(n):
        cell_temp = temps[k]
        cell_soc = socs[k]
        ocv = interp2(ocv_table, t_grid, soc_grid, cell_temp, cell_soc)
        r0 = interp2(r0_table, t_grid, soc_grid, cell_temp, cell_soc)
        r1 = interp2(r1_table, t_grid, soc_grid, cell_temp, cell_soc)
        tau1 = interp2(tau1_table, t_grid, soc_grid, cell_temp, cell_soc)
        r2 = interp2(r2_table, t_grid, soc_grid, cell_temp, cell_soc)
        tau2 = interp2(tau2_table, t_grid, soc_grid, cell_temp, cell_soc)

        v_model[k] = ocv - v1 - v2 - r0 * currents[k]  # Eq. 2

        if k + 1 < n:  # Eq. 1: the current of row k is held over the step to row k+1
            step = dts[k + 1]
            v1 = rc_step(v1, r1, tau1, currents[k], step)
            v2 = rc_step(v2, r2, tau2, currents[k], step)

    return v_model
