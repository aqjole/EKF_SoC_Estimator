# EKF results (S2)

Written by `python/run_all.py` (`make ekf`) from `results/ekf_results.csv`. Do not edit by hand.

Sanity gate: experiment 1 at 25 degC has a mean SoC RMSE of 2.07 pp over the 10 evaluation runs (tuning cycle excluded) and a maximum of 14.70 pp (LA92) over all 11 runs, against the limit of 3 pp. **FAIL.** The limit is a bug check, not a published target.

## Legend

- 63 runs (the evaluation set and the tuning cycle), one row per run and experiment in `results/ekf_results.csv`. The noise settings are the frozen ones of `results/ekf_config.json`: q_soc = 3.33e-11 1/s, q_v = 1e-08 V^2/s, r = 0.01 V^2, and the same for every experiment and temperature.
- Error = estimate - reference; the reference follows the cycler's Ah counter (docs/model.md C4).
- Evaluation window: from the filter start to the last sample where the reference SoC is at least 10 % (docs/model.md C14). Every metric is over this window. Times are in s since the filter start.
- `*` marks the tuning cycle (Mix 1 at 25 degC), on which the noise settings were tuned for experiment 2. `n/a`: no run exists. `not reached`: the error is outside the band at the end of the window, or the run is still apart from the run with the correct init; it is not an average.
- `mean` rows average the evaluation runs of the column (tuning cycle excluded); `mean of reached` leaves out the runs that did not reach; `reached` counts them.

## Experiment 1: correct initial SoC

SoC0 = the reference at the first row. The filter and plain coulomb counting are both scored.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.62 | 0.71 | 0.90 | 6.05 | 12.33 | 14.27 |
| HWFET | 1.04 | n/a | 0.82 | 1.61 | 3.11 | 3.42 |
| LA92 | 0.66 | 14.70 | 1.50 | 1.45 | 19.98 | 18.21 |
| US06 | 1.19 | 0.97 | 0.97 | 52.36 | 49.34 | 2.70 |
| Mix 1 | 0.57 | 0.30* | 20.47 | 28.41 | 23.25 | 9.58 |
| Mix 2 | 0.42 | 0.38 | 0.84 | 11.08 | 15.07 | 25.36 |
| Mix 3 | 0.86 | 0.74 | n/a | n/a | 36.14 | 34.41 |
| Mix 4 | n/a | 0.48 | 1.84 | 1.29 | n/a | 4.48 |
| Mix 5 | n/a | 0.61 | 0.72 | 7.85 | 22.38 | 19.87 |
| Mix 6 | n/a | 0.58 | 20.55 | 24.66 | 26.35 | 24.90 |
| Mix 7 | n/a | 0.89 | 1.02 | 1.20 | 3.48 | 4.69 |
| Mix 8 | n/a | 0.62 | 7.54 | 3.51 | 6.05 | 9.19 |
| **mean** | 0.77 | 2.07 | 5.20 | 12.68 | 19.77 | 14.26 |

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
| UDDS | 0.68 | 0.74 | 0.95 | 1.40 | 3.01 | 4.54 |
| HWFET | 1.47 | n/a | 1.08 | 1.66 | 2.76 | 3.70 |
| LA92 | 0.74 | 0.58 | 2.09 | 1.48 | 2.26 | 2.14 |
| US06 | 0.88 | 0.71 | 1.18 | 28.12 | 13.47 | 1.58 |
| Mix 1 | 0.64 | 0.35* | 1.39 | 7.05 | 3.56 | 2.92 |
| Mix 2 | 0.52 | 0.44 | 0.87 | 1.10 | 2.45 | 2.84 |
| Mix 3 | 0.95 | 0.79 | n/a | n/a | 2.30 | 2.26 |
| Mix 4 | n/a | 0.47 | 1.17 | 1.58 | n/a | 7.08 |
| Mix 5 | n/a | 0.66 | 0.73 | 0.94 | 2.30 | 1.71 |
| Mix 6 | n/a | 0.64 | 1.26 | 16.44 | 6.04 | 4.88 |
| Mix 7 | n/a | 0.98 | 1.22 | 2.52 | 2.82 | 7.86 |
| Mix 8 | n/a | 0.67 | 0.95 | 4.42 | 6.92 | 9.21 |
| **mean** | 0.84 | 0.67 | 1.17 | 6.07 | 4.35 | 4.23 |

