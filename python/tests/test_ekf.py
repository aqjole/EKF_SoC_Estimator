"""Tests for ekfsoc.ekf: the predict and update steps (Eq. 6 to 11), run_ekf, the synthetic convergence test and
the divergence test of the SoC limit (docs/decisions.md 1.16).

The hand computations use small made-up tables, so no raw data is needed. The synthetic test draws
its data from the model itself (results/params.csv at 25 degC) plus voltage noise, so it checks the
filter apart from model mismatch (the spec, S2). The expected values are worked out in the comments,
not by calling the code under test.
"""

import math

import numpy as np
import pytest

from ekfsoc.constants import Q_REF_AH, REPO_DIR
from ekfsoc.ekf import Ekf, EkfConfig, run_ekf
from ekfsoc.model import Params, simulate_2rc_open_loop
from ekfsoc.synthetic import SOC_START, SYNTHETIC_CFG, WRONG_INIT_PP, synthetic_data


# --- small tables for the hand computations --------------------------------------------------------


def toy_params(r0, r1, tau1, r2, tau2):
    """Params on a 2 x 2 grid with OCV = 3 + SoC (slope 1 V per unit SoC) and the given constants."""
    def constant(value):
        return np.full((2, 2), value)

    return Params(
        t_grid=[25.0, 0.0],
        soc_grid=[0.0, 1.0],
        ocv=np.array([[3.0, 4.0], [3.0, 4.0]]),
        docv=constant(1.0),
        r0=constant(r0),
        r1=constant(r1),
        tau1=constant(tau1),
        r2=constant(r2),
        tau2=constant(tau2),
    )


def scalar_ekf(r=0.01, q_soc=1e-4):
    """A filter that is a scalar Kalman filter on the SoC: the time constants are huge, R1 = R2 = 0 and
    V1, V2 have no variance, so F = 1, B = [-dt / (3600 Q_ref), 0, 0] and H = [1, -1, -1] acts on SoC alone.
    P0 = diag(0.2^2, 0, 0) = diag(0.04, 0, 0), SoC0 = 0.5, OCV(0.5) = 3.5 V, R0 = 0.05 Ohm.
    """
    params = toy_params(r0=0.05, r1=0.0, tau1=1e12, r2=0.0, tau2=1e12)
    cfg = EkfConfig(q_soc=q_soc, q_v=0.0, r=r, p0_v_std=0.0)
    return Ekf(params, cfg, soc0=0.5)


def test_predict_of_the_scalar_case():
    ekf = scalar_ekf()
    ekf.predict(i_held=1.0, t_degC=25.0, dt_s=36.0)
    # SoC- = 0.5 - 1 A * 36 s / (3600 * Q_ref) = 0.5 - 0.01 / Q_ref.
    # P- = 0.04 + q_soc * dt = 0.04 + 1e-4 * 36 = 0.0436.
    assert ekf.x[0] == pytest.approx(0.5 - 0.01 / Q_REF_AH, abs=1e-9)
    assert ekf.P[0, 0] == pytest.approx(0.0436, abs=1e-9)


def test_update_of_the_scalar_case():
    ekf = scalar_ekf(r=0.01)
    # y_hat = OCV(0.5) - 0 - 0 - R0 * I = 3.5 - 0.05 * 2 = 3.4 V.  Measured 3.42 V: innovation 0.02 V.
    # S = H P H^T + R = 0.04 + 0.01 = 0.05, K_soc = 0.04 / 0.05 = 0.8.
    # SoC = 0.5 + 0.8 * 0.02 = 0.516.  Joseph: P = 0.2^2 * 0.04 + 0.8^2 * 0.01 = 0.0016 + 0.0064 = 0.008.
    ekf.update(i_a=2.0, v_v=3.42, t_degC=25.0)
    assert ekf.y_hat == pytest.approx(3.4, abs=1e-12)
    assert ekf.x[0] == pytest.approx(0.516, abs=1e-12)
    assert ekf.P[0, 0] == pytest.approx(0.008, abs=1e-12)


