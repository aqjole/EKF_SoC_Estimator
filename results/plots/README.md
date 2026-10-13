# Plots

Every figure here is written by a repo script; none is saved by hand. The fixed list and the reasons are in `docs/decisions.md` 1.14 (S5: 1.18 to 1.20).

| Folder | Written by | Files |
|---|---|---|
| `s1/` | `python/fit_all.py` (`make fit`) | `ocv.png`, `docv.png`, `params.png`, `model_fit_<T>degC.png` x 6 |
| `s2/` | `python/run_all.py` (`make ekf`) | `summary_rmse.png`, `summary_convergence.png`, `trace_<experiment>_<cycle>_<T>degC.png` x 16, `synthetic.png` |
| `s3/` | `python/compare_c.py` (`make equiv`) | `equivalence_<T>degC.png` x 6 |
| `s5/` | `python/sensitivity.py` (`make sensitivity`), `python/compare_octave.py` (`make octave`) | `sensitivity_capacity.png`, `sensitivity_rate.png`, `equivalence_octave_25degC.png` |

Per-run traces for every evaluation run are not committed; `run_all.py` writes them to `results/runs/plots/` (gitignored).
