"""Tests for ekfsoc.fit.

Synthetic: HPPC-like data is generated from the 2RC model with known parameters (model.simulate_2rc_open_loop
with flat tables and a sloped OCV), and the two fits must recover them. Data (needs data/raw/): fit_hppc_run
on the real HPPC files.
"""

import numpy as np
import pytest

from ekfsoc.constants import FOLDER_TEMP, RAW_DIR, SOC_GRID, T_GRID_DEGC
from ekfsoc.fit import TAU1_BOUNDS_S, TAU2_BOUNDS_S, fit_hppc_run, fit_level_fast, fit_level_slow
from ekfsoc.hppc import Level, segment_hppc
from ekfsoc.loader import build_run, find_runs, load_run, soc_ref
from ekfsoc.model import Params, simulate_2rc_open_loop
from ekfsoc.ocv import OcvTable, build_ocv

R0, R1, TAU1 = 0.020, 0.010, 8.0   # Ohm, Ohm, s
R2, TAU2 = 0.005, 400.0            # Ohm, s


N_T = len(T_GRID_DEGC)


def flat_table(value):
    return np.full((N_T, len(SOC_GRID)), value)


# The true constants as Params, and the matching OcvTable. OCV = 3.2 + 0.8 * SoC at every temperature.
OCV = 3.2 + 0.8 * np.tile(SOC_GRID, (N_T, 1))
SYNTHETIC_PARAMS = Params(T_GRID_DEGC, SOC_GRID, OCV, flat_table(0.8), flat_table(R0), flat_table(R1),
                          flat_table(TAU1), flat_table(R2), flat_table(TAU2))
SYNTHETIC_OCV_TABLE = OcvTable(SOC_GRID, np.array(T_GRID_DEGC, dtype=float), OCV, flat_table(0.8), OCV,
                               flat_table(0.0), np.zeros(N_T), np.ones(N_T), np.ones(N_T, dtype=bool), False)


def synthetic_run(blocks):
    """A 25 degC Run whose voltage is the 2RC model's, from blocks (current in A, loader sign; seconds; step in s)."""
    current, dt = [], []
    for amps, seconds, step in blocks:
        n_rows = round(seconds / step)
        current += [amps] * n_rows
        dt += [step] * n_rows
    current = np.array(current)
    dt = np.array(dt)
    dt[0] = 0.0
    time = np.cumsum(dt)
    # The counter falls on discharge; the current of each row is held over the step that follows it.
    counter = np.concatenate(([0.0], np.cumsum(-current[:-1] * dt[1:]) / 3600.0))
    fields = {"Time": time, "Voltage": np.full(len(time), 3.7), "Current": -current, "Ah": counter,
              "Battery_Temp_degC": np.full(len(time), 25.0)}
    run = build_run(fields, "synthetic_hppc", "25degC", "hppc")
    run.v = simulate_2rc_open_loop(SYNTHETIC_PARAMS, run.i, run.temp, soc_ref(run), run.dt)
    return run


def pulse_level_blocks():
    """D1 C1 D2 C2 D3 C3 D4 C4: 10 s pulses at 0.1 s, a 40 s rest after each D and a 100 s rest after each C."""
    blocks = []
    for number, d_amps in enumerate((3.0, 6.0, 12.0, 18.0), start=1):
        blocks += [(d_amps, 10, 0.1), (0.0, 40, 0.1), (-1.5 * number, 10, 0.1), (0.0, 100, 1.0)]
    return blocks


def test_fast_fit_recovers_r0_r1_tau1_from_synthetic_pulses():
    run = synthetic_run([(0.0, 10, 1.0)] + pulse_level_blocks())
    (level,) = segment_hppc(run)
    fast = fit_level_fast(run, level, SYNTHETIC_OCV_TABLE)
    assert fast["fast_ok"]
    assert fast["n_pulses_used"] == 4
    assert [fast["R0_ohm"], fast["R1_ohm"], fast["tau1_s"]] == pytest.approx([R0, R1, TAU1], rel=0.05)


