"""The evaluation set and the four experiments of S2 (the spec, S2; docs/decisions.md 1.3, 1.5, 1.7, 1.13).

evaluation_runs() lists the runs every experiment is repeated on; experiment_runs() runs the
experiments of one run and returns the EKF and coulomb-counting traces. Metrics are computed from
these traces by run_all.py with ekfsoc.metrics; nothing is scored here.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ekfsoc import rawio
from ekfsoc.constants import FOLDER_TEMP, Q_REF_AH
from ekfsoc.ekf import run_ekf
from ekfsoc.loader import find_runs, soc_ref
from ekfsoc.metrics import coulomb_count, expected_drift_pp, window_mask


# Experiment 4: current offset in A, in the project sign (positive = discharge), added to the current of
# the EKF and of the coulomb counter (docs/decisions.md 1.7).
OFFSET_A = 0.200

# Experiment 2: the initial SoC error, reference - 20 pp.
INIT_ERROR_SOC = 0.20

# Experiment 3: the filter starts where the reference SoC first reaches this level (docs/decisions.md 1.13),
# at 50 % and at 90 %. The two are written out so that the float sum 0.7 + 0.2 is never formed.
EXP3_START_SOC = 0.70
EXP3_SOC0_LOW = 0.50
EXP3_SOC0_HIGH = 0.90

# The drive cycles of the evaluation set: test type (rawio.classify_test) -> name in the results tables,
# in the order the evaluation list is built. PausCycl runs are never included: they are not drive cycles
# listed in the dataset readme (decisions 1.5).
CYCLE_NAMES = {
    "udds": "UDDS",
    "hwfet": "HWFET",
    "la92": "LA92",
    "us06": "US06",
    **{f"mixed{k}": f"Mix {k}" for k in range(1, 9)},
}

# The tuning cycle, (folder, test number, test type) of 25degC/551_Mixed1: it is run and reported, flagged
# (decisions 1.3).
TUNING_RUN = ("25degC", 551, "mixed1")

# Drive files left out of the evaluation set, keyed (folder, test number, test type), with the reason
# (decisions 1.5).
EXCLUDED = {
    ("25degC", 551, "hwfet"): "no current: a 0.17 h rest at 0 A",
    ("40degC", 562, "mixed4"): "partial run of 0.19 Ah, cell at 22.7 to 25.2 degC",
    ("40degC", 562, "mixed5"): "partial run of 0.19 Ah, cell at 22.7 to 25.2 degC",
    ("40degC", 562, "mixed6"): "partial run of 0.19 Ah, cell at 22.7 to 25.2 degC",
    ("40degC", 562, "mixed7"): "partial run of 0.19 Ah, cell at 22.7 to 25.2 degC",
    ("40degC", 562, "mixed8"): "partial run of 0.19 Ah, cell at 22.7 to 25.2 degC",
    ("n10degC", 602, "mixed4"): "corrupt: 4,160 identical rows, then an unlogged 415.993 s step",
}


@dataclass
class RunSpec:
    """One run of the evaluation list.

    path                .mat file (loader.load_run reads it)
    folder              data folder name, for example "25degC"
    nominal_temp_degc   the folder's set temperature in degC
    cycle_name          "UDDS", "HWFET", "LA92", "US06" or "Mix 1" to "Mix 8"
    is_tuning           True for the tuning cycle, which the noise settings were tuned on
    """

    path: Path
    folder: str
    nominal_temp_degc: int
    cycle_name: str
    is_tuning: bool


def evaluation_runs(raw_dir):
    """Return the 62 evaluation runs and the tuning cycle (63 RunSpec), folder by folder, in table order.

    Folders follow the temperature axis (40, 25, 10, 0, -10, -20 degC) and each folder the order of
    CYCLE_NAMES. Every drive file is taken except the ones in EXCLUDED.
    """
    specs = []
    for folder, nominal_temp in FOLDER_TEMP.items():
        for test_type, cycle_name in CYCLE_NAMES.items():
            for path in find_runs(raw_dir, test_type, folder):
                key = (folder, rawio.parse_filename(path.name)["test_number"], test_type)
                if key not in EXCLUDED:
                    specs.append(RunSpec(path, folder, nominal_temp, cycle_name, key == TUNING_RUN))
    return specs


def run_case(run, params, cfg, soc0, start, current_offset):
    """Run the EKF and the plain coulomb counter from row `start` with initial SoC soc0.

    Both see current_offset added to the logged current. Returns the case dict of experiment_runs().
    """
    ekf = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, soc0, start, current_offset)
    cc = coulomb_count(run.i, run.dt, soc0, Q_REF_AH, start, current_offset)
    return {"soc": ekf["soc"], "v_pred": ekf["v_pred"], "cc": cc, "start": start, "soc0": soc0}


def experiment_runs(run, params, cfg):
    """Run every experiment on one loader Run and return {name: case}; the reference is loader.soc_ref(run).

    case is a dict with soc (EKF, fraction), v_pred (predicted voltage, V), cc (coulomb counting, fraction),
    start (first row processed) and soc0 (initial SoC). The traces are NaN before `start`.
      exp1       soc0 = reference at row 0
      exp2       soc0 = reference at row 0 - 20 pp
      exp3_low   starts where the reference first reaches EXP3_START_SOC, soc0 = 50 %
      exp3_high  the same start, soc0 = 90 %
      exp3_ref   the same start, soc0 = 70 %: the comparator of the init-forgetting time
      exp4       as exp1 with OFFSET_A added to the current; its case also holds expected_drift_pp, the
                 drift of coulomb counting over the evaluation window in pp
    """
    reference = soc_ref(run)
    soc0 = float(reference[0])
    exp3_start = int(np.flatnonzero(reference <= EXP3_START_SOC)[0])

    cases = {
        "exp1": (soc0, 0, 0.0),
        "exp2": (soc0 - INIT_ERROR_SOC, 0, 0.0),
        "exp3_low": (EXP3_SOC0_LOW, exp3_start, 0.0),
        "exp3_high": (EXP3_SOC0_HIGH, exp3_start, 0.0),
        "exp3_ref": (EXP3_START_SOC, exp3_start, 0.0),
        "exp4": (soc0, 0, OFFSET_A),
    }
    results = {name: run_case(run, params, cfg, *case) for name, case in cases.items()}

    window_time = run.t[window_mask(reference, 0)]
    duration_s = float(window_time[-1] - window_time[0])
    results["exp4"]["expected_drift_pp"] = expected_drift_pp(OFFSET_A, duration_s, Q_REF_AH)
    return results
