# Runbook: the Databricks Job

How I deploy and operate the pipeline as a Databricks Job (decision D54). The job is defined in
`databricks.yml` (a Databricks Asset Bundle) and runs on my SQL warehouse in Databricks Free
Edition. `make pipeline` (D49) remains the full local runner: it also converts and uploads the
raw files.

**The job assumes the raw files are already in the volume** `/Volumes/workspace/outages/raw/`. It
never downloads, converts or uploads anything. Before the first run, and after adding a year or
refreshing a source, I upload them with `make pipeline` (or only its convert and upload steps,
below). A missing file fails the `bronze` task.

## The job

`us_grid_outage_pipeline` runs ten SQL tasks in a chain. Each task waits for the one before it.
The five build tasks retry once after a minute (a warehouse hiccup); the five gate tasks never
retry, because a failed check is a finding about the data, and rerunning the same check on the
same tables gives the same answer (D55).

```
bronze -> bronze_gate -> silver -> silver_gate -> gold_events -> gold_events_gate
       -> gold_storm_match -> gold_storm_match_gate -> gold_reliability -> gold_reliability_gate
```

| Task | Runs |
|---|---|
| `bronze` | `01_bronze.sql`, `01_bronze_sources.sql` |
| `silver` | `02_silver_sources.sql`, `02_silver.sql` |
| `gold_events` | `03_gold_events.sql`, `03_gold_coverage.sql` |
| `gold_storm_match` | `03_gold_storm_match.sql` |
| `gold_reliability` | `03_gold_reliability.sql`, `03_gold_oe417_check.sql` |
| `*_gate` | exact row counts of the tables the task built, then its share of `90_quality_checks.sql` |

The task SQL lives in `build/databricks/` (gitignored). `scripts/render_job_sql.py` renders it from
`sql/databricks/` and `config/pipeline.yml`, the same way `make pipeline` does. I never edit
`build/` by hand: I change the source SQL or the config and deploy again.

## One-time setup

1. `.env` holds `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH` and `DATABRICKS_TOKEN` (see
   `.env.example`). The warehouse id is taken from `DATABRICKS_HTTP_PATH`.
2. `make cli` installs the pinned Databricks CLI into `.tools/bin/databricks` (checksum verified,
   nothing installed globally). `scripts/databricks_cli.py` runs it with the `.env` credentials as
   environment variables; no `~/.databrickscfg` is used.
3. The warehouse session time zone must be UTC (D1). Each task file also sets it.
4. The raw files must be in `/Volumes/workspace/outages/raw/`:
   `uv run python scripts/run_databricks.py --steps check,convert,upload`.

## Incremental loading (D56, D57)

The job loads only the EAGLE-I years in `incremental.load_years` of `config/pipeline.yml`
(currently `[2025]`): it rebuilds those Bronze tables and replaces those Silver partitions
(`INSERT INTO silver_outages REPLACE WHERE year IN (...)`), and leaves every other year untouched.
Gold events are rebuilt from 7 days (`incremental.lookback_days`) before the first new reading, and
from the start of any event still open then, so an outage running across New Year stays one
event. The tables downstream of the events are small and are rebuilt in full.

To add a year: download it, add its Bronze statement in `01_bronze.sql`, its branches in
`02_silver.sql` and `02_silver_sources.sql` and its row count in `90_quality_checks.sql`, add it to
`years` and set `load_years` to it, update `quality.expected_rows` after a DuckDB build, upload,
deploy and run. The denominators stay on `denominator.base_years` (D58). For a full rebuild, list
every year in `load_years` (or run `uv run python scripts/run_databricks.py --full`).

## New columns on existing tables (D64)

The incremental tables are created once, so a column added to their `CREATE TABLE IF NOT EXISTS`
reaches a new deployment but not the table already in `workspace.outages`. Such columns are listed
in `scripts/schema_migrations.py` with the value the existing rows get. `make migrate` (also run
by `make job-run` and by `make pipeline`) adds whatever is missing with `ALTER TABLE ... ADD
COLUMNS` and fills it; it does nothing when every column is there. It is the only ALTER the runner
sends, and only for the exact statements that file generates.

