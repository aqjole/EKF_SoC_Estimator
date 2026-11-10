"""results/s7/r1_current.csv and results/s8/r1_charge.csv: the R1 tables over current of the 2RC-I model (S7,
docs/decisions.md 1.28) and of the charge side of the 2RC-Ic model (S8, 1.35).

One row per (T, I, SoC), T-major, then current, then SoC. The T and SoC axes are those of results/s1/params.csv,
so the table is added to a 2RC Params read from that file. Numbers have 6 significant digits, as there.
"""

import csv
from dataclasses import replace

import numpy as np


COLUMNS = ("T_degC", "I_A", "soc", "R1_ohm")


def write_r1_table(params, i_grid, table, path):
    """Write one R1 table over (T, SoC, I), shape (n_t, n_soc, n_i), on the T and SoC axes of params."""
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for j, temp in enumerate(params.t_grid):
            for q, current in enumerate(i_grid):
                for m, soc in enumerate(params.soc_grid):
                    cells = (temp, current, soc, table[j, m, q])
                    writer.writerow([f"{cell:.6g}" for cell in cells])


def write_r1_current(params, path):
    """Write the R1 table over current of a 2RC-I Params (params.i_grid, params.r1_current)."""
    write_r1_table(params, params.i_grid, params.r1_current, path)


def read_r1_current(params, path):
    """Return `params` (a 2RC Params) with the R1 table over current of `path` added (the 2RC-I model)."""
    i_grid, table = read_r1_table(params, path)
    return replace(params, i_grid=i_grid, r1_current=table)


def read_r1_charge(params, path):
    """Return `params` (a 2RC-I Params) with the charge-side R1 table of `path` added (the 2RC-Ic model)."""
    i_grid, table = read_r1_table(params, path)
    return replace(params, i_grid_charge=i_grid, r1_charge=table)


def read_r1_table(params, path):
    """(current axis, table of shape (n_t, n_soc, n_i)) of an R1 table file on the T and SoC axes of params.

    Raises ValueError if the header, the block structure or the T and SoC axes do not match.
    """
    with open(path, newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None or tuple(header) != COLUMNS:
            raise ValueError(f"{path}: header is {header}, expected {list(COLUMNS)}")
        data = np.array([[float(cell) for cell in line] for line in reader if line])

    n_t, n_soc = len(params.t_grid), len(params.soc_grid)
    if len(data) == 0 or len(data) % (n_t * n_soc) != 0:
        raise ValueError(f"{path}: {len(data)} rows is not a whole number of (T, SoC) grids of {n_t} x {n_soc}")
    blocks = data.reshape(n_t, -1, n_soc, len(COLUMNS))  # blocks[j, q, m] is the row of T j, current q, SoC m
    i_grid = blocks[0, :, 0, 1]
    same_axes = (np.all(blocks[:, :, :, 0] == params.t_grid[:, None, None])
                 and np.all(blocks[:, :, :, 1] == i_grid[None, :, None])
                 and np.all(blocks[:, :, :, 2] == params.soc_grid[None, None, :]))
    if not same_axes:
        raise ValueError(f"{path}: the T, I and SoC columns do not form the grid of the 2RC tables")
    return i_grid, blocks[:, :, :, 3].transpose(0, 2, 1)
