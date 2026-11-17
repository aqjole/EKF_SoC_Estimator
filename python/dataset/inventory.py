"""S0 data inventory: walk data/raw/ and describe every file.

Writes two files:
- results/s0/data_inventory.md: one row per .mat file (time base, ranges, flags)
  plus a summary per temperature folder.
- results/s0/capacity.md: every capacity test in campaign order, the C/20 and 1C
  capacities per folder, and a check of the drive-cycle stop rule.

Run from the repo root:  PYTHONPATH=python .venv/bin/python python/dataset/inventory.py   (or: make inventory)

All values keep the cycler's sign (discharge current and discharged Ah are
negative), except where a column says "removed", which is positive. Every
number is measured from the files; nothing is copied from the readme.
"""

from dataset.capacity_report import write_capacity
from dataset.common import FOLDER_TEMPS_DEGC
from dataset.inventory_links import check_inside_earlier, check_previous_file, full_charge_start
from dataset.inventory_scan import summarize_file
from dataset.inventory_table import write_inventory
from ekfsoc.constants import RAW_DIR, REPO_DIR


RESULTS_DIR = REPO_DIR / "results"


def main():
    """Walk data/raw/, summarise every file, write both reports."""
    folder_names = [path.name for path in RAW_DIR.iterdir() if path.is_dir()]
    unknown = [name for name in folder_names if name not in FOLDER_TEMPS_DEGC]
    if unknown:
        print(f"warning: folders with no known temperature: {unknown}")

    records_by_folder = {}
    failures = []
    for folder in sorted(folder_names):
        records = []
        for path in sorted((RAW_DIR / folder).glob("*.mat")):
            try:
                records.append(summarize_file(folder, path))
            except Exception as error:   # report and continue: one bad file must not hide the rest
                failures.append((f"{folder}/{path.name}", f"{type(error).__name__}: {error}"))
        records.sort(key=lambda r: r["start"])
        for r in records:
            r["full_charge"] = full_charge_start(r, records)
        for previous, r in zip(records, records[1:]):
            check_previous_file(r, previous)
        for r in records:
            check_inside_earlier(r, records)
        for r in records:
            del r["abs_time_s"], r["voltage"], r["current"]
        records_by_folder[folder] = records
        print(f"{folder}: {len(records)} files")

    # Campaign order: folders sorted by their earliest TimeStamp.
    folders = sorted((f for f in records_by_folder if records_by_folder[f]),
                     key=lambda f: min(r["start"] for r in records_by_folder[f]))

    RESULTS_DIR.mkdir(exist_ok=True)
    write_inventory(folders, records_by_folder, failures, RESULTS_DIR / "s0" / "data_inventory.md")
    write_capacity(folders, records_by_folder, RESULTS_DIR / "s0" / "capacity.md")
    total = sum(len(records) for records in records_by_folder.values())
    print(f"wrote results/s0/data_inventory.md ({total} files, {len(failures)} failed) and results/s0/capacity.md")
    for path, error in failures:
        print(f"failed: {path}: {error}")


if __name__ == "__main__":
    main()
