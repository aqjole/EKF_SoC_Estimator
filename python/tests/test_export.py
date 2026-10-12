"""Tests for export_params: the generated C files and results/params.md.

No raw data and no real fit is needed. Each test builds a small synthetic params.csv (606 rows, the
header of the contract) and fit_levels.csv in tmp_path, runs the export on them and checks
the output: the C source compiles under strict flags, the header has the defines and the nine
declarations, every literal is a float, the values round-trip to the CSV, and two runs give the
same bytes.
"""

import csv
import math
import re
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

import export_params
from ekfsoc.constants import SOC_GRID, T_GRID_DEGC


PARAMS_HEADER = "T_degC,soc,ocv_V,docv_V_per_soc,R0_ohm,R1_ohm,tau1_s,R2_ohm,tau2_s"
LEVELS_HEADER = (
    "T_degC,level,soc_pulses,R0_ohm,R1_ohm,tau1_s,rmse_fast_mV,n_pulses_used,"
    "soc_rest,R2_ohm,tau2_s,rmse_slow_mV,fast_ok,slow_ok"
)

# Lowest SoC the C/20 discharge reaches at 40, 25, 10, 0, -10, -20 degC (results/data_checks.md section 11).
SOC_MIN = [0.0327, 0.0, 0.0474, 0.0655, 0.0781, 0.1028]

# Levels of the six HPPC files (docs/decisions.md 1.2).
N_LEVELS = [11, 12, 11, 10, 10, 9]

C_ARRAY_NAMES = [
    "ekf_t_grid_degc",
    "ekf_soc_grid",
    "ekf_ocv_v",
    "ekf_docv_v_per_soc",
    "ekf_r0_ohm",
    "ekf_r1_ohm",
    "ekf_tau1_s",
    "ekf_r2_ohm",
    "ekf_tau2_s",
]

# Table arrays and the params.csv column each one holds.
C_NAME_TO_COLUMN = {
    "ekf_ocv_v": "ocv_V",
    "ekf_docv_v_per_soc": "docv_V_per_soc",
    "ekf_r0_ohm": "R0_ohm",
    "ekf_r1_ohm": "R1_ohm",
    "ekf_tau1_s": "tau1_s",
    "ekf_r2_ohm": "R2_ohm",
    "ekf_tau2_s": "tau2_s",
}


def six(value):
    """Round to 6 significant digits like the real params.csv, and return the text."""
    return "%.6g" % value


