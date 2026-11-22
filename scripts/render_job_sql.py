"""Render the SQL of the Databricks Job (databricks.yml) from config/pipeline.yml (D54).

The job runs SQL file tasks on the SQL warehouse, and a SQL file task cannot substitute the
${section.key} placeholders of sql/databricks/. This script renders them exactly as
scripts/run_databricks.py does (pipeline_config.render, then the shared splitter of D53) and
writes one file per job task to build/databricks/ (gitignored):

    <task>.sql        the pipeline files of the task, in the run order of run_databricks.SQL_FILES
    <task>_gate.sql   the quality gate after the task: every check of 90_quality_checks.sql whose
                      tables exist by then, written to gold_quality_results; raise_error() fails
                      the task, so later tasks do not run, when any check fails

Each gate first checks the exact row count (quality.expected_rows, D50) of every table its own
task builds, so a task that went wrong stops the job at once. Then come the checks of
90_quality_checks.sql: Bronze and Silver checks in the gate of their layer, a Gold check in the
gate of the last task that builds a table it reads. Every check of the file runs exactly once.

Every statement passes the same safety check as the local runner (no DROP, ALTER, TRUNCATE,
DELETE, GRANT, REVOKE; nothing outside workspace.outages) before it is written.

Usage:
    uv run python scripts/render_job_sql.py            # writes build/databricks/
    uv run python scripts/render_job_sql.py --check    # renders and validates only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pipeline_config
import quality_checks
from run_databricks import SQL_DIR, SQL_FILES, check_safe
from sql_split import split_statements, strip_comments

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "build" / "databricks"

# Job tasks in run order with the pipeline files each one runs (must equal SQL_FILES in order).
JOB_TASKS: list[tuple[str, str, list[str]]] = [
    ("bronze", "bronze", ["01_bronze.sql", "01_bronze_sources.sql"]),
    ("silver", "silver", ["02_silver_sources.sql", "02_silver.sql"]),
    ("gold_events", "gold", ["03_gold_events.sql", "03_gold_coverage.sql"]),
    ("gold_storm_match", "gold", ["03_gold_storm_match.sql"]),
    ("gold_reliability", "gold", ["03_gold_reliability.sql", "03_gold_oe417_check.sql"]),
]
GATE_TABLE = "quality_gate_staging"
CREATED = re.compile(r"^\s*(?:CREATE\s+OR\s+REPLACE\s+TABLE|INSERT\s+OVERWRITE)\s+(\w+)", re.I)
TABLE_REF = re.compile(r"\b((?:bronze|silver|dim|gold)_\w+)\b")


class RenderError(Exception):
    """The job tasks do not match the pipeline files, or a check has no task."""


def header(task: str, what: str) -> str:
    return (f"-- {task}: {what}\n"
            "-- Rendered by scripts/render_job_sql.py from sql/databricks/ and config/pipeline.yml (D54).\n"
            "-- Do not edit: change the source SQL or the config and render again.\n")


def session(cfg: dict) -> list[str]:
    catalog, schema = cfg["project"]["catalog"], cfg["project"]["schema"]
    return [f"USE CATALOG {catalog}", f"USE SCHEMA {schema}", "SET TIME ZONE 'UTC'"]


def task_statements(files: list[str], overrides: dict | None) -> list[str]:
    out = []
    for name in files:
        out += split_statements(pipeline_config.render((SQL_DIR / name).read_text(), overrides))
    return out


def gate_statements(task: str, layer: str, checks: list[str], cfg: dict) -> list[str]:
    results = cfg["quality"]["results_table"]
    first = "MIN(CASE WHEN NOT passed THEN check_name END)"
    return session(cfg) + [
        quality_checks.results_table_sql(),
        f"""CREATE OR REPLACE TABLE {GATE_TABLE} (
    layer       STRING,
    check_name  STRING,
    observed    DOUBLE,
    expected    STRING,
    passed      BOOLEAN
)
COMMENT 'Checks of the quality gate task running now (D54); overwritten by every gate task'""",
        *[f"INSERT INTO {GATE_TABLE}\n{check}" for check in checks],
        f"""-- Keep every result with the gate's timestamp, as scripts/quality_checks.py does.
INSERT INTO {results}
SELECT CURRENT_TIMESTAMP, 'databricks', layer, check_name, observed, expected, passed
FROM {GATE_TABLE}""",
        f"""-- Fail the task (and skip every later task) when any check failed.
