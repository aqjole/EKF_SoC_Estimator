"""Stage S5 equivalence: run the Octave filter on every evaluation run and compare it with the Python filter.

Run from the repo root:  .venv/bin/python python/compare_octave.py   (or: make octave; needs data/raw/, make ekf
and octave-cli on PATH)

  1. Each run of experiments.evaluation_runs() gets its filter inputs written to results/runs/c_inputs/ exactly as
     python/compare_c.py writes them (17 significant digits), so both ports read the same float64 values.
  2. octave/ekf_run_csv.m runs experiment 1 (soc0 = the reference SoC at row 0) with the frozen noise settings of
     results/ekf_config.json, in double precision, and writes SoC with 17 significant digits. Its SoC is compared
     with the Python experiment 1 SoC saved by run_all.py in results/runs/<folder>__<file>.npz; Python is not run
     again.
  3. results/equivalence_octave.md gets max and RMS |delta SoC| in pp per run, per temperature and overall, against
     1e-3 pp (docs/decisions.md 1.20); results/plots/s5/equivalence_octave_25degC.png gets Python minus Octave SoC
     over time for US06 at 25 degC. A run whose delta is not finite is an error, and the command exits with status
     1 when the threshold is reached.

  --fixtures: run the Octave filter on the three fixtures of c/tests/fixtures/ instead and compare its SoC with
  their soc_expected column against the same threshold, with the settings ctest uses. It needs neither data/raw/
  nor results/runs/, and is what CI runs.
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from compare_c import C_DIR, compare_runs, exit_on_failure, frozen_config, report_text, tool_settings, write_report
from ekfsoc.constants import RAW_DIR, REPO_DIR
from ekfsoc.experiments import evaluation_runs
from ekfsoc.metrics import max_abs_pp
from ekfsoc.plots import ESTIMATE_COLORS, plt, save


OCTAVE_SCRIPT = REPO_DIR / "octave" / "ekf_run_csv.m"
EQUIVALENCE_MD = REPO_DIR / "results" / "equivalence_octave.md"
PLOT_PATH = REPO_DIR / "results" / "plots" / "s5" / "equivalence_octave_25degC.png"
PLOT_FOLDER = "25degC"
FIXTURES_DIR = C_DIR / "tests" / "fixtures"

# The threshold on max |delta SoC| in pp: the double-build threshold of the spec (docs/decisions.md 1.20).
THRESHOLD_PP = 1e-3

# The reference SoC at the first row of every fixture, as ctest passes it (c/tests/fixtures/README.md).
FIXTURE_SOC0 = 1.0


def run_octave(inputs_path, cfg, soc0):
    """Run the Octave filter on an input CSV and return its SoC per row."""
    with tempfile.TemporaryDirectory() as out_dir:
        out_path = Path(out_dir) / "soc.csv"
        subprocess.run(["octave-cli", OCTAVE_SCRIPT, inputs_path, out_path, *tool_settings(cfg, soc0)],
                       check=True, cwd=REPO_DIR)
        # round_trip: read the 17 digits back to the exact float64 the port wrote.
        return pd.read_csv(out_path, float_precision="round_trip")["soc"].to_numpy()


OCTAVE_IMPLEMENTATION = {"octave": (run_octave, THRESHOLD_PP)}


def equivalence_text(table, cfg):
    intro = (
        "Written by `python/compare_octave.py` (`make octave`). The Octave filter (`octave/ekf_run_csv.m`, double "
        "precision) runs experiment 1 (soc0 = the reference SoC at row 0) on the "
        f"{len(table)} runs of the evaluation set and the tuning cycle, with the frozen noise settings of "
        f"`results/ekf_config.json` (q_soc = {cfg.q_soc:g}, q_v = {cfg.q_v:g}, r = {cfg.r:g}), on the filter inputs "
        "the C port reads (dt computed in float64 by Python, written with 17 significant digits by "
        "`python/compare_c.py`). delta SoC = Python SoC - Octave SoC over every row of a run, in pp; the Python SoC "
        "is the experiment 1 trace of `python/run_all.py`. The port writes SoC with 17 significant digits, so the "
        "comparison is at full double resolution; the threshold on max |delta SoC| is the spec's double-build "
        f"threshold, {THRESHOLD_PP:g} pp (`docs/decisions.md` 1.20)."
    )
    return report_text("Octave port equivalence (S5)", intro, table, OCTAVE_IMPLEMENTATION)


def plot_equivalence(path, t, delta, title):
    """Python minus Octave SoC in pp over time, one panel."""
    fig, axis = plt.subplots(figsize=(10, 3))
    axis.plot(t, delta, color=ESTIMATE_COLORS[0], linewidth=0.8)
    axis.set_title(title)
    axis.set_ylabel("Python - Octave (pp)")
    axis.set_xlabel("time (s)")
    save(fig, path)


def fixture_delta_pp(path, runner, cfg):
    """Max |delta SoC| in pp between the runner's SoC on a fixture and the fixture's soc_expected column."""
    expected = pd.read_csv(path)["soc_expected"].to_numpy()
    soc = runner(path, cfg, FIXTURE_SOC0)
    if len(soc) != len(expected):
        raise RuntimeError(f"{path.name}: {len(soc)} rows of SoC, expected {len(expected)}")
    return max_abs_pp(expected - soc, np.ones(len(expected), dtype=bool))


def check_fixtures(runner, cfg):
    """Print one line per fixture and PASS or FAIL; return whether every fixture stays below the threshold."""
    passed = True
    for path in sorted(FIXTURES_DIR.glob("*.csv")):
        delta = fixture_delta_pp(path, runner, cfg)
        passed = passed and delta < THRESHOLD_PP  # a NaN delta compares False and fails
        print(f"{path.name}: max |delta SoC| = {delta:.2e} pp, limit {THRESHOLD_PP:g} pp")
    print("PASS" if passed else "FAIL")
    return passed


def main():
    parser = argparse.ArgumentParser(description="Compare the Octave filter with the Python filter.")
    parser.add_argument("--fixtures", action="store_true",
                        help="check the three fixtures of c/tests/fixtures/ only (needs no data/raw/)")
    fixtures_only = parser.parse_args().fixtures
    cfg = frozen_config()
    if fixtures_only:
        if not check_fixtures(run_octave, cfg):
            sys.exit(1)
        return

    started = time.perf_counter()
    specs = evaluation_runs(RAW_DIR)
    table, traces = compare_runs(specs, cfg, OCTAVE_IMPLEMENTATION)
    write_report(EQUIVALENCE_MD, equivalence_text(table, cfg), table, OCTAVE_IMPLEMENTATION)

    spec, (t, deltas) = next((spec, trace) for spec, trace in zip(specs, traces)
                             if spec.folder == PLOT_FOLDER and trace is not None)
    plot_equivalence(PLOT_PATH, t, deltas["octave"],
                     f"{spec.cycle_name} at {spec.nominal_temp_degc} degC: Python minus Octave SoC, experiment 1")
    print(f"wrote {PLOT_PATH.relative_to(REPO_DIR)}")
    print(f"runtime {time.perf_counter() - started:.1f} s")
    exit_on_failure(table, OCTAVE_IMPLEMENTATION, EQUIVALENCE_MD)


if __name__ == "__main__":
    main()
