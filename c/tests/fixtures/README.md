# C test fixtures

Three excerpts of US06 drive cycles (25, -20 and 40 degC) with the SoC the Python filter computes on them, so the C port is checked for equivalence in CI without the raw data. ctest runs `c/tools/ekf_run_csv` on each file and compares its SoC with `soc_expected`: max |delta SoC| below 0.1 pp in the float build and below 1e-3 pp in the double build.

| fixture | source file (`data/raw/`) | rows | soc0 |
|---|---|---|---|
| `25degC_551_US06.csv` | `25degC/10-29-18_10.08 551_US06_25degC_LGHG2.mat` | 6000 | 1 |
| `n20degC_610_US06.csv` | `n20degC/12-25-18_01.31 610_US06_n20degC_LGHG2.mat` | 6000 | 1 |
| `40degC_556_US06.csv` | `40degC/11-06-18_19.09 556_US06_40degC_LGHG2.mat` | 6000 | 1 |

- **Dataset:** LG 18650HG2 Li-ion Battery Data, Kollmeyer et al., McMaster University, Mendeley Data v2, DOI [10.17632/b5mj79w5w9.2](https://doi.org/10.17632/b5mj79w5w9.2).
- **Licence:** CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The fixtures are data from that dataset, so they carry the dataset's licence and the attribution above. They are **not** covered by the MIT licence of this repository's code.
- **How they were made:** `python/make_c_fixtures.py` loads each source file with the loader rules of `docs/model.md` and keeps the first 6000 rows (about 10 minutes at the 0.1 s logging step). The columns are `dt_s` (the step to the previous row, computed in float64 from Time by the loader; 0 at the first row), `i_a` (current in A, positive on discharge), `v_v` (terminal voltage in V), `t_degc` (cell temperature in degC) and `soc_expected` (fraction). Every value has 10 significant digits. `soc_expected` is the Python filter (`run_ekf`, experiment 1) run on exactly the values as written: the initial SoC is soc0 above (the reference SoC at the first row), V1 = V2 = 0, the initial covariance has the standard deviations 0.2 (SoC) and 0.05 V (V1, V2), and the first row gets an update and no predict. The noise settings are the frozen ones of `results/s2/ekf_config.json`: q_soc = 1e-07, q_v = 1e-06, r = 0.01. Run it from the repo root with `.venv/bin/python python/make_c_fixtures.py`; it needs `data/raw/`.
