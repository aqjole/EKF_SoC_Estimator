"""Stage S3 equivalence: run the C filter on every evaluation run and compare it with the Python filter.

Run from the repo root:  .venv/bin/python python/compare_c.py   (or: make equiv; needs data/raw/ and make ekf)

  1. The float and the double host builds of c/ are configured and built into c/build/float and c/build/double.
  2. Each run of experiments.evaluation_runs() is loaded with the loader rules and its filter inputs are written,
     with 17 significant digits so the double build reads exactly the float64 values Python used, to
     results/runs/c_inputs/<folder>__<file>.csv (dt_s, i_a, v_v, t_degc; git-ignored with results/runs/).
  3. c/tools/ekf_run_csv runs experiment 1 (soc0 = the reference SoC at row 0) with the frozen noise settings of
     results/ekf_config.json in each build. Its SoC is compared with the Python experiment 1 SoC saved by
     run_all.py in results/runs/<folder>__<file>.npz; Python is not run again. A trace that no longer matches the
     code or the settings shows up as a failure of the double build, whose threshold is far below any such change.
  4. results/equivalence.md gets max and RMS |delta SoC| in pp per run and build, per temperature and overall,
     against the spec's thresholds; results/plots/s3/ gets Python minus C SoC over time for US06 at each
     temperature (docs/decisions.md 1.14).
"""

import subprocess
import time
from functools import partial
from multiprocessing import Pool

import numpy as np
import pandas as pd

from ekfsoc import rawio
from ekfsoc.constants import RAW_DIR, REPO_DIR
from ekfsoc.ekf import EkfConfig
from ekfsoc.experiments import evaluation_runs
from ekfsoc.loader import load_run
from ekfsoc.metrics import PP, max_abs_pp, rmse_pp
from ekfsoc.plots import ESTIMATE_COLORS, plt, save
from export_params import write_text
from run_all import CONFIG_JSON, RUNS_DIR, load_traces


C_DIR = REPO_DIR / "c"
INPUTS_DIR = RUNS_DIR / "c_inputs"
EQUIVALENCE_MD = REPO_DIR / "results" / "equivalence.md"
PLOTS_DIR = REPO_DIR / "results" / "plots" / "s3"

# Build name -> the EKF_USE_DOUBLE setting and the threshold on max |delta SoC| in pp (the spec, S3).
BUILDS = {"float": ("OFF", 0.1), "double": ("ON", 1e-3)}

# The initial standard deviations the tool uses (c/tools/ekf_run_csv.c); the frozen settings must agree.
TOOL_P0_STDS = (0.2, 0.05)

INPUT_COLUMNS = "dt_s,i_a,v_v,t_degc"
PLOT_CYCLE = "US06"


def build_dir(build):
    return C_DIR / "build" / build


def build_c():
    """Configure and build the host targets of c/ in the float and the double build."""
    for build, (use_double, _) in BUILDS.items():
        subprocess.run(["cmake", "-S", C_DIR, "-B", build_dir(build), f"-DEKF_USE_DOUBLE={use_double}"],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["cmake", "--build", build_dir(build)], check=True, stdout=subprocess.DEVNULL)


def run_c(build, inputs_path, cfg, soc0):
    """Run the tool of one build on an input CSV and return its SoC per row."""
    out_path = inputs_path.with_suffix(f".{build}.soc.csv")
    settings = [repr(value) for value in (cfg.q_soc, cfg.q_v, cfg.r, soc0)]
    subprocess.run([build_dir(build) / "ekf_run_csv", inputs_path, out_path, *settings], check=True)
    return pd.read_csv(out_path)["soc"].to_numpy()


def compare_run(spec, cfg):
    """Return the per-run row of the equivalence table and, for the plotted cycle, (t, Python - C per build)."""
    name = f"{spec.folder}__{spec.path.stem}"
    t, _, _, cases = load_traces(RUNS_DIR / f"{name}.npz")
    soc_python = cases["exp1"]["soc"]

    run = load_run(spec.path)
    inputs_path = INPUTS_DIR / f"{name}.csv"
    np.savetxt(inputs_path, np.column_stack([run.dt, run.i, run.v, run.temp]), fmt="%.17g", delimiter=",",
               header=INPUT_COLUMNS, comments="")

    row = {"folder": spec.folder, "T": spec.nominal_temp_degc, "cycle": spec.cycle_name,
           "test": rawio.parse_filename(spec.path.name)["test_number"], "is_tuning": spec.is_tuning,
           "rows": len(soc_python)}
    deltas = {}
    everywhere = np.ones(len(soc_python), dtype=bool)
    for build in BUILDS:
        delta = soc_python - run_c(build, inputs_path, cfg, cases["exp1"]["soc0"])
        row[f"{build}_max_pp"] = max_abs_pp(delta, everywhere)
        row[f"{build}_rms_pp"] = rmse_pp(delta, everywhere)
        deltas[build] = PP * delta
    return row, (t - t[0], deltas) if spec.cycle_name == PLOT_CYCLE else None


# --- the report and the plots --------------------------------------------------------------------


def pp_text(value):
    return f"{value:.2e}"


