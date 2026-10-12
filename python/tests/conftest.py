"""pytest setup shared by all tests.

- Puts python/ on sys.path so that `import ekfsoc` works whatever directory pytest starts from.
- Defines the `needs_data` marker. A test marked with it needs the raw .mat files in data/raw/
  and is skipped when they are missing (CI has only the committed fixture).
"""

import sys
from pathlib import Path

import pytest

PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from ekfsoc.constants import RAW_DIR  # noqa: E402


def raw_data_present():
    """True when data/raw/ holds at least one .mat file under a sub-folder."""
    return RAW_DIR.is_dir() and any(RAW_DIR.glob("*/*.mat"))


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_data: test needs the raw dataset in data/raw/ (skipped when missing)")


def pytest_collection_modifyitems(config, items):
    if raw_data_present():
        return
    skip_no_data = pytest.mark.skip(reason="data/raw/ is missing or empty")
    for item in items:
        if "needs_data" in item.keywords:
            item.add_marker(skip_no_data)
