"""Run dbt for this project with credentials from ../.env (D66).

Usage (from dbt/):  uv run python run_dbt.py <dbt command and options>
    uv run python run_dbt.py build --target duckdb
    uv run python run_dbt.py build --target databricks

Loads ../.env without printing it, normalises the Databricks host (no scheme, no trailing slash),
points DBT_PROFILES_DIR at this folder and creates profiles.yml from profiles.yml.example on
first use. profiles.yml holds no secrets, but it stays local (gitignored).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent


def main() -> int:
    load_dotenv(HERE.parent / ".env")
    host = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
    if host:
        os.environ["DATABRICKS_SERVER_HOSTNAME"] = host.strip().removeprefix("https://").rstrip("/")
    profiles = HERE / "profiles.yml"
    if not profiles.exists():
        shutil.copy(HERE / "profiles.yml.example", profiles)
    os.environ["DBT_PROFILES_DIR"] = str(HERE)
    os.chdir(HERE)
    from dbt.cli.main import dbtRunner

    result = dbtRunner().invoke(sys.argv[1:])
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
