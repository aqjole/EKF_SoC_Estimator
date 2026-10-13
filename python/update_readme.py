"""Copy the results tables from results/*.md into README.md, between marker comments.

Every key in SOURCES has a marker pair in README.md, `<!-- results:<key>:begin -->` and
`<!-- results:<key>:end -->`, and the text between the two is replaced by the sections SOURCES names for
that key, copied verbatim. A section is the text under a heading line, up to the next heading of the same
or higher level. A heading path picks each heading inside the section of the one before it, because
results/ekf_summary.md repeats the same sub-headings under every experiment. Each copied section starts
with its heading path in bold, and a heading inside it becomes a bold line, so the copy never adds a
heading to the README outline. Running the script twice changes nothing.

Usage: python python/update_readme.py [--check]
--check writes nothing and exits non-zero when README.md is out of sync (CI and make readme-check).
"""

import argparse
import re
import sys

from ekfsoc.constants import REPO_DIR

# (marker key, results file, heading path): a key with several entries gets their sections in this order.
SOURCES = [
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
]

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


def fill(readme, key, content):
    """Return readme with the text between the key's markers replaced by content."""
    begin = f"<!-- results:{key}:begin -->"
    end = f"<!-- results:{key}:end -->"
    i = readme.find(begin)
    j = readme.find(end)
    if i < 0 or j < i:
        raise SystemExit(f"update_readme: README.md has no marker pair '{begin}' ... '{end}'")
    return readme[:i + len(begin)] + "\n\n" + content + "\n\n" + readme[j:]


def updated(readme, repo_dir, sources):
    """Return readme with every key of sources filled from its results sections."""
    sections = {}
    for key, file, path in sources:
        sections.setdefault(key, []).append(render(repo_dir, file, path))
    for key, parts in sections.items():
        readme = fill(readme, key, "\n\n".join(parts))
    return readme


def run(repo_dir, sources, check):
    """Update repo_dir/README.md, or with check only compare it; return the exit code."""
    readme_path = repo_dir / "README.md"
    readme = readme_path.read_text()
    new = updated(readme, repo_dir, sources)
    if check:
        if new != readme:
            print("update_readme: README.md is out of sync with results/; run 'make readme'", file=sys.stderr)
            return 1
        print("README.md is in sync with results/")
        return 0
    if new != readme:
        readme_path.write_text(new)
        print("wrote README.md")
    else:
        print("README.md unchanged")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit non-zero if README.md is out of sync")
    args = parser.parse_args()
    sys.exit(run(REPO_DIR, SOURCES, args.check))


if __name__ == "__main__":
    main()
