"""Install the Databricks CLI into the project folder, not globally (D54).

Downloads the pinned release from github.com/databricks/cli into .tools/databricks/<version>/,
checks it against the release's SHA256SUMS file and links .tools/bin/databricks to it. Nothing is
written outside the repository; .tools/ is gitignored. The Makefile calls the CLI by that path.

Usage:
    uv run python scripts/install_databricks_cli.py
"""

from __future__ import annotations

import hashlib
import platform
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSION = "1.24.0"  # pinned; released 2026-11-04
REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / ".tools"
BASE = f"https://github.com/databricks/cli/releases/download/v{VERSION}"


def asset_name() -> str:
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "AMD64": "amd64"}.get(platform.machine())
    if not system or not arch:
        raise SystemExit(f"No Databricks CLI build for {platform.system()} {platform.machine()}")
    return f"databricks_cli_{VERSION}_{system}_{arch}.tar.gz"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def main() -> int:
    target_dir = TOOLS / "databricks" / VERSION
    binary = target_dir / "databricks"
    link = TOOLS / "bin" / "databricks"
    if not binary.exists():
        name = asset_name()
        sums = fetch(f"{BASE}/databricks_cli_{VERSION}_SHA256SUMS").decode()
        expected = next((line.split()[0] for line in sums.splitlines() if line.endswith(name)), None)
        if expected is None:
            raise SystemExit(f"{name} is not listed in the release checksums")
        data = fetch(f"{BASE}/{name}")
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit(f"{name}: checksum mismatch, not installed")
        target_dir.mkdir(parents=True, exist_ok=True)
        archive = target_dir / name
        archive.write_bytes(data)
        with tarfile.open(archive) as tar:
            member = tar.getmember("databricks")
            tar.extract(member, target_dir, filter="data")
        archive.unlink()
        binary.chmod(0o755)
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(binary.relative_to(link.parent, walk_up=True))
    print(f"Databricks CLI {VERSION} at {link.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