### Convergence time t_conv (s): the error stays within +-2 pp from then on

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 7.5 | 2.4 | 2.2 | 3136.5 | not reached | not reached |
| HWFET | 916.6 | n/a | 1086.1 | 4487.5 | not reached | 2476.7 |
| LA92 | 7.1 | 0.9 | 6623.9 | 6311.2 | not reached | not reached |
| US06 | 7.5 | 2.4 | 1871.0 | not reached | not reached | 2398.6 |
| Mix 1 | 7.1 | 2.4* | 817.3 | not reached | 5588.1 | not reached |
| Mix 2 | 5.7 | 2.7 | 3.2 | 6747.6 | not reached | not reached |
| Mix 3 | 983.1 | 868.0 | n/a | n/a | not reached | not reached |
| Mix 4 | n/a | 1.2 | 495.6 | 6283.2 | n/a | not reached |
| Mix 5 | n/a | 2.5 | 2.1 | 5926.7 | not reached | not reached |
| Mix 6 | n/a | 2.4 | 787.4 | not reached | not reached | not reached |
| Mix 7 | n/a | 493.9 | 1003.1 | 4541.4 | not reached | not reached |
| Mix 8 | n/a | 1.3 | 57.9 | 7051.3 | not reached | not reached |
| **mean of reached** | 276.4 | 137.8 | 1159.1 | 5560.7 | 5588.1 | 2437.6 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 8 of 11 | 1 of 11 | 2 of 12 |

### Init-forgetting time (s): within +-1 pp of the run with the correct init

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 99.3 | 42.7 | 28.1 | not reached | not reached | not reached |
| HWFET | 638.0 | n/a | 767.6 | 360.4 | 2289.2 | not reached |
| LA92 | 77.3 | not reached | 1449.2 | 1046.0 | not reached | not reached |
| US06 | 721.5 | 683.6 | 627.3 | not reached | not reached | 2018.0 |
| Mix 1 | 69.3 | 34.5* | not reached | not reached | not reached | not reached |
| Mix 2 | 116.5 | 31.4 | 6.5 | not reached | not reached | not reached |
| Mix 3 | 677.9 | 613.6 | n/a | n/a | not reached | not reached |
| Mix 4 | n/a | 7.5 | 2203.5 | 4629.0 | n/a | 1080.1 |
| Mix 5 | n/a | 40.4 | 30.4 | not reached | not reached | not reached |
| Mix 6 | n/a | 43.4 | not reached | not reached | not reached | not reached |
| Mix 7 | n/a | 826.1 | 588.3 | 314.2 | 2805.1 | 562.4 |
| Mix 8 | n/a | 61.2 | not reached | 748.6 | 1880.9 | 1786.7 |
| **mean of reached** | 342.8 | 261.1 | 712.6 | 1419.6 | 2325.1 | 1361.8 |
| **reached** | 7 of 7 | 9 of 10 | 8 of 11 | 5 of 11 | 3 of 11 | 4 of 12 |

## Experiment 3, low start: initial SoC 50 % from a reference of 70 %

