"""Columns added to tables that already exist (D64).

Incremental tables (D56) are created once with CREATE TABLE IF NOT EXISTS, so a column added to
their definition in sql/databricks/ reaches a new deployment but not a table built by an earlier
run. Each added column is listed here with the value its existing rows get. Before the SQL runs,
scripts/run_databricks.py (step migrate) and scripts/duckdb_pipeline.py add the columns a table
is missing and fill them; a table that does not exist yet is left to its CREATE statement.

New columns go at the end of the table definition, in the order listed here, because ALTER TABLE
appends them and the incremental writes combine kept and rebuilt rows by position.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AddedColumn:
    table: str
    column: str
    type: str
    comment: str
    existing_rows: str  # SQL value for the rows already in the table


ADDED_COLUMNS = [
    # Events built before D64 are from 2022-2024, which have no empty readings, or lie in the
    # reprocess window and are rebuilt by the same run; so 0 and FALSE are their true values.
    AddedColumn("gold_outage_events", "bridged_empty_hours", "DECIMAL(23, 2)",
                "Hours of empty readings bridged inside the event (D64)", "0"),
    AddedColumn("gold_outage_events", "spans_empty_gap", "BOOLEAN",
                "Starts or ends at an empty run too long to bridge (D64)", "FALSE"),
]


def missing(existing: dict[str, set[str]]) -> list[AddedColumn]:
    """Columns to add, given {table: its current columns} for the tables that exist."""
    return [c for c in ADDED_COLUMNS if c.table in existing and c.column.lower() not in existing[c.table]]


def statements(columns: list[AddedColumn], engine: str) -> list[str]:
    """ALTER TABLE ... ADD and the UPDATE that fills the existing rows, for databricks or duckdb."""
    out = []
    for c in columns:
        if engine == "databricks":
            out.append(f"ALTER TABLE {c.table} ADD COLUMNS ({c.column} {c.type} COMMENT '{c.comment}')")
        else:
            out.append(f"ALTER TABLE {c.table} ADD COLUMN {c.column} {c.type}")
        out.append(f"UPDATE {c.table} SET {c.column} = {c.existing_rows} WHERE {c.column} IS NULL")
    return out


def run_duckdb(con) -> list[str]:
    """Add the missing columns in a DuckDB database; returns the statements run."""
    existing: dict[str, set[str]] = {}
    for table, column in con.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'main'").fetchall():
        existing.setdefault(table, set()).add(column.lower())
    stmts = statements(missing(existing), "duckdb")
    for stmt in stmts:
        con.execute(stmt)
    return stmts
