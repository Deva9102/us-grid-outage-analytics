"""The shared SQL statement splitter (scripts/sql_split.py, D53)."""

from __future__ import annotations

from pathlib import Path

import pytest

import pipeline_config
import sql_split
from sql_split import split_statements, strip_comments, table_statements, without_literals

SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "databricks"


def test_plain_statements():
    assert split_statements("SELECT 1;\nSELECT 2;\n") == ["SELECT 1", "SELECT 2"]


def test_last_statement_without_semicolon():
    assert split_statements("SELECT 1;\nSELECT 2") == ["SELECT 1", "SELECT 2"]


def test_line_comment_ending_in_semicolon_does_not_split():
    sql = "SELECT a,\n  -- keep a and b;\n  b\nFROM t;"
    assert split_statements(sql) == ["SELECT a,\n  -- keep a and b;\n  b\nFROM t"]


def test_block_comment_with_semicolons_does_not_split():
    sql = "SELECT /* one; two;\nthree; */ 1 AS x;\nSELECT 2;"
    assert split_statements(sql) == ["SELECT /* one; two;\nthree; */ 1 AS x", "SELECT 2"]


def test_string_containing_semicolon_does_not_split():
    sql = "SELECT 'a;b' AS s, 'end;' AS t;\nSELECT 2;"
    assert split_statements(sql) == ["SELECT 'a;b' AS s, 'end;' AS t", "SELECT 2"]


def test_string_with_semicolon_at_line_end_does_not_split():
    sql = "SELECT 'first line;\nsecond line' AS s;"
    assert split_statements(sql) == ["SELECT 'first line;\nsecond line' AS s"]


def test_escaped_quotes_inside_strings():
    sql = "SELECT 'it''s; fine', 'back\\'slash; too';\nSELECT 2;"
    assert split_statements(sql) == ["SELECT 'it''s; fine', 'back\\'slash; too'", "SELECT 2"]


def test_quoted_identifiers_and_double_quoted_strings():
    sql = 'SELECT `col;1`, "x;y" FROM t;\nSELECT 2;'
    assert split_statements(sql) == ['SELECT `col;1`, "x;y" FROM t', "SELECT 2"]


def test_comment_markers_inside_strings_are_text():
    sql = "SELECT '-- not a comment;' AS a, '/* nor this; */' AS b;\nSELECT 2;"
    assert split_statements(sql) == ["SELECT '-- not a comment;' AS a, '/* nor this; */' AS b", "SELECT 2"]


def test_apostrophe_in_comment_does_not_open_a_string():
    sql = "-- the county's total;\nSELECT 1;\nSELECT 2;"
    assert split_statements(sql) == ["-- the county's total;\nSELECT 1", "SELECT 2"]


def test_comment_only_pieces_are_not_statements():
    assert split_statements("-- header;\n/* note; */\n;\nSELECT 1;\n-- trailer;\n") == ["SELECT 1"]


def test_unterminated_literal_fails_loudly():
    for bad in ("SELECT 'open;", "SELECT `open;", "SELECT /* open;"):
        with pytest.raises(sql_split.SqlSplitError):
            split_statements(bad)


def test_strip_comments_keeps_strings():
    stmt = "-- lead\nSELECT '--x' AS a, /* b */ 1 -- trailing\nFROM t"
    assert strip_comments(stmt) == "SELECT '--x' AS a,   1\nFROM t"


def test_without_literals_hides_strings_and_comments():
    stmt = "-- the county's DROP\nSELECT 'DROP TABLE x' AS s FROM t /* ALTER */"
    out = without_literals(stmt)
    assert "DROP" not in out and "ALTER" not in out and "SELECT" in out and "FROM t" in out


def test_table_statements_with_tricky_comment_and_string():
    sql = ("-- header;\nCREATE OR REPLACE TABLE a\nCOMMENT 'first; table'\nAS\n"
           "SELECT 'x;y' AS s -- note;\nFROM t;\n"
           "INSERT OVERWRITE b SELECT 1;\n"
           "CREATE OR REPLACE TABLE c COMMENT 'it''s c' AS SELECT 2;")
    assert table_statements(sql) == [("a", "SELECT 'x;y' AS s -- note;\nFROM t"), ("c", "SELECT 2")]


@pytest.mark.parametrize("path", sorted(SQL_DIR.glob("*.sql")), ids=lambda p: p.name)
def test_every_pipeline_file_splits_cleanly(path):
    """Each statement in the real files starts with a known keyword once comments are removed."""
    statements = split_statements(pipeline_config.render(path.read_text()))
    assert statements
    for stmt in statements:
        first = strip_comments(stmt).split(None, 1)[0].upper()
        assert first in {"CREATE", "INSERT", "SELECT", "WITH", "USE", "SET"}, stmt[:200]
