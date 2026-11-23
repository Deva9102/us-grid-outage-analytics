"""The Power BI export (D70): every mart is exported once, and the CSV format Power BI reads."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pyarrow as pa
import yaml

import export_marts
import pipeline_config

REPO = Path(__file__).resolve().parent.parent


def test_every_mart_is_exported_once_on_a_documented_key():
    cfg = pipeline_config.load()["mart_export"]
    summary, release = cfg["summary_tables"], cfg["release_tables"]
    assert not set(summary) & set(release)
    models = {p.stem for p in (REPO / "dbt" / "models" / "marts").glob("*.sql")}
    assert set(summary) | set(release) == models
    docs = {m["name"]: m for m in yaml.safe_load((REPO / "dbt" / "models" / "marts" / "marts.yml").read_text())["models"]}
    for table, key in {**summary, **release}.items():
        key_col = next(c for c in docs[table]["columns"] if c["name"] == key)
        assert "unique" in str(key_col.get("data_tests", [])), f"{table}.{key} is not a unique key"


def test_committed_summary_matches_the_manifest():
    cfg = pipeline_config.load()["mart_export"]
    manifest = json.loads((REPO / cfg["summary_folder"] / "manifest.json").read_text())
    assert set(manifest["summary"]) == set(cfg["summary_tables"])
    assert set(manifest["release"]) == set(cfg["release_tables"])
    for item in manifest["summary"].values():
        path = REPO / item["file"]
        lines = path.read_text().count("\n")
        assert lines == item["rows"] + 1, item["file"]


def test_csv_format(tmp_path):
    ts = pa.array([dt.datetime(2024, 7, 8, 14, 15, tzinfo=dt.UTC), None], pa.timestamp("us", tz="UTC"))
    table = pa.table({
        "fips_code": ["06037", "72113"],
        "flag": [True, None],
        "at": ts,
        "x": [1.5, None],
    })
    path = tmp_path / "t.csv"
    export_marts.write_csv(export_marts.utc_naive(table), path)
    assert path.read_text().splitlines() == [
        '"fips_code","flag","at","x"',
        '"06037","true","2024-07-08 14:15:00",1.5',
        '"72113",,,',
    ]
