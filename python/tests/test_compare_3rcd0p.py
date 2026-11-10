"""S12 step C (docs/decisions.md 1.57): the step A agreement check and the wrong-start case list, on synthetic frames."""

import pandas as pd
import pytest

import compare_3rcd0p
from ekfsoc.constants import REPO_DIR, T_GRID_DEGC
from ekfsoc.experiments import RunSpec
from s12_report import peak_lines


MEANS = {"exp1": 1.0, "exp2": 2.0, "exp4": 3.0}


def mix_frame():
    """One Mix run per temperature with the given experiment-1, -2 and -4 SoC RMSE."""
    rows, specs = [], []
    for temp in T_GRID_DEGC:
        path = REPO_DIR / f"{temp}_Mix 1.mat"
        specs.append(RunSpec(path, str(temp), temp, "Mix 1", False))
        for experiment, rmse in MEANS.items():
            rows.append(dict(folder=str(temp), file=path.name, cycle="Mix 1", T_degC=temp, is_tuning=False,
                             experiment=experiment, rmse_pp=rmse, max_abs_pp=5.0, t_conv_s=1.0))
    return pd.DataFrame(rows), specs


def part3_text(exp2_at_minus_20):
    """A results/s12/start_cases.md stand-in with the 10 mV rows of the part-3 temperature table."""
    rows = [f"| 10 mV | {temp} | 1 | 1.0000 | {exp2_at_minus_20 if temp == -20 else '2.0000'} | 3.0000 |"
            for temp in T_GRID_DEGC]
    return "\n".join(["## Part 3: x", "", "### Per temperature", "",
                      "| Prior | T (degC) | Runs | exp1 (pp) | exp2 (pp) | exp4 (pp) |", "|---|---|---|---|---|---|",
                      "| 50 mV (S2) | 40 | 1 | 9.0000 | 9.0000 | 9.0000 |", *rows, "", "### Experiment 1 per Mix run", ""])


def test_part3_check_passes_when_every_printed_mean_agrees(tmp_path, monkeypatch):
    monkeypatch.setattr(compare_3rcd0p, "START_CASES_MD", tmp_path / "start_cases.md")
    (tmp_path / "start_cases.md").write_text(part3_text("2.0000"))
    frame, specs = mix_frame()
    assert len(compare_3rcd0p.part3_check(frame, specs)) == 3 * len(T_GRID_DEGC)


def test_part3_check_stops_on_a_mean_that_differs(tmp_path, monkeypatch):
    monkeypatch.setattr(compare_3rcd0p, "START_CASES_MD", tmp_path / "start_cases.md")
    (tmp_path / "start_cases.md").write_text(part3_text("2.0001"))
    frame, specs = mix_frame()
    with pytest.raises(ValueError, match="part 3"):
        compare_3rcd0p.part3_check(frame, specs)


def test_peak_lines_list_a_case_above_25_pp_under_either_filter():
    keys = dict(folder="0degC", cycle="Mix 1", T_degC=0, is_tuning=False)
    old = pd.DataFrame([dict(keys, file="a.mat", experiment="exp2", max_abs_pp=30.0),
                        dict(keys, file="b.mat", experiment="exp2", max_abs_pp=10.0),
                        dict(keys, file="c.mat", experiment="exp3_low", max_abs_pp=10.0),
                        dict(keys, file="c.mat", experiment="exp3_high", max_abs_pp=10.0)])
    new = old.assign(max_abs_pp=[10.0, 26.0, 10.0, 10.0])
    text = "\n".join(peak_lines({"old": old, "new": new}))
    listed = [line for line in text.splitlines() if line.startswith("| 0degC")]
    assert listed == ["| 0degC | Mix 1 | exp2 | 30.0000 | 10.0000 |", "| 0degC | Mix 1 | exp2 | 10.0000 | 26.0000 |"]
