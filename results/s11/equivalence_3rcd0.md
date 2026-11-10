# C port equivalence, 3RC-D0 (S11 close)

Written by `python/compare_c_3rcd0.py` (`make equiv-3rcd0`); decisions 1.46 and 1.54. The four-state C build (`-DEKF_USE_3RCD0=ON`, `c/tools/ekf_run_csv`) runs experiments 1, 2, 3 low, 3 high, 3 reference and 4 on the 63 runs with the frozen settings of `results/s2/ekf_config.json` (q_soc = 1e-07, q_v = 1e-06, r = 0.01), each from its start row with dt = 0 there and the Python soc0, experiment 4 with its current offset. delta SoC = Python SoC - C SoC over every processed row, tails included, in pp; the Python SoC is the stored trace of `results/runs/3rcd0/`. The thresholds on max |delta SoC| are those of 1.46. The tool writes SoC with 10 significant digits, so the double build sits near 5e-9 pp. Per-case values: [`equivalence_3rcd0.csv`](equivalence_3rcd0.csv).

## Result

| build | threshold (pp) | max \|delta SoC\| (pp) | worst run | largest RMS (pp) | result |
|---|---|---|---|---|---|
| float | 0.1 | 1.94e-02 | Mix 4, exp2 at 0 degC (590) | 3.65e-03 | PASS |
| double | 0.001 | 5.05e-09 | Mix 1, exp3_ref at -10 degC (601) | 2.91e-09 | PASS |

## Per experiment

| experiment | cases | float max (pp) | float largest RMS (pp) | double max (pp) | double largest RMS (pp) |
|---|---|---|---|---|---|
| exp1 | 63 | 5.91e-03 | 1.48e-03 | 5.00e-09 | 2.90e-09 |
| exp2 | 63 | 1.94e-02 | 1.59e-03 | 5.00e-09 | 2.91e-09 |
| exp3_low | 63 | 1.36e-02 | 2.42e-03 | 5.00e-09 | 2.90e-09 |
| exp3_high | 63 | 2.53e-03 | 4.66e-04 | 5.00e-09 | 2.90e-09 |
| exp3_ref | 63 | 1.73e-02 | 3.65e-03 | 5.05e-09 | 2.91e-09 |
| exp4 | 63 | 6.51e-03 | 2.52e-03 | 5.00e-09 | 2.89e-09 |

## Per temperature

| T (degC) | runs | float max (pp) | float largest RMS (pp) | double max (pp) | double largest RMS (pp) |
|---|---|---|---|---|---|
| 40 | 42 | 1.20e-03 | 4.30e-04 | 5.00e-09 | 2.90e-09 |
| 25 | 66 | 1.64e-03 | 5.53e-04 | 5.00e-09 | 2.81e-09 |
| 10 | 66 | 1.86e-03 | 4.80e-04 | 5.00e-09 | 2.90e-09 |
| 0 | 66 | 1.94e-02 | 1.48e-03 | 5.00e-09 | 2.90e-09 |
| -10 | 66 | 1.73e-02 | 3.65e-03 | 5.05e-09 | 2.90e-09 |
| -20 | 72 | 1.36e-02 | 2.52e-03 | 5.00e-09 | 2.91e-09 |
