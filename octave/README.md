# Octave port of the filter

The extended Kalman filter of `python/ekfsoc/ekf.py` and its table lookup from `python/ekfsoc/model.py`, in plain GNU Octave (double precision, no packages, Octave 8 or newer). Only the filter is ported: it reads the parameter tables from `results/s1/params.csv` and the filter inputs from the CSV format of `c/tools/ekf_run_csv`. The rules of the port are in `docs/decisions.md` 1.20; the equations are those of `docs/model.md`.

## Command line

```
octave-cli octave/ekf_run_csv.m <in.csv> <out.csv> <q_soc> <q_v> <r> <soc0>
```

The arguments are those of `c/tools/ekf_run_csv`. `in.csv` names the columns `dt_s`, `i_a`, `v_v` and `t_degc` in its header, in any order; other columns are ignored. `out.csv` gets a header `soc` and one SoC per input row with 17 significant digits. The script finds its sibling functions and `results/s1/params.csv` from its own location, so it runs from any directory.

## Files

| file | mirrors |
|---|---|
| `ekf_run_csv.m` | `c/tools/ekf_run_csv.c` (the command line) and the loop of `run_ekf` |
| `ekf_init.m` | `Ekf.__init__` |
| `ekf_step.m` | `Ekf.step` |
| `ekf_predict.m` | `Ekf.predict` (Eq. 6, Eq. 7) |
| `ekf_update.m` | `Ekf.update` (Eq. 8 to Eq. 11) |
| `limit_soc.m` | `Ekf.limit_soc` (Eq. 10) |
| `ekf_lookup.m` | `Ekf.lookup` |
| `interp2_clamped.m` | `model.interp2` (Eq. 4); renamed so as not to shadow Octave's `interp2` |
| `find_cell.m` | `model.find_cell` (Eq. 4) |
| `read_params.m` | `Params.from_csv` |
| `read_inputs.m`, `read_header.m` | the CSV reading of `c/tools/ekf_run_csv.c` |

## Checks

`python/compare_octave.py` (`make octave`) runs the port on every evaluation run and compares its SoC with the Python trace, writing `results/s5/equivalence_octave.md`. `python/compare_octave.py --fixtures` runs it on the three fixtures of `c/tests/fixtures/` against their `soc_expected`; CI runs that mode with Ubuntu's Octave.
