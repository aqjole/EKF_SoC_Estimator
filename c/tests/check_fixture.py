"""ctest check of one fixture: run c/tools/ekf_run_csv on it and compare its SoC with soc_expected.

usage: check_fixture.py <ekf_run_csv> <fixture.csv> <out.csv> <max_abs_soc> <q_soc> <q_v> <r> <soc0>

Fails (exit 1) unless max |soc - soc_expected| over all rows is below max_abs_soc (a fraction: 1e-3 is
0.1 pp). Standard library only, so the C job needs no Python packages.
"""

import csv
import subprocess
import sys


def column(path, name):
    with open(path, newline="") as handle:
        return [float(row[name]) for row in csv.DictReader(handle)]


def main():
    tool, fixture, out, max_abs_soc, q_soc, q_v, r, soc0 = sys.argv[1:]
    subprocess.run([tool, fixture, out, q_soc, q_v, r, soc0], check=True)
    soc = column(out, "soc")
    expected = column(fixture, "soc_expected")
    if len(soc) != len(expected):
        sys.exit(f"{out}: {len(soc)} rows, expected {len(expected)}")
    worst = max(abs(a - b) for a, b in zip(soc, expected))
    print(f"{fixture}: max |delta SoC| = {100 * worst:.3g} pp over {len(soc)} rows, limit {100 * float(max_abs_soc):g} pp")
    sys.exit(0 if worst < float(max_abs_soc) else 1)


if __name__ == "__main__":
    main()
