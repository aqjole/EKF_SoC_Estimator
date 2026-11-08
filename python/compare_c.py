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
     temperature (docs/decisions.md 1.14). A run whose delta is not finite is an error, and the command exits
     with status 1 when a build fails its threshold, so make equiv and CI cannot pass on a failed table.

The comparison, the tables and the verdict take a mapping from implementation name to (runner, threshold), so
python/compare_octave.py judges the Octave port with the same code.
"""

import subprocess
import sys
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

# Build name -> the EKF_USE_DOUBLE setting.
BUILDS = {"float": "OFF", "double": "ON"}

# The initial standard deviations the tools use (c/tools/ekf_run_csv.c, octave/ekf_run_csv.m); the frozen
# settings must agree.
TOOL_P0_STDS = (0.2, 0.05)

INPUT_COLUMNS = "dt_s,i_a,v_v,t_degc"
PLOT_CYCLE = "US06"


def frozen_config():
    """Return the frozen settings of results/ekf_config.json, checked against the P0 the tools hard-code."""
    cfg = EkfConfig.from_json(CONFIG_JSON)
    if (cfg.p0_soc_std, cfg.p0_v_std) != TOOL_P0_STDS:
        raise RuntimeError(f"the tools use p0 stds {TOOL_P0_STDS}, results/ekf_config.json has others")
    return cfg


def tool_settings(cfg, soc0):
    """The command-line settings q_soc, q_v, r and soc0, written with repr() so the tools read the exact float64."""
    return [repr(value) for value in (cfg.q_soc, cfg.q_v, cfg.r, soc0)]


def build_dir(build, model="2rc"):
    """c/build/float and c/build/double for the 2RC model, c/build/3rcd0-float and -double for 3RC-D0 (1.54)."""
    return C_DIR / "build" / (build if model == "2rc" else f"{model}-{build}")


def build_c(model="2rc"):
    """Configure and build the host targets of c/ in the float and the double build of one model."""
    use_3rcd0 = "ON" if model == "3rcd0" else "OFF"
    for build, use_double in BUILDS.items():
        subprocess.run(["cmake", "-S", C_DIR, "-B", build_dir(build, model), f"-DEKF_USE_DOUBLE={use_double}",
                        f"-DEKF_USE_3RCD0={use_3rcd0}"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["cmake", "--build", build_dir(build, model)], check=True, stdout=subprocess.DEVNULL)


def run_c(build, inputs_path, cfg, soc0, model="2rc"):
    """Run the tool of one build on an input CSV and return its SoC per row."""
    out_path = inputs_path.with_suffix(f".{build}.soc.csv")
    subprocess.run([build_dir(build, model) / "ekf_run_csv", inputs_path, out_path, *tool_settings(cfg, soc0)],
                   check=True)
    return pd.read_csv(out_path)["soc"].to_numpy()


# Implementation name -> (runner(inputs_path, cfg, soc0) returning the SoC per row, threshold on max |delta SoC|
# in pp from the spec, S3).
C_IMPLEMENTATIONS = {"float": (partial(run_c, "float"), 0.1), "double": (partial(run_c, "double"), 1e-3)}


def stat_columns(implementations):
    """The columns of the table that hold max and RMS |delta SoC| in pp, in the order of the implementations."""
    return [f"{name}_{stat}_pp" for name in implementations for stat in ("max", "rms")]


def compare_run(spec, cfg, implementations):
    """Return the per-run row of the equivalence table and, for the plotted cycle, (t, Python - implementation)."""
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
    for implementation, (runner, _) in implementations.items():
        delta = soc_python - runner(inputs_path, cfg, cases["exp1"]["soc0"])
        row[f"{implementation}_max_pp"] = max_abs_pp(delta, everywhere)
        row[f"{implementation}_rms_pp"] = rmse_pp(delta, everywhere)
        deltas[implementation] = PP * delta
    return row, (t - t[0], deltas) if spec.cycle_name == PLOT_CYCLE else None


def compare_runs(specs, cfg, implementations):
    """Compare every run in a process pool; return the table, checked to be finite, and the trace of each run."""
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with Pool() as pool:
        compared = pool.map(partial(compare_run, cfg=cfg, implementations=implementations), specs, chunksize=1)
    table = pd.DataFrame([row for row, _ in compared])
    check_finite(table, implementations)
    return table, [trace for _, trace in compared]


# --- the report and the plots --------------------------------------------------------------------


def pp_text(value):
    return f"{value:.2e}"


def check_finite(table, implementations):
    """Raise if a run has a non-finite statistic: the maxima below skip NaN, so such a run would vanish from the verdict."""
    bad = table[~np.isfinite(table[stat_columns(implementations)]).all(axis=1)]
    if not bad.empty:
        runs = ", ".join(f"{row.folder}/{row.cycle} test {row.test}" for row in bad.itertuples())
        raise RuntimeError(f"non-finite delta SoC in {runs}")


def failed_builds(table, implementations):
    """The implementations whose largest max |delta SoC| reaches their threshold."""
    return [name for name, (_, limit) in implementations.items() if table[f"{name}_max_pp"].max() >= limit]


def verdict_lines(table, implementations):
    lines = ["| build | threshold (pp) | max \\|delta SoC\\| (pp) | worst run | largest RMS (pp) | result |",
             "|---|---|---|---|---|---|"]
    failed = failed_builds(table, implementations)
    for name, (_, limit) in implementations.items():
        worst = table.loc[table[f"{name}_max_pp"].idxmax()]
        result = "FAIL" if name in failed else "PASS"
        lines.append(f"| {name} | {limit:g} | {pp_text(worst[f'{name}_max_pp'])} | "
                     f"{worst['cycle']} at {worst['T']} degC ({worst['test']}) | "
                     f"{pp_text(table[f'{name}_rms_pp'].max())} | {result} |")
    return lines


def temperature_lines(table, implementations):
    headers = [f"{name} {stat} (pp)" for name in implementations for stat in ("max", "largest RMS")]
    lines = ["| T (degC) | runs | " + " | ".join(headers) + " |", "|---|---" + "|---" * len(headers) + "|"]
    for temp, group in table.groupby("T", sort=False):
        cells = [pp_text(group[column].max()) for column in stat_columns(implementations)]
        lines.append(f"| {temp} | {len(group)} | " + " | ".join(cells) + " |")
    return lines


def run_lines(table, implementations):
    headers = [f"{name} {stat} (pp)" for name in implementations for stat in ("max", "RMS")]
    lines = ["| T (degC) | cycle | test | rows | " + " | ".join(headers) + " |",
             "|---|---|---|---" + "|---" * len(headers) + "|"]
    for row in table.itertuples():
        cycle = f"{row.cycle} (tuning)" if row.is_tuning else row.cycle
        cells = [pp_text(getattr(row, column)) for column in stat_columns(implementations)]
        lines.append(f"| {row.T} | {cycle} | {row.test} | {row.rows} | " + " | ".join(cells) + " |")
    return lines


def report_text(title, intro, table, implementations):
    """The equivalence report: the title, the introduction, then the result, per-temperature and per-run tables."""
    lines = [
        f"# {title}",
        "",
        intro,
        "",
        "## Result",
        "",
        *verdict_lines(table, implementations),
        "",
        "## Per temperature",
        "",
        *temperature_lines(table, implementations),
        "",
        "## Per run",
        "",
        *run_lines(table, implementations),
    ]
    return "\n".join(lines) + "\n"


def write_report(path, text, table, implementations):
    """Write the report and print its verdict table."""
    write_text(path, text)
    print(f"wrote {path.relative_to(REPO_DIR)}")
    print("\n".join(verdict_lines(table, implementations)))


def exit_on_failure(table, implementations, path):
    """Exit with status 1 when an implementation fails its threshold, naming the report."""
    failed = failed_builds(table, implementations)
    if failed:
        sys.exit(f"equivalence FAIL in the {', '.join(failed)} build, see {path.relative_to(REPO_DIR)}")


def equivalence_text(table, cfg):
    intro = (
        "Written by `python/compare_c.py` (`make equiv`). The C filter (`c/tools/ekf_run_csv`) runs experiment 1 "
        f"(soc0 = the reference SoC at row 0) on the {len(table)} runs of the evaluation set and the tuning cycle, "
        "with the frozen noise settings of `results/ekf_config.json` "
        f"(q_soc = {cfg.q_soc:g}, q_v = {cfg.q_v:g}, r = {cfg.r:g}), "
        "on the filter inputs as the loader gives them (dt computed in float64 by Python, written with 17 significant "
        "digits). delta SoC = Python SoC - C SoC over every row of a run, in pp; the Python SoC is the experiment 1 "
        "trace of `python/run_all.py`. The float build uses `ekf_real_t = float`, the double build `-DEKF_USE_DOUBLE`; "
        "the thresholds on max |delta SoC| are those of the spec. The tool writes SoC with 10 significant digits, so "
        "the double build's numbers sit at that resolution: half a unit in the 10th digit of a SoC between 0.1 and 1 "
        "is 5e-9 pp."
    )
    return report_text("C port equivalence (S3)", intro, table, C_IMPLEMENTATIONS)


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
    cfg = frozen_config()
    specs = evaluation_runs(RAW_DIR)
    build_c()
    table, traces = compare_runs(specs, cfg, C_IMPLEMENTATIONS)
    write_report(EQUIVALENCE_MD, equivalence_text(table, cfg), table, C_IMPLEMENTATIONS)

    for spec, trace in zip(specs, traces):
        if trace is not None:
            t, deltas = trace
            plot_equivalence(PLOTS_DIR / f"equivalence_{spec.folder}.png", t, deltas,
                             f"{spec.cycle_name} at {spec.nominal_temp_degc} degC: Python minus C SoC, experiment 1")
    print(f"wrote {PLOTS_DIR.relative_to(REPO_DIR)}/")
    print(f"runtime {time.perf_counter() - started:.1f} s")
    exit_on_failure(table, C_IMPLEMENTATIONS, EQUIVALENCE_MD)


if __name__ == "__main__":
    main()
