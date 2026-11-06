"""Check the 3RC-D regressor against the reference simulator on synthetic data."""

from types import SimpleNamespace

import numpy as np
import pytest

from ekfsoc.model import Params
from fit_3rcd import basis_tables, fit_nodes, make_params, regressors, voltage


@pytest.fixture
def base():
    soc = np.linspace(0, 1, 101)
    surface = np.tile(soc, (2, 1))
    return Params([25, 10], soc, 3.2 + surface, np.ones_like(surface),
                  0.02 + 0.001 * surface, 0.01 + 0.002 * surface, 4 + surface,
                  0.03 - 0.015 * surface, 280 - 60 * surface)


def test_regressors_match_full_simulation(base):
    t = np.arange(2000) * 0.3
    run = SimpleNamespace(i=1 + 3 * np.sin(t / 9), temp=18 + 9 * np.sin(t / 65),
                          dt=np.r_[0, 0.3 + 0.07 * np.sin(t[1:])])
    soc = np.linspace(1, 0, len(t))
    basis = basis_tables(base)
    values = np.r_[np.linspace(0, 0.04, 8), np.linspace(-0.4, 0.6, 8)]
    x, _ = regressors(base, basis, run, soc, np.arange(0, len(t), 10))
    expected = voltage(base, run, soc) + x @ values
    actual = voltage(make_params(base, basis, values), run, soc)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)


def test_fit_recovers_supported_node_and_leaves_empty_nodes_at_incumbent(base):
    t = np.arange(3200) * 0.5
    run = SimpleNamespace(i=1 + 4 * np.sin(t / 40), temp=np.full_like(t, 25),
                          dt=np.r_[0, np.full(len(t) - 1, 0.5)])
    soc = np.full_like(t, 0.7)
    basis = basis_tables(base)
    values = np.zeros(16)
    values[[2, 10]] = [0.035, -0.4]
    x, support = regressors(base, basis, run, soc, np.arange(len(t)))
    measured = voltage(make_params(base, basis, values), run, soc)
    fitted, _, _ = fit_nodes(x, measured - voltage(base, run, soc), support)
    np.testing.assert_allclose(fitted, values, rtol=0, atol=1e-12)
