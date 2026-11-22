"""Convert Excel source files to raw-row Parquet for Bronze (D27).

Databricks cannot read .xlsx or legacy .xls directly, so EIA-861 workbooks and OE-417 annual
summaries are converted locally. Nothing is interpreted: every row of every sheet is kept, in
order, with each cell written as text in fixed positional columns col_01 .. col_NN. Headers,
footers and blank rows stay in, exactly as in the workbook; Silver decides which rows are data.

Cell text rules (the only transformation, needed because Excel stores typed cells):
    empty cell                  -> NULL
    text                        -> unchanged
    whole number (12014.0)      -> '12014'
    other number                -> shortest round-trip text (repr), e.g. '132.89474'
    date only                   -> 'YYYY-MM-DD'
    time only (Excel date < 1901, as OE-417 times are stored) -> 'HH:MM:SS'
    date and time               -> 'YYYY-MM-DD HH:MM:SS'
    boolean                     -> 'TRUE' / 'FALSE'

Output columns: source_name, sheet_name, row_number (1-based), col_01 .. col_NN (all strings).

Files (data/raw/ is gitignored):
    data/raw/eia861/<year>/{Reliability,Sales_Ult_Cust,Service_Territory}_<year>.xlsx
        -> data/raw/eia861_parquet/<year>/{reliability,sales,service_territory}_<year>.parquet
    data/raw/oe417/<year>/OE417_<year>.xls (or .xlsx placed by hand)
        -> data/raw/oe417_parquet/<year>/oe417_<year>.parquet

Usage:
    uv run python scripts/raw_convert.py
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import openpyxl
import pyarrow as pa
import pyarrow.parquet as pq
import xlrd

import pipeline_config

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
YEARS = tuple(pipeline_config.load()["years"]["list"])

# Fixed width per file type, so every year has the same Parquet schema.
EIA_FILES = {"reliability": ("Reliability", 30), "sales": ("Sales_Ult_Cust", 30),
             "service_territory": ("Service_Territory", 10)}
OE417_WIDTH = 15


def cell_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, dt.datetime):
        if value.year < 1901:
            return value.strftime("%H:%M:%S")
        if value.time() == dt.time(0, 0):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dt.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, int):
        return str(value)
    return str(value)


def workbook_rows(path: Path):
    """Yield (sheet_name, row_number, [cell text]) for every row of every sheet."""
    if path.suffix.lower() == ".xls":
        with open(os.devnull, "w") as devnull:
            book = xlrd.open_workbook(path, logfile=devnull)
        for sheet in book.sheets():
            for r in range(sheet.nrows):
                cells = []
                for c in range(sheet.ncols):
                    cell = sheet.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_EMPTY:
                        cells.append(None)
                    elif cell.ctype == xlrd.XL_CELL_DATE:
                        cells.append(cell_text(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode)))
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        cells.append(cell_text(bool(cell.value)))
                    else:
                        cells.append(cell_text(cell.value))
                yield sheet.name, r + 1, cells
    else:
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for sheet in book.worksheets:
            for r, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                yield sheet.title, r, [cell_text(v) for v in row]
        book.close()


def convert(path: Path, out: Path, width: int) -> int:
    cols = {"source_name": [], "sheet_name": [], "row_number": []}
    cols.update({f"col_{i:02d}": [] for i in range(1, width + 1)})
    n = 0
    for sheet, rownum, cells in workbook_rows(path):
        if len(cells) > width and any(c not in (None, "") for c in cells[width:]):
            raise ValueError(f"{path.name} [{sheet}] row {rownum} has data beyond {width} columns")
        cells = (cells + [None] * width)[:width]
        cols["source_name"].append(path.name)
        cols["sheet_name"].append(sheet)
        cols["row_number"].append(str(rownum))
        for i, v in enumerate(cells, start=1):
            cols[f"col_{i:02d}"].append(v)
        n += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({k: pa.array(v, type=pa.string()) for k, v in cols.items()})
    tmp = out.with_suffix(".parquet.part")
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(out)
    return n


def targets() -> list[tuple[Path, Path, int]]:
    items = []
    for y in YEARS:
        for short, (prefix, width) in EIA_FILES.items():
            src = RAW / "eia861" / str(y) / f"{prefix}_{y}.xlsx"
            items.append((src, RAW / "eia861_parquet" / str(y) / f"{short}_{y}.parquet", width))
        folder = RAW / "oe417" / str(y)
        found = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".xls", ".xlsx")) if folder.exists() else []
        if found:
            items.append((found[0], RAW / "oe417_parquet" / str(y) / f"oe417_{y}.parquet", OE417_WIDTH))
    return items


def ensure_converted(verbose: bool = True) -> list[Path]:
    """Convert every source that is missing or older than its workbook. Returns the outputs."""
    outs = []
    for src, out, width in targets():
        if not src.exists():
            raise FileNotFoundError(f"missing source {src.relative_to(REPO_ROOT)}; run the download script")
        if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
            n = convert(src, out, width)
            if verbose:
                print(f"  {src.relative_to(REPO_ROOT)} -> {out.relative_to(REPO_ROOT)} ({n:,} rows)")
        outs.append(out)
    return outs


if __name__ == "__main__":
    ensure_converted()
