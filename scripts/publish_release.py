"""Publish the large mart exports as assets of a draft GitHub Release (D70).

Checks every Parquet file in data/gold_exports/release/ against the SHA-256 in
data/gold_exports/summary/manifest.json (written by scripts/export_marts.py), writes the release
notes to data/gold_exports/release/RELEASE_NOTES.md, then:

- with the GitHub CLI (gh) installed and logged in: creates the release as a DRAFT on
  mart_export.release_repo, or replaces the assets of an existing draft with the same tag. It
  never publishes a draft and refuses to change a release that is already published; I publish
  the draft by hand on GitHub after reviewing it.
- without gh: prints the exact steps to create the same draft in the browser.

Usage:
    uv run python scripts/publish_release.py                    # tag data-<today>
    uv run python scripts/publish_release.py --tag data-2026-11-23
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def notes(manifest: dict, tag: str) -> str:
    lines = [
        f"Large dbt mart exports for the Power BI dashboard ({tag}). The small tables are committed",
        "as CSV in `data/gold_exports/summary/`; `powerbi/data_model.md` explains how to load both.",
        "",
        "| File | Rows | Size | SHA-256 |",
        "|---|---:|---:|---|",
    ]
    for item in manifest["release"].values():
        lines.append(f"| `{Path(item['file']).name}` | {item['rows']:,} | {item['bytes'] / 1e6:.1f} MB "
                     f"| `{item['sha256']}` |")
    lines += [
        "",
        "Times are UTC. An event counts in the year it starts. Check a download with",
        "`shasum -a 256 <file>` against the table above or `data/gold_exports/summary/manifest.json`.",
        "",
        "Sources: DOE EAGLE-I (ORNL, CC BY 4.0), NOAA Storm Events Database, EIA Form 861, US Census.",
    ]
    return "\n".join(lines) + "\n"


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default=f"data-{dt.date.today().isoformat()}")
    args = parser.parse_args()
    cfg = pipeline_config.load()["mart_export"]
    repo = cfg["release_repo"]
    release_dir = REPO_ROOT / cfg["release_folder"]
    manifest = json.loads((REPO_ROOT / cfg["summary_folder"] / "manifest.json").read_text())

    files = []
    for table, item in manifest["release"].items():
        path = REPO_ROOT / item["file"]
        if not path.exists():
            raise SystemExit(f"{item['file']} is missing: run make export first")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit(f"{item['file']} does not match manifest.json: run make export again")
        files.append(path)
        print(f"  checked  {table}: {item['rows']:,} rows, {item['bytes'] / 1e6:.1f} MB")
    notes_file = release_dir / "RELEASE_NOTES.md"
    notes_file.write_text(notes(manifest, args.tag))
    title = f"Data export {args.tag}"

    if shutil.which("gh") is None:
        print(f"""
The GitHub CLI (gh) is not installed, so nothing was uploaded. To create the draft by hand:
  1. Open https://github.com/{repo}/releases/new
  2. Choose a tag: type {args.tag} and pick "Create new tag on publish" (target: main).
  3. Release title: {title}
  4. Description: paste the contents of {notes_file.relative_to(REPO_ROOT)}
  5. Attach the files (drag them into "Attach binaries"):""")
        for path in files:
            print(f"       {path.relative_to(REPO_ROOT)}")
        print("""  6. Leave "Set as a pre-release" and "Set as the latest release" unticked.
  7. Click "Save draft" (not "Publish release"). Publish it later, after reviewing it.""")
        return 0

    if gh("auth", "status").returncode != 0:
        raise SystemExit("gh is installed but not logged in: run `gh auth login`, then retry")
    view = gh("release", "view", args.tag, "--repo", repo, "--json", "isDraft")
    if view.returncode == 0:
        if not json.loads(view.stdout)["isDraft"]:
            raise SystemExit(f"release {args.tag} is already published; choose a new --tag")
        result = gh("release", "upload", args.tag, *map(str, files), "--clobber", "--repo", repo)
        action = "replaced the assets of the draft"
    else:
        result = gh("release", "create", args.tag, *map(str, files), "--draft", "--target", "main",
                    "--title", title, "--notes-file", str(notes_file), "--repo", repo)
        action = "created the draft"
    if result.returncode != 0:
        raise SystemExit(f"gh failed: {result.stderr.strip()}")
    print(f"  {action} {args.tag} on {repo}. Review and publish it on GitHub when ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
