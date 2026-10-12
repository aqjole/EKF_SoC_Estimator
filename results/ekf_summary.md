# EKF results (S2)

Written by `python/run_all.py` (`make ekf`) from `results/ekf_results.csv`. Do not edit by hand.

Sanity gate: experiment 1 at 25 degC has a mean SoC RMSE of 0.87 pp over the 10 evaluation runs (tuning cycle excluded) and a maximum of 1.14 pp (Mix 3) over all 11 runs, against the limit of 3 pp. **PASS.** The limit is a bug check, not a published target.

## Legend

- 63 runs (the evaluation set and the tuning cycle), one row per run and experiment in `results/ekf_results.csv`. The noise settings are the frozen ones of `results/ekf_config.json`: q_soc = 1e-07 1/s, q_v = 1e-06 V^2/s, r = 0.01 V^2, and the same for every experiment and temperature.
- Error = estimate - reference; the reference follows the cycler's Ah counter (docs/model.md C4).
- Evaluation window: from the filter start to the last sample where the reference SoC is at least 10 % (docs/model.md C14). Every metric is over this window. Times are in s since the filter start.
- `*` marks the tuning cycle (Mix 1 at 25 degC), on which the noise settings were tuned for experiments 2 and 4 (the mean of their SoC RMSE, docs/decisions.md 1.16). `n/a`: no run exists. `not reached`: the error is outside the band at the end of the window, or the run is still apart from the run with the correct init; it is not an average.
- `mean` rows average the evaluation runs of the column (tuning cycle excluded); `mean of reached` leaves out the runs that did not reach; `reached` counts them.

## Experiment 1: correct initial SoC

SoC0 = the reference at the first row. The filter and plain coulomb counting are both scored.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.81 | 0.88 | 1.04 | 1.50 | 2.83 | 3.27 |
| HWFET | 0.80 | n/a | 0.96 | 2.67 | 3.79 | 3.09 |
| LA92 | 0.73 | 0.68 | 1.63 | 1.35 | 2.33 | 2.41 |
| US06 | 1.04 | 1.05 | 1.18 | 1.13 | 3.23 | 2.75 |
| Mix 1 | 0.69 | 0.61* | 0.90 | 1.98 | 2.39 | 2.59 |
| Mix 2 | 0.71 | 0.87 | 1.14 | 1.48 | 2.69 | 2.92 |
| Mix 3 | 0.73 | 1.14 | n/a | n/a | 3.11 | 1.90 |
| Mix 4 | n/a | 1.09 | 1.52 | 1.87 | n/a | 6.05 |
| Mix 5 | n/a | 0.69 | 1.22 | 2.06 | 2.70 | 2.64 |
| Mix 6 | n/a | 0.58 | 1.20 | 1.87 | 2.57 | 3.96 |
| Mix 7 | n/a | 0.80 | 1.11 | 1.76 | 3.74 | 3.64 |
| Mix 8 | n/a | 0.95 | 1.08 | 4.73 | 8.38 | 9.12 |
| **mean** | 0.79 | 0.87 | 1.18 | 2.04 | 3.43 | 3.70 |

### Coulomb counting against the reference: SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.11 | 0.02 | 0.00 | 0.02 | 0.12 | 0.03 |
| HWFET | 0.00 | n/a | 0.00 | 0.01 | 0.00 | 0.00 |
| LA92 | 0.09 | 0.06 | 0.02 | 0.04 | 0.02 | 0.04 |
| US06 | 0.01 | 0.03 | 0.13 | 0.18 | 0.03 | 0.13 |
| Mix 1 | 0.12 | 0.05* | 0.02 | 0.00 | 0.03 | 0.01 |
| Mix 2 | 0.03 | 0.02 | 0.00 | 0.03 | 0.01 | 0.00 |
| Mix 3 | 0.02 | 0.09 | n/a | n/a | 0.06 | 0.01 |
| Mix 4 | n/a | 0.01 | 0.02 | 0.04 | n/a | 0.01 |
| Mix 5 | n/a | 0.01 | 0.02 | 0.03 | 0.00 | 0.06 |
| Mix 6 | n/a | 0.01 | 0.03 | 0.05 | 0.10 | 0.02 |
| Mix 7 | n/a | 0.02 | 0.09 | 0.01 | 0.03 | 0.01 |
| Mix 8 | n/a | 0.08 | 0.03 | 0.03 | 0.09 | 0.03 |
| **mean** | 0.06 | 0.03 | 0.03 | 0.04 | 0.05 | 0.03 |

