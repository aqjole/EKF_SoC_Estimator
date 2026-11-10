"""Stage S2 tuning: choose the EKF noise settings q_soc, q_v and r on the tuning cycle, then freeze them.

Run from the repo root:  .venv/bin/python python/tune.py   (or: make tune)

The spec's rule (S2) with the refinements of docs/decisions.md 1.16, applied to the tuning cycle only
(25degC/551_Mixed1, docs/decisions.md 1.3):

  1. grid search over q_soc, q_v and r, one point per decade: eight decades for q_soc, six for q_v and r
     (8 x 6 x 6 = 288 points);
  2. one refinement: the 27 combinations of factors 1/3, 1 and 3 around the best grid point;
  3. the best point after the refinement is frozen.

The objective is the mean of the SoC RMSE of experiment 2 (initial SoC 20 pp below the reference) and of
experiment 4 (a current offset), in pp, over the evaluation window (docs/model.md C14). Both experiments
are run by experiments.experiment_runs, so their definitions live in one place. The points run in a
process pool and the result does not depend on it: each point is one deterministic filter run, and ties
go to the point that comes first in the tables.

Writes results/s2/tuning.md (all 315 objectives and the chosen values), results/s2/ekf_config.json (the frozen
EkfConfig) and section 1.15 of docs/decisions.md (replaced if it is already there).
"""

import itertools
import re
import time
from functools import cache
from multiprocessing import Pool

from ekfsoc.constants import RAW_DIR, REPO_DIR
from ekfsoc.ekf import EkfConfig
from ekfsoc.experiments import OFFSET_A, evaluation_runs, experiment_runs
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import rmse_pp, window_mask
from ekfsoc.model import Params
from export_params import PARAMS_CSV, md_table, write_text


CONFIG_JSON = REPO_DIR / "results" / "s2" / "ekf_config.json"
TUNING_MD = REPO_DIR / "results" / "s2" / "tuning.md"
DECISIONS_MD = REPO_DIR / "docs" / "decisions.md"
DECISION_HEADING = "### 1.15 EKF noise settings (S2, frozen)"

# The grid: one value per decade. q_soc in 1/s over eight decades (two more than the spec, decisions 1.16),
# q_v in V^2/s and r in V^2 over six.
GRIDS = {
    "q_soc": (1e-12, 1e-11, 1e-10, 1e-9, 1e-8, 1e-7, 1e-6, 1e-5),
    "q_v": (1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3),
    "r": (1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1),
}
POINT_HEADER = ["q_soc (1/s)", "q_v (V^2/s)", "r (V^2)"]

# The refinement around the best grid point (the spec: "factors of 3").
REFINE_FACTORS = (1 / 3, 1.0, 3.0)

# The experiments whose SoC RMSE the objective averages (decisions 1.16).
OBJECTIVE_EXPERIMENTS = ("exp2", "exp4")


# --- the objective --------------------------------------------------------------------------------


@cache
def tuning_problem():
    """Load the tuning cycle once per process: Params, the Run, its reference SoC and its evaluation window."""
    spec = next(spec for spec in evaluation_runs(RAW_DIR) if spec.is_tuning)
    run = load_run(spec.path)
    reference = soc_ref(run)
    return Params.from_csv(PARAMS_CSV), run, reference, window_mask(reference, 0)


def objective(point):
    """Mean SoC RMSE in pp of experiments 2 and 4 on the tuning cycle, for point = (q_soc, q_v, r)."""
    params, run, reference, window = tuning_problem()
    cases = experiment_runs(run, params, EkfConfig(*point))
    rmses = [rmse_pp(cases[name]["soc"] - reference, window) for name in OBJECTIVE_EXPERIMENTS]
    return sum(rmses) / len(rmses)


# --- the search -----------------------------------------------------------------------------------


def grid_points():
    """The 288 grid points (q_soc, q_v, r), q_soc varying slowest."""
    return list(itertools.product(*GRIDS.values()))


