# Plots

Every figure here is written by a repo script; none is saved by hand. The fixed list and the reasons are in `docs/decisions.md` 1.14 (S5: 1.18 to 1.20; S6 to S11 follow 1.21 to 1.49).

| Folder | Written by | Files |
|---|---|---|
| `s1/` | `python/fit_all.py` (`make fit`) | `ocv.png`, `docv.png`, `params.png`, `model_fit_<T>degC.png` x 6 |
| `s2/` | `python/run_all.py` (`make ekf`) | `summary_rmse.png`, `summary_convergence.png`, `trace_<experiment>_<cycle>_<T>degC.png` x 16, `synthetic.png` |
| `s3/` | `python/compare_c.py` (`make equiv`) | `equivalence_<T>degC.png` x 6 |
| `s5/` | `python/sensitivity.py` (`make sensitivity`), `python/compare_octave.py` (`make octave`) | `sensitivity_capacity.png`, `sensitivity_rate.png`, `equivalence_octave_25degC.png` |
| `s6/` | `python/fit_3rc.py` (`make fit-3rc`), `python/fit_3rc_rest.py` (`make fit-3rc-rest`) | `params_3rc.png`, `params_3rc_rest.png` |
| `s7/` | `python/fit_r1_current.py` (`make fit-r1i`), `python/compare_r1i.py` (`make ekf-r1i`) | `r1_current.png`, `model_compare_r1i.png` |
| `s8/` | `python/compare_r1d.py` (`make ekf-r1d`), `python/fit_r1_charge.py` (`make fit-r1c`), `python/compare_r1c.py` (`make ekf-r1c`), `python/compare_r1l.py` (`make ekf-r1l`) | `model_compare_r1d.png`, `r1_charge.png`, `model_compare_r1c.png`, `model_compare_r1l.png` |
| `s9/` | `python/fit_3rcd.py` (`make fit-3rcd`), `python/compare_3rcd.py` (`make ekf-3rcd`) | `params_3rcd.png`, `model_compare_3rcd.png` |
| `s10/` | `python/diagnose_accuracy.py`, `python/fit_3rcd0.py`, `python/compare_3rcd0.py` | `accuracy_residuals.png`, `params_3rcd0.png`, `model_compare_3rcd0.png` |
| `s11/` | `python/tune_3rcd0.py` (`make tune-3rcd0`), `python/compare_3rcd0n.py` (`make ekf-3rcd0n`) | `tuning_3rcd0.png`, `model_compare_3rcd0n.png` |

Per-run traces for every evaluation run are not committed; `run_all.py` writes them to `results/runs/plots/` (gitignored).
