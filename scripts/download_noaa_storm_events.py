"""Download NOAA Storm Events Database "details" files for 2022-2024.

Source: NCEI bulk CSV directory
    https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
Files are named StormEvents_details-ftp_v1.0_d<year>_c<yyyymmdd>.csv.gz, where c<date> is the
date NCEI last rebuilt the file. The newest c<date> per year is used.

Saved as data/raw/noaa_storm_events/<year>/<file name> (still gzipped; DuckDB reads it directly).

Verification (NCEI publishes no checksums): size matches the server, the gzip stream is complete,
the header has the expected columns, and every row's YEAR equals the file year.

Usage:
    uv run python scripts/download_noaa_storm_events.py [--years 2022 2023 2024]
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys

import duckdb
import requests

import pipeline_config
from download_utils import HEADERS, RAW, FetchFailed, ManualFile, Report, fetch, remote_size

BASE = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
SOURCE_DIR = RAW / "noaa_storm_events"
REQUIRED_COLUMNS = {
    "EVENT_ID", "EPISODE_ID", "STATE", "STATE_FIPS", "YEAR", "EVENT_TYPE", "CZ_TYPE", "CZ_FIPS",
    "CZ_NAME", "BEGIN_DATE_TIME", "END_DATE_TIME", "CZ_TIMEZONE", "DAMAGE_PROPERTY",
}


def latest_files(years: list[int]) -> dict[int, str]:
    resp = requests.get(BASE, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    names = set(re.findall(r"StormEvents_details-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz", resp.text))
    out = {}
    for year in years:
        dates = sorted(c for y, c in names if int(y) == year)
        if dates:
            out[year] = f"StormEvents_details-ftp_v1.0_d{year}_c{dates[-1]}.csv.gz"
    return out


def verify(path, year: int) -> str:
    with gzip.open(path, "rb") as f:
        while f.read(8 * 1024 * 1024):
            pass
    con = duckdb.connect()
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_csv('{path.as_posix()}', all_varchar = true)").fetchall()}
    missing = REQUIRED_COLUMNS - cols
    if missing:
        raise ValueError(f"missing columns {sorted(missing)}")
    rows, other_years = con.execute(f"""
        SELECT COUNT(*), COUNT(*) FILTER (WHERE YEAR <> '{year}')
        FROM read_csv('{path.as_posix()}', all_varchar = true)
    """).fetchone()
    if other_years:
        raise ValueError(f"{other_years} rows with YEAR other than {year}")
    return f"{rows:,} rows, gzip complete, columns ok"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs="+", default=pipeline_config.load()["years"]["list"])
    args = parser.parse_args()
    report = Report()

    try:
        files = latest_files(args.years)
    except requests.RequestException as e:
        print(f"Could not read the NCEI directory listing ({type(e).__name__}).")
        files = {}

    for year in args.years:
        folder = SOURCE_DIR / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        name = files.get(year)
        if name is None:
            report.add(ManualFile(
                name=f"StormEvents_details-ftp_v1.0_d{year}_c<latest date>.csv.gz",
                page=BASE,
                how="open the page, pick the details file for that year with the newest c<date>, download it",
                dest=folder / f"StormEvents_details-ftp_v1.0_d{year}_c<date>.csv.gz",
                why="the directory listing could not be read or has no file for this year",
            ))
            continue
        dest = folder / name
        older = [p for p in folder.glob("StormEvents_details-*.csv.gz") if p.name != name]
        size = remote_size(BASE + name)
        if dest.exists() and (size is None or dest.stat().st_size == size):
            print(f"  {name}: already downloaded")
        else:
            try:
                fetch(BASE + name, dest)
            except FetchFailed as e:
                report.add(ManualFile(name=name, page=BASE, dest=dest, why=str(e),
                                      how="open the page, click the file name to download it"))
                continue
        try:
            print(f"  {name}: {verify(dest, year)}")
        except (OSError, EOFError, ValueError, duckdb.Error) as e:
            dest.unlink(missing_ok=True)
            print(f"  {name}: verification failed ({e}); file removed, rerun to retry")
            return 1
        for p in older:
            print(f"  note: older version also present, not used: {p.name}")

    return report.finish(SOURCE_DIR)


if __name__ == "__main__":
    sys.exit(main())
