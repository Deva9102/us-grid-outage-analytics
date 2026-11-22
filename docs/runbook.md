# Runbook: the Databricks Job

How I deploy and operate the pipeline as a Databricks Job (decision D54). The job is defined in
`databricks.yml` (a Databricks Asset Bundle) and runs on my SQL warehouse in Databricks Free
Edition. `make pipeline` (D49) remains the full local runner: it also converts and uploads the
raw files, which the job expects to find in the volume already.

## The job

`us_grid_outage_pipeline` runs ten SQL tasks in a chain. Each task waits for the one before it and
retries once after a minute.

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

Starts the job, waits and prints each task's result and duration with the run's URL. The same
run can be started from the Jobs UI with **Run now**. Afterwards I confirm the results with

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
rebuilds its tables with `CREATE OR REPLACE` / `INSERT OVERWRITE`, so re-running is safe.

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

   `quality_gate_staging` holds all checks of the most recent gate.
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