## Experiment 2: initial SoC 20 pp too low

SoC0 = the reference at the first row - 20 pp. The init-forgetting time is against experiment 1.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.84 | 0.90 | 1.02 | 1.48 | 2.80 | 3.49 |
| HWFET | 1.22 | n/a | 1.18 | 2.87 | 4.32 | 7.00 |
| LA92 | 0.80 | 0.69 | 2.00 | 1.32 | 2.38 | 2.73 |
| US06 | 0.99 | 0.93 | 1.20 | 1.22 | 3.21 | 2.50 |
| Mix 1 | 0.76 | 0.65* | 0.90 | 1.96 | 2.36 | 2.48 |
| Mix 2 | 0.78 | 0.90 | 1.17 | 1.48 | 2.65 | 2.89 |
| Mix 3 | 0.91 | 1.19 | n/a | n/a | 3.14 | 1.93 |
| Mix 4 | n/a | 1.04 | 1.51 | 2.37 | n/a | 16.97 |
| Mix 5 | n/a | 0.71 | 1.14 | 1.98 | 2.64 | 2.40 |
| Mix 6 | n/a | 0.61 | 1.27 | 1.77 | 2.35 | 3.53 |
| Mix 7 | n/a | 1.05 | 1.43 | 3.52 | 3.42 | 14.36 |
| Mix 8 | n/a | 0.95 | 1.06 | 6.26 | 9.65 | 23.71 |
| **mean** | 0.90 | 0.90 | 1.26 | 2.39 | 3.54 | 7.00 |

### Convergence time t_conv (s): the error stays within +-2 pp from then on

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | not reached | 14023.5 | 13997.2 | 13174.3 | 12118.2 | 7361.4 |
| HWFET | 912.6 | n/a | 3808.2 | 4406.0 | 4479.2 | 2829.5 |
| LA92 | 7.1 | 8136.2 | 8504.3 | 7622.1 | 7103.8 | not reached |
| US06 | 3188.5 | 3268.4 | 3285.6 | 3148.9 | not reached | not reached |
| Mix 1 | 7.1 | 2.4* | 6236.3 | 6221.5 | not reached | not reached |
| Mix 2 | 5.7 | 7235.2 | 6329.9 | 6668.9 | not reached | 3764.8 |
| Mix 3 | 891.2 | 6452.7 | n/a | n/a | not reached | 3845.9 |
| Mix 4 | n/a | not reached | 6272.3 | 6232.9 | n/a | 4249.0 |
| Mix 5 | n/a | 2.5 | 6089.8 | 5961.8 | not reached | 4130.3 |
| Mix 6 | n/a | 2.4 | 6781.1 | 5702.8 | 5304.9 | not reached |
| Mix 7 | n/a | 941.3 | 6227.2 | 5714.6 | not reached | not reached |
| Mix 8 | n/a | 7731.5 | 6687.5 | 7119.3 | not reached | not reached |
| **mean of reached** | 835.4 | 5310.4 | 6747.2 | 6543.0 | 7251.5 | 4363.5 |
| **reached** | 6 of 7 | 9 of 10 | 11 of 11 | 11 of 11 | 4 of 11 | 6 of 12 |