def update_with_branch_variance():
    """One update with P0 = diag(0.04, 0.01, 0.01) and R = 0.01: H = [1, -1, -1], so H P H^T = 0.06, S = 0.07.
    y_hat = 3.4 V and the measurement is 3.47 V: innovation 0.07 V, so K * innovation = P H^T = [0.04, -0.01, -0.01].
    """
    params = toy_params(r0=0.05, r1=0.0, tau1=1e12, r2=0.0, tau2=1e12)
    ekf = Ekf(params, EkfConfig(q_soc=0.0, q_v=0.0, r=0.01, p0_v_std=0.1), soc0=0.5)
    ekf.update(i_a=2.0, v_v=3.47, t_degC=25.0)
    return ekf


def test_update_spreads_a_positive_innovation_over_soc_and_both_branches():
    # A measured voltage above the prediction raises SoC and lowers V1 and V2 (V = OCV - V1 - V2 - R0 I).
    assert update_with_branch_variance().x.tolist() == pytest.approx([0.54, -0.01, -0.01], abs=1e-12)


def test_update_covariance_is_the_posterior_of_the_kalman_filter():
    # P = P- - (P- H^T)(P- H^T)^T / S, with P- H^T = [0.04, -0.01, -0.01] and S = 0.07 (the Joseph form gives the same).
    expected = np.array([[0.04, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 0.01]]) - np.outer(
        [0.04, -0.01, -0.01], [0.04, -0.01, -0.01]
    ) / 0.07
    assert update_with_branch_variance().P == pytest.approx(expected, abs=1e-12)


def test_step_holds_the_previous_current_over_the_step():
    # R so large that the update does nothing (K ~ 4e-14): the SoC after the second step is the prediction.
    # The first sample's 1 A is held over the 36 s, not the second sample's 3 A.
    ekf = scalar_ekf(r=1e12)
    ekf.step(i_a=1.0, v_v=3.4, t_degC=25.0, dt_s=0.0)
    soc = ekf.step(i_a=3.0, v_v=3.4, t_degC=25.0, dt_s=36.0)
    assert soc == pytest.approx(0.5 - 1.0 * 36.0 / (3600.0 * Q_REF_AH), abs=1e-9)


def test_predict_with_zero_dt_leaves_x_and_p_unchanged():
    ekf = scalar_ekf()
    x_before, p_before = ekf.x.copy(), ekf.P.copy()
    ekf.predict(i_held=5.0, t_degC=25.0, dt_s=0.0)
    assert np.array_equal(ekf.x, x_before) and np.array_equal(ekf.P, p_before)


def test_predict_moves_the_rc_branches_and_a_full_covariance():
    params = toy_params(r0=0.05, r1=0.02, tau1=10.0, r2=0.03, tau2=100.0)
    cfg = EkfConfig(q_soc=1e-4, q_v=1e-3, r=0.01)
    ekf = Ekf(params, cfg, soc0=0.5, v1=0.02, v2=0.01)
    ekf.P = np.array([[0.04, 0.001, -0.002], [0.001, 0.0025, 0.0003], [-0.002, 0.0003, 0.0025]])
    p_before = ekf.P.copy()
    dt, i_held = 10.0, 2.0

    ekf.predict(i_held=i_held, t_degC=25.0, dt_s=dt)

    # a_i = exp(-dt / tau_i): a1 = exp(-1), a2 = exp(-0.1).  F = diag(1, a1, a2).
    a1, a2 = math.exp(-1.0), math.exp(-0.1)
    f = [1.0, a1, a2]
    assert ekf.x[0] == pytest.approx(0.5 - i_held * dt / (3600.0 * Q_REF_AH), abs=1e-12)
    assert ekf.x[1] == pytest.approx(a1 * 0.02 + 0.02 * (1.0 - a1) * i_held, abs=1e-12)
    assert ekf.x[2] == pytest.approx(a2 * 0.01 + 0.03 * (1.0 - a2) * i_held, abs=1e-12)
    # P-[i][j] = f_i * f_j * P[i][j], plus q_i * dt on the diagonal.
    q_dt = [1e-4 * dt, 1e-3 * dt, 1e-3 * dt]
    for i in range(3):
        for j in range(3):
            expected = f[i] * f[j] * p_before[i, j] + (q_dt[i] if i == j else 0.0)
            assert ekf.P[i, j] == pytest.approx(expected, abs=1e-15)


