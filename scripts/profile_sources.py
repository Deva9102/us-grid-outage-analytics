"""Profile the added sources with DuckDB and measure how they join to EAGLE-I.

Sources (2022-2024, as downloaded by the download_* scripts):
    NOAA Storm Events details      data/raw/noaa_storm_events/<year>/
    NWS zone-county correlation    data/raw/nws_zone_county/<effective year>/
    EIA-861 reliability, sales, service territory   data/raw/eia861/<year>/
    DOE OE-417 annual summaries    data/raw/oe417/<year>/

For each source: columns, row counts, date ranges, nulls, time zone handling, location coding,
and measured join rates to EAGLE-I: by location (does the record resolve to EAGLE-I counties?) and,
for event sources, by time (is there an overlapping EAGLE-I outage event?). EAGLE-I events are
rebuilt in DuckDB with the final Gold logic (D17-D19, 0.25% threshold).

Writes docs/data_profile_sources.md. Raw files are only read.

Usage:
    uv run python scripts/profile_sources.py
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import xlrd

import test_gold_events_duckdb as gold
import test_silver_duckdb as silver

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
OUT = REPO_ROOT / "docs" / "data_profile_sources.md"
REGIONS = REPO_ROOT / "data" / "reference" / "state_regions.csv"
YEARS = (2022, 2023, 2024)

# NOAA event types that plausibly cause power outages, for the event-level match rates.
OUTAGE_TYPES = [
    "Thunderstorm Wind", "High Wind", "Strong Wind", "Tornado", "Hurricane", "Hurricane (Typhoon)",
    "Tropical Storm", "Tropical Depression", "Winter Storm", "Ice Storm", "Blizzard", "Heavy Snow",
    "Winter Weather", "Wildfire", "Lightning", "Hail", "Storm Surge/Tide", "Flash Flood", "Flood",
    "Excessive Heat", "Heat", "Extreme Cold/Wind Chill", "Cold/Wind Chill", "Debris Flow",
]


# -----------------------------------------------------------------------------
# Markdown helpers
# -----------------------------------------------------------------------------

def fmt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.1f}" if abs(v) >= 100 else f"{v:,.3g}"
    return str(v).replace("|", "/").replace("\n", " ")


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(fmt(v.item() if hasattr(v, "item") else v) for v in row) + " |")
    return "\n".join(lines)


def pct(n, d) -> str:
    return "n/a" if not d else f"{n / d:.1%}"


def q(con, sql) -> pd.DataFrame:
    return con.execute(sql).fetchdf()


# -----------------------------------------------------------------------------
# Name normalization for name-based sources (OE-417, EIA service territory)
# -----------------------------------------------------------------------------

SUFFIXES = r"\b(county|parish|borough|census area|city and borough|municipality|municipio)\b"


def norm_county(name: str) -> str:
    s = str(name).lower().strip()
    s = s.replace("&", " and ").replace(".", "").replace("'", "").replace("-", " ")
    s = re.sub(r"^(st|ste)\s", lambda m: "saint " if m.group(1) == "st" else "sainte ", s)
    s = re.sub(SUFFIXES, " ", s)
    return re.sub(r"\s+", " ", s).strip()


# -----------------------------------------------------------------------------
# EAGLE-I reference: counties, names, events
# -----------------------------------------------------------------------------

def build_eaglei(con) -> None:
    print("Building EAGLE-I Silver and Gold in DuckDB (all years) ...", flush=True)
    silver.bronze(con, month_filter=None)
    silver.build_dim(con)
    for name, _, sql in silver.SILVER_STEPS:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
    for name, _, _ in silver.SILVER_STEPS[:-1]:
        con.execute(f"DROP TABLE {name}")
    gold.build_gold(con)
    con.execute("""
        CREATE TABLE eaglei_counties AS
        SELECT s.fips_code, MAX(s.county) AS county, MAX(s.state_abbr) AS state_abbr,
               MAX(s.state) AS state_name, MAX(k.customers) AS customers
        FROM silver_outages s LEFT JOIN dim_county_customers k USING (fips_code)
        GROUP BY 1
    """)
    con.execute(f"CREATE TABLE regions AS SELECT * FROM read_csv('{REGIONS.as_posix()}', all_varchar = true)")


# -----------------------------------------------------------------------------
# NOAA Storm Events + NWS zones
# -----------------------------------------------------------------------------

def load_noaa(con) -> None:
    files = sorted((RAW / "noaa_storm_events").rglob("StormEvents_details-*.csv.gz"))
    paths = ", ".join(f"'{p.as_posix()}'" for p in files)
    con.execute(f"CREATE TABLE noaa_raw AS SELECT * FROM read_csv([{paths}], all_varchar = true, union_by_name = true)")
    # Local times from the numeric parts; CZ_TIMEZONE holds the UTC offset ('CST-6', 'GST10').
    con.execute("""
        CREATE TABLE noaa AS
        SELECT
            *,
            TRY_STRPTIME(BEGIN_YEARMONTH || LPAD(BEGIN_DAY, 2, '0') || LPAD(BEGIN_TIME, 4, '0'), '%Y%m%d%H%M') AS begin_local,
            TRY_STRPTIME(END_YEARMONTH || LPAD(END_DAY, 2, '0') || LPAD(END_TIME, 4, '0'), '%Y%m%d%H%M') AS end_local,
            TRY_CAST(regexp_extract(CZ_TIMEZONE, '(-?[0-9]+)$', 1) AS INTEGER) AS utc_offset_h
        FROM noaa_raw
    """)
    con.execute("""
        ALTER TABLE noaa ADD COLUMN begin_utc TIMESTAMP;
        ALTER TABLE noaa ADD COLUMN end_utc TIMESTAMP;
        UPDATE noaa SET begin_utc = begin_local - utc_offset_h * INTERVAL 1 HOUR,
                        end_utc   = end_local   - utc_offset_h * INTERVAL 1 HOUR;
    """)


def load_zones(con) -> pd.DataFrame:
    files = sorted((RAW / "nws_zone_county").rglob("bp*.dbx"))
    months = {"ja": 1, "fe": 2, "mr": 3, "ap": 4, "my": 5, "jn": 6, "jl": 7, "au": 8, "se": 9,
              "sp": 9, "oc": 10, "nv": 11, "no": 11, "de": 12, "dc": 12}
    versions = []
    for p in files:
        m = re.fullmatch(r"bp(\d{2})([a-z]{2})(\d{2})", p.stem)
        versions.append((p.stem, date(2000 + int(m.group(3)), months[m.group(2)], int(m.group(1))), p))
    versions.sort(key=lambda v: v[1])
    rows = []
    for i, (name, eff, p) in enumerate(versions):
        until = versions[i + 1][1] if i + 1 < len(versions) else date(2025, 3, 18)
        rows.append((name, eff, until, p.as_posix()))
    con.execute("CREATE TABLE zone_versions (version VARCHAR, effective_from DATE, effective_to DATE, path VARCHAR)")
    con.executemany("INSERT INTO zone_versions VALUES (?, ?, ?, ?)", rows)
    parts = []
    for name, _, _, path in rows:
        parts.append(f"""
            SELECT '{name}' AS version, * FROM read_csv('{path}', delim = '|', header = false, encoding = 'latin-1',
                columns = {{'state': 'VARCHAR', 'zone': 'VARCHAR', 'cwa': 'VARCHAR', 'name': 'VARCHAR',
                            'state_zone': 'VARCHAR', 'county': 'VARCHAR', 'fips': 'VARCHAR', 'time_zone': 'VARCHAR',
                            'fe_area': 'VARCHAR', 'lat': 'VARCHAR', 'lon': 'VARCHAR'}})""")
    con.execute("CREATE TABLE zones AS " + " UNION ALL ".join(parts))
    return pd.DataFrame(rows, columns=["version", "effective_from", "effective_to", "path"])


def resolve_noaa(con) -> None:
    """NOAA event -> EAGLE-I county FIPS, with the zone file in effect at the event date (and latest-only)."""
    con.execute("""
        CREATE TABLE noaa_keyed AS
        SELECT n.*, r.state_abbr,
               LPAD(n.STATE_FIPS, 2, '0') || LPAD(n.CZ_FIPS, 3, '0') AS county_fips_c,
               r.state_abbr || LPAD(n.CZ_FIPS, 3, '0') AS zone_key
        FROM noaa n LEFT JOIN regions r ON r.state_fips = LPAD(n.STATE_FIPS, 2, '0')
    """)
    con.execute("""
        CREATE TABLE noaa_county_eff AS
        SELECT n.EVENT_ID, n.EVENT_TYPE, n.CZ_TYPE, n.begin_utc, n.end_utc, n.county_fips_c AS fips
        FROM noaa_keyed n WHERE n.CZ_TYPE = 'C'
        UNION ALL
        SELECT DISTINCT n.EVENT_ID, n.EVENT_TYPE, n.CZ_TYPE, n.begin_utc, n.end_utc, z.fips
        FROM noaa_keyed n
        JOIN zone_versions v ON CAST(n.begin_local AS DATE) >= v.effective_from AND CAST(n.begin_local AS DATE) < v.effective_to
        JOIN zones z ON z.version = v.version AND z.state || z.zone = n.zone_key
        WHERE n.CZ_TYPE = 'Z'
    """)
    con.execute("""
        CREATE TABLE noaa_county_latest AS
        SELECT DISTINCT n.EVENT_ID, z.fips
        FROM noaa_keyed n JOIN zones z ON z.version = 'bp05mr24' AND z.state || z.zone = n.zone_key
        WHERE n.CZ_TYPE = 'Z'
    """)


def profile_noaa(con, md: list[str], zv: pd.DataFrame) -> dict:
    md += ["## 1. NOAA Storm Events (details files)", "",
           "Files: `data/raw/noaa_storm_events/<year>/StormEvents_details-ftp_v1.0_d<year>_c20261119.csv.gz` "
           "(NCEI rebuilt all three years on 2026-11-19). One row per event; an event is one weather "
           "phenomenon in one county or forecast zone.", ""]
    md += ["### Rows by year and location type", ""]
    md.append(table(q(con, """
        SELECT YEAR AS year, COUNT(*) AS events, COUNT(DISTINCT EPISODE_ID) AS episodes,
               COUNT(*) FILTER (WHERE CZ_TYPE = 'C') AS county_C,
               COUNT(*) FILTER (WHERE CZ_TYPE = 'Z') AS zone_Z,
               COUNT(*) FILTER (WHERE CZ_TYPE NOT IN ('C', 'Z')) AS other,
               COUNT(DISTINCT EVENT_TYPE) AS event_types,
               strftime(MIN(begin_utc), '%Y-%m-%d %H:%M') AS first_begin_utc,
               strftime(MAX(end_utc), '%Y-%m-%d %H:%M') AS last_end_utc
        FROM noaa GROUP BY 1 ORDER BY 1
    """)))
    md.append("")

    cols = [r[0] for r in con.execute("DESCRIBE noaa_raw").fetchall()]
    nulls = con.execute("SELECT " + ", ".join(
        f"COUNT(*) FILTER (WHERE \"{c}\" IS NULL OR TRIM(\"{c}\") = '')" for c in cols) + ", COUNT(*) FROM noaa_raw").fetchone()
    total = nulls[-1]
    md += ["### Columns and nulls (all years)", "",
           "Read as text. Null means empty or missing.", ""]
    md.append(table(pd.DataFrame({"column": cols, "null_or_empty": nulls[:-1],
                                  "share": [pct(n, total) for n in nulls[:-1]]})))
    md.append("")

    md += ["### Time zone handling", "",
           "`BEGIN_DATE_TIME` / `END_DATE_TIME` (and the numeric `BEGIN_YEARMONTH`, `BEGIN_DAY`, "
           "`BEGIN_TIME` parts) are **local standard time** of the county or zone. `CZ_TIMEZONE` holds the "
           "offset, e.g. `CST-6` = UTC-6, `GST10` = UTC+10 (Guam). UTC = local - offset. A few rows "
           "carry daylight codes (`EDT-4`, `CDT-5`, `PDT-7`), which the same rule handles.", ""]
    md.append(table(q(con, """
        SELECT CZ_TIMEZONE AS cz_timezone, utc_offset_h, COUNT(*) AS events,
               COUNT(*) FILTER (WHERE begin_utc IS NULL) AS unparsed
        FROM noaa GROUP BY 1, 2 ORDER BY 3 DESC
    """)))
    mism = con.execute("""
        SELECT COUNT(*) FILTER (WHERE UPPER(strftime(begin_local, '%d-%b-%y %H:%M:%S')) <> UPPER(BEGIN_DATE_TIME)),
               COUNT(*) FILTER (WHERE end_utc < begin_utc)
        FROM noaa
    """).fetchone()
    md += ["", f"The numeric parts agree with `BEGIN_DATE_TIME` ({mism[0]:,} mismatches). "
               f"{mism[1]:,} events end before they begin.", ""]

    md += ["### Top event types", ""]
    md.append(table(q(con, """
        SELECT EVENT_TYPE AS event_type, COUNT(*) AS events,
               COUNT(*) FILTER (WHERE CZ_TYPE = 'C') AS by_county, COUNT(*) FILTER (WHERE CZ_TYPE = 'Z') AS by_zone
        FROM noaa GROUP BY 1 ORDER BY 2 DESC LIMIT 20
    """)))
    md.append("")
    md += ["### Damage fields", "",
           "`DAMAGE_PROPERTY` and `DAMAGE_CROPS` are text with K/M/B suffixes (e.g. `10.00K`); empty is "
           "not the same as `0.00K`.", ""]
    md.append(table(q(con, """
        SELECT regexp_extract(DAMAGE_PROPERTY, '([A-Za-z])$', 1) AS suffix, COUNT(*) AS events
        FROM noaa GROUP BY 1 ORDER BY 2 DESC
    """)))
    md.append("")

    # Location resolution
    stats = con.execute("""
        WITH ev AS (SELECT EVENT_ID, CZ_TYPE, state_abbr, county_fips_c FROM noaa_keyed),
        eff AS (SELECT DISTINCT e.EVENT_ID FROM noaa_county_eff e JOIN eaglei_counties c ON c.fips_code = e.fips),
        eff_any AS (SELECT DISTINCT EVENT_ID FROM noaa_county_eff),
        lat AS (SELECT DISTINCT l.EVENT_ID FROM noaa_county_latest l JOIN eaglei_counties c ON c.fips_code = l.fips)
        SELECT
            COUNT(*) FILTER (WHERE CZ_TYPE = 'C'),
            COUNT(*) FILTER (WHERE CZ_TYPE = 'C' AND EVENT_ID IN (SELECT EVENT_ID FROM eff)),
            COUNT(*) FILTER (WHERE CZ_TYPE = 'Z'),
            COUNT(*) FILTER (WHERE CZ_TYPE = 'Z' AND EVENT_ID IN (SELECT EVENT_ID FROM eff_any)),
            COUNT(*) FILTER (WHERE CZ_TYPE = 'Z' AND EVENT_ID IN (SELECT EVENT_ID FROM eff)),
            COUNT(*) FILTER (WHERE CZ_TYPE = 'Z' AND EVENT_ID IN (SELECT EVENT_ID FROM lat)),
            COUNT(*) FILTER (WHERE state_abbr IS NULL)
        FROM ev
    """).fetchone()
    c_all, c_ok, z_all, z_zone, z_ok, z_latest, no_state = stats
    fan = con.execute("""
        SELECT MEDIAN(n), MAX(n), AVG(n) FROM (SELECT EVENT_ID, COUNT(*) n FROM noaa_county_eff WHERE CZ_TYPE = 'Z' GROUP BY 1)
    """).fetchone()
    unresolved = q(con, """
        SELECT n.STATE AS noaa_state, n.CZ_TYPE AS cz_type, COUNT(*) AS events
        FROM noaa_keyed n
        WHERE n.EVENT_ID NOT IN (SELECT e.EVENT_ID FROM noaa_county_eff e JOIN eaglei_counties c ON c.fips_code = e.fips)
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 12
    """)
    md += ["### Location coding and resolution to EAGLE-I counties", "",
           "- `CZ_TYPE = 'C'`: `CZ_FIPS` is the county FIPS within `STATE_FIPS`; county FIPS = "
           "`LPAD(STATE_FIPS, 2) || LPAD(CZ_FIPS, 3)`.",
           "- `CZ_TYPE = 'Z'`: `CZ_FIPS` is an NWS forecast zone number. Zone key = state abbreviation "
           "(from `STATE_FIPS` via `data/reference/state_regions.csv`) + 3-digit zone, mapped to counties "
           "with the NWS correlation file in effect on the event's begin date. One zone can cover several "
           "counties, and one county several zones.",
           "- No `M` (marine) rows appear in these three files.", "",
           "| Measure | Value |", "|---|---|",
           f"| County events (C) resolving to an EAGLE-I county | {c_ok:,} of {c_all:,} ({pct(c_ok, c_all)}) |",
           f"| Zone events (Z) found in the zone file in effect | {z_zone:,} of {z_all:,} ({pct(z_zone, z_all)}) |",
           f"| Zone events (Z) resolving to at least one EAGLE-I county | {z_ok:,} of {z_all:,} ({pct(z_ok, z_all)}) |",
           f"| Same, using only the latest 2022-2024 zone file (bp05mr24) | {z_latest:,} of {z_all:,} ({pct(z_latest, z_all)}) |",
           f"| Counties per resolved zone event | median {fan[0]:.0f}, mean {fan[2]:.2f}, max {fan[1]:,} |",
           f"| Events whose STATE_FIPS is not a state, DC or territory in the lookup | {no_state:,} |",
           "", "Unresolved events by NOAA state (top 12):", ""]
    md.append(table(unresolved))
    md += ["", "Most unresolved land events are not a join problem: EAGLE-I has no data for those counties. "
               "EAGLE-I county coverage against the counties in the NWS zone file (bp05mr24), states below 95%:", ""]
    md.append(table(q(con, """
        WITH nws AS (SELECT LEFT(fips, 2) AS state_fips, COUNT(DISTINCT fips) AS nws_counties
                     FROM zones WHERE version = 'bp05mr24' GROUP BY 1),
        eag AS (SELECT LEFT(fips_code, 2) AS state_fips, COUNT(*) AS eaglei_counties FROM eaglei_counties GROUP BY 1)
        SELECT r.state_abbr AS state, n.nws_counties, COALESCE(e.eaglei_counties, 0) AS eaglei_counties,
               ROUND(COALESCE(e.eaglei_counties, 0) / n.nws_counties, 3) AS coverage
        FROM nws n JOIN regions r ON r.state_fips = n.state_fips LEFT JOIN eag e ON e.state_fips = n.state_fips
        WHERE COALESCE(e.eaglei_counties, 0) < 0.95 * n.nws_counties
        ORDER BY coverage
    """)))
    md.append("")

    # Event-level match
    types = ", ".join(f"'{t}'" for t in OUTAGE_TYPES)
    fwd = q(con, f"""
        WITH ev AS (
            SELECT DISTINCT e.EVENT_ID, e.EVENT_TYPE, e.CZ_TYPE, e.begin_utc, e.end_utc, e.fips
            FROM noaa_county_eff e JOIN eaglei_counties c ON c.fips_code = e.fips
            WHERE e.EVENT_TYPE IN ({types})
        ),
        hit AS (
            SELECT DISTINCT ev.EVENT_ID FROM ev JOIN gold_outage_events o
              ON o.fips_code = ev.fips
             AND o.event_start <= ev.end_utc + INTERVAL 12 HOUR
             AND o.event_end   >= ev.begin_utc - INTERVAL 1 HOUR
        )
        SELECT EVENT_TYPE AS event_type, COUNT(DISTINCT EVENT_ID) AS resolved_events,
               COUNT(DISTINCT EVENT_ID) FILTER (WHERE EVENT_ID IN (SELECT EVENT_ID FROM hit)) AS with_eaglei_event
        FROM ev GROUP BY 1 ORDER BY 2 DESC
    """)
    fwd["match_rate"] = [pct(a, b) for a, b in zip(fwd.with_eaglei_event, fwd.resolved_events)]
    tot_r, tot_h = int(fwd.resolved_events.sum()), int(fwd.with_eaglei_event.sum())

    rev = q(con, """
        WITH ranked AS (
            SELECT *, ROW_NUMBER() OVER (ORDER BY customer_hours_lost DESC) AS rk FROM gold_outage_events
        ),
        matched AS (
            SELECT DISTINCT r.event_id FROM ranked r JOIN noaa_county_eff n
              ON n.fips = r.fips_code
             AND n.begin_utc <= r.event_start + INTERVAL 2 HOUR
             AND n.end_utc   >= r.event_start - INTERVAL 24 HOUR
        )
        SELECT bucket, COUNT(*) AS eaglei_events, COUNT(*) FILTER (WHERE event_id IN (SELECT event_id FROM matched)) AS with_noaa_event
        FROM (
            SELECT event_id, 'top 100 by customer-hours' AS bucket FROM ranked WHERE rk <= 100
            UNION ALL SELECT event_id, 'top 1,000 by customer-hours' FROM ranked WHERE rk <= 1000
            UNION ALL SELECT event_id, 'peak >= 10,000 customers out' FROM ranked WHERE peak_customers_out >= 10000
            UNION ALL SELECT event_id, 'all events' FROM ranked
        ) GROUP BY 1 ORDER BY 2
    """)
    rev["match_rate"] = [pct(a, b) for a, b in zip(rev.with_noaa_event, rev.eaglei_events)]
    md += ["### Event-level match to EAGLE-I outage events", "",
           "NOAA to EAGLE-I: a resolved NOAA event (outage-relevant types only) matches when one of its "
           "counties has an EAGLE-I event overlapping [NOAA begin - 1 h, NOAA end + 12 h] in UTC. "
           f"Overall: {tot_h:,} of {tot_r:,} ({pct(tot_h, tot_r)}).", ""]
    md.append(table(fwd))
    md += ["", "EAGLE-I to NOAA: an EAGLE-I event matches when a NOAA event (any type) in the same county "
               "was active between 24 h before and 2 h after the outage started.", ""]
    md.append(table(rev))
    md.append("")
    return {"c": (c_ok, c_all), "z": (z_ok, z_all), "z_latest": (z_latest, z_all), "fan": fan,
            "fwd": (tot_h, tot_r), "rev": rev}


def profile_zones(con, md: list[str], zv: pd.DataFrame) -> None:
    md += ["## 2. NWS zone-county correlation", "",
           "Files: `data/raw/nws_zone_county/<effective year>/bp<ddmmyy>.dbx`, pipe-delimited, no header, "
           "11 fields: STATE, ZONE, CWA, NAME, STATE_ZONE, COUNTY, FIPS, TIME_ZONE, FE_AREA, LAT, LON. "
           "Each version is valid from its date until the next one.", ""]
    md.append(table(q(con, """
        SELECT v.version, v.effective_from, v.effective_to, COUNT(*) AS rows,
               COUNT(DISTINCT z.state || z.zone) AS zones, COUNT(DISTINCT z.fips) AS counties,
               COUNT(DISTINCT z.fips) FILTER (WHERE z.fips IN (SELECT fips_code FROM eaglei_counties)) AS eaglei_counties_covered,
               COUNT(*) FILTER (WHERE z.fips IS NULL OR z.zone IS NULL) AS null_keys
        FROM zone_versions v JOIN zones z USING (version) GROUP BY ALL ORDER BY v.effective_from
    """)))
    md.append("")
    md.append(table(q(con, """
        WITH k AS (SELECT version, state || zone AS zone_key, COUNT(DISTINCT fips) n FROM zones GROUP BY 1, 2),
        c AS (SELECT version, fips, COUNT(DISTINCT state || zone) n FROM zones GROUP BY 1, 2)
        SELECT k.version,
               COUNT(*) FILTER (WHERE k.n > 1) AS zones_with_several_counties,
               MAX(k.n) AS max_counties_per_zone,
               (SELECT COUNT(*) FROM c WHERE c.version = k.version AND c.n > 1) AS counties_in_several_zones
        FROM k GROUP BY 1 ORDER BY 1
    """)))
    md.append("")
    md += ["Changes between consecutive versions (zone keys added or removed):", ""]
    md.append(table(q(con, """
        WITH v AS (SELECT version, effective_from, LAG(version) OVER (ORDER BY effective_from) AS prev FROM zone_versions),
        keys AS (SELECT DISTINCT version, state || zone AS zone_key FROM zones)
        SELECT v.prev || ' -> ' || v.version AS change,
               (SELECT COUNT(*) FROM keys a WHERE a.version = v.version AND a.zone_key NOT IN (SELECT zone_key FROM keys b WHERE b.version = v.prev)) AS zones_added,
               (SELECT COUNT(*) FROM keys a WHERE a.version = v.prev AND a.zone_key NOT IN (SELECT zone_key FROM keys b WHERE b.version = v.version)) AS zones_removed
        FROM v WHERE v.prev IS NOT NULL ORDER BY v.effective_from
    """)))
    md += ["", "Time zone field: `TIME_ZONE` is a one- or two-letter NWS code per zone; it is not needed for "
               "the join because NOAA events carry their own offset.", ""]


# -----------------------------------------------------------------------------
# EIA-861
# -----------------------------------------------------------------------------

def read_eia(path: Path, sheet: str, header_rows: int, names: list[str]) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, header=None, skiprows=header_rows, dtype=str)
    df = df.iloc[:, : len(names)]
    df.columns = names
    return df[df[names[0]].fillna("").str.fullmatch(r"\d{4}")]


REL_COLS = ["data_year", "utility_number", "utility_name", "state", "ownership",
            "ieee_saidi_with_med", "ieee_saifi_with_med", "ieee_caidi_with_med",
            "ieee_saidi_without_med", "ieee_saifi_without_med", "ieee_caidi_without_med",
            "ieee_saidi_los_removed", "ieee_saifi_los_removed", "ieee_caidi_los_removed",
            "ieee_customers", "ieee_highest_voltage", "ieee_outages_recorded_auto",
            "other_saidi_with_med", "other_saifi_with_med", "other_caidi_with_med",
            "other_saidi_without_med", "other_saifi_without_med", "other_caidi_without_med",
            "other_customers", "inactive_accounts_included", "momentary_interruptions",
            "other_highest_voltage", "other_outages_recorded_auto"]
SALES_COLS = ["data_year", "utility_number", "utility_name", "part", "service_type", "data_type", "state",
              "ownership", "ba_code", "res_revenue", "res_sales", "res_customers", "com_revenue", "com_sales",
              "com_customers", "ind_revenue", "ind_sales", "ind_customers", "trn_revenue", "trn_sales",
              "trn_customers", "total_revenue", "total_sales", "total_customers"]
TERR_COLS = ["data_year", "utility_number", "utility_name", "short_form", "state", "county"]


def load_eia(con) -> None:
    rel, sales, terr = [], [], []
    for y in YEARS:
        d = RAW / "eia861" / str(y)
        for sheet in ("Reliability_States", "Reliability_Territories"):
            rel.append(read_eia(d / f"Reliability_{y}.xlsx", sheet, 3, REL_COLS).assign(sheet=sheet))
        for sheet in ("States", "Territories"):
            sales.append(read_eia(d / f"Sales_Ult_Cust_{y}.xlsx", sheet, 3, SALES_COLS).assign(sheet=sheet))
        for sheet in ("Counties_States", "Counties_Territories"):
            terr.append(read_eia(d / f"Service_Territory_{y}.xlsx", sheet, 1, TERR_COLS).assign(sheet=sheet))
    for name, frames in (("eia_rel", rel), ("eia_sales", sales), ("eia_terr", terr)):
        df = pd.concat(frames, ignore_index=True)
        con.register(f"{name}_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_df")


def profile_eia(con, md: list[str]) -> dict:
    md += ["## 3. EIA Form 861", "",
           "Files: `data/raw/eia861/<year>/f861<year>.zip` with `Reliability_<year>.xlsx`, "
           "`Sales_Ult_Cust_<year>.xlsx` and `Service_Territory_<year>.xlsx` extracted. Each sheet has a "
           "multi-row header (3 rows for Reliability and Sales, 1 for Service Territory) and a footer row; "
           "only rows whose first cell is a 4-digit year are data. The unit of record is utility x state x "
           "year. There are no dates or times: everything is annual, so time zones do not apply.", ""]

    md += ["### Reliability (SAIDI / SAIFI)", "",
           "Two reporting standards side by side: IEEE 1366 and 'other'. Each has values with major event "
           "days (all events) and without; IEEE adds 'loss of supply removed'. Missing values are `.` "
           "(not reported) or empty.", ""]
    md.append(table(q(con, """
        SELECT data_year AS year, COUNT(*) AS rows, COUNT(DISTINCT utility_number) AS utilities,
               COUNT(DISTINCT state) AS states,
               COUNT(*) FILTER (WHERE TRY_CAST(ieee_saidi_with_med AS DOUBLE) IS NOT NULL) AS ieee_saidi_with_med,
               COUNT(*) FILTER (WHERE TRY_CAST(ieee_saidi_without_med AS DOUBLE) IS NOT NULL) AS ieee_saidi_without_med,
               COUNT(*) FILTER (WHERE TRY_CAST(other_saidi_with_med AS DOUBLE) IS NOT NULL) AS other_saidi_with_med,
               COUNT(*) FILTER (WHERE TRY_CAST(ieee_saidi_with_med AS DOUBLE) IS NULL
                                  AND TRY_CAST(other_saidi_with_med AS DOUBLE) IS NULL) AS neither,
               COUNT(*) FILTER (WHERE TRY_CAST(ieee_saidi_with_med AS DOUBLE) IS NOT NULL
                                  AND TRY_CAST(other_saidi_with_med AS DOUBLE) IS NOT NULL) AS both
        FROM eia_rel GROUP BY 1 ORDER BY 1
    """)))
    md.append("")
    md += ["Placeholder values in the IEEE SAIDI-with-MED column (all years):", ""]
    md.append(table(q(con, """
        SELECT COALESCE(ieee_saidi_with_med, '<empty>') AS value, COUNT(*) AS rows FROM eia_rel
        WHERE TRY_CAST(ieee_saidi_with_med AS DOUBLE) IS NULL GROUP BY 1 ORDER BY 2 DESC
    """)))
    md.append("")
    md += ["Eversource and National Grid entities (analysis question 5), 2024, IEEE standard:", ""]
    md.append(table(q(con, """
        SELECT utility_number, utility_name, state, ownership, ieee_customers AS customers,
               ieee_saidi_with_med AS saidi_with_med, ieee_saidi_without_med AS saidi_without_med,
               ieee_saifi_with_med AS saifi_with_med, ieee_saifi_without_med AS saifi_without_med
        FROM eia_rel
        WHERE data_year = '2024' AND regexp_matches(utility_name,
            '(?i)(nstar|eversource|connecticut light|public service co of nh|western massachusetts|massachusetts electric|nantucket electric|niagara mohawk|narragansett|national grid|brooklyn union|keyspan)')
        ORDER BY utility_name, state
    """)))
    md.append("")

    md += ["### Sales to ultimate customers (customers per utility and state)", "",
           "`Part` matters: A = bundled service, B = energy-only, C = delivery-only, D = bundled by other "
           "providers. In retail-choice states one customer appears twice, once with its energy supplier "
           "(B) and once with its wires utility (C). Customer totals must use A + C + D, never B.", ""]
    md.append(table(q(con, """
        SELECT data_year AS year, part, service_type, COUNT(*) AS rows,
               SUM(TRY_CAST(total_customers AS BIGINT)) AS customers
        FROM eia_sales GROUP BY ALL ORDER BY 1, 2
    """)))
    md.append("")
    st = q(con, """
        WITH eia AS (
            SELECT state, SUM(TRY_CAST(total_customers AS BIGINT)) AS eia_customers
            FROM eia_sales WHERE data_year = '2024' AND part IN ('A', 'C', 'D') GROUP BY 1
        ),
        eag AS (SELECT state_abbr AS state, SUM(customers) AS eaglei_customers FROM eaglei_counties GROUP BY 1)
        SELECT e.state, e.eia_customers, g.eaglei_customers,
               ROUND(g.eaglei_customers / e.eia_customers, 3) AS ratio
        FROM eia e LEFT JOIN eag g USING (state)
    """)
    tot_e, tot_g = int(st.eia_customers.sum()), int(st.eaglei_customers.fillna(0).sum())
    md += [f"State join to EAGLE-I, 2024: EIA customers (parts A + C + D) {tot_e:,}; EAGLE-I D13 denominators "
           f"{tot_g:,} (ratio {tot_g / tot_e:.3f}). Per-state ratio EAGLE-I / EIA: median "
           f"{st.ratio.median():.3f}, {int((st.ratio.between(0.9, 1.1)).sum())} of {len(st)} states within 10%.", "",
           "States furthest from 1:", ""]
    st["dist"] = (st.ratio - 1).abs()
    md.append(table(st.sort_values("dist", ascending=False).drop(columns="dist").head(8)))
    md += ["", "Where the gap comes from in MA and SC: the D13 denominator mostly comes from EAGLE-I's own 2024 "
               "`total_customers`, which is far above both MCC and EIA there (D12's larger-value rule keeps it).", ""]
    md.append(table(q(con, """
        SELECT c.state_abbr AS state, d.denominator_source, COUNT(*) AS counties, SUM(d.customers) AS d13_customers
        FROM dim_county_customers d JOIN eaglei_counties c USING (fips_code)
        WHERE c.state_abbr IN ('MA', 'SC') GROUP BY ALL ORDER BY 1, 2
    """)))
    md += ["", "Largest MA counties by D13 denominator (for scale: Suffolk County has about "
               "770,000 residents, so 1.67 M customers is not plausible):", ""]
    md.append(table(q(con, """
        SELECT d.fips_code, c.county, d.customers AS d13_customers, d.denominator_source
        FROM dim_county_customers d JOIN eaglei_counties c USING (fips_code)
        WHERE c.state_abbr = 'MA' ORDER BY d.customers DESC LIMIT 5
    """)))
    md.append("")

    md += ["### Service territory (utility to county)", "",
           "The only county-level link in EIA-861: one row per utility, state and county **name**. There "
           "is no county FIPS. Matching to EAGLE-I therefore needs a one-off name-to-FIPS crosswalk "
           "(the project rule is to join on FIPS codes, never on names).", ""]
    terr = con.execute("SELECT data_year, state, county, utility_number FROM eia_terr").fetchdf()
    eag = con.execute("SELECT fips_code, county, state_abbr FROM eaglei_counties").fetchdf()
    eag["key"] = eag.state_abbr + "|" + eag.county.map(norm_county)
    dup = eag[eag.duplicated("key", keep=False)]
    lookup = eag.drop_duplicates("key").set_index("key").fips_code
    terr["key"] = terr.state + "|" + terr.county.map(norm_county)
    terr["matched"] = terr.key.isin(lookup.index)
    rows = []
    for y in YEARS:
        t = terr[terr.data_year == str(y)]
        pairs = t.drop_duplicates(["state", "county"])
        rows.append((str(y), len(t), t.utility_number.nunique(), len(pairs), int(pairs.matched.sum()),
                     pct(int(pairs.matched.sum()), len(pairs))))
    md.append(table(pd.DataFrame(rows, columns=["year", "rows", "utilities", "state_county_pairs",
                                                "matched_to_eaglei", "match_rate"])))
    t24 = terr[terr.data_year == "2024"]
    upc = t24.groupby("key").utility_number.nunique()
    miss = t24[~t24.matched].drop_duplicates(["state", "county"]).head(12)
    md += ["", f"Utilities per county (2024): median {upc.median():.0f}, mean {upc.mean():.2f}, max {upc.max()}; "
               f"{int((upc > 1).sum()):,} of {len(upc):,} counties have more than one utility. EAGLE-I "
               f"(state, name) keys that are ambiguous after normalization: {dup.key.nunique()} "
               f"(e.g. {', '.join(sorted(dup.key.unique())[:4])}).", "",
           "Unmatched (state, county) examples, 2024:", ""]
    md.append(table(miss[["state", "county"]]))
    md.append("")
    return {"sales_ratio": (tot_g, tot_e), "terr": rows, "upc": upc}


# -----------------------------------------------------------------------------
# OE-417
# -----------------------------------------------------------------------------

def load_oe417(con) -> pd.DataFrame:
    rows = []
    for y in YEARS:
        files = sorted((RAW / "oe417" / str(y)).glob("*.xls*")) if (RAW / "oe417" / str(y)).exists() else []
        if not files:
            continue
        book = xlrd.open_workbook(files[0], logfile=open("/dev/null", "w"))
        sh = book.sheet_by_index(0)
        hdr = next(r for r in range(sh.nrows) if "Date Event Began" in [str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)])
        names = [str(sh.cell_value(hdr, c)).strip() for c in range(sh.ncols)]
        for r in range(hdr + 1, sh.nrows):
            rec = {"file_year": y}
            for c, n in enumerate(names):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    v = xlrd.xldate.xldate_as_datetime(cell.value, book.datemode)
                    rec[n] = v.strftime("%H:%M") if v.year < 1901 else v.strftime("%m/%d/%Y")
                else:
                    rec[n] = str(cell.value).strip()
            rows.append(rec)
    df = pd.DataFrame(rows)

    def dt(d, t):
        try:
            day = datetime.strptime(d, "%m/%d/%Y")
        except (TypeError, ValueError):
            return None
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", t or "")
        return day + timedelta(hours=int(m.group(1)), minutes=int(m.group(2))) if m else day

    df["begin"] = [dt(d, t) for d, t in zip(df["Date Event Began"], df["Time Event Began"])]
    df["restored"] = [dt(d, t) for d, t in zip(df["Date of Restoration"], df["Time of Restoration"])]
    return df


def parse_area(area: str) -> list[tuple[str, list[str]]]:
    parts = re.split(r"([A-Z][A-Za-z .]+?):", area or "")
    out = []
    for i in range(1, len(parts) - 1, 2):
        counties = [c.strip() for c in re.split(r"[,;]", parts[i + 1]) if c.strip()]
        out.append((parts[i].strip(), counties))
    return out


def profile_oe417(con, md: list[str]) -> dict:
    df = load_oe417(con)
    regions = con.execute("SELECT state_name, state_abbr FROM regions").fetchdf()
    name_to_abbr = dict(zip(regions.state_name.str.lower(), regions.state_abbr))
    eag = con.execute("SELECT fips_code, county, state_abbr FROM eaglei_counties").fetchdf()
    lookup = {}
    for f, c, s in zip(eag.fips_code, eag.county, eag.state_abbr):
        lookup.setdefault(f"{s}|{norm_county(c)}", f)

    rec_rows, named, matched_names, state_ok, state_total = [], 0, 0, 0, 0
    for idx, area in zip(df.index, df["Area Affected"]):
        parsed = parse_area(area)
        fips, states = set(), set()
        for st, counties in parsed:
            state_total += 1
            abbr = name_to_abbr.get(st.lower())
            if abbr:
                state_ok += 1
                states.add(abbr)
            for c in counties:
                named += 1
                key = f"{abbr}|{norm_county(c)}"
                if abbr and key in lookup:
                    matched_names += 1
                    fips.add(lookup[key])
        rec_rows.append((idx, sorted(fips), sorted(states), len(parsed) > 0,
                         any(cs for _, cs in parsed)))
    loc = pd.DataFrame(rec_rows, columns=["idx", "fips", "states", "has_state", "has_county"]).set_index("idx")
    df = df.join(loc)

    md += ["## 4. DOE OE-417 electric emergency incident and disturbance reports", "",
           "Files: `data/raw/oe417/<year>/OE417_<year>.xls` (legacy Excel, read with xlrd). 2022 and 2023 "
           "come from Internet Archive copies of the official download URLs (`OE417_<year>.source.txt` "
           "records each). **2024 is missing:** the official host is IPv6-only and unreachable from this "
           "network, and no archived copy exists; `scripts/download_oe417.py` prints the manual steps.", ""]
    cols = [c for c in df.columns if c not in ("file_year", "begin", "restored", "fips", "states", "has_state", "has_county")]
    md += ["### Columns, rows and nulls", ""]
    nn = [(c, int((df[c].fillna("").astype(str).str.strip() == "").sum()),
           int(df[c].fillna("").astype(str).str.strip().str.lower().isin(["unknown", "ongoing", "n/a"]).sum())) for c in cols]
    md.append(table(pd.DataFrame(nn, columns=["column", "empty", "unknown_or_ongoing"])))
    md.append("")
    by_year = df.groupby("file_year").agg(rows=("begin", "size"), first=("begin", "min"), last=("begin", "max"),
                                          restoration_missing=("restored", lambda s: int(s.isna().sum()))).reset_index()
    by_year["first"] = by_year["first"].dt.strftime("%Y-%m-%d")
    by_year["last"] = by_year["last"].dt.strftime("%Y-%m-%d")
    md.append(table(by_year.rename(columns={"file_year": "year"}).astype({"year": str})))
    md.append("")
    cust = pd.to_numeric(df["Number of Customers Affected"], errors="coerce")
    md += [f"`Number of Customers Affected` is numeric in {int(cust.notna().sum())} of {len(df)} rows; "
           f"{int((cust == 0).sum())} are 0. `Demand Loss (MW)` is numeric in "
           f"{int(pd.to_numeric(df['Demand Loss (MW)'], errors='coerce').notna().sum())} rows.", ""]
    et = df["Event Type"].str.replace(r"^[\s\-]+", "", regex=True).str.strip()
    md += ["Event type text is not standardized (leading dashes, several types joined). Top values:", ""]
    md.append(table(et.value_counts().head(10).rename_axis("event_type").reset_index(name="rows")))
    md.append("")

    md += ["### Time zone handling", "",
           "Dates are stored as text (`mm/dd/yyyy`) and times as Excel time cells. The file states no time "
           "zone. The estimate below compares OE-417 begin times, read as if UTC, with EAGLE-I event starts "
           "(UTC) in the same counties.", ""]
    md += ["### Location coding", "",
           "`Area Affected` is free text: `State: County, County;` repeated, often just `State:` with no "
           "county, sometimes several states. No FIPS codes. Parsed here with a regex and matched to EAGLE-I "
           "county names after normalization (lowercase, no 'County'/'Parish' suffix, 'St.' = 'Saint').", "",
           "| Measure | Value |", "|---|---|",
           f"| Rows with at least one state | {int(df.has_state.sum())} of {len(df)} ({pct(int(df.has_state.sum()), len(df))}) |",
           f"| Rows naming at least one county | {int(df.has_county.sum())} of {len(df)} ({pct(int(df.has_county.sum()), len(df))}) |",
           f"| State names recognized | {state_ok} of {state_total} ({pct(state_ok, state_total)}) |",
           f"| County names matched to an EAGLE-I county | {matched_names} of {named} ({pct(matched_names, named)}) |",
           f"| Rows with at least one matched county | {int((df.fips.str.len() > 0).sum())} of {len(df)} |", ""]

    # Event-level match
    ev = con.execute("SELECT fips_code, event_start, event_end, customer_hours_lost FROM gold_outage_events").fetchdf()
    ev_by_fips = {f: g for f, g in ev.groupby("fips_code")}
    st_of = dict(zip(eag.fips_code, eag.state_abbr))
    ev["state"] = ev.fips_code.map(st_of)
    ev_by_state = {s: g for s, g in ev.groupby("state")}
    res, offsets = [], []
    for r in df.itertuples():
        if r.begin is None or pd.isna(r.begin):
            res.append(("no date", False))
            continue
        lo = r.begin - timedelta(days=1)
        hi = (r.restored if r.restored is not None and not pd.isna(r.restored) else r.begin) + timedelta(days=1)
        if r.fips:
            g = pd.concat([ev_by_fips[f] for f in r.fips if f in ev_by_fips]) if any(f in ev_by_fips for f in r.fips) else ev.iloc[0:0]
            level = "county"
            near = g[(g.event_start - r.begin).abs() <= pd.Timedelta(hours=12)]
            offsets += [((s - r.begin).total_seconds() / 3600) for s in near.event_start]
        elif r.states:
            g = pd.concat([ev_by_state[s] for s in r.states if s in ev_by_state]) if any(s in ev_by_state for s in r.states) else ev.iloc[0:0]
            level = "state only"
        else:
            res.append(("no location", False))
            continue
        hit = bool(((g.event_start <= hi) & (g.event_end >= lo)).any())
        res.append((level, hit))
    m = pd.DataFrame(res, columns=["level", "hit"])
    cust_n = pd.to_numeric(df["Number of Customers Affected"], errors="coerce")
    m["customers_affected"] = pd.cut(cust_n.values, [-1, 0, 999, 9_999, float("inf")],
                                     labels=["0", "1-999", "1,000-9,999", "10,000+"]).astype(str)
    m.loc[cust_n.isna().values, "customers_affected"] = "unknown"
    by_cust = (m[m.level == "county"].groupby("customers_affected")
               .agg(rows=("hit", "size"), with_eaglei_event=("hit", "sum")).reset_index())
    by_cust["match_rate"] = [pct(a, b) for a, b in zip(by_cust.with_eaglei_event, by_cust.rows)]
    lvl = m.groupby("level").agg(rows=("hit", "size"), with_eaglei_event=("hit", "sum")).reset_index()
    lvl["match_rate"] = [pct(a, b) for a, b in zip(lvl.with_eaglei_event, lvl.rows)]
    md += ["### Event-level match to EAGLE-I outage events", "",
           "A row matches when an EAGLE-I event in its matched counties (or, with no county, anywhere in its "
           "states) overlaps [begin date - 1 day, restoration date + 1 day]. Day-level windows because the "
           "OE-417 time zone is not stated. State-only matches are weak: large states have EAGLE-I events "
           "almost every day.", ""]
    md.append(table(lvl))
    md += ["", "County-level rows by customers affected (incidents with no customer impact, such as "
               "vandalism or suspicious activity, are not expected to appear in EAGLE-I):", ""]
    md.append(table(by_cust))
    md.append("")
    off = pd.Series(offsets).round()
    if len(off):
        dist = off.value_counts().sort_index()
        md += [f"EAGLE-I start minus OE-417 begin (read as UTC), county-level rows, events within 12 h: "
               f"{len(off)} pairs, median {off.median():+.0f} h. Most common offsets:", ""]
        md.append(table(dist.sort_values(ascending=False).head(6).rename_axis("hours").reset_index(name="pairs")))
        md.append("")
    return {"df": df, "lvl": lvl, "by_cust": by_cust, "named": (matched_names, named), "offset": off.median() if len(off) else None,
            "county_rows": int(df.has_county.sum())}


# -----------------------------------------------------------------------------

def main() -> None:
    con = duckdb.connect()
    build_eaglei(con)
    print("Loading sources ...", flush=True)
    load_noaa(con)
    zv = load_zones(con)
    resolve_noaa(con)
    load_eia(con)

    md: list[str] = [
        "# Data Profile: Storm, Zone, Reliability and Disturbance Sources", "",
        f"Profiled on {date.today().isoformat()} with DuckDB {duckdb.__version__} using "
        "`scripts/profile_sources.py`. Raw files are read only. Join rates are measured against EAGLE-I "
        "Silver and Gold rebuilt in DuckDB with the final rules (D1-D20, 0.25% event threshold): "
        f"{con.execute('SELECT COUNT(*) FROM eaglei_counties').fetchone()[0]:,} counties, "
        f"{con.execute('SELECT COUNT(*) FROM gold_outage_events').fetchone()[0]:,} outage events.", "",
    ]
    print("Profiling NOAA ...", flush=True)
    noaa = profile_noaa(con, md, zv)
    print("Profiling zones ...", flush=True)
    profile_zones(con, md, zv)
    print("Profiling EIA-861 ...", flush=True)
    eia = profile_eia(con, md)
    print("Profiling OE-417 ...", flush=True)
    oe = profile_oe417(con, md)

    md += ["## 5. How each source joins to EAGLE-I", "",
           "| Source | Grain | Location key | Time | Join to EAGLE-I | Measured |", "|---|---|---|---|---|---|",
           f"| NOAA, CZ_TYPE C | event x county | county FIPS (STATE_FIPS + CZ_FIPS) | local standard, offset in CZ_TIMEZONE | county FIPS + UTC time overlap | {pct(*noaa['c'])} of C events resolve |",
           f"| NOAA, CZ_TYPE Z | event x zone | state + zone via NWS file in effect | same | zone -> counties (1:n), then as above | {pct(*noaa['z'])} of Z events resolve |",
           "| NWS zone-county | zone x county x version | STATE + ZONE -> FIPS | effective dates per file | bridge only | see section 2 |",
           f"| EIA-861 reliability / sales | utility x state x year | state code; utility number | annual | state level only | EAGLE-I / EIA customers {eia['sales_ratio'][0] / eia['sales_ratio'][1]:.3f} |",
           f"| EIA-861 service territory | utility x county name x year | state + county name | annual | needs name -> FIPS crosswalk | {eia['terr'][-1][5]} of 2024 pairs match |",
           f"| OE-417 | incident | free-text state and county names | local?, not stated | parsed names -> FIPS, day-level overlap | {pct(*oe['named'])} of named counties match |",
           ""]
    OUT.write_text("\n".join(md))
    print(f"Wrote {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