### Init-forgetting time (s): within +-1 pp of the run with the correct init

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 124.6 | 45.8 | 28.7 | 121.5 | 2917.5 | 2984.8 |
| HWFET | 816.7 | n/a | 791.1 | 136.7 | 1531.3 | not reached |
| LA92 | 72.7 | 5.1 | 1755.8 | 26.6 | 1820.7 | 3817.0 |
| US06 | 635.7 | 31.0 | 39.5 | 117.8 | 701.9 | 1373.8 |
| Mix 1 | 71.8 | 38.3* | 58.1 | 56.4 | 404.7 | 56.8 |
| Mix 2 | 80.8 | 17.5 | 6.5 | 78.9 | 207.1 | 206.9 |
| Mix 3 | 726.9 | 689.1 | n/a | n/a | 1974.1 | 15.8 |
| Mix 4 | n/a | 4.5 | 259.4 | 4723.7 | n/a | 3376.3 |
| Mix 5 | n/a | 43.3 | 30.7 | 147.8 | 4540.3 | 1134.0 |
| Mix 6 | n/a | 46.8 | 1054.8 | 158.4 | 1135.8 | 3172.3 |
| Mix 7 | n/a | 813.5 | 470.5 | 2893.1 | 2664.7 | not reached |
| Mix 8 | n/a | 31.4 | 59.3 | 3932.4 | 3523.4 | not reached |
| **mean of reached** | 361.3 | 172.8 | 414.0 | 1126.7 | 1947.4 | 1793.1 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 11 of 11 | 11 of 11 | 9 of 12 |

## Experiment 3, low start: initial SoC 50 % from a reference of 70 %

The filter starts where the reference first reaches 70 % with SoC0 = 50 %. The init-forgetting time is against the restart with SoC0 = 70 %.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 1.08 | 1.37 | 1.78 | 2.17 | 3.64 | 6.24 |
| HWFET | 1.17 | n/a | 2.37 | 4.63 | 8.06 | 13.09 |
| LA92 | 1.11 | 1.22 | 2.11 | 3.59 | 5.15 | 7.01 |
| US06 | 1.74 | 2.42 | 3.02 | 3.01 | 6.38 | 8.13 |
| Mix 1 | 1.34 | 1.52* | 1.98 | 3.39 | 3.82 | 8.51 |
| Mix 2 | 1.17 | 1.54 | 2.27 | 2.48 | 5.79 | 11.12 |
| Mix 3 | 1.16 | 1.92 | n/a | n/a | 7.39 | 7.75 |
| Mix 4 | n/a | 1.73 | 1.96 | 3.38 | n/a | 7.84 |
| Mix 5 | n/a | 1.15 | 1.95 | 3.39 | 5.27 | 8.37 |
| Mix 6 | n/a | 1.25 | 2.16 | 3.20 | 7.53 | 11.13 |
| Mix 7 | n/a | 1.38 | 2.31 | 2.81 | 6.67 | 11.08 |
| Mix 8 | n/a | 1.51 | 1.76 | 3.75 | 6.61 | 13.40 |
| **mean** | 1.25 | 1.55 | 2.15 | 3.25 | 6.03 | 9.47 |

### Convergence time t_conv (s): the error stays within +-2 pp from then on

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | not reached | 8634.3 | 8816.6 | 8253.7 | 7551.3 | not reached |
| HWFET | 184.6 | n/a | 2067.4 | 2719.1 | not reached | not reached |
| LA92 | 129.1 | 4863.3 | 5369.4 | 4866.9 | 4501.9 | not reached |
| US06 | 1959.1 | 2078.9 | 2113.7 | 2163.0 | not reached | not reached |
| Mix 1 | 390.7 | 667.2* | 4141.2 | 4166.5 | 3802.3 | not reached |
| Mix 2 | 170.1 | 4348.2 | 3580.6 | 3977.5 | not reached | 1418.4 |
| Mix 3 | 369.3 | 4630.7 | n/a | n/a | not reached | 1397.9 |
| Mix 4 | n/a | not reached | 3644.9 | 3802.2 | n/a | 1935.3 |
| Mix 5 | n/a | 124.9 | 4145.9 | 4059.9 | not reached | 2257.5 |
| Mix 6 | n/a | 157.2 | 4187.1 | 3217.7 | not reached | not reached |
| Mix 7 | n/a | 154.4 | 4057.8 | 3737.3 | not reached | not reached |
| Mix 8 | n/a | 4321.1 | 3314.2 | 3695.2 | not reached | not reached |
| **mean of reached** | 533.8 | 3257.0 | 4130.8 | 4059.9 | 5285.2 | 1752.3 |
| **reached** | 6 of 7 | 9 of 10 | 11 of 11 | 11 of 11 | 3 of 11 | 4 of 12 |

