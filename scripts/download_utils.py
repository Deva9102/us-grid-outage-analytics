"""Shared helpers for the download scripts.

Every download script:
    - creates its own data/raw/<source>/<year>/ folders,
    - downloads into a .part file and renames it only when complete,
    - skips files that are already present and pass verification,
    - collects files it cannot fetch automatically and prints exact manual-download
      instructions (page, file, where to save it), then exits with code 2.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
# identity: ask for the file as stored, so Content-Length matches the bytes written. Some servers
# (weather.gov) otherwise send gzip with the compressed length.
HEADERS = {"User-Agent": "us-grid-outage-analytics/0.1 (python-requests)", "Accept-Encoding": "identity"}
CHUNK = 1024 * 1024


class FetchFailed(Exception):
    """The server did not return the file (error status, HTML page, timeout)."""


@dataclass
class ManualFile:
    name: str
    page: str
    dest: Path
    how: str
    why: str = ""


@dataclass
class Report:
    manual: list[ManualFile] = field(default_factory=list)

    def add(self, item: ManualFile) -> None:
        self.manual.append(item)

    def finish(self, source_dir: Path) -> int:
        list_tree(source_dir)
        if not self.manual:
            return 0
        print("\nThese files must be downloaded by hand:")
        for m in self.manual:
            print(f"\n  - {m.name}")
            if m.why:
                print(f"      why:     {m.why}")
            print(f"      page:    {m.page}")
            print(f"      how:     {m.how}")
            print(f"      save to: {m.dest.relative_to(REPO_ROOT)}")
        print("\nThen rerun this script; it verifies files that are already in place.")
        return 2


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fetch(url: str, dest: Path, timeout: float = 60, allow_html: bool = False) -> Path:
    """Download url to dest with progress. Raises FetchFailed on any failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=timeout) as resp:
            if resp.status_code != 200:
                raise FetchFailed(f"HTTP {resp.status_code} for {url}")
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype and not allow_html:
                raise FetchFailed(f"got an HTML page instead of a file from {url}")
            total = int(resp.headers.get("Content-Length") or 0)
            done, started = 0, time.time()
            with part.open("wb") as f:
                for block in resp.iter_content(CHUNK):
                    f.write(block)
                    done += len(block)
                    if total:
                        rate = done / max(time.time() - started, 1e-6)
                        sys.stdout.write(f"\r    {dest.name}: {done / total:6.1%} of {human(total)}  {human(rate)}/s ")
                        sys.stdout.flush()
            if total:
                print()
            if total and done != total:
                raise FetchFailed(f"incomplete download: {done} of {total} bytes")
    except requests.RequestException as e:
        part.unlink(missing_ok=True)
        raise FetchFailed(f"{type(e).__name__} for {url}") from e
    except FetchFailed:
        part.unlink(missing_ok=True)
        raise
    part.rename(dest)
    return dest


def remote_size(url: str, timeout: float = 30) -> int | None:
    try:
        resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and resp.headers.get("Content-Length"):
            return int(resp.headers["Content-Length"])
    except requests.RequestException:
        pass
    return None


def list_tree(root: Path) -> None:
    if not root.exists():
        return
    print(f"\nContents of {root.relative_to(REPO_ROOT)}/")
    total = 0
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(".part"):
            total += p.stat().st_size
            print(f"  {human(p.stat().st_size):>10}  {p.relative_to(root)}")
    print(f"  {human(total):>10}  total")
