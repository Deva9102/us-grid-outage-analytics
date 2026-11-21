"""Download DOE EAGLE-I county outage files into data/raw/eaglei/.

Source: ORNL EAGLE-I recorded electricity outages, published on Figshare
(DOI 10.6084/m9.figshare.24237376). The file list, sizes and MD5 checksums
come from the Figshare API, pinned to one dataset version so reruns are
reproducible.

Layout:
    data/raw/eaglei/<year>/eaglei_outages_<year>.csv
    data/raw/eaglei/metadata/MCC.csv               modeled customers per county
    data/raw/eaglei/metadata/coverage_history.csv  share of customers covered per state/year
    data/raw/eaglei/metadata/DQI.csv               data quality index

Usage:
    uv run python scripts/download_eaglei.py
    uv run python scripts/download_eaglei.py --years 2022 2023 2024 --verify
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
import zipfile
from pathlib import Path

import requests

import pipeline_config

ARTICLE_ID = 24237376
ARTICLE_VERSION = 4
LANDING_PAGE = f"https://doi.org/10.6084/m9.figshare.{ARTICLE_ID}.v{ARTICLE_VERSION}"
API_URL = f"https://api.figshare.com/v2/articles/{ARTICLE_ID}/versions/{ARTICLE_VERSION}"

DEFAULT_YEARS = pipeline_config.load()["years"]["list"]
METADATA_FILES = ["MCC.csv", "coverage_history.csv", "DQI.csv"]

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "eaglei"

HEADERS = {"User-Agent": "us-grid-outage-analytics/0.1 (python-requests)"}
CHUNK = 1024 * 1024


class ManualDownloadRequired(Exception):
    """The server returned something other than the file (login page, captcha, error)."""


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fetch_file_index() -> dict[str, dict]:
    resp = requests.get(API_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return {f["name"]: f for f in resp.json()["files"]}


def print_progress(name: str, done: int, total: int, started: float) -> None:
    elapsed = max(time.time() - started, 1e-6)
    pct = done / total * 100 if total else 0
    rate = done / elapsed
    sys.stdout.write(
        f"\r  {name}: {pct:5.1f}%  {human(done)} / {human(total)}  {human(rate)}/s   "
    )
    sys.stdout.flush()


def download(meta: dict, dest: Path, verify: bool) -> None:
    name, size, md5 = meta["name"], meta["size"], meta.get("computed_md5")
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size == size:
        if not verify or md5sum(dest) == md5:
            print(f"  {name}: already downloaded ({human(size)}), skipping")
            return
        print(f"  {name}: checksum mismatch, downloading again")
        dest.unlink()

    # Download into a .part file so an interrupted run resumes instead of restarting.
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = dict(HEADERS)
    if have:
        headers["Range"] = f"bytes={have}-"

    with requests.get(meta["download_url"], headers=headers, stream=True, timeout=60) as resp:
        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code in (401, 403) or "text/html" in ctype:
            raise ManualDownloadRequired(name)
        if resp.status_code == 200 and have:
            have = 0  # server ignored the Range header, start over
        elif resp.status_code not in (200, 206):
            resp.raise_for_status()

        started = time.time()
        with part.open("ab" if have else "wb") as f:
            done = have
            for block in resp.iter_content(CHUNK):
                f.write(block)
                done += len(block)
                print_progress(name, done, size, started)
        print()

    if part.stat().st_size != size:
        raise RuntimeError(f"{name}: expected {size} bytes, got {part.stat().st_size}")
    if md5 and md5sum(part) != md5:
        part.unlink()
        raise RuntimeError(f"{name}: MD5 mismatch, partial file removed, rerun to retry")
    part.rename(dest)
    print(f"  {name}: done, MD5 verified")


def extract_if_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        return
    marker = path.with_suffix(".extracted")
    if marker.exists():
        return
    print(f"  extracting {path.name}")
    with zipfile.ZipFile(path) as zf:
        zf.extractall(path.parent)
    marker.touch()


def list_tree(root: Path) -> None:
    print(f"\nContents of {root.relative_to(REPO_ROOT)}/")
    total = 0
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != ".gitkeep":
            total += p.stat().st_size
            print(f"  {human(p.stat().st_size):>10}  {p.relative_to(root)}")
    print(f"  {human(total):>10}  total")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS)
    parser.add_argument("--verify", action="store_true", help="re-check MD5 of files already on disk")
    args = parser.parse_args()

    print(f"Reading file index from {API_URL}")
    index = fetch_file_index()

    targets: list[tuple[str, Path]] = []
    for year in args.years:
        name = f"eaglei_outages_{year}.csv"
        targets.append((name, RAW_DIR / str(year) / name))
    for name in METADATA_FILES:
        targets.append((name, RAW_DIR / "metadata" / name))

    missing = [name for name, _ in targets if name not in index]
    if missing:
        print(f"Not in dataset version {ARTICLE_VERSION}: {', '.join(missing)}")
        return 1

    manual: list[tuple[str, Path]] = []
    for name, dest in targets:
        try:
            download(index[name], dest, args.verify)
            extract_if_zip(dest)
        except ManualDownloadRequired:
            print(f"\n  {name}: server did not return the file directly")
            manual.append((name, dest))

    if manual:
        print("\nThese files must be downloaded by hand:")
        for name, dest in manual:
            print(f"  - {name}")
            print(f"      page:    {LANDING_PAGE}")
            print(f"      save as: {dest.relative_to(REPO_ROOT)}")
        print("Then rerun this script to verify them.")
        return 2

    list_tree(RAW_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
