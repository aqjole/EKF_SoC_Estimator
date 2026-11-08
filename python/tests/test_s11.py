"""S11 search correctness, native equivalence and guard-scope regressions."""

import itertools
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.experiments import RunSpec
from ekfsoc.constants import REPO_DIR
from fit_3rcd0 import load_candidate
from s11_native import NativeModel
from s11_report import OLD, NEW, guards
from s11_search import balanced_halves
from tune import refine_points
from tune_3rcd0 import AXES


def test_evaluation_refuses_settings_different_from_search(tmp_path, monkeypatch):
    import compare_3rcd0n as comparison
    import json
    report = tmp_path / "search.md"
    config = tmp_path / "config.json"
    selected = {"q_soc": 1e-8, "q_v": 1e-7, "r": .01, "p0_v_std": .015}
    report.write_text(f"Settings: `{selected}`.\n")
    config.write_text(json.dumps(selected | {"p0_soc_std": .2}))
    monkeypatch.setattr(comparison, "REPORT", report)
    monkeypatch.setattr(comparison, "CONFIG", config)
    comparison.verify_settings()
    config.write_text(json.dumps(selected | {"p0_soc_std": .1}))
    with pytest.raises(ValueError, match="differs"):
        comparison.verify_settings()


@pytest.mark.parametrize("settings", [(1e-7, 1e-6, .01, .05), (1e-12, 1e-8, 1e-6, .015),
                                      (1e-5, 1e-3, .1, .15)])
def test_native_changing_temperature_regen_gaps_and_projection(settings):
    """Exercise both clamped axes, current hold, irregular dt and state projection."""
    params = load_candidate()
    cfg = EkfConfig(*settings[:3], p0_v_std=settings[3])
    n = 350
    run = SimpleNamespace(i=np.resize([0., 5., -2., 15., -6.], n),
                          v=np.resize([4.2, 3.6, 4.1, 2.8, 4.4], n),
                          temp=np.linspace(-30, 50, n), dt=np.resize([0., .1, .3, 2., 60.], n))
    for soc0 in (-.05, .5, 1.05):
        fast = NativeModel(params).run(run, cfg, soc0, offset=.2)
        slow = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, soc0, current_offset=.2)
        for key in fast:
            np.testing.assert_allclose(fast[key], slow[key], atol=1e-8, rtol=0)
        assert np.all((fast["soc"] >= 0) & (fast["soc"] <= 1))


def test_optional_history_leaves_default_results_identical():
    params = load_candidate()
    cfg = EkfConfig(1e-7, 1e-6, .01)
    n, start = 20, 3
    args = (params, cfg, np.ones(n), np.full(n, 3.7), np.full(n, -10.), np.full(n, .1), .7)
    plain = run_ekf(*args, start=start)
    detailed = run_ekf(*args, start=start, record_state=True)
    assert set(plain) == {"soc", "v_pred", "p_soc"}
    for key in plain:
        np.testing.assert_array_equal(plain[key], detailed[key])
    np.testing.assert_array_equal(detailed["state"][:, 0], plain["soc"])
    np.testing.assert_array_equal(detailed["p_diag"][:, 0], plain["p_soc"])
    assert np.isnan(detailed["state"][:start]).all()
    assert np.isfinite(detailed["state"][start:]).all()
    assert (detailed["p_diag"][start:] >= 0).all()


def test_temperature_balancing_and_grid_order():
    # Three warm runs must not outweigh a single cold run.
    assert balanced_halves([(25, 1., 3.)] * 3 + [(-20, 5., 9.)]) == [3., 6.]
    points = list(itertools.product(*AXES.values()))
    assert len(points) == 864
    assert [p[3] for p in points[:3]] == [.015, .05, .15]
    assert points[0] == (1e-12, 1e-8, 1e-6, .015)
    assert len(refine_points(points[0])) == 81


def guard_example():
    rows, mix, standard = [], [], []
    for temp in (40, 25, 10, 0, -10, -20):
        for cycle, target in (("Mix 1", mix), ("US06", standard)):
            path = REPO_DIR / f"{temp}_{cycle}.mat"
            target.append(RunSpec(path, str(temp), temp, cycle, cycle == "Mix 1"))
            for exp in ("exp1", "exp2", "exp3_low", "exp3_high", "exp4"):
                rows.append(dict(folder=str(temp), file=path.name, cycle=cycle, T_degC=temp,
                                 is_tuning=cycle == "Mix 1", experiment=exp, rmse_pp=1.,
                                 max_abs_pp=20., t_conv_s=10.))
    old = pd.DataFrame(rows)
    new = old.copy()
    new.loc[new.experiment == "exp1", "rmse_pp"] = .9
    return {OLD: old, NEW: new}, mix, standard


def test_guards_include_tuning_run_and_use_correct_splits():
    frames, mix, standard = guard_example()
    assert all(row[2] for row in guards(frames, mix, standard, 23.24))
    new = frames[NEW]
    new.loc[(new.cycle == "Mix 1") & (new.T_degC == -10) & (new.experiment == "exp1"), "rmse_pp"] = 1.6
    checked = guards(frames, mix, standard, 23.24)
    assert checked[1][2]  # standard improvement does not count Mix runs
    assert not checked[2][2]  # per-run guard includes the old tuning flag
    assert not checked[7][2]  # Mix mean guard includes it too


def test_wrong_start_peak_and_reached_counts_are_independent_guards():
    frames, mix, standard = guard_example()
    new = frames[NEW]
    where = (new.cycle == "US06") & (new.T_degC == 25) & (new.experiment == "exp3_high")
    new.loc[where, "max_abs_pp"] = 25.00001
    new.loc[where, "t_conv_s"] = np.nan
    checked = guards(frames, mix, standard, 23.24)
    assert not checked[5][2]
    assert not checked[6][2]
    assert checked[6][3] < 1e-4  # triggers the unrounded threshold check