@pytest.mark.parametrize("soc0, v_measured, expected", [(0.99, 4.5, 1.0), (0.01, 2.0, 0.0)])
def test_soc_is_clamped_to_zero_and_one_after_the_update(soc0, v_measured, expected):
    # The innovation (about +-1.5 V) pushes the gain-weighted SoC far past the end of its range.
    params = toy_params(r0=0.05, r1=0.0, tau1=1e12, r2=0.0, tau2=1e12)
    ekf = Ekf(params, EkfConfig(q_soc=0.0, q_v=0.0, r=0.01, p0_v_std=0.0), soc0=soc0)
    ekf.update(i_a=0.0, v_v=v_measured, t_degC=25.0)
    assert ekf.x[0] == expected


@pytest.mark.parametrize(
    "x_post, expected",
    [
        # SoC 1.2: the bound is 1, (SoC - b) / P00 = 0.2 / 0.04 = 5 and P[:, 0] = [0.04, 0.002, -0.004],
        # so x moves by [0.2, 0.01, -0.02]: V1 falls to 0.04 and V2 rises to 0.12.
        ([1.2, 0.05, 0.10], [1.0, 0.04, 0.12]),
        # SoC -0.1: the bound is 0, (SoC - b) / P00 = -0.1 / 0.04 = -2.5, so x moves by [-0.1, -0.005, 0.01].
        ([-0.1, 0.05, 0.10], [0.0, 0.055, 0.09]),
        # SoC 0.7 is inside [0, 1]: nothing moves.
        ([0.7, 0.05, 0.10], [0.7, 0.05, 0.10]),
    ],
)
def test_limit_soc_moves_the_state_onto_the_bound_along_the_first_column_of_p(x_post, expected):
    P_post = np.array([[0.04, 0.002, -0.004], [0.002, 0.01, 0.0], [-0.004, 0.0, 0.01]])
    p_before = P_post.copy()
    limited = scalar_ekf().limit_soc(np.array(x_post), P_post)
    assert limited.tolist() == pytest.approx(expected, abs=1e-12)
    assert np.array_equal(P_post, p_before)


# --- run_ekf ---------------------------------------------------------------------------------------


def run_scalar_case(start, current_offset):
    params = toy_params(r0=0.05, r1=0.0, tau1=1e12, r2=0.0, tau2=1e12)
    cfg = EkfConfig(q_soc=0.0, q_v=0.0, r=0.01, p0_v_std=0.0)
    n = 4
    dt = np.array([0.0, 0.1, 0.1, 0.1])
    return run_ekf(params, cfg, i=np.full(n, 2.0), v=np.full(n, 3.4), temp=np.zeros(n), dt=dt,
                   soc0=0.5, start=start, current_offset=current_offset)


def test_run_ekf_is_nan_before_start():
    out = run_scalar_case(start=2, current_offset=0.0)
    assert np.isnan(out["soc"][:2]).all() and np.isnan(out["v_pred"][:2]).all() and np.isnan(out["p_soc"][:2]).all()


@pytest.mark.parametrize("current_offset, expected", [(0.0, 3.4), (1.0, 3.35)])
def test_run_ekf_first_row_is_an_update_from_soc0_and_adds_the_offset(current_offset, expected):
    # v_pred[start] = OCV(0.5) - 0 - 0 - R0 * (I + offset) = 3.5 - 0.05 * (2 + offset).
    out = run_scalar_case(start=1, current_offset=current_offset)
    assert out["v_pred"][1] == pytest.approx(expected, abs=1e-12)


def test_config_json_round_trip(tmp_path):
    cfg = EkfConfig(q_soc=3e-9, q_v=1e-8, r=2.5e-4, p0_soc_std=0.2, p0_v_std=0.05)
    cfg.to_json(tmp_path / "ekf_config.json")
    assert EkfConfig.from_json(tmp_path / "ekf_config.json") == cfg


# --- synthetic data: the filter on data from the model itself ---------------------------------------


@pytest.fixture(scope="module")
def synthetic():
    """The 1500 s of model voltage plus 5 mV noise that ekfsoc.synthetic draws, at 25 degC."""
    return synthetic_data(Params.from_csv(REPO_DIR / "results" / "params.csv"))


