"""The dbt project in dbt/ (D66): its copies of config values, its docs and its profile example.

dbt itself runs in its own environment (dbt/pyproject.toml); CI runs dbt parse and dbt build on
the fixture. These checks need only the files.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

import pipeline_config

DBT = Path(__file__).resolve().parent.parent / "dbt"


def test_vars_match_the_pipeline_config():
    cfg = pipeline_config.load()
    v = yaml.safe_load((DBT / "dbt_project.yml").read_text())["vars"]
    assert v["denominator_base_years"] == cfg["denominator"]["base_years"]
    assert v["ranked_jurisdictions"] == cfg["ranking"]["ranked_jurisdictions"]
    years = cfg["years"]["list"]
    assert v["date_spine_start"] == f"{years[0]}-01-01"
    assert v["date_spine_end"] == f"{years[-1] + 1}-01-01"


def test_every_model_and_column_is_described():
    docs = {}
    for path in (DBT / "models").rglob("*.yml"):
        for m in yaml.safe_load(path.read_text()).get("models", []):
            docs[m["name"]] = m
    models = {p.stem for p in (DBT / "models").rglob("*.sql")}
    assert models == set(docs)
    for name, m in docs.items():
        assert m.get("description"), name
        assert m.get("columns"), name
        for col in m["columns"]:
            assert col.get("description"), f"{name}.{col['name']}"


def test_profile_example_reads_every_credential_from_the_environment():
    text = (DBT / "profiles.yml.example").read_text()
    for key in ("host", "http_path", "token", "account", "user", "password"):
        values = re.findall(rf"^\s+{key}: (.+)$", text, re.M)
        assert values and all("env_var(" in v for v in values), key
