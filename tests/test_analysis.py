"""The analysis docs (D68): every number in docs/findings.md and docs/case_study.md is rendered
from the committed query results in docs/analysis_results/. `make check-findings` reruns the
queries on the warehouse; this fast check only needs the files."""

from __future__ import annotations

import analysis


def test_docs_are_rendered_from_the_committed_results():
    rendered = analysis.render(analysis.load())
    assert set(rendered) == {"findings.md", "case_study.md"}
    for name, text in rendered.items():
        assert (analysis.DOCS / name).read_text() == text, f"docs/{name} is stale: run scripts/analysis.py render"


def test_every_result_has_a_query_and_a_file():
    names = [n for n, _ in analysis.statements()]
    assert sorted(names) == sorted(p.stem for p in analysis.RESULTS.glob("*.csv"))


def test_values_are_normalised_the_same_on_both_engines():
    # Databricks returns text; DuckDB returns Python values.
    assert analysis.normalise("2.1227271E7") == analysis.normalise(21227271.0) == "21227271"
    assert analysis.normalise("2024-07-08T14:15:00.000Z") == "2024-07-08 14:15"
    assert analysis.normalise("06037") == "06037"
    assert analysis.fmt("21227271", "m1") == "21.2 M"
    assert analysis.fmt("0.3519", "pct0") == "35%"