SELECT
    CASE WHEN COUNT_IF(NOT passed) > 0
        THEN raise_error(CONCAT('Quality gate {task} failed: ', CAST(COUNT_IF(NOT passed) AS STRING),
                                ' check(s), first: ', {first}, '. See {results}.'))
        ELSE CONCAT(CAST(COUNT(*) AS STRING), ' checks passed')
    END AS gate_result
FROM {GATE_TABLE}""",
    ]


def row_count_check(layer: str, tables: list[str], overrides: dict | None) -> str:
    """Exact row counts of the tables one task builds."""
    rows = [f"SELECT '{t}' AS table_name, COUNT(*) AS observed, "
            f"{int(pipeline_config.get(f'quality.expected_rows.{t}', overrides))} AS expected FROM {t}"
            for t in tables]
    union = "\n    UNION ALL ".join(rows)
    return f"""WITH
-- One count per table built by the task, with its expected value from the config (D50).
counts AS (
    {union}
)
SELECT
    '{layer}'                                  AS layer,
    CONCAT('task row count: ', table_name)     AS check_name,
    CAST(observed AS DOUBLE)                   AS observed,
    CAST(expected AS STRING)                   AS expected,
    observed = expected                        AS passed
FROM counts"""


def render(overrides: dict | None = None) -> dict[str, str]:
    """{file name: SQL text} for every job task and gate."""
    cfg = pipeline_config.load()
    order = [f for _, _, files in JOB_TASKS for f in files]
    if order != SQL_FILES:
        raise RenderError(f"job tasks run {order}, the pipeline runs {SQL_FILES}")

    builds: dict[str, list[str]] = {}
    owner: dict[str, int] = {}
    for k, (task, _, files) in enumerate(JOB_TASKS):
        builds[task] = task_statements(files, overrides)
        for stmt in builds[task]:
            m = CREATED.match(strip_comments(stmt))
            if m:
                owner.setdefault(m.group(1), k)

    gates: dict[str, list[str]] = {
        task: [row_count_check(layer, sorted(t for t, k2 in owner.items() if k2 == k), overrides)]
        for k, (task, layer, _) in enumerate(JOB_TASKS)}
    layer_tasks = {layer: [k for k, (_, lay, _) in enumerate(JOB_TASKS) if lay == layer]
                   for layer in quality_checks.LAYERS}
    for layer, checks in quality_checks.statements_by_layer(overrides).items():
        for check in checks:
            tables = {t for t in TABLE_REF.findall(strip_comments(check)) if t in owner}
            if not tables:
                raise RenderError(f"{layer} check reads no pipeline table:\n{check[:300]}")
            k = max(owner[t] for t in tables)
            if k not in layer_tasks[layer]:
                k = max(layer_tasks[layer])
            gates[JOB_TASKS[k][0]].append(check)

    out: dict[str, str] = {}
    for task, layer, files in JOB_TASKS:
        parts = {f"{task}.sql": (header(task, ", ".join(files)), builds[task]),
                 f"{task}_gate.sql": (header(f"{task}_gate", f"{len(gates[task])} {layer} check statements"),
                                      gate_statements(task, layer, gates[task], cfg))}
        for name, (head, statements) in parts.items():
            for stmt in statements:
                check_safe(stmt)
            out[name] = head + "\n" + ";\n\n".join(statements) + ";\n"
    return out


def gate_check_counts(rendered: dict[str, str]) -> dict[str, int]:
    """Check statements per gate file (for the summary and the tests)."""
    return {name: len([s for s in split_statements(sql) if strip_comments(s).startswith(f"INSERT INTO {GATE_TABLE}")])
            for name, sql in rendered.items() if name.endswith("_gate.sql")}


def write(rendered: dict[str, str], out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.sql"):
        if old.name not in rendered:
            old.unlink()
    for name, sql in rendered.items():
        (out_dir / name).write_text(sql)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="render and validate without writing")
    args = parser.parse_args()
    try:
        rendered = render()
    except (RenderError, pipeline_config.ConfigError) as e:
        print(f"Render failed: {e}", file=sys.stderr)
        return 1
    counts = gate_check_counts(rendered)
    for task, _, _ in JOB_TASKS:
        n = len(split_statements(rendered[f"{task}.sql"]))
        print(f"  {task:<18} {n:>3} statements   gate: {counts[f'{task}_gate.sql']:>2} check statements")
    if not args.check:
        write(rendered)
        print(f"Wrote {len(rendered)} files to {OUT_DIR.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
