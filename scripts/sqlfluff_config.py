"""Write .sqlfluff with the configuration placeholders filled from config/pipeline.yml (D51).

The SQL in sql/databricks/ references values as ${section.key} (D47). sqlfluff's placeholder
templater substitutes them before parsing, so every placeholder needs a value in .sqlfluff. The
values are the same SQL literals that scripts/pipeline_config.py renders, so the linted SQL is
the SQL that runs. tests/test_config.py fails when .sqlfluff is out of date.

Usage:
    uv run python scripts/sqlfluff_config.py           # rewrite .sqlfluff
    uv run python scripts/sqlfluff_config.py --check   # exit 1 if .sqlfluff is out of date
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql" / "databricks"
TARGET = REPO_ROOT / ".sqlfluff"

HEADER = """\
# sqlfluff configuration for sql/databricks/ (D51).
# Lint locally with "make lint" (the CLI flags --ignore-local-config --config .sqlfluff keep
# sqlfluff from reading config outside the repo).
#
# The [sqlfluff:templater:placeholder] section is written by scripts/sqlfluff_config.py from
# config/pipeline.yml. Do not edit it by hand: change the config and rerun the script.

[sqlfluff]
dialect = databricks
templater = placeholder
max_line_length = 160
# The largest files (02_silver_sources.sql, 90_quality_checks.sql) are above the 20 KB default.
large_file_skip_byte_limit = 0
# Rules left out on purpose (D51): they fight the house layout, which aligns columns and AS
# aliases, keeps short count queries and UNION ALL branches on one line, puts each CTE's comment
# directly above it, and indents AND under WHERE. Everything else is enforced.
#   LT01 spacing (alignment)      LT02 indentation       LT08 blank line after a CTE
#   LT09 one select target a line LT11 set operators on their own line
#   LT14 keyword on a new line    AL03 aliases on UNION ALL branches after the first
#   AM04 Bronze tables are SELECT * from raw files by design (D14)
#   CP02 NOAA and MCC source columns keep their upper-case source names
#   RF04 year, state and similar names are part of the published schema
#   ST06 column order follows the published schema
#   ST09 join conditions are written in the order that reads best per join
exclude_rules = LT01, LT02, LT08, LT09, LT11, LT14, AL03, AM04, CP02, RF04, ST06, ST09

[sqlfluff:indentation]
tab_space_size = 4
indented_joins = False
indented_using_on = True
implicit_indents = allow

[sqlfluff:rules:capitalisation.keywords]
capitalisation_policy = upper

[sqlfluff:rules:capitalisation.functions]
extended_capitalisation_policy = upper

[sqlfluff:rules:capitalisation.literals]
capitalisation_policy = upper

[sqlfluff:rules:capitalisation.types]
extended_capitalisation_policy = upper

[sqlfluff:rules:ambiguous.column_references]
group_by_and_order_by_style = consistent

[sqlfluff:rules:references.consistent]
single_table_references = consistent

[sqlfluff:templater:placeholder]
# sqlfluff nests dotted keys, so each value is keyed by the last part of its placeholder name
# (${events.threshold_share} -> threshold_share); the script checks those parts are unique.
param_regex = \\$\\{(?:[A-Za-z_]\\w*\\.)*(?P<param_name>[A-Za-z_]\\w*)\\}
"""


def placeholders() -> list[str]:
    names: set[str] = set()
    for path in sorted(SQL_DIR.glob("*.sql")):
        names |= set(pipeline_config.PLACEHOLDER.findall(path.read_text()))
    return sorted(names)


def render() -> str:
    lines = [HEADER.rstrip("\n")]
    keys: dict[str, str] = {}
    for name in placeholders():
        key = name.rsplit(".", 1)[-1]
        if key in keys:
            raise SystemExit(f"placeholders {keys[key]} and {name} share the key {key}; rename one")
        keys[key] = name
        lines.append(f"{key} = {pipeline_config.literal(pipeline_config.get(name))}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit 1 when .sqlfluff is out of date")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = TARGET.read_text() if TARGET.exists() else ""
        if current != text:
            print(".sqlfluff is out of date: run uv run python scripts/sqlfluff_config.py", file=sys.stderr)
            return 1
        print(".sqlfluff is up to date")
        return 0
    TARGET.write_text(text)
    print(f"wrote {TARGET.relative_to(REPO_ROOT)} with {len(placeholders())} placeholder values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