The filter starts where the reference first reaches 70 % with SoC0 = 50 %. The init-forgetting time is against the restart with SoC0 = 70 %.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.88 | 0.95 | 1.18 | 2.40 | 3.67 | 7.13 |
| HWFET | 1.01 | n/a | 2.42 | 5.86 | 7.49 | 12.18 |
| LA92 | 0.79 | 0.93 | 1.91 | 2.99 | 4.54 | 8.42 |
| US06 | 1.39 | 2.78 | 2.23 | 3.69 | 6.88 | 9.90 |
| Mix 1 | 1.06 | 1.21* | 1.74 | 4.31 | 6.59 | 10.65 |
| Mix 2 | 1.28 | 2.92 | 1.87 | 2.95 | 4.95 | 9.53 |
| Mix 3 | 0.82 | 0.97 | n/a | n/a | 5.62 | 9.14 |
| Mix 4 | n/a | 1.08 | 2.00 | 3.32 | n/a | 11.46 |
| Mix 5 | n/a | 1.73 | 2.28 | 6.15 | 5.42 | 8.78 |
| Mix 6 | n/a | 1.82 | 2.23 | 5.97 | 7.09 | 10.83 |
| Mix 7 | n/a | 1.96 | 2.46 | 7.84 | 6.84 | 12.31 |
| Mix 8 | n/a | 1.64 | 2.29 | 3.32 | 6.17 | 13.39 |
| **mean** | 1.03 | 1.68 | 2.06 | 4.44 | 5.93 | 10.31 |

### Convergence time t_conv (s): the error stays within +-2 pp from then on

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 254.5 | 410.9 | 643.4 | 2913.9 | not reached | not reached |
| HWFET | 146.7 | n/a | 2042.3 | 2822.8 | not reached | 1769.0 |
| LA92 | 103.3 | 266.5 | 3750.1 | 4394.6 | not reached | not reached |
| US06 | 120.4 | 998.4 | 1761.8 | 1868.7 | 1935.9 | not reached |
| Mix 1 | 126.6 | 312.7* | 581.5 | 4192.0 | not reached | not reached |
| Mix 2 | 788.1 | 2067.3 | 938.9 | 4119.5 | not reached | not reached |
| Mix 3 | 190.9 | 256.8 | n/a | n/a | not reached | not reached |
| Mix 4 | n/a | 158.5 | 3687.8 | 3883.8 | n/a | not reached |
| Mix 5 | n/a | 485.4 | 1517.1 | 4087.8 | not reached | not reached |
| Mix 6 | n/a | 869.1 | 2492.4 | 2791.6 | not reached | 1839.8 |
| Mix 7 | n/a | 1331.5 | 1620.5 | 3068.6 | not reached | not reached |
| Mix 8 | n/a | 692.8 | 3127.6 | 3766.7 | not reached | not reached |
| **mean of reached** | 247.2 | 753.7 | 2014.9 | 3446.4 | 1935.9 | 1804.4 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 11 of 11 | 1 of 11 | 2 of 12 |

### Init-forgetting time (s): within +-1 pp of the run with the correct init

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 54.1 | 122.6 | 61.5 | 8.7 | 94.9 | 353.6 |
| HWFET | 107.5 | n/a | 6.2 | 1341.9 | 118.6 | 157.2 |
| LA92 | 129.9 | 216.8 | 136.2 | 14.8 | 216.9 | 255.8 |
| US06 | 107.1 | 18.7 | 5.5 | 82.2 | 8.1 | 65.3 |
| Mix 1 | 145.2 | 4.3* | 416.8 | 120.9 | 227.9 | 700.9 |
| Mix 2 | 150.0 | 3.5 | 8.0 | 1047.4 | 39.5 | 430.1 |
| Mix 3 | 90.0 | 91.5 | n/a | n/a | 923.2 | 1054.3 |
| Mix 4 | n/a | 216.7 | 348.7 | 352.3 | n/a | 157.9 |
| Mix 5 | n/a | 243.6 | 568.1 | 2325.7 | 55.9 | 539.7 |
| Mix 6 | n/a | 208.7 | 7.2 | 1725.8 | 70.5 | 337.7 |
| Mix 7 | n/a | 217.4 | 6.1 | 518.0 | 62.6 | 192.2 |
| Mix 8 | n/a | 215.4 | 499.1 | 785.1 | 16.0 | 140.5 |
| **mean of reached** | 112.0 | 155.5 | 187.6 | 756.6 | 166.7 | 365.4 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 11 of 11 | 11 of 11 | 12 of 12 |

