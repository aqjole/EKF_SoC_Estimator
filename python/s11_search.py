"""Calibration objective and native/reference checks for S11 (decisions 1.49–1.50)."""

from functools import cache

import numpy as np

from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.loader import load_run, soc_ref
from ekfsoc.metrics import rmse_pp, window_mask
from fit_3rcd0 import load_candidate
from s10_protocol import splits
from s11_native import NativeModel


def config(point):
    return EkfConfig(*point[:3], p0_v_std=point[3])


@cache
def problem():
    params = load_candidate()
    data = []
    for spec in splits()[0]:
        run = load_run(spec.path)
        reference = soc_ref(run)
        data.append((spec, run, reference, window_mask(reference, 0)))
    return params, NativeModel(params), data


def balanced_halves(rows):
    """Equal temperature weight, then equal run weight, separately for exp2 and exp4."""
    return [float(np.mean([np.mean([row[k + 1] for row in rows if row[0] == temp])
                           for temp in sorted({row[0] for row in rows})])) for k in range(2)]


def objective(point):
    _, native, data = problem()
    cfg = config(point)
    rows = []
    for spec, run, ref, window in data:
        errors = [rmse_pp(native.run(run, cfg, ref[0] - delta, offset)["soc"] - ref, window)
                  for delta, offset in ((.2, 0.), (0., .2))]
        rows.append((spec.nominal_temp_degc, *errors))
    return float(np.mean(balanced_halves(rows)))


def score_point(task):
    index, point = task
    return index, objective(point)


def reference_run(task):
    """Full Python objective contribution, with a native agreement check on this run."""
    spec, point = task
    params = load_candidate()
    native = NativeModel(params)
    run = load_run(spec.path)
    ref, cfg = soc_ref(run), config(point)
    window = window_mask(ref, 0)
    errors = []
    for delta, offset in ((.2, 0.), (0., .2)):
        result = run_ekf(params, cfg, run.i, run.v, run.temp, run.dt, ref[0] - delta,
                         current_offset=offset)
        fast = native.run(run, cfg, ref[0] - delta, offset)
        for name in ("soc", "v_pred"):
            np.testing.assert_allclose(fast[name], result[name], rtol=0, atol=1e-8)
        error = rmse_pp(result["soc"] - ref, window)
        assert abs(error - rmse_pp(fast["soc"] - ref, window)) <= 1e-6
        errors.append(error)
    return (spec.nominal_temp_degc, *errors)


def reference_objective(pool, point):
    rows = pool.map(reference_run, [(spec, point) for spec in splits()[0]], chunksize=1)
    return balanced_halves(rows)


def validate_native(pool):
    """Every temperature, including cold Mix 8; incumbent and both extreme settings."""
    mix, _ = splits()
    specs = [next(s for s in reversed(mix) if s.nominal_temp_degc == temp)
             for temp in sorted({s.nominal_temp_degc for s in mix})]
    points = [(1e-7, 1e-6, .01, .05), (1e-12, 1e-8, 1e-6, .015), (1e-5, 1e-3, .1, .15)]
    pool.map(reference_run, [(spec, point) for spec in specs for point in points], chunksize=1)
