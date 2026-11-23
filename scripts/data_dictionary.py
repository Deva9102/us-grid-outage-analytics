"""Write docs/data_dictionary.md from the dbt docs (D66, D68).

Reads dbt/target/manifest.json (descriptions, lineage) and dbt/target/catalog.json (column types
as the warehouse reports them), both written by `dbt docs generate`. For each mart column the
source is the upstream table (Gold, Silver or another mart) with a column of the same name; a
column no upstream table has is computed in the model.

Usage (after `cd dbt && uv run python run_dbt.py docs generate --target databricks`):
    uv run python scripts/data_dictionary.py          # or: make data-dictionary
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "dbt" / "target"
OUT = REPO_ROOT / "docs" / "data_dictionary.md"


def cell(text: str | None) -> str:
    return " ".join((text or "").split()).replace("|", "\\|")


def main() -> None:
    manifest = json.loads((TARGET / "manifest.json").read_text())
    catalog = json.loads((TARGET / "catalog.json").read_text())
    nodes = {**catalog["nodes"], **catalog["sources"]}
    adapter = manifest["metadata"].get("adapter_type", "")

    def columns_of(unique_id: str) -> dict[str, str]:
        return {c.lower(): v["type"] for c, v in nodes.get(unique_id, {}).get("columns", {}).items()}

    def label(unique_id: str) -> str:
        node = manifest["nodes"].get(unique_id) or manifest["sources"][unique_id]
        return node["name"]

    models = sorted((n for n in manifest["nodes"].values() if n["resource_type"] == "model"),
                    key=lambda n: (not n["name"].startswith("fct_"), n["name"]))
    lines = [
        "<!-- Written by scripts/data_dictionary.py from the dbt docs; edit dbt/models/*.yml, not this file. -->",
        "# Data dictionary: dbt marts",
        "",
        f"Every table and column of the star schema in `dbt/` (D66), with the type the warehouse reports"
        f" ({adapter}), its meaning and where it comes from. The marts are tables in"
        " `workspace.outages`; they reshape the Gold tables and never recompute a metric. Rule numbers"
        " (D-numbers) refer to `docs/decisions.md`. An event counts in the year it starts.",
        "",
        "| Table | Grain | Rows from |",
        "|---|---|---|",
    ]
    for m in models:
        ups = ", ".join(f"`{label(u)}`" for u in m["depends_on"]["nodes"]) or "a date spine, no upstream table"
        grain = cell(m["description"]).split(". ")[0].rstrip(".")
        lines.append(f"| [`{m['name']}`](#{m['name']}) | {grain}. | {ups} |")
    for m in models:
        types = columns_of(m["unique_id"])
        # The table the model reads first is its main source; it wins when several have the column.
        code = m.get("raw_code", "")
        ups = sorted(m["depends_on"]["nodes"], key=lambda u: code.find(f"'{label(u)}'") % (len(code) + 1))
        upstream = [(label(u), columns_of(u)) for u in ups]
        lines += ["", f"## {m['name']}", "", cell(m["description"]), "",
                  "| Column | Type | Meaning | Source |", "|---|---|---|---|"]
        for name, col in m["columns"].items():
            src = next((f"`{t}.{name}`" for t, cols in upstream if name.lower() in cols), f"computed in `{m['name']}.sql`")
            lines.append(f"| `{name}` | {types.get(name.lower(), '')} | {cell(col['description'])} | {src} |")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"docs/data_dictionary.md: {len(models)} tables")


if __name__ == "__main__":
    main()
