"""Small offline native evaluator; Python remains the adoption reference (1.50)."""

import ctypes
from functools import cache
from hashlib import sha256
import subprocess
import sys

import numpy as np

from ekfsoc.constants import Q_REF_AH, REPO_DIR


SOURCE = REPO_DIR / "c" / "tools" / "ekf_tuning.c"
BUILD = REPO_DIR / "c" / "build" / "tuning"


def build():
    """Build serially before starting workers; never replace a loaded library."""
    digest = sha256(SOURCE.read_bytes()).hexdigest()[:16]
    path = BUILD / f"ekf_tuning_{digest}.{'dylib' if sys.platform == 'darwin' else 'so'}"
    if not path.exists():
        BUILD.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cc", "-O3", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-ffp-contract=off", "-fno-fast-math", "-shared", "-fPIC",
                        str(SOURCE), "-o", str(path), "-lm"], check=True)
    return path


@cache
def library():
    lib = ctypes.CDLL(str(build()))
    array = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    lib.ekf_tuning_run.argtypes = ([ctypes.c_int] * 3 + [array] * 8
                                  + [ctypes.c_double] * 3 + [array] * 2)
    lib.ekf_tuning_run.restype = ctypes.c_int
    return lib


class NativeModel:
    """Pack immutable 3RC-D0 tables once for repeated evaluations."""

    def __init__(self, params):
        if len(params.branches) != 3 or params.r1_current is not None:
            raise ValueError("The tuning evaluator supports current-independent 3RC only")
        self.tables = np.ascontiguousarray([getattr(params, name) for name in params.table_names])
        self.t_grid = np.ascontiguousarray(params.t_grid)
        self.soc_grid = np.ascontiguousarray(params.soc_grid)

    def run(self, run, cfg, soc0, offset=0.0):
        """Same row-zero update and held-current convention as run_ekf."""
        arrays = [np.ascontiguousarray(values, dtype=np.float64)
                  for values in (run.i, run.v, run.temp, run.dt)]
        settings = np.array([cfg.q_soc, cfg.q_v, cfg.r, cfg.p0_soc_std, cfg.p0_v_std])
        soc, voltage = np.empty(len(run.i)), np.empty(len(run.i))
        failed = library().ekf_tuning_run(len(soc), len(self.t_grid), len(self.soc_grid),
                                         self.tables, self.t_grid, self.soc_grid, settings, *arrays,
                                         Q_REF_AH, soc0, offset, soc, voltage)
        if failed or not np.isfinite(soc).all() or not np.isfinite(voltage).all():
            raise ValueError(f"Native EKF nonfinite/invalid covariance at row {failed - 1}")
        return {"soc": soc, "v_pred": voltage}
