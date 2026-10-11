#!/usr/bin/env bash
# Fetch the LG 18650HG2 dataset (Mendeley Data b5mj79w5w9, version 2, CC BY 4.0)
# into data/raw/ file by file and verify it. Raw data is never committed.
#
# Why file by file: the "Download All" zip on Mendeley's S3 cache refuses
# non-browser clients (HTTP 403). The per-file public API works and publishes
# a sha256 per file. Only the .mat files and the documentation are fetched;
# the readme states the CSV files hold identical data.
#
# First run:  records every file's sha256 in data/checksums.sha256.
# Later runs: verifies every file against data/checksums.sha256.
# Every run also verifies each file against the sha256 published by the API.
# Re-running is safe: complete files are skipped, partial ones are refetched.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW="$HERE/raw"
CHECKSUMS="$HERE/checksums.sha256"
mkdir -p "$RAW"

python3 -I - "$RAW" "$CHECKSUMS" <<'PY'
import hashlib, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

DATASET = "b5mj79w5w9"
VERSION = "2"
API = f"https://data.mendeley.com/public-api/datasets/{DATASET}"
KEEP = (".mat", ".txt", ".pdf", ".m")  # .csv duplicates are skipped
WORKERS = 8
# Mendeley's CDN rejects Python's default user agent with HTTP 403.
HEADERS = {"User-Agent": "ekf-soc-estimator/data-download.sh (python-urllib)", "Accept": "*/*"}

raw, checksums = sys.argv[1], sys.argv[2]


def open_url(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120)


def get_json(url):
    with open_url(url) as r:
        return json.load(r)


def fetch(url, path):
    with open_url(url) as r, open(path, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_folder(folder_id, rel):
    files = get_json(f"{API}/files?folder_id={folder_id}&version={VERSION}&$start=0&$limit=1000")
    out = []
    for f in files:
        name = f["filename"]
        if not name.lower().endswith(KEEP):
            continue
        cd = f["content_details"]
        out.append((os.path.join(rel, name), cd["download_url"], cd["sha256_hash"], f["size"]))
    return out


def download_one(entry):
    """Download one file unless a complete copy exists. Returns (rel, downloaded, error)."""
    rel, url, api_sha, size = entry
    path = os.path.join(raw, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) == size:
        return rel, False, None
    for attempt in range(3):
        try:
            fetch(url, path + ".part")
            os.replace(path + ".part", path)
            return rel, True, None
        except Exception as e:  # network hiccup: retry
            if attempt == 2:
                return rel, False, str(e)
            time.sleep(3)


print("Listing files on Mendeley Data ...")
entries = list_folder("root", "")
for folder in get_json(f"{API}/folders/{VERSION}"):
    entries += list_folder(folder["id"], folder["name"])
entries.sort()
total = sum(e[3] for e in entries)
print(f"  {len(entries)} files to keep, {total/1e6:.1f} MB")

recorded = {}
if os.path.exists(checksums) and os.path.getsize(checksums) > 0:
    with open(checksums) as f:
        for line in f:
            digest, _, rel = line.rstrip("\n").partition("  ")
            recorded[rel] = digest
    print(f"  verifying against {len(recorded)} entries in data/checksums.sha256")

errors = 0
downloaded = 0
print(f"Downloading with {WORKERS} parallel connections ...")
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    for i, (rel, got, err) in enumerate(pool.map(download_one, entries), 1):
        if err:
            print(f"ERROR: download failed for {rel}: {err}", file=sys.stderr)
            errors += 1
        downloaded += int(got)
        if i % 25 == 0:
            print(f"  {i}/{len(entries)} files handled, {downloaded} downloaded ...")

print("Verifying sha256 ...")
for rel, url, api_sha, size in entries:
    path = os.path.join(raw, rel)
    if not os.path.exists(path):
        continue
    got = sha256_of(path)
    if got != api_sha:
        print(f"ERROR: sha256 mismatch against the API for {rel}", file=sys.stderr)
        errors += 1
    if recorded:
        if rel not in recorded:
            print(f"ERROR: {rel} is not in data/checksums.sha256", file=sys.stderr)
            errors += 1
        elif recorded[rel] != got:
            print(f"ERROR: sha256 differs from the one recorded on the first download for {rel}", file=sys.stderr)
            errors += 1

if errors:
    print(f"{errors} error(s).", file=sys.stderr)
    sys.exit(1)

if not recorded:
    with open(checksums, "w") as f:
        for rel, url, api_sha, size in entries:
            f.write(f"{api_sha}  {rel}\n")
    print(f"  recorded {len(entries)} sha256 values in data/checksums.sha256 (first download)")

print(f"Done. {downloaded} file(s) downloaded this run, {len(entries)} verified.")
PY

echo "Contents of data/raw/:"
find "$RAW" -mindepth 1 -maxdepth 1 | sort
echo "$(find "$RAW" -name '*.mat' | wc -l | tr -d ' ') .mat files"
