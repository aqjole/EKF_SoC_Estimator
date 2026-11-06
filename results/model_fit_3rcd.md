# 3RC-D fit on the Mix runs (S9)

Written by `python/fit_3rcd.py` (`make fit-3rcd`).

The standard cycles were held out of the final parameter fit. Prior diagnostics and the low-SoC boundary choice used these runs, and they share segments with the Mix runs (docs/decisions.md 1.40 and 1.41).

## Fit and checks

BVLS status 1. Success True. First-order optimality 5.82e-12.
Design matrix rank 46 of 46. Condition number 1.58e+03.
Largest full-rate difference from the linear prediction over all Mix runs 3.11e-15 V (limit 1e-9 V).

A bound flag of -1 marks the lower bound, +1 the upper bound and 0 no active solver bound.

| T_degC | soc | R3_ohm | s | support | fitted | R3_bound | s_bound |
|---|---|---|---|---|---|---|---|
| 40 | 0 | 0 | 1 |  | fixed | 0 | 0 |
| 40 | 0.1 | 0.00869026603 | 1.35866177 | 2547.2114 | yes | 0 | 0 |
| 40 | 0.4 | 0.0145460818 | 0 | 6391.4468 | yes | 0 | -1 |
| 40 | 0.7 | 0.00605117028 | 0.581140096 | 6701.4283 | yes | 0 | 0 |
| 40 | 1 | 0.00351521357 | 1.3589242 | 3683.7246 | yes | 0 | 0 |
| 25 | 0 | 0 | 1 |  | fixed | 0 | 0 |
| 25 | 0.1 | 0.0178560881 | 0.867912876 | 7096.0347 | yes | 0 | 0 |
| 25 | 0.4 | 0.0172546137 | 0.312402108 | 18546.3744 | yes | 0 | 0 |
| 25 | 0.7 | 0.00959398131 | 0.384624825 | 18996.7555 | yes | 0 | 0 |
| 25 | 1 | 0.00364438854 | 1.24934848 | 10469.6712 | yes | 0 | 0 |
| 10 | 0 | 0 | 1 |  | fixed | 0 | 0 |
| 10 | 0.1 | 0.0303983391 | 0 | 8896.8795 | yes | 0 | -1 |
| 10 | 0.4 | 0.01903475 | 0.822169928 | 18171.0287 | yes | 0 | 0 |
| 10 | 0.7 | 0.0138615622 | 0.425832947 | 17028.1765 | yes | 0 | 0 |
| 10 | 1 | 0.00406980057 | 1.01123534 | 9958.1066 | yes | 0 | 0 |
| 0 | 0 | 0 | 1 |  | fixed | 0 | 0 |
| 0 | 0.1 | 0.0582644516 | 0.350209761 | 7340.6721 | yes | 0 | 0 |
| 0 | 0.4 | 0.0289179512 | 0.794297717 | 18252.8837 | yes | 0 | 0 |
| 0 | 0.7 | 0.0199057002 | 0.289608253 | 16514.8928 | yes | 0 | 0 |
| 0 | 1 | 0.00641908471 | 0.924381601 | 10003.4991 | yes | 0 | 0 |
| -10 | 0 | 0 | 1 |  | fixed | 0 | 0 |
| -10 | 0.1 | 0.0808352685 | 1.35931139 | 3597.7122 | yes | 0 | 0 |
| -10 | 0.4 | 0.075085909 | 0.650664393 | 15815.2365 | yes | 0 | 0 |
| -10 | 0.7 | 0.0140376791 | 0.828231302 | 15452.1249 | yes | 0 | 0 |
| -10 | 1 | 0.0138086001 | 0.540122379 | 8605.8240 | yes | 0 | 0 |
| -20 | 0 | 0 | 1 |  | fixed | 0 | 0 |
| -20 | 0.1 | 0 | 1 | 0.0201 | no | 0 | 0 |
| -20 | 0.4 | 0.132245413 | 1.14680827 | 8973.6208 | yes | 0 | 0 |
| -20 | 0.7 | 0.0523123138 | 0.699537863 | 12847.2688 | yes | 0 | 0 |
| -20 | 1 | 0.0208778506 | 0.421642926 | 7761.4067 | yes | 0 | 0 |

## Open-loop voltage

RMSE in mV, pooled over the evaluation-window rows and scored using the exported tables.

| T (degC) | Mix 2RC-I | Mix 3RC-D (in-sample) | Standard 2RC-I | Standard 3RC-D |
|---|---|---|---|---|
| 40 | 12.48 | 7.88 | 13.41 | 9.69 |
| 25 | 17.33 | 9.71 | 13.68 | 10.27 |
| 10 | 25.18 | 14.80 | 22.28 | 15.53 |
| 0 | 37.95 | 19.56 | 33.61 | 19.92 |
| -10 | 62.07 | 30.44 | 49.62 | 32.07 |
| -20 | 80.88 | 46.42 | 76.31 | 47.11 |

## US06 gate

**PASS.** 3RC-D scores 23.1312 mV over all rows at 25 degC (limit 30 mV).

The window and tail columns separate the in-window and subsequent rows. All columns are in mV.

| T (degC) | 2RC-I all | 3RC-D all | 2RC-I window | 3RC-D window | 2RC-I tail | 3RC-D tail |
|---|---|---|---|---|---|---|
| 40 | 20.56 | 17.29 | 17.85 | 12.40 | 31.55 | 33.10 |
| 25 | 29.75 | 23.13 | 22.14 | 15.96 | 53.81 | 44.29 |
| 10 | 40.87 | 21.32 | 40.87 | 21.32 | n/a | n/a |
| 0 | 60.31 | 35.04 | 60.31 | 35.04 | n/a | n/a |
| -10 | 77.75 | 63.59 | 77.75 | 63.59 | n/a | n/a |
| -20 | 104.85 | 76.74 | 104.85 | 76.74 | n/a | n/a |

## Leave-one-Mix-run-out voltage

Mean per-run window RMSE in mV. Each fold recomputes node support and fits on the other 39 Mix runs. Earlier Mix diagnostics selected the structure, so the folds evaluate that selected structure.

| T (degC) | 2RC-I | 3RC-D |
|---|---|---|
| 40 | 12.47 | 8.79 |
| 25 | 17.30 | 10.15 |
| 10 | 24.96 | 15.21 |
| 0 | 37.66 | 20.49 |
| -10 | 62.11 | 31.77 |
| -20 | 80.55 | 47.73 |
