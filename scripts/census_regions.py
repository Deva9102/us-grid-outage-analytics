"""Build the state-to-region lookup used by the Silver layer.

One row per state, DC and territory, keyed by 2-digit state FIPS so Silver can join on
LEFT(fips_code, 2) instead of on state names. Columns:

    state_fips, state_abbr, state_name, census_region, census_division, fema_region

Census regions and divisions follow the US Census Bureau definitions. Territories are not
part of any Census region, so Puerto Rico and the US Virgin Islands get 'Territory' (D8).
FEMA regions follow FEMA's ten standard regions.

Output: data/reference/state_regions.csv (committed: small, built reference data, not a raw
download). On Databricks it is uploaded to /Volumes/workspace/outages/raw/reference/.

Usage:
    uv run python scripts/census_regions.py
"""

from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "reference" / "state_regions.csv"

# Census division -> (region, member state abbreviations)
CENSUS_DIVISIONS = {
    "New England": ("Northeast", ["CT", "ME", "MA", "NH", "RI", "VT"]),
    "Middle Atlantic": ("Northeast", ["NJ", "NY", "PA"]),
    "East North Central": ("Midwest", ["IL", "IN", "MI", "OH", "WI"]),
    "West North Central": ("Midwest", ["IA", "KS", "MN", "MO", "NE", "ND", "SD"]),
    "South Atlantic": ("South", ["DE", "DC", "FL", "GA", "MD", "NC", "SC", "VA", "WV"]),
    "East South Central": ("South", ["AL", "KY", "MS", "TN"]),
    "West South Central": ("South", ["AR", "LA", "OK", "TX"]),
    "Mountain": ("West", ["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY"]),
    "Pacific": ("West", ["AK", "CA", "HI", "OR", "WA"]),
    "Territory": ("Territory", ["PR", "VI"]),
}

FEMA_REGIONS = {
    "I": ["CT", "ME", "MA", "NH", "RI", "VT"],
    "II": ["NJ", "NY", "PR", "VI"],
    "III": ["DE", "DC", "MD", "PA", "VA", "WV"],
    "IV": ["AL", "FL", "GA", "KY", "MS", "NC", "SC", "TN"],
    "V": ["IL", "IN", "MI", "MN", "OH", "WI"],
    "VI": ["AR", "LA", "NM", "OK", "TX"],
    "VII": ["IA", "KS", "MO", "NE"],
    "VIII": ["CO", "MT", "ND", "SD", "UT", "WY"],
    "IX": ["AZ", "CA", "HI", "NV"],
    "X": ["AK", "ID", "OR", "WA"],
}

# abbreviation -> (state FIPS, name as written in EAGLE-I)
STATES = {
    "AL": ("01", "Alabama"), "AK": ("02", "Alaska"), "AZ": ("04", "Arizona"),
    "AR": ("05", "Arkansas"), "CA": ("06", "California"), "CO": ("08", "Colorado"),
    "CT": ("09", "Connecticut"), "DE": ("10", "Delaware"), "DC": ("11", "District of Columbia"),
    "FL": ("12", "Florida"), "GA": ("13", "Georgia"), "HI": ("15", "Hawaii"),
    "ID": ("16", "Idaho"), "IL": ("17", "Illinois"), "IN": ("18", "Indiana"),
    "IA": ("19", "Iowa"), "KS": ("20", "Kansas"), "KY": ("21", "Kentucky"),
    "LA": ("22", "Louisiana"), "ME": ("23", "Maine"), "MD": ("24", "Maryland"),
    "MA": ("25", "Massachusetts"), "MI": ("26", "Michigan"), "MN": ("27", "Minnesota"),
    "MS": ("28", "Mississippi"), "MO": ("29", "Missouri"), "MT": ("30", "Montana"),
    "NE": ("31", "Nebraska"), "NV": ("32", "Nevada"), "NH": ("33", "New Hampshire"),
    "NJ": ("34", "New Jersey"), "NM": ("35", "New Mexico"), "NY": ("36", "New York"),
    "NC": ("37", "North Carolina"), "ND": ("38", "North Dakota"), "OH": ("39", "Ohio"),
    "OK": ("40", "Oklahoma"), "OR": ("41", "Oregon"), "PA": ("42", "Pennsylvania"),
    "RI": ("44", "Rhode Island"), "SC": ("45", "South Carolina"), "SD": ("46", "South Dakota"),
    "TN": ("47", "Tennessee"), "TX": ("48", "Texas"), "UT": ("49", "Utah"),
    "VT": ("50", "Vermont"), "VA": ("51", "Virginia"), "WA": ("53", "Washington"),
    "WV": ("54", "West Virginia"), "WI": ("55", "Wisconsin"), "WY": ("56", "Wyoming"),
    "PR": ("72", "Puerto Rico"), "VI": ("78", "United States Virgin Islands"),
}


def build_rows() -> list[dict[str, str]]:
    division_of = {abbr: (div, region) for div, (region, members) in CENSUS_DIVISIONS.items() for abbr in members}
    fema_of = {abbr: region for region, members in FEMA_REGIONS.items() for abbr in members}

    # Every state must appear exactly once in each grouping.
    for name, mapping in (("Census division", division_of), ("FEMA region", fema_of)):
        missing = set(STATES) - set(mapping)
        extra = set(mapping) - set(STATES)
        if missing or extra:
            raise ValueError(f"{name} mapping mismatch: missing {sorted(missing)}, extra {sorted(extra)}")
    for name, groups in (("Census division", CENSUS_DIVISIONS), ("FEMA region", FEMA_REGIONS)):
        members = [a for g in groups.values() for a in (g[1] if isinstance(g, tuple) else g)]
        if len(members) != len(set(members)):
            raise ValueError(f"{name} mapping lists a state twice")

    rows = []
    for abbr, (fips, name) in sorted(STATES.items(), key=lambda kv: kv[1][0]):
        division, region = division_of[abbr]
        rows.append({
            "state_fips": fips,
            "state_abbr": abbr,
            "state_name": name,
            "census_region": region,
            "census_division": division,
            "fema_region": fema_of[abbr],
        })
    return rows


def main() -> None:
    rows = build_rows()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
