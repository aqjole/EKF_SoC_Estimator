"""pytest setup shared by all tests.

- Puts python/ on sys.path so that `import ekfsoc` works whatever directory pytest starts from.
- Defines the `needs_data` marker. A test marked with it needs the raw .mat files in data/raw/
  and is skipped when they are missing (CI has only the committed fixture).
- data_checks_table: reads one table of results/s0/data_checks.md for the tests that compare with it.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ekfsoc.constants import RAW_DIR, REPO_DIR  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_data: test needs the raw dataset in data/raw/ (skipped when missing)")


def pytest_collection_modifyitems(config, items):
    if RAW_DIR.is_dir() and any(RAW_DIR.glob("*/*.mat")):
        return
    skip_no_data = pytest.mark.skip(reason="data/raw/ is missing or empty")
    for item in items:
        if "needs_data" in item.keywords:
            item.add_marker(skip_no_data)


@pytest.fixture(scope="session")
def data_checks_table():
    """Return table(section, header_text) -> {folder: {column: cell text}}, read from results/s0/data_checks.md.

    The table is the first one under "## <section>. ..." whose header line "| folder | ..." contains header_text.
    """
    text = (REPO_DIR / "results" / "s0" / "data_checks.md").read_text()

    def table(section, header_text):
        lines = text.split(f"\n## {section}. ")[1].split("\n## ")[0].splitlines()
        start = next(n for n, line in enumerate(lines) if line.startswith("| folder |") and header_text in line)
        header = [cell.strip() for cell in lines[start].strip("|").split("|")]
        rows = {}
        for line in lines[start + 2:]:
            if not line.startswith("|"):
                break
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows[cells[0]] = dict(zip(header, cells))
        return rows

    return table
