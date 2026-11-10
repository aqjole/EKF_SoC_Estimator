# Octave port equivalence (S5)

Written by `python/compare_octave.py` (`make octave`). The Octave filter (`octave/ekf_run_csv.m`, double precision) runs experiment 1 (soc0 = the reference SoC at row 0) on the 63 runs of the evaluation set and the tuning cycle, with the frozen noise settings of `results/s2/ekf_config.json` (q_soc = 1e-07, q_v = 1e-06, r = 0.01), on the filter inputs the C port reads (dt computed in float64 by Python, written with 17 significant digits by `python/compare_c.py`). delta SoC = Python SoC - Octave SoC over every row of a run, in pp; the Python SoC is the experiment 1 trace of `python/run_all.py`. The port writes SoC with 17 significant digits, so the comparison is at full double resolution; the threshold on max |delta SoC| is the spec's double-build threshold, 0.001 pp (`docs/decisions.md` 1.20).

## Result

| build | threshold (pp) | max \|delta SoC\| (pp) | worst run | largest RMS (pp) | result |
|---|---|---|---|---|---|
| octave | 0.001 | 8.67e-12 | Mix 6 at -20 degC (611) | 1.79e-12 | PASS |

## Per temperature

| T (degC) | runs | octave max (pp) | octave largest RMS (pp) |
|---|---|---|---|
| 40 | 7 | 1.78e-13 | 2.82e-14 |
| 25 | 11 | 1.55e-13 | 2.64e-14 |
| 10 | 11 | 1.08e-12 | 3.46e-13 |
| 0 | 11 | 7.55e-13 | 3.28e-13 |
| -10 | 11 | 2.19e-12 | 2.68e-13 |
| -20 | 12 | 8.67e-12 | 1.79e-12 |

## Per run