def refine_points(best):
    """The 27 points at factors 1/3, 1 and 3 of `best`; each value is rounded to 3 significant digits.

    The rounding makes a refined value read the same in the tables, the JSON file and the decision (3.33e-09, not 3.3333333333333335e-09).
    """
    axes = [[float(f"{value * factor:.3g}") for factor in REFINE_FACTORS] for value in best]
    return list(itertools.product(*axes))


def score(pool, points):
    """Return [(point, objective)] sorted by objective; sorted() is stable, so a tie keeps the order of `points`."""
    return sorted(zip(points, pool.map(objective, points)), key=lambda scored: scored[1])


def edge_parameters(grid, refined):
    """Return (parameters at the edge of the grid, parameters at the end of the refinement range) of the best point.

    The best grid point is at the edge of the grid in a parameter when it takes the lowest or highest
    grid value. The refined point is at the end of the refinement range in a parameter when it is a
    factor of 3 or 1/3 off the best grid point. The objective may keep falling beyond either.
    """
    best_grid, best_refined = grid[0][0], refined[0][0]
    at_grid_edge = [name for name, value in zip(GRIDS, best_grid) if value in (GRIDS[name][0], GRIDS[name][-1])]
    at_range_end = [name for name, new, old in zip(GRIDS, best_refined, best_grid) if new != old]
    return at_grid_edge, at_range_end


def edge_notes(grid, refined):
    """Say where the search ended, so a reader knows if the frozen point may not be a minimum."""
    at_grid_edge, at_range_end = edge_parameters(grid, refined)
    return (f"The best grid point is at the edge of the grid in: {', '.join(at_grid_edge) or 'none'}. "
            f"The refined point is at the end of the refinement range in: {', '.join(at_range_end) or 'none'}.")


def interior_note(grid, refined):
    """Say whether the frozen point is interior to the search, and what follows from it."""
    if any(edge_parameters(grid, refined)):
        return ("The frozen point is not interior to the search: the objective may keep falling beyond it in the parameters "
                "named above, and the grid and the single refinement are not extended.")
    return ("The frozen point is interior to the search in all three parameters: it is not at the edge of the grid or at the "
            "end of the refinement range, and its neighbours one decade or a factor of 3 away in each parameter score worse.")


# --- the report -----------------------------------------------------------------------------------


def point_cells(point):
    return [f"{value:.3g}" for value in point]


def grid_span(name):
    """The lowest and highest grid value of parameter `name` as text, for example '1e-12 to 1e-05'."""
    values = GRIDS[name]
    return f"{values[0]:.0e} to {values[-1]:.0e}"


def result_table(scored):
    """Markdown table lines of a sorted search: rank, the three values, the objective in pp."""
    rows = [[str(rank)] + point_cells(point) + [f"{value:.4f}"] for rank, (point, value) in enumerate(scored, start=1)]
    return md_table(["#"] + POINT_HEADER + ["objective (pp)"], rows)