## Experiment 3, high start: initial SoC 90 % from a reference of 70 %

The same start with SoC0 = 90 %; the init-forgetting time is against the same restart.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 0.83 | 0.87 | 0.93 | 2.08 | 3.60 | 7.05 |
| HWFET | 0.44 | n/a | 1.76 | 6.07 | 7.19 | 12.05 |
| LA92 | 0.46 | 0.71 | 1.60 | 2.89 | 3.99 | 8.62 |
| US06 | 0.69 | 2.28 | 2.17 | 3.45 | 6.59 | 10.43 |
| Mix 1 | 0.68 | 0.76* | 1.75 | 4.31 | 6.64 | 10.24 |
| Mix 2 | 0.84 | 2.63 | 1.60 | 3.29 | 4.59 | 8.35 |
| Mix 3 | 0.49 | 0.57 | n/a | n/a | 5.25 | 8.92 |
| Mix 4 | n/a | 0.79 | 1.69 | 3.16 | n/a | 11.21 |
| Mix 5 | n/a | 1.81 | 2.90 | 7.59 | 4.92 | 8.29 |
| Mix 6 | n/a | 1.51 | 1.67 | 5.77 | 6.62 | 10.10 |
| Mix 7 | n/a | 1.66 | 1.80 | 8.45 | 6.55 | 12.46 |
| Mix 8 | n/a | 1.15 | 2.30 | 3.59 | 5.85 | 13.07 |
| **mean** | 0.63 | 1.40 | 1.83 | 4.61 | 5.62 | 10.07 |

### Convergence time t_conv (s): the error stays within +-2 pp from then on

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 92.0 | 405.0 | 641.8 | 2827.0 | not reached | not reached |
| HWFET | 89.0 | n/a | 2079.2 | 2827.6 | not reached | 1704.1 |
| LA92 | 0.1 | 230.4 | 3731.9 | 4395.1 | not reached | not reached |
| US06 | 80.5 | 991.9 | 1763.1 | 1873.5 | 1933.8 | not reached |
| Mix 1 | 29.3 | 218.0* | 592.0 | 4192.5 | not reached | not reached |
| Mix 2 | 69.2 | 2098.5 | 867.6 | 4110.4 | not reached | not reached |
| Mix 3 | 142.0 | 242.6 | n/a | n/a | not reached | not reached |
| Mix 4 | n/a | 200.4 | 3687.5 | 3884.5 | n/a | not reached |
| Mix 5 | n/a | 478.2 | 1547.2 | 4104.5 | not reached | not reached |
| Mix 6 | n/a | 876.1 | 2482.6 | 2819.3 | not reached | 1840.7 |
| Mix 7 | n/a | 1331.6 | 1464.0 | 3067.0 | not reached | not reached |
| Mix 8 | n/a | 648.2 | 3060.6 | 3767.4 | not reached | not reached |
| **mean of reached** | 71.7 | 750.3 | 1992.5 | 3442.6 | 1933.8 | 1772.4 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 11 of 11 | 1 of 11 | 2 of 12 |

### Init-forgetting time (s): within +-1 pp of the run with the correct init

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 62.7 | 100.6 | 260.3 | 747.3 | 357.4 | 342.1 |
| HWFET | 69.6 | n/a | 1127.4 | 1492.7 | 170.6 | 407.9 |
| LA92 | 97.0 | 173.3 | 501.7 | 42.1 | 631.9 | 351.5 |
| US06 | 128.9 | 252.8 | 25.0 | 500.2 | 242.0 | 834.1 |
| Mix 1 | 108.1 | 327.9* | 380.6 | 672.6 | 194.1 | 1173.8 |
| Mix 2 | 97.5 | 203.1 | 1014.1 | 1434.1 | 172.7 | 427.6 |
| Mix 3 | 76.3 | 98.7 | n/a | n/a | 960.4 | 1034.9 |
| Mix 4 | n/a | 183.9 | 411.0 | 1626.0 | n/a | 160.4 |
| Mix 5 | n/a | 323.0 | 408.4 | 1409.1 | 629.2 | not reached |
| Mix 6 | n/a | 183.9 | 846.2 | 2033.2 | 216.3 | 339.5 |
| Mix 7 | n/a | 300.4 | 757.3 | 694.6 | 142.6 | 214.8 |
| Mix 8 | n/a | 399.2 | 334.8 | 67.0 | 205.8 | 144.2 |
| **mean of reached** | 91.4 | 221.9 | 551.5 | 974.4 | 356.6 | 493.7 |
| **reached** | 7 of 7 | 10 of 10 | 11 of 11 | 11 of 11 | 11 of 11 | 11 of 12 |