| T (degC) | cycle | test | rows | octave max (pp) | octave RMS (pp) |
|---|---|---|---|---|---|
| 40 | UDDS | 556 | 158955 | 8.88e-14 | 2.46e-14 |
| 40 | HWFET | 556 | 55909 | 5.55e-14 | 1.14e-14 |
| 40 | LA92 | 556 | 98636 | 8.33e-14 | 1.22e-14 |
| 40 | US06 | 556 | 39960 | 1.33e-13 | 1.80e-14 |
| 40 | Mix 1 | 556 | 75341 | 8.88e-14 | 1.63e-14 |
| 40 | Mix 2 | 556 | 78955 | 6.66e-14 | 8.49e-15 |
| 40 | Mix 3 | 557 | 67625 | 1.78e-13 | 2.82e-14 |
| 25 | UDDS | 551 | 159646 | 6.66e-14 | 1.61e-14 |
| 25 | LA92 | 551 | 100763 | 7.77e-14 | 2.29e-14 |
| 25 | US06 | 551 | 40154 | 7.77e-14 | 2.48e-14 |
| 25 | Mix 1 (tuning) | 551 | 77226 | 4.44e-14 | 1.04e-14 |
| 25 | Mix 2 | 551 | 79171 | 7.77e-14 | 1.76e-14 |
| 25 | Mix 3 | 552 | 73826 | 1.55e-13 | 2.40e-14 |
| 25 | Mix 4 | 552 | 80850 | 6.66e-14 | 2.64e-14 |
| 25 | Mix 5 | 552 | 72184 | 6.66e-14 | 1.81e-14 |
| 25 | Mix 6 | 552 | 78105 | 1.11e-13 | 1.40e-14 |
| 25 | Mix 7 | 552 | 73234 | 4.44e-14 | 1.47e-14 |
| 25 | Mix 8 | 552 | 85915 | 6.66e-14 | 1.63e-14 |
| 10 | UDDS | 576 | 148897 | 1.33e-13 | 2.13e-14 |
| 10 | HWFET | 576 | 52877 | 2.55e-13 | 7.47e-14 |
| 10 | LA92 | 582 | 89701 | 1.78e-13 | 2.53e-14 |
| 10 | US06 | 567 | 38718 | 1.08e-12 | 3.46e-13 |
| 10 | Mix 1 | 567 | 72328 | 9.99e-14 | 2.04e-14 |
| 10 | Mix 2 | 567 | 77751 | 5.55e-14 | 2.13e-14 |
| 10 | Mix 4 | 571 | 73928 | 4.77e-13 | 1.07e-13 |
| 10 | Mix 5 | 571 | 67173 | 9.99e-14 | 3.22e-14 |
| 10 | Mix 6 | 571 | 73529 | 1.89e-13 | 1.32e-14 |
| 10 | Mix 7 | 571 | 69324 | 1.55e-13 | 4.40e-14 |
| 10 | Mix 8 | 571 | 81422 | 1.11e-13 | 1.86e-14 |
| 0 | UDDS | 589 | 140433 | 1.11e-13 | 2.76e-14 |
| 0 | HWFET | 589 | 49677 | 1.22e-13 | 4.74e-14 |
| 0 | LA92 | 589 | 81577 | 1.67e-13 | 4.22e-14 |
| 0 | US06 | 589 | 33806 | 2.89e-13 | 1.81e-14 |
| 0 | Mix 1 | 589 | 67311 | 1.67e-13 | 4.25e-14 |
| 0 | Mix 2 | 589 | 72303 | 1.55e-13 | 2.15e-14 |
| 0 | Mix 4 | 590 | 68026 | 7.55e-13 | 3.28e-13 |
| 0 | Mix 5 | 590 | 64994 | 4.22e-13 | 2.70e-14 |
| 0 | Mix 6 | 590 | 62483 | 3.44e-13 | 2.81e-14 |
| 0 | Mix 7 | 590 | 61539 | 6.66e-14 | 2.35e-14 |
| 0 | Mix 8 | 590 | 75838 | 4.11e-13 | 3.97e-14 |
| -10 | UDDS | 596 | 123601 | 3.44e-13 | 4.06e-14 |
| -10 | HWFET | 596 | 44903 | 2.19e-12 | 2.68e-13 |
| -10 | LA92 | 596 | 72097 | 1.80e-13 | 6.28e-14 |
| -10 | US06 | 601 | 31912 | 7.66e-13 | 3.82e-14 |
| -10 | Mix 1 | 601 | 62621 | 1.89e-13 | 5.73e-14 |
| -10 | Mix 2 | 601 | 65253 | 8.88e-14 | 2.98e-14 |
| -10 | Mix 3 | 604 | 55214 | 1.33e-13 | 3.01e-14 |
| -10 | Mix 5 | 602 | 60086 | 4.88e-13 | 6.52e-14 |
| -10 | Mix 6 | 604 | 55967 | 4.66e-13 | 1.07e-13 |
| -10 | Mix 7 | 604 | 55939 | 2.33e-13 | 5.27e-14 |
| -10 | Mix 8 | 604 | 67325 | 1.67e-13 | 4.00e-14 |
| -20 | UDDS | 610 | 81910 | 3.11e-13 | 9.54e-14 |
| -20 | HWFET | 610 | 33344 | 3.97e-12 | 1.18e-12 |
| -20 | LA92 | 610 | 52485 | 5.00e-13 | 1.83e-13 |
| -20 | US06 | 610 | 27605 | 5.55e-13 | 1.22e-13 |
| -20 | Mix 1 | 610 | 45342 | 6.00e-13 | 4.63e-14 |
| -20 | Mix 2 | 610 | 43043 | 5.49e-12 | 1.79e-12 |
| -20 | Mix 3 | 611 | 45163 | 3.55e-13 | 4.03e-14 |
| -20 | Mix 4 | 611 | 46052 | 6.88e-13 | 1.77e-13 |
| -20 | Mix 5 | 611 | 45457 | 5.83e-13 | 2.15e-13 |
| -20 | Mix 6 | 611 | 44195 | 8.67e-12 | 1.65e-12 |
| -20 | Mix 7 | 611 | 40682 | 2.11e-13 | 5.53e-14 |
| -20 | Mix 8 | 611 | 46762 | 8.99e-13 | 1.69e-13 |
