"""Stage S3 footprint: cross-compile the C library for a Cortex-M4 and write results/s3/c_footprint.md.

Run from the repo root:  .venv/bin/python python/arm_footprint.py   (or: make arm; needs arm-none-eabi-gcc on PATH)
With --model 3rcd0 (make arm-3rcd0, decision 1.54) the four-state 3RC-D0 build is measured instead, compiled with
-fstack-usage, and results/s11/c_footprint_3rcd0.md also lists the static stack frame of each library function.

  1. c/ is configured with the toolchain file c/cmake/arm-none-eabi.cmake into c/build/arm, and only the ekf
     library is built (the spec, S3: library objects only, nothing is linked).
  2. arm-none-eabi-size gives .text, .data and .bss of ekf.c.obj and ekf_params.c.obj.
  3. sizeof(ekf_t) on the target is the size of the object ekf_t_size_marker (c/src/ekf_size_marker.c), read with
     arm-none-eabi-nm -S, because a struct with a pointer has another size on a 64-bit host.
  4. arm-none-eabi-nm -u lists the symbols the library needs from outside. A double-precision helper of the Arm
     run-time ABI among them means a double operation slipped into the float build: the table is still written,
     then the script exits with status 1.

Standard library only, so the CI job runs it without installing the Python requirements.
"""

import argparse
import json
import shlex
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
C_DIR = REPO_DIR / "c"
TOOLCHAIN_FILE = C_DIR / "cmake" / "arm-none-eabi.cmake"

# Model -> (build folder, extra CMake options, counted objects, report path, make target).
MODELS = {
    "2rc": ("arm", (), ("ekf.c.obj", "ekf_params.c.obj"), REPO_DIR / "results" / "s3" / "c_footprint.md", "make arm"),
    "3rcd0": ("arm-3rcd0", ("-DEKF_USE_3RCD0=ON", "-DEKF_STACK_USAGE=ON"), ("ekf.c.obj", "ekf_params_3rcd0.c.obj"),
              REPO_DIR / "results" / "s11" / "c_footprint_3rcd0.md", "make arm-3rcd0"),
}
MARKER_OBJECT = "ekf_size_marker.c.obj"
DOUBLE_HELPERS = ("__aeabi_d*", "__aeabi_f2d", "__aeabi_i2d", "__aeabi_ui2d", "__aeabi_l2d", "__aeabi_ul2d")


def output_of(*command):
    """Run a command and return its standard output."""
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def build_library(build_dir, options):
    """Configure the ARM build and build the ekf library target only."""
    subprocess.run(["cmake", "-S", str(C_DIR), "-B", str(build_dir), f"-DCMAKE_TOOLCHAIN_FILE={TOOLCHAIN_FILE}",
                    "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", *options], check=True)
    subprocess.run(["cmake", "--build", str(build_dir), "--target", "ekf"], check=True)


def compiler_version():
    return output_of("arm-none-eabi-gcc", "--version").splitlines()[0]


def library_flags(build_dir):
    """The flags ekf.c was compiled with, from compile_commands.json, without include paths, -c and -o."""
    commands = json.loads((build_dir / "compile_commands.json").read_text())
    command = next(entry["command"] for entry in commands if entry["file"].endswith("/src/ekf.c"))
    flags = [token for token in shlex.split(command)[1:] if token.startswith("-")]
    return [flag for flag in flags if not flag.startswith("-I") and flag not in ("-c", "-o")]


def section_sizes(object_dir, objects):
    """(object, text, data, bss) of each counted object, from the Berkeley format of arm-none-eabi-size."""
    text = output_of("arm-none-eabi-size", *(str(object_dir / name) for name in objects))
    rows = []
    for line, name in zip(text.splitlines()[1:], objects):
        text_b, data_b, bss_b = (int(field) for field in line.split()[:3])
        rows.append((name, text_b, data_b, bss_b))
    return rows


def ekf_t_size(object_dir):
    """sizeof(ekf_t) on the target: the size column of nm -S for ekf_t_size_marker."""
    for line in output_of("arm-none-eabi-nm", "-S", str(object_dir / MARKER_OBJECT)).splitlines():
        fields = line.split()
        if fields and fields[-1] == "ekf_t_size_marker":
            return int(fields[1], 16)
    raise RuntimeError("ekf_t_size_marker not found in " + MARKER_OBJECT)


