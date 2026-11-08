"""Evaluate the S11 A settings candidate without changing any historical result."""

import argparse
import ast
import itertools
import json
import re
from multiprocessing import Pool

import numpy as np
import pandas as pd

from compare_r1c import scored_frame
from export_params import write_text
from fit_all import validate_us06
from fit_3rcd0 import load_candidate
from s10_protocol import RESULTS, splits, verify_baseline
from s11_evaluate import evaluate, grid_peaks, replay
from s11_report import OLD, NEW, comparison_lines, guards, plot
from s8_compare import decided_guards
from tune_3rcd0 import CONFIG, REPORT


CSV = RESULTS / "ekf_results_3rcd0n.csv"
COMPARISON = RESULTS / "model_compare_3rcd0n.md"


def verify_settings():
    """Do not label an edited config as the candidate selected by the saved search."""
    match = re.search(r"^Settings: `(.+)`\.$", REPORT.read_text(), re.MULTILINE)
    if match is None:
        raise ValueError("Calibration report has no selected settings")
    expected = ast.literal_eval(match.group(1)) | {"p0_soc_std": .2}
    if json.loads(CONFIG.read_text()) != expected:
        raise ValueError("Candidate config differs from the settings selected by the search report")


def grid_winners():
    """Read the committed calibration report; evaluation never re-runs the search."""
    section = REPORT.read_text().split("## Grid winners by initial branch standard deviation\n", 1)[1]
    section = section.split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        if re.match(r"\| [0-9]", line):
            values = [float(x.strip()) for x in line.strip().strip("|").split("|")]
            rows.append((tuple(values[:4]), values[4]))
    if len(rows) != 3:
        raise ValueError("Expected three grid winners in the calibration report")
    return rows


def verify_incumbent(raw, frozen):
    """Catch stale/corrupted incumbent traces before using full-precision threshold checks."""
    keys = ["folder", "file", "experiment"]
    left, right = [frame.sort_values(keys).reset_index(drop=True) for frame in (raw, frozen)]
    pd.testing.assert_frame_equal(left[keys], right[keys])
    for name in left.select_dtypes(include="number"):
        np.testing.assert_allclose(left[name], right[name], atol=5.01e-5, rtol=0, equal_nan=True,
                                   err_msg=f"Frozen incumbent mismatch: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    verify_baseline()
    verify_settings()
    mix, standard = splits()
    specs = mix + standard
    voltage = validate_us06(load_candidate(), 25)["rmse_mv"]
    with Pool(args.workers) as pool:
        print("Python evaluation: experiments 1–4 on all 63 runs", flush=True)
        scored = []
        for i, rows in enumerate(pool.imap(evaluate, specs, chunksize=1), 1):
            scored.append(rows)
            if i % 7 == 0:
                print(f"Evaluated {i}/63", flush=True)
        raw = {name: scored_frame([row[k] for row in scored]) for k, name in enumerate((OLD, NEW))}
        frozen = pd.read_csv(RESULTS / "ekf_results_3rcd0.csv")
        verify_incumbent(raw[OLD], frozen)
        raw[NEW].to_csv(CSV, index=False, float_format="%.4f")
        frames = {OLD: frozen, NEW: pd.read_csv(CSV)}
        decided = decided_guards(guards(frames, mix, standard, voltage), guards(raw, mix, standard, voltage))
        print("Guard result: " + ", ".join(f"{row[0]}={'PASS' if row[2] else 'FAIL'}" for row in decided), flush=True)
        counts = []
        for point, objective in grid_winners():
            print(f"Python wrong-start diagnostic: p0_v_std={point[3]}", flush=True)
            peaks = list(itertools.chain.from_iterable(pool.map(grid_peaks, [(s, point) for s in specs], chunksize=1)))
            counts.append([*[f"{x:.3g}" for x in point], f"{objective:.8f}",
                           str(sum(x > 25 for x in peaks)), f"{max(peaks):.6f}"])
        print("Replaying state/covariance for incumbent wrong-start peaks", flush=True)
        replays = list(itertools.chain.from_iterable(pool.map(replay, specs, chunksize=1)))
    write_text(COMPARISON, comparison_lines(frames, mix, standard, decided, counts, replays))
    plot(frames, mix, standard)
    print("3RC-D0-N " + ("ADOPTED" if all(row[2] for row in decided) else "NOT ADOPTED"), flush=True)


if __name__ == "__main__":
    main()