## Experiment 4: current offset

The current seen by the filter and by coulomb counting is +0.200 A off (positive = discharge). The expected drift is what the offset does to a coulomb counter over the window.

### SoC RMSE (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | 6.90 | 6.59 | 6.11 | 5.52 | 9.01 | 13.49 |
| HWFET | 2.35 | n/a | 1.68 | 2.11 | 3.20 | 3.30 |
| LA92 | 11.50 | 11.97 | 3.79 | 18.26 | 18.40 | 23.45 |
| US06 | 1.57 | 1.02 | 1.00 | 52.51 | 52.14 | 2.74 |
| Mix 1 | 3.44 | 2.92* | 23.32 | 27.14 | 28.63 | 14.30 |
| Mix 2 | 10.79 | 8.25 | 8.43 | 11.58 | 13.48 | 26.46 |
| Mix 3 | 24.11 | 2.99 | n/a | n/a | 35.86 | 35.82 |
| Mix 4 | n/a | 2.78 | 2.23 | 1.93 | n/a | 2.93 |
| Mix 5 | n/a | 13.39 | 2.07 | 16.44 | 25.35 | 26.52 |
| Mix 6 | n/a | 3.40 | 3.19 | 24.16 | 27.46 | 27.58 |
| Mix 7 | n/a | 2.84 | 2.59 | 2.11 | 3.39 | 3.84 |
| Mix 8 | n/a | 3.95 | 3.39 | 3.82 | 5.97 | 6.56 |
| **mean** | 8.67 | 5.72 | 5.26 | 15.05 | 20.26 | 15.58 |

### EKF error at the end of the window (pp)

| cycle | 40 degC | 25 degC | 10 degC | 0 degC | -10 degC | -20 degC |
|---|---|---|---|---|---|---|
| UDDS | -5.84 | -7.21 | -4.64 | -4.08 | -3.17 | +6.87 |
| HWFET | -2.80 | n/a | -0.92 | -0.93 | -2.63 | -3.71 |
| LA92 | -0.06 | +1.39 | -3.27 | +9.67 | +12.97 | +23.77 |
| US06 | -2.03 | -1.65 | +0.42 | +73.65 | +74.84 | +0.48 |
| Mix 1 | -3.38 | -3.84* | +14.16 | +24.36 | +27.00 | +12.69 |
| Mix 2 | +2.67 | +0.83 | +0.62 | +4.36 | +8.81 | +35.76 |
| Mix 3 | +13.64 | -3.88 | n/a | n/a | +36.35 | +40.50 |
| Mix 4 | n/a | -3.72 | -1.41 | -0.60 | n/a | -3.48 |
| Mix 5 | n/a | +5.69 | -1.65 | +9.67 | +21.91 | +27.73 |
| Mix 6 | n/a | -5.25 | -3.19 | +20.48 | +26.76 | +31.61 |
| Mix 7 | n/a | -4.54 | -2.75 | -1.90 | -3.55 | -4.12 |
| Mix 8 | n/a | -5.39 | -3.02 | -2.48 | -4.32 | -5.21 |
| **mean** | +0.31 | -2.37 | -0.51 | +12.02 | +17.72 | +13.57 |

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
