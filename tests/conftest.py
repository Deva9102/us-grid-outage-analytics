"""Shared pytest fixtures: the pipeline built in DuckDB from tests/fixtures/ (D51).

The real SQL files in sql/databricks/ are rendered from config/pipeline.yml and run statement by
statement by scripts/duckdb_pipeline.py. The build takes about a second and is shared by every
test in the session; tests must only read from it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import duckdb_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
RAW = REPO_ROOT / "data" / "raw"


@pytest.fixture(scope="session")
def expected_rows() -> dict[str, int]:
    return yaml.safe_load((FIXTURES / "expected_rows.yml").read_text())


@pytest.fixture(scope="session")
def con():
    """A DuckDB connection holding every Bronze, Silver and Gold table built from the fixture."""
    connection = duckdb_pipeline.connect()
    duckdb_pipeline.run_all(connection, FIXTURES)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def rows(con):
    """rows(sql) -> list of tuples."""
    return lambda sql: con.execute(sql).fetchall()


@pytest.fixture(scope="session")
def one(con):
    """one(sql) -> the first column of the first row."""
    return lambda sql: con.execute(sql).fetchone()[0]


def pytest_collection_modifyitems(config, items):
    """Skip the full-data tests when the raw downloads are not present (fresh clone, CI)."""
    if RAW.exists():
        return
    skip = pytest.mark.skip(reason="data/raw/ not downloaded (run make download)")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
