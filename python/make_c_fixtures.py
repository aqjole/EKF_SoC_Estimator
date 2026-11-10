"""Write the CI fixtures of the C port: c/tests/fixtures/<name>.csv and their README.md.

Each fixture is the first N_ROWS rows (about 10 minutes at the 0.1 s logging step) of one US06 run after
the loader rules, at 25, -20 and 40 degC, with the SoC the Python filter computes on them. CI runs the C
tool (c/tools/ekf_run_csv.c) on each and compares, without the raw data.

Columns: dt_s, i_a, v_v, t_degc (the filter inputs, dt from the loader in float64, so the tool never
subtracts timestamps) and soc_expected. Every value is written with 10 significant digits, and
soc_expected is python run_ekf (experiment 1: soc0 = the reference SoC at row 0, V1 = V2 = 0, no predict
at row 0) on exactly the inputs as written, with the frozen noise settings of results/s2/ekf_config.json.
The output is deterministic.

Run from the repo root:  .venv/bin/python python/make_c_fixtures.py   (needs data/raw/)
"""

import numpy as np

from ekfsoc import rawio
from ekfsoc.constants import RAW_DIR, REPO_DIR
from ekfsoc.ekf import EkfConfig, run_ekf
from ekfsoc.loader import find_runs, load_run, soc_ref
from ekfsoc.model import Params
from export_params import PARAMS_CSV, write_text
from tune import CONFIG_JSON


FIXTURES_DIR = REPO_DIR / "c" / "tests" / "fixtures"

# The source runs: (folder, test number) of a US06 file.
SOURCES = (("25degC", 551), ("n20degC", 610), ("40degC", 556))

N_ROWS = 6000
COLUMNS = ("dt_s", "i_a", "v_v", "t_degc", "soc_expected")
MAX_BYTES = 1_000_000  # the fixtures are committed: all three together stay under 1 MB


def as_text(value):
    """Return a value with 10 significant digits, the form every fixture cell is written in."""
    return f"{value:.10g}"


def as_written(values):
    """Return the float64 values a reader gets back from the cells of `values`."""
    return np.array([float(as_text(value)) for value in values])


def find_source(folder, test_number):
    """Return the path of the US06 file with this test number in data/raw/<folder>/."""
    matches = [path for path in find_runs(RAW_DIR, "us06", folder)
               if rawio.parse_filename(path.name)["test_number"] == test_number]
    if len(matches) != 1:
        raise RuntimeError(f"expected one US06 file {test_number} in {folder}, found {[p.name for p in matches]}")
    return matches[0]


def make_fixture(path, params, cfg):
    """Return (CSV text, soc0, rows) for the first N_ROWS rows of the run in `path`."""
    run = load_run(path)
    dt, i, v, temp = (as_written(column[:N_ROWS]) for column in (run.dt, run.i, run.v, run.temp))
    soc0 = float(as_text(soc_ref(run)[0]))
    soc = run_ekf(params, cfg, i, v, temp, dt, soc0)["soc"]

    lines = [",".join(COLUMNS)]
    lines += [",".join(as_text(value) for value in row) for row in zip(dt, i, v, temp, soc)]
    return "\n".join(lines) + "\n", soc0, len(dt)


def readme_text(entries, cfg):
    """Return the text of c/tests/fixtures/README.md; entries are (fixture name, source path, soc0, rows)."""
    rows = [f"| `{name}.csv` | `{path.parent.name}/{path.name}` | {n_rows} | {as_text(soc0)} |"
            for name, path, soc0, n_rows in entries]
    lines = [
        "# C test fixtures",
        "",
        "Three excerpts of US06 drive cycles (25, -20 and 40 degC) with the SoC the Python filter computes on them, "
        "so the C port is checked for equivalence in CI without the raw data. ctest runs `c/tools/ekf_run_csv` on each "
        "file and compares its SoC with `soc_expected`: max |delta SoC| below 0.1 pp in the float build and "
        "below 1e-3 pp in the double build.",
        "",
        "| fixture | source file (`data/raw/`) | rows | soc0 |",
        "|---|---|---|---|",
        *rows,
        "",
        "- **Dataset:** LG 18650HG2 Li-ion Battery Data, Kollmeyer et al., McMaster University, Mendeley Data v2, "
        "DOI [10.17632/b5mj79w5w9.2](https://doi.org/10.17632/b5mj79w5w9.2).",
        "- **Licence:** CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The fixtures are data from that "
        "dataset, so they carry the dataset's licence and the attribution above. They are **not** covered by the MIT "
        "licence of this repository's code.",
        f"- **How they were made:** `python/make_c_fixtures.py` loads each source file with the loader rules of "
        f"`docs/model.md` and keeps the first {N_ROWS} rows (about 10 minutes at the 0.1 s logging step). "
        "The columns are `dt_s` (the step to the previous row, computed in float64 from Time by the loader; "
        "0 at the first row), `i_a` (current in A, positive on discharge), `v_v` (terminal voltage in V), "
        "`t_degc` (cell temperature in degC) and `soc_expected` (fraction). Every value has 10 significant digits. "
        "`soc_expected` is the Python filter (`run_ekf`, experiment 1) run on exactly the values as written: "
        "the initial SoC is soc0 above (the reference SoC at the first row), V1 = V2 = 0, the initial covariance "
        f"has the standard deviations {as_text(cfg.p0_soc_std)} (SoC) and {as_text(cfg.p0_v_std)} V (V1, V2), "
        "and the first row gets an update and no predict. The noise settings are the frozen ones of "
        f"`results/s2/ekf_config.json`: q_soc = {as_text(cfg.q_soc)}, q_v = {as_text(cfg.q_v)}, r = {as_text(cfg.r)}. "
        "Run it from the repo root with `.venv/bin/python python/make_c_fixtures.py`; it needs `data/raw/`.",
    ]
    return "\n".join(lines) + "\n"


def main():
    params = Params.from_csv(PARAMS_CSV)
    cfg = EkfConfig.from_json(CONFIG_JSON)

    entries = []
    texts = {}
    for folder, test_number in SOURCES:
        path = find_source(folder, test_number)
        name = f"{folder}_{test_number}_US06"
        texts[name], soc0, n_rows = make_fixture(path, params, cfg)
        entries.append((name, path, soc0, n_rows))

    total_bytes = sum(len(text.encode()) for text in texts.values())
    if total_bytes >= MAX_BYTES:
        raise RuntimeError(f"the fixtures take {total_bytes} bytes; they must stay under {MAX_BYTES}")

    for name, text in texts.items():
        write_text(FIXTURES_DIR / f"{name}.csv", text)
    write_text(FIXTURES_DIR / "README.md", readme_text(entries, cfg))
    print(f"wrote {len(texts)} fixtures ({total_bytes} bytes) and README.md to {FIXTURES_DIR.relative_to(REPO_DIR)}")


if __name__ == "__main__":
    main()
