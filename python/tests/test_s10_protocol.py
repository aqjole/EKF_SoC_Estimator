from dataclasses import replace

import numpy as np
import pandas as pd

import fit_3rcd0
from compare_3rcd0 import SCORED_MODELS, temperature_lines
from compare_r1i import per_temperature
from ekfsoc.constants import T_GRID_DEGC
from ekfsoc.model import Params
from fit_3rcd import PARAMS_3RCD_CSV
from fit_3rcd0 import CANDIDATE, INCUMBENT, MODELS, SUBSTITUTION
from s10_protocol import verify_baseline


def test_frozen_baseline_still_matches():
    verify_baseline()


def test_substitution_keeps_original_s9_tables_without_current_axis():
    params = fit_3rcd0.load_substitution()
    original = Params.from_csv(PARAMS_3RCD_CSV)
    assert params.r1_current is None
    for name in params.table_names:
        np.testing.assert_array_equal(getattr(params, name), getattr(original, name))


def test_candidate_roundtrip_keeps_v1_r1_without_current_table(tmp_path, monkeypatch):
    base = fit_3rcd0.load_substitution()
    candidate = replace(base, r3=base.r3 * 0.5)
    path = tmp_path / "params.csv"
    candidate.to_csv(path)
    monkeypatch.setattr(fit_3rcd0, "PARAMS_CSV_D0", path)
    reloaded = fit_3rcd0.load_candidate()
    assert reloaded.r1_current is None
    np.testing.assert_array_equal(reloaded.r1, base.r1)


def test_temperature_report_uses_only_exp1_for_substitution():
    rows = []
    for temp in T_GRID_DEGC:
        for experiment in ("exp1", "exp2", "exp3_low", "exp3_high", "exp4"):
            rows.append({"file": str(temp), "folder": str(temp), "experiment": experiment, "T_degC": temp,
                         "is_tuning": False, "rmse_pp": 2.0, "t_conv_s": 0.0})
    frame = pd.DataFrame(rows)
    tables = {model: per_temperature(frame) for model in SCORED_MODELS}
    experiment1 = frame[frame["experiment"] == "exp1"]
    results = {model: experiment1 for model in MODELS}
    text = "\n".join(temperature_lines(results, tables))
    assert f"{SUBSTITUTION} mean" in text
    assert f"{CANDIDATE} exp4" in text
    assert f"{INCUMBENT} mean" in text