def verdict_lines(table):
    lines = ["| build | threshold (pp) | max \\|delta SoC\\| (pp) | worst run | largest RMS (pp) | result |",
             "|---|---|---|---|---|---|"]
    for build, (_, limit) in BUILDS.items():
        worst = table.loc[table[f"{build}_max_pp"].idxmax()]
        result = "PASS" if table[f"{build}_max_pp"].max() < limit else "FAIL"
        lines.append(f"| {build} | {limit:g} | {pp_text(worst[f'{build}_max_pp'])} | "
                     f"{worst['cycle']} at {worst['T']} degC ({worst['test']}) | "
                     f"{pp_text(table[f'{build}_rms_pp'].max())} | {result} |")
    return lines


def temperature_lines(table):
    lines = ["| T (degC) | runs | float max (pp) | float largest RMS (pp) | double max (pp) | double largest RMS (pp) |",
             "|---|---|---|---|---|---|"]
    for temp, group in table.groupby("T", sort=False):
        cells = [pp_text(group[f"{build}_{stat}_pp"].max()) for build in BUILDS for stat in ("max", "rms")]
        lines.append(f"| {temp} | {len(group)} | " + " | ".join(cells) + " |")
    return lines


def run_lines(table):
    lines = ["| T (degC) | cycle | test | rows | float max (pp) | float RMS (pp) | double max (pp) | double RMS (pp) |",
             "|---|---|---|---|---|---|---|---|"]
    for row in table.itertuples():
        cycle = f"{row.cycle} (tuning)" if row.is_tuning else row.cycle
        cells = [pp_text(getattr(row, f"{build}_{stat}_pp")) for build in BUILDS for stat in ("max", "rms")]
        lines.append(f"| {row.T} | {cycle} | {row.test} | {row.rows} | " + " | ".join(cells) + " |")
    return lines


def equivalence_text(table, cfg):
    lines = [
        "# C port equivalence (S3)",
        "",
        "Written by `python/compare_c.py` (`make equiv`). The C filter (`c/tools/ekf_run_csv`) runs experiment 1 "
        f"(soc0 = the reference SoC at row 0) on the {len(table)} runs of the evaluation set and the tuning cycle, "
        "with the frozen noise settings of `results/ekf_config.json` "
        f"(q_soc = {cfg.q_soc:g}, q_v = {cfg.q_v:g}, r = {cfg.r:g}), "
        "on the filter inputs as the loader gives them (dt computed in float64 by Python, written with 17 significant "
        "digits). delta SoC = Python SoC - C SoC over every row of a run, in pp; the Python SoC is the experiment 1 "
        "trace of `python/run_all.py`. The float build uses `ekf_real_t = float`, the double build `-DEKF_USE_DOUBLE`; "
        "the thresholds on max |delta SoC| are those of the spec. The tool writes SoC with 10 significant digits, so "
        "the double build's numbers sit at that resolution: half a unit in the 10th digit of a SoC between 0.1 and 1 "
        "is 5e-9 pp.",
        "",
        "## Result",
        "",
        *verdict_lines(table),
        "",
        "## Per temperature",
        "",
        *temperature_lines(table),
        "",
        "## Per run",
        "",
        *run_lines(table),
    ]
    return "\n".join(lines) + "\n"


def plot_equivalence(path, t, deltas, title):
    """Python minus C SoC in pp over time, the float build above and the double build below."""
    fig, axes = plt.subplots(len(deltas), 1, sharex=True, figsize=(10, 5))
    for axis, (build, delta), color in zip(axes, deltas.items(), ESTIMATE_COLORS):
        axis.plot(t, delta, color=color, linewidth=0.8)
        axis.set_ylabel(f"{build} build\nPython - C (pp)")
    axes[0].set_title(title)
    axes[-1].set_xlabel("time (s)")
    save(fig, path)


def main():
    started = time.perf_counter()
    cfg = EkfConfig.from_json(CONFIG_JSON)
    if (cfg.p0_soc_std, cfg.p0_v_std) != TOOL_P0_STDS:
        raise RuntimeError(f"ekf_run_csv uses p0 stds {TOOL_P0_STDS}, results/ekf_config.json has others")
    specs = evaluation_runs(RAW_DIR)
    build_c()
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with Pool() as pool:
        compared = pool.map(partial(compare_run, cfg=cfg), specs, chunksize=1)

    table = pd.DataFrame([row for row, _ in compared])
    write_text(EQUIVALENCE_MD, equivalence_text(table, cfg))
    print(f"wrote {EQUIVALENCE_MD.relative_to(REPO_DIR)}")
    print("\n".join(verdict_lines(table)))

    for spec, (_, trace) in zip(specs, compared):
        if trace is not None:
            t, deltas = trace
            plot_equivalence(PLOTS_DIR / f"equivalence_{spec.folder}.png", t, deltas,
                             f"{spec.cycle_name} at {spec.nominal_temp_degc} degC: Python minus C SoC, experiment 1")
    print(f"wrote {PLOTS_DIR.relative_to(REPO_DIR)}/")
    print(f"runtime {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
