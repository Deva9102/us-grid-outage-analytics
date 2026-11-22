# Test fixture

A small sample of real rows from every source the pipeline reads (about 390 KB). The fast pytest
suite runs the real SQL in `sql/databricks/` against it in DuckDB (`scripts/duckdb_pipeline.py`)
and checks exact expected results. Every row is copied unchanged from the raw downloads by
`scripts/build_test_fixture.py` (`make fixture`); nothing is edited or invented. Rules that real
data never exercises (duplicate keys, unparseable rows, storm-window edges) are tested with
synthetic rows inside the tests, never in these files. Design and selection: `docs/decisions.md` D51.

## What is in it

| Folder | Source | Rows | Why these rows |
|---|---|---|---|
| `eaglei/<year>/` | EAGLE-I county outages | 624 / 195 / 3,965 | 13 counties in 5 windows (below), plus one reading each for Kalawao HI and Norton city VA |
| `eaglei/metadata/MCC.csv` | EAGLE-I modeled customer counts | 14 | the fixture counties and the Grand Total row (D5) |
| `noaa_storm_events/<year>/` | NOAA Storm Events details | 51 events | storms whose match window overlaps a fixture window in a fixture county, plus one water-area event (one hail event is skipped because its narrative trips the repository word scan) |
| `nws_zone_county/<year>/` | NWS zone-county correlation files | 261 | the zones of those storms, in all six file versions |
| `eia861/<year>/` | EIA-861 Sales, Reliability, Service Territory (raw rows) | 6 to 483 per file | Sales for HI, UT, MA, TX, CA and VA 2024; Reliability for HI, UT and MA 2024 and the utilities behind the D39 and National Grid checks |
| `oe417/<year>/` | DOE OE-417 annual summaries (raw rows) | 8 | header rows and four incidents: matched, not matched, no county, no time |
| `expected_rows.yml` | | | row count of every table built from the fixture |

Reference lookups (`state_regions.csv` and the others) are read from `data/reference/`.

Counties: Harris and Fort Bend TX, Los Angeles CA, all five Hawaii counties, and Salt Lake, Utah,
Davis, Weber and Rich UT.

| Window (UTC) | What it covers |
|---|---|
| 2022-10-25 00:00 to 20:00 | Harris event matched by an OE-417 incident (D40); Thunderstorm Wind attribution (D37) |
| 2023-03-22 18:00 to 24:00 | the off-grid 20:31 run floored to 20:30 (D7) |
| 2024-05-23 18:00 to 05-24 12:00 | the 9-hour nationwide feed gap, 00:15 to 09:00 (D3, D10) |
| 2024-06-15 20:00 to 06-16 03:00 | Rich UT readings above its customer count (D4, D45 footnote) |
| 2024-07-08 00:00 to 07-12 00:00 | Hurricane Beryl: the Harris and Fort Bend feed dropouts (D19), Harris overcount (D4), Kauai's peak that sets its D35 floor |

Harris reports in every collected 15-minute slot of every window, so the only empty slots inside a
window are real nationwide feed gaps. All Hawaii counties are present, so Hawaii's D21 calibration
and Kauai's D35 floor are exactly the full-data values. Utah's five counties hold 75% of EIA
customers, so Utah is ranked (D22); Texas and California are not.

Values that depend on the whole dataset differ from the full pipeline and are fixture-only: event
IDs (numbered per county), events cut at a window edge, state coverage of TX and CA, and ranks.

File formats follow the volume layout used on Databricks, except that Parquet and gzipped CSV
uploads are stored here as plain CSV (every column as text, as in Bronze).

## Sources and credits

- **EAGLE-I county outages and MCC** — Oak Ridge National Laboratory, Environment for Analysis of
  Geo-Located Energy Information (EAGLE-I), U.S. Department of Energy. Brelsford, C., Tennille, S.,
  Myers, A., et al., "A dataset of recorded electricity outages by United States county 2014–2022",
  with the 2023 and 2024 releases, figshare, https://doi.org/10.6084/m9.figshare.24237376.v4.
  Licensed under Creative Commons Attribution 4.0 (CC BY 4.0,
  https://creativecommons.org/licenses/by/4.0/). The rows here are an unmodified subset.
- **NOAA Storm Events Database** — NOAA National Centers for Environmental Information,
  https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/ (U.S. Government work, public domain).
- **NWS zone-county correlation files** — NOAA National Weather Service,
  https://www.weather.gov/gis/ZoneCounty (U.S. Government work, public domain).
- **EIA Form 861** — U.S. Energy Information Administration, https://www.eia.gov/electricity/data/eia861/
  (U.S. Government work, public domain).
- **DOE OE-417 Electric Emergency and Disturbance Reports** — U.S. Department of Energy, Office of
  Cybersecurity, Energy Security, and Emergency Response,
  https://www.oe.netl.doe.gov/OE417_annual_summary.aspx (U.S. Government work, public domain).
