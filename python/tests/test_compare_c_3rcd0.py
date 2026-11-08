"""The restart inputs of the 3RC-D0 C equivalence (decision 1.54) and the generated C files of export_3rcd0.py."""

from types import SimpleNamespace

import numpy as np

import export_3rcd0
from compare_c_3rcd0 import write_inputs
from ekfsoc.model import Params
from export_params import source_text


RUN = SimpleNamespace(dt=np.array([0.0, 0.1, 0.1, 0.2]), i=np.array([1.0, 2.0, -1.0, 3.0]),
                      v=np.array([4.0, 3.9, 4.1, 3.8]), temp=np.array([25.0, 25.0, 25.1, 25.2]))


def test_restart_inputs_start_with_dt_zero_and_carry_the_offset(tmp_path):
    path = tmp_path / "inputs.csv"
    write_inputs(path, RUN, 2, 0.2)
    rows = np.loadtxt(path, delimiter=",", skiprows=1)
    np.testing.assert_array_equal(rows, [[0.0, -1.0 + 0.2, 4.1, 25.1], [0.2, 3.0 + 0.2, 3.8, 25.2]])


def test_committed_c_tables_match_the_3rcd0_parameters():
    params = Params.from_csv(export_3rcd0.PARAMS_CSV)
    assert export_3rcd0.SOURCE.read_text() == source_text(params, tables=export_3rcd0.TABLES, note=export_3rcd0.NOTE,
                                                          header=export_3rcd0.HEADER.name)