### Init-forgetting time (s): within +-1 pp of the run with the correct init

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 60.2 | 179.9 | 102.8 | 8.8 | 529.9 | 237.9 |
| HWFET | 153.2 | n/a | 6.2 | 948.1 | 242.5 | not reached |
| LA92 | 165.5 | 229.7 | 141.5 | 15.0 | 1177.0 | 42.3 |
| US06 | 94.5 | 18.8 | 5.5 | 96.9 | 198.1 | 107.7 |
| Mix 1 | 180.8 | 4.3* | 56.4 | 1530.7 | 715.1 | not reached |
| Mix 2 | 189.4 | 3.6 | 8.1 | 63.7 | 41.8 | 1285.9 |
| Mix 3 | 285.3 | 163.5 | n/a | n/a | 27.5 | 1401.8 |
| Mix 4 | n/a | 192.9 | 105.6 | 10.0 | n/a | 69.8 |
| Mix 5 | n/a | 5.0 | 197.6 | 1857.9 | 65.2 | not reached |
| Mix 6 | n/a | 62.2 | 7.2 | 1109.1 | 115.4 | 1303.9 |
| Mix 7 | n/a | 62.9 | 6.2 | 30.7 | 84.9 | 1252.0 |
| Mix 8 | n/a | 5.6 | 7.4 | 12.1 | 1459.2 | 1207.6 |
| **mean of reached** | 161.3 | 92.4 | 58.6 | 516.6 | 423.3 | 767.7 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 11 of 11 | 11 of 11 | 9 of 12 |

## Experiment 3, high start: initial SoC 90 % from a reference of 70 %

The same start with SoC0 = 90 %; the init-forgetting time is against the same restart.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 1.00 | 1.06 | 1.35 | 1.90 | 3.11 | 8.76 |
| HWFET | 0.57 | n/a | 2.38 | 3.65 | 7.26 | 12.02 |
| LA92 | 0.78 | 0.88 | 1.87 | 3.50 | 2.86 | 8.86 |
| US06 | 0.91 | 1.31 | 2.92 | 2.50 | 5.93 | 11.58 |
| Mix 1 | 0.79 | 0.81* | 1.74 | 3.72 | 3.57 | 6.77 |
| Mix 2 | 0.91 | 2.04 | 2.15 | 2.19 | 5.20 | 11.10 |
| Mix 3 | 0.73 | 1.42 | n/a | n/a | 7.16 | 5.69 |
| Mix 4 | n/a | 1.21 | 1.70 | 3.23 | n/a | 7.49 |
| Mix 5 | n/a | 1.03 | 1.60 | 4.18 | 5.11 | 5.61 |
| Mix 6 | n/a | 1.21 | 1.75 | 2.72 | 6.54 | 8.99 |
| Mix 7 | n/a | 1.37 | 1.57 | 2.14 | 6.02 | 11.15 |
| Mix 8 | n/a | 1.24 | 1.38 | 3.72 | 5.93 | 13.06 |
| **mean** | 0.81 | 1.28 | 1.86 | 3.04 | 5.34 | 9.26 |

### Convergence time t_conv (s): the error stays within +-2 pp from then on

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | not reached | 8634.3 | 8816.6 | 8253.7 | 7542.8 | 3820.0 |
| HWFET | 0.2 | n/a | 2564.1 | 2711.4 | not reached | 1823.7 |
| LA92 | 0.1 | 4858.3 | 5369.5 | 4866.9 | 4510.4 | not reached |
| US06 | 0.1 | 2014.8 | 2113.6 | 2164.5 | not reached | not reached |
| Mix 1 | 29.5 | 79.9* | 4141.1 | 4165.9 | 3798.8 | not reached |
| Mix 2 | 23.4 | 4339.5 | 3586.5 | 3977.5 | not reached | not reached |
| Mix 3 | 93.5 | 4629.9 | n/a | n/a | not reached | 1391.5 |
| Mix 4 | n/a | not reached | 3644.9 | 3802.2 | n/a | 1936.9 |
| Mix 5 | n/a | 340.1 | 4145.2 | 4057.0 | not reached | 2122.9 |
| Mix 6 | n/a | 1055.3 | 4188.1 | 3207.5 | not reached | not reached |
| Mix 7 | n/a | 1155.0 | 4088.6 | 3736.2 | not reached | not reached |
| Mix 8 | n/a | 4317.9 | 3314.2 | 3693.2 | not reached | not reached |
| **mean of reached** | 24.5 | 3482.8 | 4179.3 | 4057.8 | 5284.0 | 2219.0 |
| **reached** | 6 of 7 | 9 of 10 | 11 of 11 | 11 of 11 | 3 of 11 | 5 of 12 |

