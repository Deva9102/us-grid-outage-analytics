"""Download EIA Form 861 annual files for 2022-2024.

Source: https://www.eia.gov/electricity/data/eia861/ (one zip per year). The newest year is under
zip/, older years under archive/zip/; both are tried.

Saved as data/raw/eia861/<year>/f861<year>.zip, with these members extracted next to it:
    Reliability_<year>.xlsx         SAIDI / SAIFI per utility and state, with and without major event days
    Sales_Ult_Cust_<year>.xlsx      retail sales and customers per utility and state
    Service_Territory_<year>.xlsx   counties (by name) each utility serves, the only county-level link

Verification (EIA publishes no checksums): size matches the server, the zip passes its CRC test,
the three members exist and each opens as a workbook.

Usage:
    uv run python scripts/download_eia861.py [--years 2022 2023 2024]
"""

from __future__ import annotations

import argparse
import sys
import zipfile

import openpyxl

import pipeline_config

from download_utils import RAW, FetchFailed, ManualFile, Report, fetch, remote_size

PAGE = "https://www.eia.gov/electricity/data/eia861/"
URLS = [PAGE + "zip/f861{y}.zip", PAGE + "archive/zip/f861{y}.zip"]
SOURCE_DIR = RAW / "eia861"
MEMBERS = ["Reliability_{y}.xlsx", "Sales_Ult_Cust_{y}.xlsx", "Service_Territory_{y}.xlsx"]


def verify_and_extract(zpath, year: int) -> str:
    with zipfile.ZipFile(zpath) as zf:
        broken = zf.testzip()
        if broken:
            raise ValueError(f"CRC error in {broken}")
        names = {n.split("/")[-1]: n for n in zf.namelist()}
        out = []
        for pattern in MEMBERS:
            member = pattern.format(y=year)
            if member not in names:
                raise ValueError(f"{member} not in zip")
            target = zpath.parent / member
            if not target.exists() or target.stat().st_size != zf.getinfo(names[member]).file_size:
                with zf.open(names[member]) as src, target.open("wb") as dst:
                    dst.write(src.read())
            wb = openpyxl.load_workbook(target, read_only=True)
            out.append(f"{member} ({len(wb.sheetnames)} sheet{'s' if len(wb.sheetnames) > 1 else ''})")
            wb.close()
    return "zip ok; " + ", ".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs="+", default=pipeline_config.load()["years"]["list"])
    args = parser.parse_args()
    report = Report()
    for year in args.years:
        dest = SOURCE_DIR / str(year) / f"f861{year}.zip"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            errors = []
            for url in (u.format(y=year) for u in URLS):
                try:
                    fetch(url, dest)
                    break
                except FetchFailed as e:
                    errors.append(str(e))
            else:
                report.add(ManualFile(
                    name=f"f861{year}.zip", page=PAGE, dest=dest, why="; ".join(errors),
                    how=f"on the page, find the {year} row of the annual files table and click its ZIP link",
                ))
                continue
        else:
            size = next((s for s in (remote_size(u.format(y=year)) for u in URLS) if s), None)
            if size and dest.stat().st_size != size:
                print(f"  f861{year}.zip: local size differs from the server (EIA may have revised it); "
                      f"delete it and rerun to refresh")
            print(f"  f861{year}.zip: already downloaded")
        try:
            print(f"  f861{year}.zip: {verify_and_extract(dest, year)}")
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            dest.unlink(missing_ok=True)
            print(f"  f861{year}.zip: verification failed ({e}); file removed, rerun to retry")
            return 1
    return report.finish(SOURCE_DIR)


if __name__ == "__main__":
    sys.exit(main())