def test_slow_fit_recovers_r2_tau2_from_a_synthetic_move_and_rest():
    """A 240 s move at 0.9 A, then a 3600 s rest logged at 10 s with a 0.1 s tail, as in the HPPC files."""
    run = synthetic_run([(0.0, 10, 1.0), (0.9, 240, 10.0), (0.0, 3590, 10.0), (0.0, 10, 0.1)])
    move_start, rest_start = 10, 34
    soc = soc_ref(run)
    level = Level(k=1, soc_pulses=1.0, pulses=[], move=slice(move_start, rest_start),
                  rest_after_move=slice(rest_start, len(run.t)), soc_after_move=float(soc[rest_start - 1]))
    fast = {"R0_ohm": R0, "R1_ohm": R1, "tau1_s": TAU1, "fast_ok": True}
    slow = fit_level_slow(run, level, fast, SYNTHETIC_OCV_TABLE)
    assert slow["slow_ok"]
    assert [slow["R2_ohm"], slow["tau2_s"]] == pytest.approx([R2, TAU2], rel=0.05)


def test_fast_fit_without_a_usable_pulse_returns_none_and_a_flag():
    run = synthetic_run([(0.0, 10, 1.0)] + pulse_level_blocks())
    fast = fit_level_fast(run, Level(1, 1.0, [], None, None, None), SYNTHETIC_OCV_TABLE)
    assert (fast["fast_ok"], fast["R0_ohm"], fast["R1_ohm"], fast["tau1_s"]) == (False, None, None, None)


def test_slow_fit_after_a_failed_fast_fit_returns_none_and_a_flag():
    run = synthetic_run([(0.0, 10, 1.0), (0.9, 240, 10.0), (0.0, 600, 10.0)])
    level = Level(1, 1.0, [], slice(10, 34), slice(34, len(run.t)), 0.9)
    slow = fit_level_slow(run, level, {"fast_ok": False}, SYNTHETIC_OCV_TABLE)
    assert (slow["slow_ok"], slow["R2_ohm"], slow["tau2_s"]) == (False, None, None)


# Real files (need data/raw/)


@pytest.fixture(scope="module")
def hppc_fits():
    """{folder: (Run, fit_hppc_run rows)} for the six HPPC files, fitted once."""
    c20_runs = {}
    for folder, temp_degc in FOLDER_TEMP.items():
        (path,) = find_runs(RAW_DIR, test_type="c20", folder=folder)
        c20_runs[temp_degc] = load_run(path)
    ocv_table = build_ocv(c20_runs, SOC_GRID, T_GRID_DEGC)

    fits = {}
    for folder in FOLDER_TEMP:
        (path,) = find_runs(RAW_DIR, test_type="hppc", folder=folder)
        run = load_run(path)
        fits[folder] = (run, fit_hppc_run(run, ocv_table))
    return fits


@pytest.mark.needs_data
@pytest.mark.parametrize("folder", list(FOLDER_TEMP))
def test_fitted_time_constants_and_rmse_are_inside_the_bounds_and_finite(hppc_fits, folder):
    _, rows = hppc_fits[folder]
    assert all(row["fast_ok"] for row in rows)
    assert all(TAU1_BOUNDS_S[0] <= row["tau1_s"] <= TAU1_BOUNDS_S[1] for row in rows)
    assert all(np.isfinite(row["rmse_fast_mV"]) for row in rows)

    with_rest = rows[:-1]
    assert all(row["slow_ok"] for row in with_rest)
    assert all(TAU2_BOUNDS_S[0] <= row["tau2_s"] <= TAU2_BOUNDS_S[1] for row in with_rest)
    assert all(np.isfinite(row["rmse_slow_mV"]) for row in with_rest)


@pytest.mark.needs_data
def test_the_last_level_has_no_slow_fit(hppc_fits):
    _, rows = hppc_fits["25degC"]
    assert (rows[-1]["soc_rest"], rows[-1]["R2_ohm"], rows[-1]["tau2_s"], rows[-1]["slow_ok"]) == (None,) * 4


@pytest.mark.needs_data
def test_25degc_first_level_r0_is_near_the_voltage_step_of_its_pulses(hppc_fits):
    """The step of each usable discharge pulse, read at its first row with current: V drop over I rise."""
    run, rows = hppc_fits["25degC"]
    (level,) = [level for level in segment_hppc(run) if level.k == 1]
    steps = []
    for pulse in level.pulses:
        if pulse.kind == "D" and pulse.usable:
            first, before = pulse.rows.start, pulse.rows.start - 1
            steps.append((run.v[before] - run.v[first]) / (run.i[first] - run.i[before]))
    assert rows[0]["R0_ohm"] == pytest.approx(float(np.median(steps)), rel=0.30)
