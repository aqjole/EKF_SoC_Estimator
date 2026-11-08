"""Python reference evaluation and wrong-start state replays for S11 A."""

from hashlib import sha256
import json

import numpy as np

from ekfsoc.constants import REPO_DIR
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.experiments import experiment_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import max_abs_pp, window_mask
from fit_3rcd0 import PARAMS_CSV_D0, load_candidate
from run_all import CONFIG_JSON, load_traces, save_traces, score_run
from s10_protocol import RESULTS
from s11_search import config
from tune_3rcd0 import CONFIG


RUNS = RESULTS / "runs" / "3rcd0n"
WRONG = ("exp2", "exp3_low", "exp3_high")


def digest(paths):
    h = sha256()
    for path in paths:
        h.update(str(path.relative_to(REPO_DIR)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def dependencies():
    return [PARAMS_CSV_D0, REPO_DIR / "python/s11_evaluate.py", REPO_DIR / "python/run_all.py",
            REPO_DIR / "python/s11_search.py", REPO_DIR / "python/fit_3rcd0.py",
            *sorted((REPO_DIR / "python/ekfsoc").glob("*.py"))]


def trace_path(spec, directory=RUNS):
    return directory / f"{spec.folder}__{spec.path.stem}.npz"


def evaluate(spec):
    """Cache candidate by content, reuse frozen incumbent traces, return full precision scores."""
    path = trace_path(spec)
    stamp = path.with_suffix(".sha256")
    wanted = digest([spec.path, CONFIG, *dependencies()])
    if not path.exists() or not stamp.exists() or stamp.read_text() != wanted:
        run = load_run(spec.path)
        cases = experiment_runs(run, load_candidate(), EkfConfig.from_json(CONFIG))
        save_traces(path, run.t, run.v, soc_ref(run), cases)
        stamp.write_text(wanted)
    baseline = trace_path(spec, RESULTS / "runs/3rcd0")
    if not baseline.exists():
        # Do not rewrite historical traces; this fallback is local to S11.
        baseline = trace_path(spec, RUNS / "baseline")
        baseline_stamp = baseline.with_suffix(".sha256")
        wanted_old = digest([spec.path, CONFIG_JSON, *dependencies()])
        if (not baseline.exists() or not baseline_stamp.exists()
                or baseline_stamp.read_text() != wanted_old):
            run = load_run(spec.path)
            cases = experiment_runs(run, load_candidate(), EkfConfig.from_json(CONFIG_JSON))
            save_traces(baseline, run.t, run.v, soc_ref(run), cases)
            baseline_stamp.write_text(wanted_old)
    return score_run(spec, *load_traces(baseline)), score_run(spec, *load_traces(path))


def grid_peaks(task):
    """Guard-7 diagnostic for a grid winner, also evaluated with Python, not native C."""
    spec, point = task
    path = RUNS / "grid_peaks" / (sha256(repr((spec.folder, spec.path.name, point)).encode()).hexdigest() + ".json")
    wanted = digest([spec.path, *dependencies()])
    if path.exists():
        cached = json.loads(path.read_text())
        if cached["inputs"] == wanted:
            return cached["peaks"]
    run, params, cfg = load_run(spec.path), load_candidate(), config(point)
    ref = soc_ref(run)
    start3 = int(np.flatnonzero(ref <= .7)[0])
    peaks = []
    for soc0, start in ((ref[0] - .2, 0), (.5, start3), (.9, start3)):
        result = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, soc0, start)
        peaks.append(max_abs_pp(result["soc"] - ref, window_mask(ref, start)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"inputs": wanted, "peaks": peaks}) + "\n")
    return peaks


def replay(spec):
    """State and diagonal covariance at start, >=10 s and own peak for incumbent bad cases."""
    baseline = trace_path(spec, RESULTS / "runs/3rcd0")
    if not baseline.exists():
        baseline = trace_path(spec, RUNS / "baseline")
    t, _, ref, cases = load_traces(baseline)
    names = [name for name in WRONG if max_abs_pp(cases[name]["soc"] - ref,
                                                 window_mask(ref, cases[name]["start"])) > 25]
    if not names:
        return []
    path = trace_path(spec, RUNS / "replay").with_suffix(".json")
    wanted = digest([spec.path, CONFIG, CONFIG_JSON, *dependencies()])
    if path.exists():
        cached = json.loads(path.read_text())
        if cached["inputs"] == wanted:
            return cached["rows"]
    run, params = load_run(spec.path), load_candidate()
    rows = []
    for name in names:
        case = cases[name]
        start, soc0 = case["start"], case["soc0"]
        window = window_mask(ref, start)
        for label, source in (("Incumbent", CONFIG_JSON), ("Candidate", CONFIG)):
            result = run_ekf(params, EkfConfig.from_json(source), run.i, run.v, run.temp, run.dt,
                             soc0, start, record_state=True)
            indices = np.flatnonzero(window)
            peak = int(indices[np.argmax(abs(result["soc"][window] - ref[window]))])
            after10 = min(int(np.searchsorted(t, t[start] + 10.)), len(t) - 1)
            for event, k in (("start", start), ("10 s", after10), ("own peak", peak)):
                rows.append([spec.folder, spec.cycle_name, name, label, event, f"{t[k] - t[start]:.3f}",
                             ", ".join(f"{x:.9g}" for x in result["state"][k]),
                             ", ".join(f"{x:.9g}" for x in result["p_diag"][k])])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"inputs": wanted, "rows": rows}) + "\n")
    return rows