def undefined_symbols(library):
    """The symbols the library objects reference but do not define, sorted and without duplicates."""
    lines = output_of("arm-none-eabi-nm", "-u", str(library)).splitlines()
    return sorted({line.split()[-1] for line in lines if line.strip().startswith("U ")})


def stack_frames(object_dir):
    """(function, bytes, kind) from the compiler's ekf.c.su: the static stack frame of each function of ekf.c."""
    rows = []
    for line in (object_dir / "ekf.c.su").read_text().splitlines():
        location, size, kind = line.split("\t")
        rows.append((location.rsplit(":", 1)[-1], int(size), kind))
    return rows


def stack_lines(frames):
    lines = ["", "## Static stack frames", "",
             "From `-fstack-usage` (`ekf.c.su`): the frame of each function of `ekf.c` in bytes, as the compiler",
             "reports it. A call nests the frames of the functions it calls; nothing here is measured on a target.", "",
             "| function | bytes | kind |", "|---|---:|---|"]
    return lines + [f"| {name} | {size} | {kind} |" for name, size, kind in frames]


def footprint_md(version, flags, rows, state_size, undefined, helpers, title, command, frames=None):
    total = [sum(row[k] for row in rows) for k in (1, 2, 3)]
    lines = [
        f"# {title}",
        "",
        f"Generated by python/arm_footprint.py ({command}), do not edit. The library is cross-compiled only; nothing",
        "is linked or run on a target.",
        "",
        f"- Compiler: `{version}`",
        f"- Flags of the library objects: `{' '.join(flags)}`",
        "",
        "Sections of the library objects in bytes, from arm-none-eabi-size. The parameter tables are const, so they",
        "count in .text (flash), not in .data (RAM). The size marker object and the host tools are not counted.",
        "",
        "| object | .text | .data | .bss | total |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, text_b, data_b, bss_b in rows:
        lines.append(f"| {name} | {text_b} | {data_b} | {bss_b} | {text_b + data_b + bss_b} |")
    lines += [
        f"| total | {total[0]} | {total[1]} | {total[2]} | {sum(total)} |",
        "",
        f"sizeof(ekf_t) = {state_size} bytes: the state of one filter, which the caller owns (one per cell). Read",
        "with arm-none-eabi-nm -S from the object ekf_t_size_marker[sizeof(ekf_t)] (c/src/ekf_size_marker.c).",
        "",
        "## Double-precision helper check",
        "",
        "Undefined symbols of libekf.a (arm-none-eabi-nm -u): " + ", ".join(f"`{s}`" for s in undefined) + ".",
        "",
        "Double-precision helpers searched for: " + ", ".join(f"`{h}`" for h in DOUBLE_HELPERS) + ".",
        "",
        ("Result: FAIL, found " + ", ".join(f"`{h}`" for h in helpers) + ".") if helpers else "Result: PASS, none found.",
    ]
    if frames is not None:
        lines += stack_lines(frames)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", choices=MODELS, default="2rc")
    model = parser.parse_args().model
    folder, options, objects, path, command = MODELS[model]
    build_dir = C_DIR / "build" / folder
    object_dir = build_dir / "CMakeFiles" / "ekf.dir" / "src"
    build_library(build_dir, options)
    undefined = undefined_symbols(build_dir / "libekf.a")
    helpers = [symbol for symbol in undefined if any(fnmatchcase(symbol, helper) for helper in DOUBLE_HELPERS)]
    title = "C library footprint (Cortex-M4, float build)" if model == "2rc" else \
        "C library footprint, 3RC-D0 (Cortex-M4, float build)"
    frames = stack_frames(object_dir) if model == "3rcd0" else None
    text = footprint_md(compiler_version(), library_flags(build_dir), section_sizes(object_dir, objects),
                        ekf_t_size(object_dir), undefined, helpers, title, command, frames)
    path.write_text(text)
    print(f"wrote {path.relative_to(REPO_DIR)}")
    if helpers:
        sys.exit("double-precision helpers referenced by the library: " + ", ".join(helpers))


if __name__ == "__main__":
    main()