### Init-forgetting time (s): within +-1 pp of the run with the correct init

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 72.2 | 351.1 | 524.9 | 411.2 | 1166.0 | 3017.7 |
| HWFET | 99.8 | n/a | 1354.8 | 2268.4 | 457.5 | not reached |
| LA92 | 126.0 | 556.1 | 141.3 | 66.9 | 1181.5 | 1409.0 |
| US06 | 666.2 | 1874.1 | 25.3 | 97.6 | 286.8 | 1347.6 |
| Mix 1 | 170.0 | 582.3* | 64.2 | 1955.9 | 687.6 | not reached |
| Mix 2 | 173.7 | 2154.0 | 112.5 | 122.6 | 353.7 | not reached |
| Mix 3 | 99.6 | 274.0 | n/a | n/a | 534.3 | 529.2 |
| Mix 4 | n/a | 548.9 | 108.3 | 88.2 | n/a | 665.4 |
| Mix 5 | n/a | 423.9 | 75.3 | 1922.0 | 168.5 | not reached |
| Mix 6 | n/a | 376.6 | 1675.1 | 2673.8 | 338.8 | not reached |
| Mix 7 | n/a | 383.5 | 2099.7 | 1408.4 | 325.0 | 108.4 |
| Mix 8 | n/a | 438.5 | 281.9 | 155.5 | 416.5 | 99.7 |
| **mean of reached** | 201.1 | 738.1 | 587.6 | 1015.5 | 537.8 | 1025.3 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 11 of 11 | 11 of 11 | 7 of 12 |

## Experiment 4: current offset

The current seen by the filter and by coulomb counting is +0.200 A off (positive = discharge). The expected drift is what the offset does to a coulomb counter over the window.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 1.33 | 1.36 | 1.24 | 1.75 | 2.73 | 4.69 |
| HWFET | 1.03 | n/a | 1.17 | 2.95 | 3.98 | 4.01 |
| LA92 | 1.22 | 1.16 | 1.74 | 1.58 | 2.41 | 2.31 |
| US06 | 1.18 | 1.24 | 1.18 | 1.37 | 3.29 | 2.74 |
| Mix 1 | 1.08 | 0.85* | 0.92 | 1.91 | 2.65 | 2.85 |
| Mix 2 | 1.06 | 1.18 | 1.19 | 1.56 | 2.75 | 3.63 |
| Mix 3 | 1.31 | 1.74 | n/a | n/a | 3.13 | 1.67 |
| Mix 4 | n/a | 1.35 | 1.31 | 2.34 | n/a | 5.70 |
| Mix 5 | n/a | 0.81 | 1.13 | 1.99 | 2.77 | 2.35 |
| Mix 6 | n/a | 0.85 | 1.33 | 2.12 | 3.24 | 3.91 |
| Mix 7 | n/a | 1.09 | 1.14 | 1.96 | 3.68 | 3.56 |
| Mix 8 | n/a | 1.31 | 2.32 | 4.93 | 8.64 | 8.79 |
| **mean** | 1.17 | 1.21 | 1.33 | 2.22 | 3.57 | 3.85 |

### EKF error at the end of the window (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | -2.32 | -1.41 | -0.44 | -0.29 | +0.77 | +2.40 |
| HWFET | -0.99 | n/a | +0.59 | +1.04 | -1.31 | -0.35 |
| LA92 | -1.20 | -2.06 | -1.20 | -0.21 | +0.70 | +3.65 |
| US06 | -1.35 | -1.62 | +0.58 | +1.85 | +6.67 | +4.13 |
| Mix 1 | -1.78 | -1.68* | +0.85 | +0.16 | -1.80 | +3.45 |
| Mix 2 | -1.84 | -2.06 | +0.41 | +0.12 | +5.94 | +6.50 |
| Mix 3 | -1.33 | -1.99 | n/a | n/a | +6.42 | +0.42 |
| Mix 4 | n/a | -2.78 | +0.32 | +1.24 | n/a | -0.54 |
| Mix 5 | n/a | +0.30 | +0.97 | +0.16 | -2.19 | -0.11 |
| Mix 6 | n/a | -1.97 | -0.64 | -0.35 | -1.90 | +4.95 |
| Mix 7 | n/a | -1.87 | -0.44 | -0.58 | -2.23 | +2.53 |
| Mix 8 | n/a | -1.98 | -0.17 | -0.99 | -2.79 | +5.84 |
| **mean** | -1.54 | -1.74 | +0.07 | +0.20 | +0.75 | +2.74 |

