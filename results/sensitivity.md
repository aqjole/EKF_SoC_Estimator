# Sensitivity (S5)

Written by `python/sensitivity.py` (`make sensitivity`) from `results/sensitivity.csv`. Do not edit by hand. Experiment 1 on the 63 runs (the evaluation set and the tuning cycle) with the frozen noise settings of `results/ekf_config.json` (q_soc = 1e-07 1/s, q_v = 1e-06 V^2/s, r = 0.01 V^2), with a wrong filter capacity (docs/decisions.md 1.18) and at 1 Hz (docs/decisions.md 1.19).

## Capacity error: the filter capacity at -5 % and +5 %

- The filter and the coulomb counter both believe 0.95 Q_ref and 1.05 Q_ref (Q_ref = 2.7807 Ah) and start from the reference SoC at the first row (experiment 1).
- Every cell is the mean SoC RMSE in pp over the evaluation window of the folder's runs; nominal is the experiment-1 value of `results/ekf_results.csv`; the reference SoC does not change.

| T (degC) | runs | EKF -5 % | EKF nominal | EKF +5 % | coulomb counting -5 % | coulomb counting nominal | coulomb counting +5 % |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 1.11 | 0.79 | 0.63 | 2.67 | 0.06 | 2.32 |
| 25 | 11 | 1.11 | 0.85 | 0.81 | 2.62 | 0.04 | 2.32 |
| 10 | 11 | 1.43 | 1.18 | 1.19 | 2.79 | 0.03 | 2.47 |
| 0 | 11 | 2.43 | 2.04 | 1.88 | 2.74 | 0.04 | 2.42 |
| -10 | 11 | 3.85 | 3.43 | 3.29 | 2.58 | 0.05 | 2.26 |
| -20 | 12 | 4.02 | 3.70 | 3.67 | 1.95 | 0.03 | 1.73 |
| all | 63 | 2.43 | 2.10 | 2.02 | 2.54 | 0.04 | 2.24 |

Largest per-run EKF RMSE: 9.35 pp (Mix 8 at -20 degC, -5 %); largest per-run coulomb-counting RMSE: 3.19 pp (US06 at 10 degC, -5 %).

Plot: `results/plots/s5/sensitivity_capacity.png`.

## Sample rate: every 10th row (1 Hz)

- The 1 Hz run keeps rows 0, 10, 20, ... of the loader's run and recomputes dt between them. The kept sample's current is held over the whole step (docs/model.md C11), the reference SoC is read at the kept rows and the evaluation window is C14 on them.
- RMSE cells are means over the folder's runs; max |error| cells are the largest over the folder's runs. The 0.1 s columns are experiment 1 of `results/ekf_results.csv`.

| T (degC) | runs | EKF RMSE 0.1 s | EKF RMSE 1 s | EKF max \|error\| 0.1 s | EKF max \|error\| 1 s | coulomb counting RMSE 0.1 s | coulomb counting RMSE 1 s |
|---|---|---|---|---|---|---|---|
| 40 | 7 | 0.79 | 0.66 | 2.27 | 2.10 | 0.06 | 0.43 |
| 25 | 11 | 0.85 | 0.70 | 3.34 | 2.28 | 0.04 | 0.53 |
| 10 | 11 | 1.18 | 1.12 | 5.01 | 3.84 | 0.03 | 0.58 |
| 0 | 11 | 2.04 | 1.65 | 10.20 | 5.41 | 0.04 | 0.54 |
| -10 | 11 | 3.43 | 3.00 | 15.57 | 9.60 | 0.05 | 0.56 |
| -20 | 12 | 3.70 | 3.79 | 18.53 | 11.57 | 0.03 | 0.25 |
| all | 63 | 2.10 | 1.92 | 18.53 | 11.57 | 0.04 | 0.48 |

Plot: `results/plots/s5/sensitivity_rate.png`.
