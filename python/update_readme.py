"""Copy the results tables from results/*.md into README.md and docs/results.md, between marker comments.

Every key in a document's sources has a marker pair in that document, `<!-- results:<key>:begin -->` and
`<!-- results:<key>:end -->`, and the text between the two is replaced by the sections the document's sources
name for that key, copied verbatim. A section is the text under a heading line, up to the next heading of the same
or higher level. A heading path picks each heading inside the section of the one before it, because
results/ekf_summary.md repeats the same sub-headings under every experiment. Each copied section starts
with its heading path in bold, and a heading inside it becomes a bold line, so the copy never adds a
heading to the document's outline. Running the script twice changes nothing.

Usage: python python/update_readme.py [--check]
--check writes nothing and exits non-zero when a document is out of sync (CI and make readme-check).
"""

import argparse
import re
import sys

from ekfsoc.constants import REPO_DIR

# (marker key, results file, heading path): a key with several entries gets their sections in this order.
README_SOURCES = [
    ("summary_exp1", "results/model_compare_r1i.md", ("Experiment 1",)),
    ("summary_equivalence", "results/equivalence.md", ("Result",)),
]

RESULTS_SOURCES = [
    ("capacity", "results/capacity.md", ("C/20 and 1C capacities per folder",)),
    ("model_fit", "results/model_fit.md", ("Open-loop voltage error on US06",)),
    ("ocv_correction", "results/params.md", ("OCV correction from the HPPC rest voltages",)),
    ("ekf_legend", "results/ekf_summary.md", ("Legend",)),
    ("ekf_exp1", "results/ekf_summary.md", ("Experiment 1: correct initial SoC", "SoC RMSE (pp)")),
    ("ekf_exp1", "results/ekf_summary.md",
     ("Experiment 1: correct initial SoC", "Coulomb counting against the reference: SoC RMSE (pp)")),
    ("ekf_exp2", "results/ekf_summary.md", ("Experiment 2: initial SoC 20 pp too low", "SoC RMSE (pp)")),
    ("ekf_exp2", "results/ekf_summary.md",
     ("Experiment 2: initial SoC 20 pp too low",
      "Convergence time t_conv (s): the error stays within +-2 pp from then on")),
    ("ekf_exp3", "results/ekf_summary.md",
     ("Experiment 3, low start: initial SoC 50 % from a reference of 70 %",
      "Convergence time t_conv (s): the error stays within +-2 pp from then on")),
    ("ekf_exp3", "results/ekf_summary.md",
     ("Experiment 3, high start: initial SoC 90 % from a reference of 70 %",
      "Convergence time t_conv (s): the error stays within +-2 pp from then on")),
    ("ekf_exp4", "results/ekf_summary.md", ("Experiment 4: current offset", "EKF error at the end of the window (pp)")),
    ("ekf_exp4", "results/ekf_summary.md",
     ("Experiment 4: current offset", "Coulomb counting error at the end of the window (pp)")),
    ("ekf_exp4", "results/ekf_summary.md",
     ("Experiment 4: current offset", "Expected coulomb-counting drift over the window (pp)")),
    ("equivalence", "results/equivalence.md", ("Result",)),
    ("equivalence", "results/equivalence.md", ("Per temperature",)),
    ("footprint", "results/c_footprint.md", ("C library footprint (Cortex-M4, float build)",)),
    ("sensitivity_capacity", "results/sensitivity.md", ("Capacity error: the filter capacity at -5 % and +5 %",)),
    ("sensitivity_rate", "results/sensitivity.md", ("Sample rate: every 10th row (1 Hz)",)),
    ("equivalence_octave", "results/equivalence_octave.md", ("Result",)),
    ("equivalence_octave", "results/equivalence_octave.md", ("Per temperature",)),
    ("model_fit_3rc", "results/model_fit_3rc.md", ("Open-loop voltage error on US06, 2RC and 3RC",)),
    ("model_fit_3rc", "results/model_fit_3rc.md", ("Ceiling: a third branch added to the 2RC model",)),
    ("model_fit_3rc", "results/model_fit_3rc.md", ("Ceiling over every drive cycle",)),
    ("model_fit_3rc_rest", "results/model_fit_3rc_rest.md", ("Open-loop voltage error on US06, 2RC and second 3RC fit",)),
    ("model_fit_3rc_rest", "results/model_fit_3rc_rest.md", ("Open-loop error over every drive cycle",)),
    ("model_fit_r1i", "results/model_fit_r1i.md", ("R1 per pulse",)),
    ("model_compare_r1i", "results/model_compare_r1i.md", ("Open loop",)),
    ("model_compare_r1i", "results/model_compare_r1i.md", ("Experiment 1",)),
    ("model_compare_r1i", "results/model_compare_r1i.md", ("Experiments 2 to 4",)),
    ("model_compare_r1i", "results/model_compare_r1i.md", ("Adoption verdict",)),
    ("s8_us06", "results/model_compare_r1c.md", ("Experiment 1", "US06")),
    ("s8_step_a", "results/model_compare_r1d.md", ("Guards and adoption verdict",)),
    ("s8_step_b", "results/model_compare_r1c.md", ("Guards and adoption verdict",)),
]

