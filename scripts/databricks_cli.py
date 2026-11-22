"""Run the project-local Databricks CLI with credentials from .env (D54).

Reads DATABRICKS_SERVER_HOSTNAME, DATABRICKS_TOKEN and DATABRICKS_HTTP_PATH from .env and passes
them to .tools/bin/databricks as environment variables only: nothing is written to
~/.databrickscfg and the token is never printed. The warehouse id from DATABRICKS_HTTP_PATH becomes
the bundle variable warehouse_id. DATABRICKS_CONFIG_FILE points at a project path, so a profile
in the home folder is never read.

Usage:
    uv run python scripts/databricks_cli.py bundle validate
    uv run python scripts/databricks_cli.py bundle deploy
    uv run python scripts/databricks_cli.py bundle run outage_pipeline
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / ".tools" / "bin" / "databricks"


def cli_env() -> dict[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    missing = [k for k in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing in .env: {', '.join(missing)}")
    host = os.environ["DATABRICKS_SERVER_HOSTNAME"].strip().removeprefix("https://").rstrip("/")
    env = {k: v for k, v in os.environ.items() if not k.startswith("DATABRICKS_")}
    env.update({
        "DATABRICKS_HOST": f"https://{host}",
        "DATABRICKS_TOKEN": os.environ["DATABRICKS_TOKEN"].strip(),
        "DATABRICKS_CONFIG_FILE": str(REPO_ROOT / ".tools" / "databrickscfg"),
        "BUNDLE_VAR_warehouse_id": os.environ["DATABRICKS_HTTP_PATH"].strip().rstrip("/").split("/")[-1],
    })
    return env


def main(argv: list[str]) -> int:
    if not CLI.exists():
        raise SystemExit("Databricks CLI not installed: run make cli")
    return subprocess.run([str(CLI), *argv], env=cli_env(), cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
