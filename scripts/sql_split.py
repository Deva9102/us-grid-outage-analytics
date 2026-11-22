"""Split SQL text into statements (D53). The one splitter every runner and script uses.

A small tokenizer walks the text once and tells code apart from:
    '...'  string literals   ('' and backslash escapes, as in Databricks SQL)
    "..."  quoted strings / identifiers
    `...`  backtick identifiers
    -- ... line comments (to the end of the line)
    /* */  block comments
A semicolon ends a statement only when it is code. Semicolons inside literals, identifiers and
comments are kept as text, so a comment ending in ";" or a string such as 'a;b' never cuts a
statement in two. Statements are returned as written (comments included, trailing ";" removed);
a piece holding only comments and whitespace is not a statement.

Usage:
    from sql_split import split_statements, strip_comments, without_literals, table_statements
"""

from __future__ import annotations

import re
from collections.abc import Iterator

CODE, STRING, IDENT, COMMENT = "code", "string", "ident", "comment"


class SqlSplitError(ValueError):
    """The SQL text has an unterminated literal, identifier or block comment."""


def tokens(text: str) -> Iterator[tuple[str, str]]:
    """(kind, text) pieces of the SQL; joined back together they give the input unchanged."""
    i, n, start = 0, len(text), 0
    while i < n:
        ch = text[i]
        if ch in "'\"`" or text.startswith("--", i) or text.startswith("/*", i):
            if start < i:
                yield CODE, text[start:i]
            j = _end_of(text, i)
            kind = COMMENT if ch in "-/" else (IDENT if ch == "`" else STRING)
            yield kind, text[i:j]
            i = start = j
        else:
            i += 1
    if start < n:
        yield CODE, text[start:]


def _end_of(text: str, i: int) -> int:
    """Index just past the literal, identifier or comment that starts at i."""
    n = len(text)
    if text.startswith("--", i):
        j = text.find("\n", i)
        return n if j == -1 else j  # the newline itself stays code
    if text.startswith("/*", i):
        j = text.find("*/", i + 2)
        if j == -1:
            raise SqlSplitError(f"unterminated block comment at offset {i}")
        return j + 2
    quote = text[i]
    j = i + 1
    while j < n:
        c = text[j]
        if c == "\\" and quote != "`":
            j += 2
            continue
        if c == quote:
            if j + 1 < n and text[j + 1] == quote:  # doubled quote is an escaped quote
                j += 2
                continue
            return j + 1
        j += 1
    raise SqlSplitError(f"unterminated {quote} at offset {i}")


def split_statements(text: str) -> list[str]:
    """Statements of a SQL script, split on semicolons that are code."""
    statements, buf = [], []
    for kind, piece in tokens(text):
        if kind != CODE:
            buf.append(piece)
            continue
        parts = piece.split(";")
        buf.append(parts[0])
        for part in parts[1:]:
            _flush(buf, statements)
            buf = [part]
    _flush(buf, statements)
    return statements


def _flush(buf: list[str], statements: list[str]) -> None:
    stmt = "".join(buf).strip()
    if strip_comments(stmt):
        statements.append(stmt)


def strip_comments(stmt: str) -> str:
    """The statement without comments; blank lines left behind are dropped."""
    out = "".join(" " if kind == COMMENT and piece.startswith("/*") else piece
                  for kind, piece in tokens(stmt) if not (kind == COMMENT and piece.startswith("--")))
    return "\n".join(line.rstrip() for line in out.splitlines() if line.strip()).strip()


def without_literals(stmt: str) -> str:
    """The statement with string literals emptied and comments removed, for safety checks."""
    return "".join("''" if kind == STRING and piece[0] == "'" else ("" if kind == COMMENT else piece)
                   for kind, piece in tokens(stmt))


CTAS = re.compile(r"^CREATE\s+OR\s+REPLACE\s+TABLE\s+(\w+)\s+COMMENT\s+'(?:[^'\\]|''|\\.)*'\s+AS\s+(.*)$",
                  re.S | re.I)


def table_statements(text: str) -> list[tuple[str, str]]:
    """(table name, query) for each CREATE OR REPLACE TABLE t COMMENT '..' AS <query> in the text.

    The query keeps its own comments; other statements (DDL, INSERT, SELECT) are skipped.
    """
    out = []
    for stmt in split_statements(text):
        head = strip_comments(stmt)
        if not CTAS.match(head):
            continue
        # Match on the statement itself so the query keeps its comments; only the leading
        # comments before CREATE are removed.
        body = stmt[_code_start(stmt):]
        m = CTAS.match(body)
        if m is None:  # a comment between CREATE and AS: fall back to the comment-free text
            m = CTAS.match(head)
        out.append((m.group(1), m.group(2).strip()))
    return out


def _code_start(stmt: str) -> int:
    """Offset of the first code character after any leading comments and whitespace."""
    pos = 0
    for kind, piece in tokens(stmt):
        if kind == COMMENT or not piece.strip():
            pos += len(piece)
            continue
        return pos + len(piece) - len(piece.lstrip())
    return pos