def test_filter_started_20_pp_wrong_converges_below_1_pp_and_stays(synthetic):
    s = synthetic
    soc0 = SOC_START - WRONG_INIT_PP / 100.0
    out = run_ekf(s["params"], SYNTHETIC_CFG, s["i"], s["v"], s["temp"], s["dt"], soc0)
    error_pp = np.abs(out["soc"] - s["soc_true"]) * 100.0
    last_quarter = len(error_pp) // 4  # by 375 s the error is under 1 pp, and it stays there to the end
    assert error_pp[last_quarter:].max() < 1.0


def test_covariance_stays_symmetric_and_positive_semidefinite(synthetic):
    s = synthetic
    ekf = Ekf(s["params"], SYNTHETIC_CFG, soc0=SOC_START - WRONG_INIT_PP / 100.0)
    worst_asymmetry = 0.0
    lowest_eigenvalue = math.inf
    for k in range(3000):  # the first 300 s hold the large corrections of the wrong start
        ekf.step(s["i"][k], s["v"][k], s["temp"][k], 0.0 if k == 0 else s["dt"][k])
        worst_asymmetry = max(worst_asymmetry, np.abs(ekf.P - ekf.P.T).max())
        lowest_eigenvalue = min(lowest_eigenvalue, np.linalg.eigvalsh(ekf.P).min())
    assert worst_asymmetry < 1e-14 and lowest_eigenvalue > -1e-14


# --- the SoC limit under a biased voltage (docs/decisions.md 1.16) ---------------------------------

BIAS_V = 0.030  # added to the voltage the filter measures
N_BIASED = 6000  # 600 s at 0.1 s


class TruncatingEkf(Ekf):
    """The filter with the SoC limit of the first full run: SoC is cut at the bounds, V1 and V2 are kept."""

    def limit_soc(self, x_post, P_post):
        x_cut = x_post.copy()
        x_cut[0] = min(max(x_cut[0], 0.0), 1.0)
        return x_cut


@pytest.fixture(scope="module")
def biased_discharge(synthetic):
    """600 s of a 3 A discharge from SoC 1 at 25 degC: the model voltage plus 30 mV, which the filter takes as measured."""
    dt = np.full(N_BIASED, 0.1)
    dt[0] = 0.0
    i = np.full(N_BIASED, 3.0)
    temp = np.full(N_BIASED, 25.0)
    soc_true = 1.0 - np.concatenate(([0.0], np.cumsum(i[:-1] * dt[1:]))) / (3600.0 * Q_REF_AH)
    v_model = simulate_2rc_open_loop(synthetic["params"], i, temp, soc_true, dt)
    return {"params": synthetic["params"], "i": i, "v": v_model + BIAS_V, "temp": temp, "dt": dt, "soc_true": soc_true}


def run_biased(ekf_class, data):
    """Run ekf_class over the biased discharge, started at the true SoC 1; return the SoC error (pp) and V2 (V) per sample."""
    ekf = ekf_class(data["params"], SYNTHETIC_CFG, soc0=1.0)
    soc_error_pp = np.zeros(N_BIASED)
    v2 = np.zeros(N_BIASED)
    for k in range(N_BIASED):
        ekf.step(data["i"][k], data["v"][k], data["temp"][k], data["dt"][k])
        soc_error_pp[k] = (ekf.x[0] - data["soc_true"][k]) * 100.0
        v2[k] = ekf.x[2]
    return soc_error_pp, v2


def test_projection_keeps_v2_bounded_under_a_voltage_bias(biased_discharge):
    soc_error_pp, v2 = run_biased(Ekf, biased_discharge)
    # A 30 mV bias costs a filter 30 mV / (OCV slope) of SoC, which no tuning removes. The 25 degC slope falls to
    # 0.32 V per unit SoC near 90 %, which the discharge crosses at about 300 s: up to 9.4 pp. So the SoC error
    # cannot stay under 3 pp for the 600 s (the run passes it at 110 s); it peaks at 7.8 pp at 515 s.
    assert np.abs(soc_error_pp).max() < 10.0
    assert np.abs(v2).max() < 0.3


def test_plain_truncation_lets_v2_run_away_under_the_same_bias(biased_discharge):
    soc_error_pp, v2 = run_biased(TruncatingEkf, biased_discharge)
    assert np.abs(v2).max() > 1.0  # it grows without bound (3.6e16 V here), and the SoC stays pinned at 100 %
    assert np.abs(soc_error_pp).max() > 10.0