### Coulomb counting error at the end of the window (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | -30.71 | -30.57 | -29.75 | -28.10 | -24.90 | -16.32 |
| HWFET | -9.91 | n/a | -10.56 | -9.94 | -8.97 | -6.66 |
| LA92 | -18.46 | -18.21 | -17.98 | -16.39 | -14.42 | -10.54 |
| US06 | -6.76 | -6.75 | -7.94 | -7.05 | -6.42 | -5.71 |
| Mix 1 | -13.99 | -13.83* | -14.42 | -13.45 | -12.55 | -9.07 |
| Mix 2 | -14.63 | -14.47 | -15.53 | -14.40 | -13.03 | -8.60 |
| Mix 3 | -13.49 | -13.23 | n/a | n/a | -11.13 | -9.01 |
| Mix 4 | n/a | -14.62 | -14.80 | -13.65 | n/a | -9.21 |
| Mix 5 | n/a | -12.76 | -13.45 | -12.95 | -12.00 | -9.17 |
| Mix 6 | n/a | -14.23 | -14.75 | -12.55 | -11.34 | -8.86 |
| Mix 7 | n/a | -13.26 | -13.99 | -12.31 | -11.13 | -8.14 |
| Mix 8 | n/a | -15.86 | -16.32 | -15.20 | -13.58 | -9.39 |
| **mean** | -15.42 | -15.39 | -15.41 | -14.18 | -12.68 | -9.22 |

### Expected coulomb-counting drift over the window (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | -30.52 | -30.50 | -29.75 | -28.06 | -24.69 | -16.36 |
| HWFET | -9.91 | n/a | -10.56 | -9.92 | -8.97 | -6.66 |
| LA92 | -18.32 | -18.12 | -17.94 | -16.32 | -14.42 | -10.50 |
| US06 | -6.75 | -6.70 | -7.74 | -6.75 | -6.38 | -5.51 |
| Mix 1 | -13.80 | -13.74* | -14.45 | -13.45 | -12.51 | -9.06 |
| Mix 2 | -14.55 | -14.50 | -15.53 | -14.44 | -13.04 | -8.60 |
| Mix 3 | -13.51 | -13.06 | n/a | n/a | -11.03 | -9.02 |
| Mix 4 | n/a | -14.60 | -14.77 | -13.59 | n/a | -9.20 |
| Mix 5 | n/a | -12.77 | -13.42 | -12.98 | -12.00 | -9.08 |
| Mix 6 | n/a | -14.21 | -14.69 | -12.48 | -11.18 | -8.83 |
| Mix 7 | n/a | -13.23 | -13.85 | -12.29 | -11.18 | -8.13 |
| Mix 8 | n/a | -15.71 | -16.27 | -15.15 | -13.45 | -9.34 |
| **mean** | -15.34 | -15.34 | -15.36 | -14.13 | -12.62 | -9.19 |

## Synthetic data

Data from the model itself: the 2RC model at 25 degC from `results/params.csv` on a made-up current (-2.0 to 6.0 A), 1500 s at 0.1 s, true SoC starting at 80 %, plus Gaussian voltage noise. This checks the filter apart from model mismatch. The filter uses the settings of the test, not the frozen ones: q_soc = 1e-08 1/s, q_v = 1e-08 V^2/s, r = 0.001 V^2.

| start | error stays within +-1 pp from (s) | RMSE after that (pp) |
|---|---|---|
| EKF started 20 pp low | 36.1 | 0.056 |
| EKF started 20 pp high | 220.1 | 0.093 |

Plot: `results/plots/s2/synthetic.png`.
