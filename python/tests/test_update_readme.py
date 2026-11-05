"""Tests for update_readme: filling the marker blocks, idempotence, the two errors and --check.

Each test writes a small results file, README.md and docs/results.md in tmp_path and runs the script's functions on them
with its own sources list, so neither the real README nor results/ is touched.
"""

import pytest

import update_readme

RESULTS = """# Title

## Experiment A

### Table

| a | b |
|---|---|
| 1 | 2 |

## Experiment B

### Table

| a | b |
|---|---|
| 3 | 4 |

#### Note

Legend line.
"""

README = """# Readme

Prose before.

<!-- results:b:begin -->
stale text
<!-- results:b:end -->

Prose after.
"""

SOURCES = [("b", "results.md", ("Experiment B", "Table"))]
DOCS = {"README.md": SOURCES, "docs/results.md": [("b", "results.md", ("Experiment A", "Table"))]}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "results.md").write_text(RESULTS)
    (tmp_path / "README.md").write_text(README)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "results.md").write_text(README)
    return tmp_path


def test_fill_copies_the_section_under_the_heading_path(repo):
    text = update_readme.updated(README, repo, SOURCES, "README.md")
    expected = (
        "<!-- results:b:begin -->\n\n**Experiment B / Table**\n\n"
        "| a | b |\n|---|---|\n| 3 | 4 |\n\n**Note**\n\nLegend line.\n\n<!-- results:b:end -->"
    )
    assert expected in text


def test_second_run_changes_nothing(repo):
    once = update_readme.updated(README, repo, SOURCES, "README.md")
    assert update_readme.updated(once, repo, SOURCES, "README.md") == once


def test_missing_marker_exits_with_message(repo):
    with pytest.raises(SystemExit, match="README.md has no marker pair '<!-- results:c:begin -->'"):
        update_readme.updated(README, repo, [("c", "results.md", ("Experiment B", "Table"))], "README.md")


def test_missing_heading_exits_with_message(repo):
    with pytest.raises(SystemExit, match="results.md .* has no heading 'Experiment C'"):
        update_readme.updated(README, repo, [("b", "results.md", ("Experiment C", "Table"))], "README.md")


def test_check_fails_when_out_of_sync_and_writes_nothing(repo):
    assert update_readme.run(repo, DOCS, check=True) == 1
    assert (repo / "README.md").read_text() == README
    assert (repo / "docs" / "results.md").read_text() == README


def test_check_passes_after_an_update(repo):
    update_readme.run(repo, DOCS, check=False)
    assert update_readme.run(repo, DOCS, check=True) == 0


def test_each_document_gets_its_own_sections(repo):
    update_readme.run(repo, DOCS, check=False)
    assert "| 1 | 2 |" in (repo / "docs" / "results.md").read_text()