## Deploy

```
make job-deploy
```

Renders `build/databricks/`, validates the bundle and deploys it. It creates or updates the job
and uploads the ten SQL files to my workspace under `.bundle/us_grid_outage_analytics/dev/`.
Deploy again after any change to `sql/databricks/`, `config/pipeline.yml` or `databricks.yml`;
the job always runs the files from the last deploy.

Any CLI command works through the wrapper, for example:

```
uv run python scripts/databricks_cli.py bundle summary
```

## Run

```
make job-run
```

Adds any missing columns (`make migrate`), then starts the job, waits and prints each task's result
and duration with the run's URL. The same run can be started from the Jobs UI with **Run now**.
Afterwards I confirm the results with

```
uv run python scripts/run_databricks.py --steps verify
```

which compares every table's row count, the detail checks and the top 10 events with the
expected values.

## Re-run a failed task

A failed task skips every task after it. Once the cause is fixed (and redeployed, if the fix
changed the SQL or the config):

```
uv run python scripts/job_run.py --repair <run_id>                  # re-run every failed task
uv run python scripts/job_run.py --repair <run_id> --task silver    # re-run one task
```

A repair re-runs the chosen tasks and the tasks that depend on them, in the same run, and keeps
the successful tasks before them. In the UI: open the run and choose **Repair run**. Every task
rebuilds its tables with `CREATE OR REPLACE`, `INSERT OVERWRITE` or a partition `REPLACE WHERE`,
and the Gold reprocess window is computed from the events the last run wrote, so re-running is
safe and gives the same rows.

## When a quality gate fails

A gate task fails with `Quality gate <task> failed: N check(s), first: <check name>`. Nothing
after it has run, so the tables downstream still hold the last good build. Then:

1. See every failed check of the run:

   ```sql
   SELECT layer, check_name, observed, expected
   FROM workspace.outages.gold_quality_results
   WHERE NOT passed
     AND run_ts >= current_timestamp() - INTERVAL 1 DAY
   ORDER BY run_ts DESC
   ```

   `quality_gate_staging` holds all checks of the most recent gate. Results are kept for
   `quality.results_retention_days` (90) days: every gate deletes older rows at its end (D55).
2. Decide which kind of failure it is:
   - **Row count** (`row count: <table>` or `task row count: <table>`): the expected counts are a
     contract (D50). A changed count means a source file, the SQL or the config changed. Find
     which; if the change is intended and reviewed, record it in `docs/decisions.md`, update
     `quality.expected_rows` in `config/pipeline.yml` and `tests/fixtures/expected_rows.yml` if
     affected, and redeploy.
   - **Rule check** (duplicates, nulls, thresholds, ranking): a real data problem or a SQL bug.
     Reproduce it locally with `make test` and `make quality ENGINE=duckdb`, fix the SQL, and log
     the fix as a decision.
   - **Missing table or input**: usually the raw files are not in the volume or a previous task
     did not finish; upload them or repair from the earlier task.
3. Redeploy if anything changed, then repair the run from the task that built the bad table
   (not just the gate), so the gate checks fresh data.

I never loosen a check or edit an expected value only to make a gate pass.

## Schedule

The job has a daily schedule at 06:00 UTC that is **PAUSED** to protect the Free Edition quota.
To enable it, set `pause_status: UNPAUSED` in `databricks.yml` and run `make job-deploy`; set it
back to `PAUSED` and redeploy to stop it. (Resuming it in the Jobs UI also works, but the next
deploy pauses it again.)

## Failure emails

`databricks.yml` has a commented `email_notifications.on_failure` example. To use it, uncomment
it, put in my address and redeploy.

## Remove the job

`uv run python scripts/databricks_cli.py bundle destroy` deletes the job and the uploaded SQL
files. It does not touch any table in `workspace.outages`.