def tuning_md(grid, refined):
    """Text of results/s2/tuning.md. `grid` and `refined` are the sorted results of the two searches."""
    _, run, _, window = tuning_problem()
    window_time = run.t[window]
    cfg = EkfConfig(*refined[0][0])
    grid_shape = " x ".join(str(len(values)) for values in GRIDS.values())
    lines = [
        "# EKF tuning",
        "",
        "Written by `python/tune.py` (`make tune`). Do not edit by hand.",
        "",
        "The noise settings q_soc, q_v and r of the filter (docs/model.md Eq. 7 and Eq. 9) are tuned once, on the tuning cycle only (docs/decisions.md 1.3, 1.16), and then frozen (docs/decisions.md 1.15).",
        "",
        "## Method",
        "",
        f"- Tuning cycle: `{run.meta['folder']}/{run.meta['file']}`, {len(run.t)} rows used, {window.sum()} of them in the evaluation window ({window_time[-1] - window_time[0]:.1f} s).",
        "- Objective: the mean of the SoC RMSE in pp of experiments 2 and 4 over the evaluation window (docs/model.md C14), both run by `experiments.experiment_runs` (docs/decisions.md 1.16):",
        "  - experiment 2: the filter starts at the first row with the initial SoC 20 pp below the reference, V1 = V2 = 0, and is not told the init is wrong;",
        f"  - experiment 4: the initial SoC is the reference, and {OFFSET_A:.3f} A is added to the current the filter sees (docs/decisions.md 1.7).",
        f"- Fixed: P0 = diag({cfg.p0_soc_std}^2, {cfg.p0_v_std}^2, {cfg.p0_v_std}^2); the 2RC tables of `results/s1/params.csv`.",
        f"- Grid: one point per decade, q_soc {grid_span('q_soc')} 1/s, q_v {grid_span('q_v')} V^2/s, r {grid_span('r')} V^2: {grid_shape} = {len(grid)} points. The q_soc range is two decades longer than the spec's (docs/decisions.md 1.16).",
        f"- Refinement: the 3 x 3 x 3 = {len(refined)} points at factors 1/3, 1 and 3 of the best grid point, each value rounded to 3 significant digits. The refinement may leave the grid.",
        "- Ties go to the point that comes first in the order of evaluation (q_soc slowest, r fastest).",
        "",
        "## Result",
        "",
        *md_table([""] + POINT_HEADER + ["objective (pp)"], [
            ["best grid point"] + point_cells(grid[0][0]) + [f"{grid[0][1]:.4f}"],
            ["best refined point (frozen)"] + point_cells(refined[0][0]) + [f"{refined[0][1]:.4f}"],
        ]),
        "",
        edge_notes(grid, refined),
        "",
        "The frozen values are written to `results/s2/ekf_config.json`; no later stage tunes again.",
        "",
        f"## Refinement ({len(refined)} points, best first)",
        "",
        *result_table(refined),
        "",
        f"## Grid ({len(grid)} points, best first)",
        "",
        *result_table(grid),
        "",
    ]
    return "\n".join(lines)


def decision_section(grid, refined):
    """Text of section 1.15 of docs/decisions.md.

    It keeps the flat result paths it was written with: entries before 1.59 stay as written.
    """
    cfg = EkfConfig(*refined[0][0])
    return "\n".join([
        DECISION_HEADING,
        "",
        f"**q_soc = {cfg.q_soc:.3g} 1/s, q_v = {cfg.q_v:.3g} V^2/s and r = {cfg.r:.3g} V^2, with P0 = diag({cfg.p0_soc_std}^2, {cfg.p0_v_std}^2, {cfg.p0_v_std}^2) as in the spec. "
        "They are frozen in `results/ekf_config.json` and used unchanged for every experiment, run and temperature. There is no re-tuning on the evaluation set.**",
        "",
        f"- Reason: they give the lowest objective on the tuning cycle (1.3), {refined[0][1]:.4f} pp, among the {len(grid)} grid points and the {len(refined)} refinement points of "
        f"`results/tuning.md`; the best grid point alone gives {grid[0][1]:.4f} pp. The objective is the mean of the experiment-2 and experiment-4 SoC RMSE, and the q_soc grid "
        "is eight decades long (1.16).",
        f"- {edge_notes(grid, refined)} {interior_note(grid, refined)}",
        "",
    ])


def write_decision(section):
    """Put `section` into docs/decisions.md: replace the 1.15 section if it is there, else insert it before section 2.

    The section ends where the next heading of level 2 or 3 starts, so section 1.16 stays as it is.
    """
    text = DECISIONS_MD.read_text()
    start = text.find(DECISION_HEADING)
    if start < 0:
        start = end = text.index("\n## 2. ") + 1
    else:
        end = start + re.search(r"\n#{2,3} ", text[start:]).start() + 1
    write_text(DECISIONS_MD, text[:start] + section + "\n" + text[end:])


def main():
    started = time.perf_counter()
    with Pool() as pool:
        grid = score(pool, grid_points())
        refined = score(pool, refine_points(grid[0][0]))

    EkfConfig(*refined[0][0]).to_json(CONFIG_JSON)
    write_text(TUNING_MD, tuning_md(grid, refined))
    write_decision(decision_section(grid, refined))

    for label, (point, value) in (("best grid point", grid[0]), ("best refined point", refined[0])):
        print(f"{label}: q_soc, q_v, r = {point}, objective {value:.4f} pp")
    print(f"runtime {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
