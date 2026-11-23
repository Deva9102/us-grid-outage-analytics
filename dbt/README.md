# dbt star schema

The marts for Power BI and the later Snowflake copy, built on the pipeline's Gold tables (D66 in
`docs/decisions.md`). They reshape Gold without recomputing any metric; every rule stays in
`sql/databricks/`.

| Model | Grain |
|---|---|
| `fct_outage_events` | one county outage event, with its storm, flags and per-1,000 values |
| `fct_county_reliability` | county and year, 50 states and DC, ranked, with footnote reasons |
| `fct_state_reliability` | state and year, 50 states and DC, ranked, with footnote reasons |
| `fct_territory_reliability` | Puerto Rico or the US Virgin Islands and year, unranked |
| `fct_utility_reliability` | EIA-861 utility, state and year; IEEE 1366 ranked, other standards apart |
| `dim_county`, `dim_state`, `dim_date`, `dim_storm_type`, `dim_utility` | one row per member |

An event counts in the year it starts (UTC), also when it runs into the next year.

## Running it

dbt has its own uv environment here, because dbt-databricks needs an older `databricks-sdk` than
the pipeline (D65, D66). From the repository root:

```
make dbt-test-local   # pipeline on tests/fixtures/ into build/duckdb/fixture.duckdb, dbt build, check
make dbt-build        # dbt build on Databricks (workspace.outages), then the same check
make dbt-docs         # docs for the fixture build
```

Or from `dbt/`: `uv run python run_dbt.py <command> --target duckdb|databricks|snowflake`.
`run_dbt.py` loads `../.env` and creates `profiles.yml` from `profiles.yml.example` on first use.
Credentials are only read from the environment. For the full data locally, build it with
`uv run python scripts/build_duckdb.py --root data/raw --out build/duckdb/full.duckdb` and set
`DBT_DUCKDB_PATH=../build/duckdb/full.duckdb`. The `snowflake` target is a placeholder until the
warehouse copy is built.
