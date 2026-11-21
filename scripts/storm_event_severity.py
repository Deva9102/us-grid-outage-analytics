"""Build data/reference/storm_event_severity.csv: NOAA event types, severity order, outage relevance (D37).

Used by the storm match (03_gold_storm_match.sql):
    can_cause_outage = N   the type is never matched to an outage (it does not damage the grid, or
                           it is a long background condition such as drought whose window would
                           swallow every outage in the county)
    severity_rank          1 = most severe; breaks ties between storms with the same overlap

Tiers, most severe first: tropical cyclones, tornadoes, ice and snow, wind, wildfire, flooding,
lightning and hail, temperature, other. Within a tier, types are ordered by how directly they
damage lines and poles.

Usage:
    uv run python scripts/storm_event_severity.py
"""

from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "data" / "reference" / "storm_event_severity.csv"

CAUSAL = [  # (event type, tier), most severe first
    ("Hurricane (Typhoon)", "tropical_cyclone"),
    ("Tropical Storm", "tropical_cyclone"),
    ("Storm Surge/Tide", "tropical_cyclone"),
    ("Tropical Depression", "tropical_cyclone"),
    ("Tornado", "tornado"),
    ("Ice Storm", "ice_snow"),
    ("Blizzard", "ice_snow"),
    ("Winter Storm", "ice_snow"),
    ("Heavy Snow", "ice_snow"),
    ("Lake-Effect Snow", "ice_snow"),
    ("Sleet", "ice_snow"),
    ("Thunderstorm Wind", "wind"),
    ("High Wind", "wind"),
    ("Strong Wind", "wind"),
    ("Dust Storm", "wind"),
    ("Wildfire", "wildfire"),
    ("Flash Flood", "flood"),
    ("Flood", "flood"),
    ("Coastal Flood", "flood"),
    ("Lakeshore Flood", "flood"),
    ("Debris Flow", "flood"),
    ("Heavy Rain", "flood"),
    ("Tsunami", "flood"),
    ("Seiche", "flood"),
    ("Lightning", "lightning_hail"),
    ("Hail", "lightning_hail"),
    ("Excessive Heat", "temperature"),
    ("Heat", "temperature"),
    ("Extreme Cold/Wind Chill", "temperature"),
    ("Cold/Wind Chill", "temperature"),
    ("Winter Weather", "temperature"),
    ("Avalanche", "other"),
]
NOT_CAUSAL = [
    "Drought", "Dense Fog", "Freezing Fog", "Dense Smoke", "Frost/Freeze", "Funnel Cloud", "High Surf",
    "Rip Current", "Sneakerwave", "Astronomical Low Tide", "Dust Devil", "Volcanic Ashfall", "Waterspout",
    "Marine Dense Fog", "Marine Hail", "Marine High Wind", "Marine Hurricane/Typhoon", "Marine Lightning",
    "Marine Strong Wind", "Marine Thunderstorm Wind", "Marine Tropical Depression", "Marine Tropical Storm",
]


def main() -> None:
    rows = [(t, i, tier, "Y") for i, (t, tier) in enumerate(CAUSAL, start=1)]
    rows += [(t, 100 + i, "not_causal", "N") for i, t in enumerate(NOT_CAUSAL, start=1)]
    names = [r[0] for r in rows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate event type")
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_type", "severity_rank", "severity_tier", "can_cause_outage"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} event types ({len(CAUSAL)} causal) to {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
