"""Download DOE OE-417 Electric Emergency Incident and Disturbance annual summaries, 2022-2024.

Official page: https://www.oe.netl.doe.gov/OE417_annual_summary.aspx
Each year's Excel file is at download.aspx?type=OE417XLS&ID=<id> (2022 = 82, 2023 = 84).

As of November 2026 the official host publishes only an IPv6 address, so it cannot be reached from
an IPv4-only network. The script tries, in order:
    1. the official file URL,
    2. the Internet Archive's copy of that same URL (raw bytes, not the archive page),
    3. manual download instructions.
No archived copy of the 2024 file exists, so 2024 needs the official site or a manual download.

Saved as data/raw/oe417/<year>/OE417_<year>.xls, with OE417_<year>.source.txt recording where the
file came from. A file placed by hand (.xls or .xlsx) in that folder is verified and used.

Verification (DOE publishes no checksums): the file opens as a workbook and its event dates fall in
the expected year.

Usage:
    uv run python scripts/download_oe417.py [--years 2022 2023 2024]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime

import openpyxl
import requests
import xlrd

import pipeline_config
from download_utils import HEADERS, RAW, FetchFailed, ManualFile, Report, fetch

PAGE = "https://www.oe.netl.doe.gov/OE417_annual_summary.aspx"
FILE_URL = "https://www.oe.netl.doe.gov/download.aspx?type=OE417XLS&ID={id}"
SOURCE_DIR = RAW / "oe417"
KNOWN_IDS = {2022: 82, 2023: 84}
# Internet Archive captures of the official file URLs (status 200, application/vnd.ms-excel).
ARCHIVE_CAPTURES = {2022: "20241127222854", 2023: "20241219211845"}


def rows_of(path) -> list[list]:
    if path.suffix.lower() == ".xlsx":
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    out = []
    for r in range(sheet.nrows):
        row = []
        for c in range(sheet.ncols):
            cell = sheet.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                row.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
            else:
                row.append(cell.value)
        out.append(row)
    return out


def as_date(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                pass
    return None


def verify(path, year: int) -> str:
    """The 'Date Event Began' column must hold dates, at least 90% in the year, reaching December.

    Dates are stored as text (mm/dd/yyyy) and times as Excel time cells, so the column is found by
    its header. Reaching December guards against a truncated file.
    """
    rows = rows_of(path)
    header = next((i for i, r in enumerate(rows) if any(str(v).strip() == "Date Event Began" for v in r)), None)
    if header is None:
        raise ValueError("no 'Date Event Began' header found")
    col = [str(v).strip() for v in rows[header]].index("Date Event Began")
    dates = [d for r in rows[header + 1:] if (d := as_date(r[col] if col < len(r) else None))]
    if not dates:
        raise ValueError("no event dates found")
    in_year = [d for d in dates if d.year == year]
    share = len(in_year) / len(dates)
    if share < 0.9:
        raise ValueError(f"only {share:.0%} of event dates are in {year}")
    last_month = max(d.month for d in in_year)
    if last_month < 12:
        raise ValueError(f"events end in month {last_month}; the file may be truncated")
    return (f"{len(dates):,} events, {share:.0%} dated {year}, "
            f"{min(in_year):%Y-%m-%d} to {max(in_year):%Y-%m-%d}")


def official_id(year: int) -> int | None:
    if year in KNOWN_IDS:
        return KNOWN_IDS[year]
    try:
        html = requests.get(PAGE, headers=HEADERS, timeout=20).text
    except requests.RequestException:
        return None
    m = re.search(rf">\s*{year}\s*<.*?OE417XLS&(?:amp;)?ID=(\d+)", html, re.S)
    return int(m.group(1)) if m else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs="+", default=pipeline_config.load()["years"]["list"])
    args = parser.parse_args()
    report = Report()
    for year in args.years:
        folder = SOURCE_DIR / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        existing = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".xls", ".xlsx"))
        dest = folder / f"OE417_{year}.xls"
        note = folder / f"OE417_{year}.source.txt"

        if not existing:
            attempts = []
            fid = official_id(year)
            sources = []
            if fid is not None:
                sources.append(("official", FILE_URL.format(id=fid)))
            if year in ARCHIVE_CAPTURES:
                sources.append(("Internet Archive copy of the official file",
                                f"https://web.archive.org/web/{ARCHIVE_CAPTURES[year]}id_/{FILE_URL.format(id=KNOWN_IDS[year])}"))
            for label, url in sources:
                try:
                    fetch(url, dest, timeout=30)
                    note.write_text(
                        f"source: {label}\nurl: {url}\n"
                        f"downloaded: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC\n"
                    )
                    print(f"  {year}: downloaded from {label}")
                    existing = [dest]
                    break
                except FetchFailed as e:
                    attempts.append(f"{label}: {e}")
            if not existing:
                report.add(ManualFile(
                    name=f"OE-417 annual summary {year} (Excel)",
                    page=PAGE,
                    dest=dest,
                    why=("the official host is IPv6-only and unreachable from this network"
                         + ("" if year in ARCHIVE_CAPTURES else "; no archived copy exists")
                         + (f" ({'; '.join(attempts)})" if attempts else "")),
                    how=(f"from a network with IPv6 (for example a phone hotspot), open the page, "
                         f"click the XLS link in the {year} row, and save the file under this name"),
                ))
                continue
        else:
            print(f"  {year}: using {existing[0].name}")

        try:
            print(f"  {year}: {existing[0].name}: {verify(existing[0], year)}")
        except (OSError, ValueError, xlrd.XLRDError) as e:
            print(f"  {year}: {existing[0].name} failed verification ({e})")
            return 1
    return report.finish(SOURCE_DIR)


if __name__ == "__main__":
    sys.exit(main())