# Each document, relative to the repo root, with the sections copied into it.
DOCS = {"README.md": README_SOURCES, "docs/results.md": RESULTS_SOURCES}

HEADING = re.compile(r"(#{1,6}) (.+)")


def section(lines, title, where):
    """Return the lines under the first heading named title, up to the next heading of its level or higher."""
    for start, line in enumerate(lines):
        match = HEADING.fullmatch(line)
        if match and match.group(2).strip() == title:
            level = len(match.group(1))
            body = []
            for line in lines[start + 1:]:
                inner = HEADING.fullmatch(line)
                if inner and len(inner.group(1)) <= level:
                    break
                body.append(line)
            return body
    raise SystemExit(f"update_readme: {where} has no heading '{title}'")


def render(repo_dir, file, path):
    """Return one copied section: its heading path in bold, then its text with inner headings in bold."""
    lines = (repo_dir / file).read_text().splitlines()
    for title in path:
        lines = section(lines, title, f"{file} (heading path {' / '.join(path)})")
    body = []
    for line in lines:
        match = HEADING.fullmatch(line)
        body.append(f"**{match.group(2).strip()}**" if match else line)
    text = "\n".join(body).strip("\n")
    return f"**{' / '.join(path)}**\n\n{text}"


def fill(text, key, content, name):
    """Return text (the document called name) with the part between the key's markers replaced by content."""
    begin = f"<!-- results:{key}:begin -->"
    end = f"<!-- results:{key}:end -->"
    i = text.find(begin)
    j = text.find(end)
    if i < 0 or j < i:
        raise SystemExit(f"update_readme: {name} has no marker pair '{begin}' ... '{end}'")
    return text[:i + len(begin)] + "\n\n" + content + "\n\n" + text[j:]


def updated(text, repo_dir, sources, name):
    """Return text (the document called name) with every key of sources filled from its results sections."""
    sections = {}
    for key, file, path in sources:
        sections.setdefault(key, []).append(render(repo_dir, file, path))
    for key, parts in sections.items():
        text = fill(text, key, "\n\n".join(parts), name)
    return text


def run(repo_dir, docs, check):
    """Update every document of docs, or with check only compare them; return the exit code."""
    stale = []
    for name, sources in docs.items():
        path = repo_dir / name
        text = path.read_text()
        new = updated(text, repo_dir, sources, name)
        if new != text:
            stale.append(name)
            if not check:
                path.write_text(new)
                print(f"wrote {name}")
    if check and stale:
        print(f"update_readme: {', '.join(stale)} out of sync with results/; run 'make readme'", file=sys.stderr)
        return 1
    if check or not stale:
        print(f"{', '.join(docs)}: in sync with results/")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit non-zero if README.md or docs/results.md is out of sync")
    args = parser.parse_args()
    sys.exit(run(REPO_DIR, DOCS, args.check))


if __name__ == "__main__":
    main()
