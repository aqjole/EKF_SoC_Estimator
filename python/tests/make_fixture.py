"""Write the CI fixture python/tests/fixtures/lghg2_excerpt.mat from the raw data.

The fixture is a copy of data/raw/25degC/<551_Cap_1C file>: a 1C constant-current discharge at 25 degC,
logged every 10 s, 397 rows, about 11 kB. The whole file is small, so nothing is trimmed. It is saved
with scipy.io.savemat as the same struct "meas" with the same eight fields, in the types the cycler
file stores them (Wh as uint8, TimeStamp as a cell array of text), so the loader sees what it sees in
the real files. Tests that use it run in CI without the 206 raw files.

Run from the repo root:  .venv/bin/python python/tests/make_fixture.py
Needs data/raw/. The source file and licence are in python/tests/fixtures/README.md.
"""

import sys
from pathlib import Path

import numpy as np
import scipy.io

# The package lives in python/, one level above this script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ekfsoc import rawio  # noqa: E402
from ekfsoc.constants import RAW_DIR  # noqa: E402
from ekfsoc.loader import find_runs  # noqa: E402


SOURCE_MARKER = "551_Cap_1C"
OUT_PATH = Path(__file__).resolve().parent / "fixtures" / "lghg2_excerpt.mat"
MAX_BYTES = 1_000_000  # the fixture is committed, so the whole source file must be small


def find_source():
    """Return the path of the 25degC 551_Cap_1C file (there is a second Cap_1C file, 552, in that folder)."""
    candidates = find_runs(RAW_DIR, test_type="cap_1c", folder="25degC")
    matches = [path for path in candidates if SOURCE_MARKER in path.name]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {SOURCE_MARKER} file in 25degC, found {[p.name for p in matches]}")
    return matches[0]


def read_stored_columns(path):
    """Read the struct fields with their stored types (rawio.load_mat would cast everything to float64).

    The cycler files store every field as a column (n, 1); that shape is kept.
    """
    struct = scipy.io.loadmat(path, squeeze_me=True, struct_as_record=False)["meas"]
    return {name: np.atleast_1d(getattr(struct, name)).reshape(-1, 1) for name in struct._fieldnames}


def main():
    source = find_source()
    size = source.stat().st_size
    if size >= MAX_BYTES:
        raise RuntimeError(f"{source.name} is {size} bytes; the whole file is not under 1 MB, trim it first")

    scipy.io.savemat(OUT_PATH, {"meas": read_stored_columns(source)}, do_compression=True)

    # Read both back through the project's own reader and compare every field.
    original = rawio.load_mat(source)
    excerpt = rawio.load_mat(OUT_PATH)
    for name in rawio.EXPECTED_FIELDS:
        if not np.array_equal(original[name], excerpt[name], equal_nan=name != "TimeStamp"):
            raise RuntimeError(f"field {name} differs between the source and the fixture")

    print(f"source:  {source.name} ({size} bytes, {len(original['Time'])} rows)")
    print(f"fixture: {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
