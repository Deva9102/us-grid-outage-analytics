"""Download the NWS public forecast zone to county correlation files in effect during 2022-2025.

Many NOAA Storm Events are reported by forecast zone (CZ_TYPE = 'Z'), not county. This file maps
each zone to the counties it covers. NWS redraws zones from time to time and publishes a new file
named bp<ddmmmyy>.dbx, effective from that date, at
    https://www.weather.gov/source/gis/Shapefiles/County/
(listed on https://www.weather.gov/gis/ZoneCounty, which shows only the latest versions).

Every version in effect at some point in 2022-2025 is downloaded, starting with the one in force on
2022-01-01. Each is saved under the year it took effect:
    data/raw/nws_zone_county/<effective year>/bp<ddmmmyy>.dbx

Format: pipe-delimited text, no header, 11 fields:
    STATE | ZONE | CWA | NAME | STATE_ZONE | COUNTY | FIPS | TIME_ZONE | FE_AREA | LAT | LON

Verification (NWS publishes no checksums): size matches the server, every line has 11 fields,
STATE is two letters, ZONE three digits and FIPS five digits.

Usage:
    uv run python scripts/download_nws_zone_county.py
"""

from __future__ import annotations

import re
import sys
from datetime import date

from download_utils import RAW, FetchFailed, ManualFile, Report, fetch, remote_size

BASE = "https://www.weather.gov/source/gis/Shapefiles/County/"
PAGE = "https://www.weather.gov/gis/ZoneCounty"
ARCHIVE = "https://web.archive.org/web/2025*/https://www.weather.gov/source/gis/Shapefiles/County/"
SOURCE_DIR = RAW / "nws_zone_county"

# Versions in effect during 2022-2025, by effective date. bp08se21 was in force on 2022-01-01;
# bp05mr24 stayed in force until bp18mr25 replaced it, and bp18mr25 until bp16ap26 (D59).
VERSIONS = ["bp08se21", "bp22mr22", "bp13se22", "bp08mr23", "bp19se23", "bp05mr24", "bp18mr25"]


# NWS file names use two-letter month codes.
MONTHS = {"ja": 1, "fe": 2, "mr": 3, "ap": 4, "my": 5, "jn": 6, "jl": 7, "au": 8, "se": 9,
          "sp": 9, "oc": 10, "nv": 11, "no": 11, "de": 12, "dc": 12}


def effective_date(version: str) -> date:
    m = re.fullmatch(r"bp(\d{2})([a-z]{2})(\d{2})", version)
    if not m or m.group(2) not in MONTHS:
        raise ValueError(f"cannot read the effective date from {version}")
    return date(2000 + int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))


def verify(path) -> str:
    bad = 0
    lines = 0
    with path.open(encoding="latin-1") as f:
        for line in f:
            if not line.strip():
                continue
            lines += 1
            parts = line.rstrip("\r\n").split("|")
            if (len(parts) != 11 or not re.fullmatch(r"[A-Z]{2}", parts[0])
                    or not re.fullmatch(r"\d{3}", parts[1]) or not re.fullmatch(r"\d{5}", parts[6])):
                bad += 1
    if lines == 0 or bad:
        raise ValueError(f"{bad} malformed lines of {lines}")
    return f"{lines:,} zone-county rows, format ok"


def main() -> int:
    report = Report()
    for version in VERSIONS:
        eff = effective_date(version)
        name = f"{version}.dbx"
        dest = SOURCE_DIR / str(eff.year) / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = remote_size(BASE + name)
        if dest.exists() and (size is None or dest.stat().st_size == size):
            print(f"  {name} (effective {eff}): already downloaded")
        else:
            try:
                fetch(BASE + name, dest)
            except FetchFailed as e:
                report.add(ManualFile(
                    name=f"{name} (effective {eff})", page=BASE + name, dest=dest, why=str(e),
                    how=f"if the link is gone, find {name} on {ARCHIVE} and save the raw file",
                ))
                continue
        try:
            print(f"  {name} (effective {eff}): {verify(dest)}")
        except (OSError, ValueError) as e:
            dest.unlink(missing_ok=True)
            print(f"  {name}: verification failed ({e}); file removed, rerun to retry")
            return 1
    return report.finish(SOURCE_DIR)


if __name__ == "__main__":
    sys.exit(main())
