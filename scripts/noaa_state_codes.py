"""Build data/reference/noaa_state_codes.csv: NOAA Storm Events STATE_FIPS -> Census state FIPS (D28).

NOAA uses Census FIPS for the 50 states and DC, but its own codes for territories and water
areas: Puerto Rico is 99 (Census 72), the US Virgin Islands 96 (Census 78), American Samoa 97,
Guam 98, and 81-95 are marine and Great Lakes areas.

Columns:
    noaa_state_fips   2-digit code as used in NOAA STATE_FIPS (zero-padded)
    noaa_state_name   NOAA STATE text
    state_fips        Census state FIPS, empty for water areas
    area_type         state | territory | territory_not_tracked | water
                      (territory_not_tracked = no EAGLE-I data and not in state_regions.csv)

Usage:
    uv run python scripts/noaa_state_codes.py
"""

from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGIONS = REPO_ROOT / "data" / "reference" / "state_regions.csv"
OUT = REPO_ROOT / "data" / "reference" / "noaa_state_codes.csv"

TERRITORIES = [  # NOAA code, NOAA name, Census FIPS, area type
    ("99", "PUERTO RICO", "72", "territory"),
    ("96", "VIRGIN ISLANDS", "78", "territory"),
    ("97", "AMERICAN SAMOA", "60", "territory_not_tracked"),
    ("98", "GUAM", "66", "territory_not_tracked"),
]
WATER = [
    ("81", "LAKE ST CLAIR"), ("83", "GUAM WATERS"), ("84", "HAWAII WATERS"), ("85", "GULF OF MEXICO"),
    ("86", "E PACIFIC"), ("87", "ATLANTIC SOUTH"), ("88", "ATLANTIC NORTH"), ("89", "GULF OF ALASKA"),
    ("90", "LAKE HURON"), ("91", "LAKE MICHIGAN"), ("92", "LAKE SUPERIOR"), ("93", "ST LAWRENCE R"),
    ("94", "LAKE ONTARIO"), ("95", "LAKE ERIE"),
]


def main() -> None:
    rows = []
    for r in csv.DictReader(REGIONS.open()):
        if r["state_abbr"] in ("PR", "VI"):
            continue  # NOAA codes these as 99 and 96
        rows.append((r["state_fips"], r["state_name"].upper(), r["state_fips"], "state"))
    rows += TERRITORIES
    rows += [(code, name, "", "water") for code, name in WATER]
    rows.sort()
    codes = [r[0] for r in rows]
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate NOAA code")
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["noaa_state_fips", "noaa_state_name", "state_fips", "area_type"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
