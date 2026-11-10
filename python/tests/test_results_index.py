"""results/README.md, the index of the result files, against what git tracks under results/s*/."""

import re
import subprocess

from ekfsoc.constants import REPO_DIR

RESULTS = REPO_DIR / "results"
INDEX = (RESULTS / "README.md").read_text()
# A stage file as the index names it, relative to results/: s7/r1_current.csv (not plots/s7/...).
NAMED = set(re.findall(r"(?<![\w/.])s\d+/[\w.-]+\.\w+", INDEX))
LINKS = set(re.findall(r"\]\(([^)#]+)", INDEX))


def tracked_stage_files():
    """Every file git tracks under results/s<n>/, relative to results/."""
    files = subprocess.run(["git", "ls-files", "results"], cwd=REPO_DIR, check=True, capture_output=True,
                           text=True).stdout.splitlines()
    return {path.removeprefix("results/") for path in files if re.match(r"results/s\d+/", path)}


def test_every_tracked_result_file_is_named():
    assert tracked_stage_files() - NAMED == set()


def test_every_named_file_exists():
    assert {name for name in NAMED if not (RESULTS / name).is_file()} == set()


def test_every_link_resolves():
    assert {link for link in LINKS if not (RESULTS / link).exists()} == set()
