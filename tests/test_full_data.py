"""Full-data checks: the original DuckDB scripts on data/raw/ (minutes, several GB of memory).

Marked slow and skipped by default; run with  uv run pytest -m slow  after make download.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SCRIPTS = [
    ["scripts/test_silver_duckdb.py"],
    ["scripts/test_gold_events_duckdb.py"],
    ["scripts/test_sources_duckdb.py"],
    ["scripts/test_gold_analysis_duckdb.py"],
    ["scripts/quality_checks.py", "--engine", "duckdb"],
]


@pytest.mark.slow
@pytest.mark.parametrize("args", SCRIPTS, ids=lambda a: Path(a[0]).stem)
def test_full_data_script(args):
    result = subprocess.run([sys.executable, *args], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