def write_synthetic(directory, fallback=False):
    """Write a synthetic params.csv and fit_levels.csv into `directory` and return their paths.

    The OCV rises with SoC and is held at the SoC_MIN value below SoC_MIN of each temperature (the
    same hold rule as build_ocv). `fallback=True` copies the 25 degC OCV row to every temperature.
    """
    params_path = directory / "params.csv"
    levels_path = directory / "fit_levels.csv"

    ocv_by_t = []
    for j, temp in enumerate(T_GRID_DEGC):
        curve = []
        for soc in SOC_GRID:
            held_soc = max(soc, SOC_MIN[j])
            curve.append(3.0 + 0.9 * held_soc + 0.35 * held_soc**3 - 0.002 * (25 - temp) * (1.0 - held_soc))
        ocv_by_t.append(curve)
    if fallback:
        ocv_by_t = [ocv_by_t[1] for _ in T_GRID_DEGC]

    with open(params_path, "w", newline="") as handle:
        handle.write(PARAMS_HEADER + "\n")
        writer = csv.writer(handle, lineterminator="\n")
        for j, temp in enumerate(T_GRID_DEGC):
            ocv = np.array(ocv_by_t[j])
            docv = np.gradient(ocv, SOC_GRID)
            cold = (25 - temp) / 45.0
            for m, soc in enumerate(SOC_GRID):
                r0 = 0.02 * (1.0 + cold) * (1.0 + 0.5 * (1.0 - soc))
                r1 = 0.01 * (1.0 + 1.5 * cold) * (1.0 + 0.3 * (1.0 - soc))
                tau1 = 3.0 * (1.0 + cold) * (1.0 + 0.2 * soc)
                r2 = 0.015 * (1.0 + cold)
                tau2 = 300.0 * (1.0 + cold) * (1.0 + 0.5 * soc)
                values = [temp, soc, ocv[m], docv[m], r0, r1, tau1, r2, tau2]
                writer.writerow([six(value) for value in values])

    with open(levels_path, "w", newline="") as handle:
        handle.write(LEVELS_HEADER + "\n")
        writer = csv.writer(handle, lineterminator="\n")
        for j, temp in enumerate(T_GRID_DEGC):
            n_levels = N_LEVELS[j]
            cold = (25 - temp) / 45.0
            for level in range(1, n_levels + 1):
                soc_pulses = 1.0 - 0.09 * (level - 1)
                soc_rest = 1.0 - 0.09 * level
                r0 = 0.02 * (1.0 + cold)
                r1 = 0.01 * (1.0 + 1.5 * cold)
                tau1 = 3.0 * (1.0 + cold)
                last = level == n_levels
                # The last level has no 1 h rest, so R2, tau2 and their RMSE are empty cells. A failed
                # fit of the first level at -20 degC is empty too.
                failed_fast = temp == -20 and level == 1
                row = [
                    temp,
                    level,
                    six(soc_pulses),
                    "" if failed_fast else six(r0),
                    "" if failed_fast else six(r1),
                    "" if failed_fast else six(tau1),
                    "" if failed_fast else six(1.2),
                    0 if failed_fast else 4,
                    "" if last else six(soc_rest),
                    "" if last else six(0.015 * (1.0 + cold)),
                    "" if last else six(300.0 * (1.0 + cold)),
                    "" if last else six(0.8),
                    not failed_fast,
                    "" if last else True,
                ]
                writer.writerow(row)
    return params_path, levels_path


def run_export(directory, fallback=False):
    """Write the synthetic inputs and run export_params into `directory`; return the three output paths."""
    params_path, levels_path = write_synthetic(directory, fallback=fallback)
    md_path = directory / "out" / "params.md"
    c_path = directory / "out" / "src" / "ekf_params.c"
    h_path = directory / "out" / "include" / "ekf_params.h"
    export_params.export_params(params_path, levels_path, md_path, c_path, h_path)
    return md_path, c_path, h_path


def strip_comments(text):
    """Remove /* ... */ comments from C text."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def array_values(c_text, name):
    """Return the literals of the C array `name` as a flat float array (suffix f removed, comments ignored)."""
    code = strip_comments(c_text)
    match = re.search(r"const float " + name + r"\[[^=]*=\s*\{(.*?)\n\};", code, flags=re.DOTALL)
    assert match, f"array {name} not found"
    tokens = re.findall(r"[-+]?\d[\w.+-]*", match.group(1))
    return np.array([float(token.rstrip("f")) for token in tokens])


# --- C files -------------------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler (cc) on this machine")
def test_c_source_compiles_with_strict_flags(tmp_path):
    _, c_path, h_path = run_export(tmp_path)
    command = [
        "cc", "-std=c99", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-Wdouble-promotion",
        "-I", str(h_path.parent), "-c", str(c_path), "-o", str(tmp_path / "ekf_params.o"),
    ]  # fmt: skip
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "ekf_params.o").exists()


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler (cc) on this machine")
def test_compiled_arrays_hold_the_csv_values(tmp_path):
    # Link a tiny main against the generated source and print three table entries: the compiler's own
    # reading of the literals is checked against the CSV, not only our reading of the text.
    _, c_path, h_path = run_export(tmp_path)
    main_path = tmp_path / "check_main.c"
    main_path.write_text(
        '#include <stdio.h>\n#include "ekf_params.h"\n'
        "int main(void) {\n"
        '    printf("%d %d\\n", EKF_N_T, EKF_N_SOC);\n'
        '    printf("%.7g %.7g %.7g\\n", (double)ekf_t_grid_degc[5], (double)ekf_ocv_v[0][0], (double)ekf_tau2_s[5][100]);\n'
        "    return 0;\n}\n"
    )
    exe_path = tmp_path / "check_main"
    command = ["cc", "-std=c99", "-I", str(h_path.parent), str(c_path), str(main_path), "-o", str(exe_path)]
    build = subprocess.run(command, capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    output = subprocess.run([str(exe_path)], capture_output=True, text=True, check=True).stdout.split("\n")

    assert output[0] == "6 101"
    t_last, ocv_first, tau2_last = (float(word) for word in output[1].split())
    params_df = pd.read_csv(tmp_path / "params.csv")
    assert t_last == -20.0
    assert ocv_first == pytest.approx(params_df["ocv_V"].iloc[0], rel=1e-6)
    assert tau2_last == pytest.approx(params_df["tau2_s"].iloc[-1], rel=1e-6)


def test_header_defines_sizes_and_declares_nine_arrays(tmp_path):
    _, _, h_path = run_export(tmp_path)
    text = h_path.read_text()

    assert re.search(r"^#define EKF_N_T 6$", text, flags=re.MULTILINE)
    assert re.search(r"^#define EKF_N_SOC 101$", text, flags=re.MULTILINE)
    declared = re.findall(r"^extern const float (\w+)\[", text, flags=re.MULTILINE)
    assert declared == C_ARRAY_NAMES
    assert "EKF_N_T][EKF_N_SOC]" in text
    assert text.startswith("/* generated by python/export_params.py from results/params.csv, do not edit")
    assert "#ifndef EKF_PARAMS_H" in text and "#endif" in text


def test_source_has_the_generated_note_and_includes_the_header(tmp_path):
    _, c_path, _ = run_export(tmp_path)
    text = c_path.read_text()
    assert text.startswith("/* generated by python/export_params.py from results/params.csv, do not edit")
    assert '#include "ekf_params.h"' in text
    for name in C_ARRAY_NAMES:
        assert re.search(r"^const float " + name + r"\[", text, flags=re.MULTILINE), name


def test_every_float_literal_has_an_f_suffix(tmp_path):
    _, c_path, _ = run_export(tmp_path)
    code = strip_comments(c_path.read_text())
    # A number is a token that starts with a digit and is not part of an identifier (r0 in ekf_r0_ohm).
    literals = re.findall(r"(?<![\w.])\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[fF]?(?![\w.])", code)
    # 6 temperatures + 101 SoC nodes + 7 tables of 606 values. The #include line has no number.
    assert len(literals) == 6 + 101 + 7 * 606
    for literal in literals:
        assert literal.endswith("f"), literal
        assert "." in literal or "e" in literal, literal  # "40f" would not be a float literal
    # Nothing numeric is left once the literals are removed, so no literal was missed by the pattern.
    remainder = re.sub(r"(?<![\w.])\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[fF]?(?![\w.])", "", code)
    assert not re.search(r"(?<!\w)\d", remainder)


def test_c_values_round_trip_to_the_csv(tmp_path):
    _, c_path, _ = run_export(tmp_path)
    c_text = c_path.read_text()
    params_df = pd.read_csv(tmp_path / "params.csv")

    axis_t = array_values(c_text, "ekf_t_grid_degc")
    axis_soc = array_values(c_text, "ekf_soc_grid")
    assert list(axis_t) == T_GRID_DEGC
    assert axis_soc == pytest.approx(SOC_GRID, abs=1e-6)

    for c_name, column in C_NAME_TO_COLUMN.items():
        c_values = array_values(c_text, c_name)
        csv_values = params_df[column].to_numpy()
        assert len(c_values) == 606, c_name
        # First and last entry, as the contract states.
        assert c_values[0] == pytest.approx(csv_values[0], rel=1e-6), c_name
        assert c_values[-1] == pytest.approx(csv_values[-1], rel=1e-6), c_name
        # And every entry, in row order (T-major), so a swapped row or column would fail.
        assert c_values == pytest.approx(csv_values, rel=1e-6, abs=0.0), c_name


def test_two_runs_give_byte_identical_files(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = run_export(tmp_path / "a")
    second = run_export(tmp_path / "b")
    for path_a, path_b in zip(first, second):
        assert path_a.read_bytes() == path_b.read_bytes(), path_a.name

    # Running again into the same files also leaves the bytes unchanged.
    before = [path.read_bytes() for path in first]
    run_export(tmp_path / "a")
    assert [path.read_bytes() for path in first] == before


def test_c_float_literals():
    assert export_params.c_float(40.0) == "40.0f"
    assert export_params.c_float(0.07) == "0.07f"
    assert export_params.c_float(-20) == "-20.0f"
    assert export_params.c_float(1.234567890123) == "1.234568f"  # 7 significant digits
    assert export_params.c_float(0.00001234567) == "1.234567e-05f"
    assert export_params.c_float(0.0) == "0.0f"
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            export_params.c_float(bad)


def test_axes_that_are_not_the_project_grids_are_refused(tmp_path):
    params_path, levels_path = write_synthetic(tmp_path)
    text = params_path.read_text().replace("\n-20,", "\n-21,")
    params_path.write_text(text)
    with pytest.raises(ValueError, match="project grids"):
        export_params.export_params(
            params_path, levels_path, tmp_path / "p.md", tmp_path / "c" / "a.c", tmp_path / "c" / "a.h"
        )


# --- results/params.md ---------------------------------------------------------------------------


def md_ocv_rows(md_text):
    """Return {T: (valid-from SoC text, held count text)} from the OCV table of params.md."""
    rows = {}
    in_ocv = False
    for line in md_text.split("\n"):
        if line.startswith("## "):
            in_ocv = line == "## OCV"
        elif in_ocv and re.match(r"\| -?\d", line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows[float(cells[0])] = (cells[1], cells[2])
    return rows


def test_md_has_the_ocv_valid_range_per_temperature(tmp_path):
    md_path, _, _ = run_export(tmp_path)
    text = md_path.read_text()
    rows = md_ocv_rows(text)

    # The synthetic OCV is held below SoC_MIN, so it first changes at the first grid point at or above it:
    # 0.0327 -> 0.04, 0.0 -> 0 (nothing held), 0.0474 -> 0.05, 0.0655 -> 0.07, 0.0781 -> 0.08, 0.1028 -> 0.11.
    expected = {40.0: ("4.0", "4"), 25.0: ("0.0", "0"), 10.0: ("5.0", "5"), 0.0: ("7.0", "7"), -10.0: ("8.0", "8"), -20.0: ("11.0", "11")}
    assert rows == expected
    assert "OCV fallback (the 25 degC curve used at every temperature): no." in text


def test_md_flags_the_ocv_fallback(tmp_path):
    md_path, _, _ = run_export(tmp_path, fallback=True)
    text = md_path.read_text()
    assert "OCV fallback (the 25 degC curve used at every temperature): yes." in text
    # With the 25 degC curve everywhere, every temperature is valid from 0.
    assert set(md_ocv_rows(text).values()) == {("0.0", "0")}


def test_md_has_one_pair_of_tables_per_temperature_with_c_equal_tau_over_r(tmp_path):
    md_path, _, _ = run_export(tmp_path)
    text = md_path.read_text()

    for temp in T_GRID_DEGC:
        assert f"### {temp} degC" in text
    assert text.count("Fast branch (RC 1):") == 6
    assert text.count("Slow branch (RC 2):") == 6
    for title in ("R0 (mOhm)", "R1 (mOhm)", "tau1 (s)", "C1 (F)", "R2 (mOhm)", "tau2 (s)", "C2 (F)", "RMSE (mV)", "pulses used"):
        assert title in text, title

    # 25 degC, level 1: cold = 0, so R1 = 0.01 Ohm, tau1 = 3 s, C1 = 300 F; R2 = 0.015 Ohm, tau2 = 300 s, C2 = 20000 F.
    section = text.split("### 25 degC")[1].split("### 10 degC")[0]
    level_1_rows = [line for line in section.split("\n") if line.startswith("| 1 |")]  # fast table, then slow table
    fast_cells = [cell.strip() for cell in level_1_rows[0].strip("|").split("|")]
    assert fast_cells == ["1", "100", "20", "10", "3", "300", "1.2", "4"]
    slow_cells = [cell.strip() for cell in level_1_rows[1].strip("|").split("|")]
    assert slow_cells == ["1", "91", "15", "300", "20000", "0.8"]


def test_md_shows_n_a_for_missing_values_and_ignores_flag_columns(tmp_path):
    md_path, _, _ = run_export(tmp_path)
    text = md_path.read_text()

    # The last level of 25 degC (level 12) has no R2, tau2, SoC or RMSE for the slow branch.
    section = text.split("### 25 degC")[1].split("### 10 degC")[0]
    slow_last = [line for line in section.split("\n") if line.startswith("| 12 |")][1]
    assert [cell.strip() for cell in slow_last.strip("|").split("|")] == ["12", "n/a", "n/a", "n/a", "n/a", "n/a"]

    # The failed fast fit of -20 degC level 1 shows n/a in R0, R1, tau1, C1 and RMSE, and 0 pulses used.
    section = text.split("### -20 degC")[1]
    fast_first = [line for line in section.split("\n") if line.startswith("| 1 |")][0]
    cells = [cell.strip() for cell in fast_first.strip("|").split("|")]
    assert cells == ["1", "100", "n/a", "n/a", "n/a", "n/a", "n/a", "0"]

    # The flag columns of fit_levels.csv are not shown.
    assert "_ok" not in text and "True" not in text
    assert "nan" not in text.lower().replace("n/a", "")


def test_md_text_takes_dataframes_and_is_plain_text():
    # params_md_text works on DataFrames, so a caller that has them in memory needs no files.
    params_df = pd.DataFrame(
        {
            "T_degC": [25.0] * 3,
            "soc": [0.0, 0.5, 1.0],
            "ocv_V": [3.0, 3.5, 4.0],
            "docv_V_per_soc": [1.0, 1.0, 1.0],
        }
    )
    levels_df = pd.DataFrame(
        {
            "T_degC": [25.0, 25.0],
            "level": [2, 1],
            "soc_pulses": [0.8, 1.0],
            "R0_ohm": [0.02, 0.021],
            "R1_ohm": [0.01, 0.011],
            "tau1_s": [3.0, 3.3],
            "rmse_fast_mV": [1.0, 1.1],
            "n_pulses_used": [4, 3],
            "soc_rest": [0.8, 0.6],
            "R2_ohm": [0.015, np.nan],
            "tau2_s": [300.0, np.nan],
            "rmse_slow_mV": [0.5, np.nan],
        }
    )
    text = export_params.params_md_text(params_df, levels_df)
    # Levels are listed in level order, not input order.
    assert text.index("| 1 | 100 |") < text.index("| 2 | 80 |")


def test_md_prints_n_a_for_c_when_a_resistance_is_zero_or_missing():
    # C = tau / R must not stop the export when R is 0 (a fit that ends at the bound) or missing (a failed fit).
    assert export_params.capacitance(3.0, 0.01) == pytest.approx(300.0)
    assert math.isnan(export_params.capacitance(3.0, 0.0))
    assert math.isnan(export_params.capacitance(3.0, math.nan))
    assert math.isnan(export_params.capacitance(math.nan, 0.01))

    params_df = pd.DataFrame({"T_degC": [25.0, 25.0], "soc": [0.0, 1.0], "ocv_V": [3.0, 4.0]})
    levels_df = pd.DataFrame(
        {
            "T_degC": [25.0],
            "level": [1],
            "soc_pulses": [1.0],
            "R0_ohm": [0.02],
            "R1_ohm": [0.0],
            "tau1_s": [3.0],
            "rmse_fast_mV": [1.0],
            "n_pulses_used": [4],
            "soc_rest": [0.9],
            "R2_ohm": [0.0],
            "tau2_s": [300.0],
            "rmse_slow_mV": [0.5],
        }
    )
    text = export_params.params_md_text(params_df, levels_df)
    assert "| 1 | 100 | 20 | 0 | 3 | n/a | 1 | 4 |" in text
    assert "| 1 | 90 | 0 | 300 | n/a | 0.5 |" in text


def test_outputs_do_not_name_the_private_spec_file(tmp_path):
    md_path, c_path, h_path = run_export(tmp_path)
    for path in (md_path, c_path, h_path, export_params.__file__):
        text = open(path).read()
        assert "PR" + "D" not in text, path
