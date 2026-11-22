"""Run the deployed Databricks Job once, or repair a failed run, and print each task (D54).

Finds the job by its name in databricks.yml, starts it (or repairs a run), waits until it ends
and prints the state and duration of every task attempt. Credentials come from .env.

Usage:
    uv run python scripts/job_run.py                         # run the whole job
    uv run python scripts/job_run.py --repair RUN_ID         # re-run the failed tasks of a run
    uv run python scripts/job_run.py --repair RUN_ID --task silver_gate   # re-run one task
"""

from __future__ import annotations

import argparse
import sys
import time

import yaml
from databricks.sdk.service.jobs import RunLifeCycleState

from run_databricks import REPO_ROOT, Stop, connect

JOB_KEY = "outage_pipeline"


def job_id(w) -> int:
    bundle = yaml.safe_load((REPO_ROOT / "databricks.yml").read_text())
    name = bundle["resources"]["jobs"][JOB_KEY]["name"]
    jobs = [j for j in w.jobs.list(name=name)]
    if len(jobs) != 1:
        raise Stop(f"expected one job named {name}, found {len(jobs)}; run make job-deploy")
    return jobs[0].job_id


def wait(w, run_id: int):
    last = None
    while True:
        run = w.jobs.get_run(run_id)
        state = run.state.life_cycle_state
        if state != last:
            print(f"  run {run_id}: {state.value}", flush=True)
            last = state
        if state in (RunLifeCycleState.TERMINATED, RunLifeCycleState.SKIPPED,
                     RunLifeCycleState.INTERNAL_ERROR):
            return run
        time.sleep(15)


def report(run) -> bool:
    print(f"\nRun {run.run_id}: {run.state.result_state.value if run.state.result_state else run.state.life_cycle_state.value}"
          f"  ({(run.end_time - run.start_time) / 1000:.0f}s)  {run.run_page_url}")
    print(f"  {'task':<24} {'attempt':>7} {'result':<10} {'duration':>9}")
    for t in sorted(run.tasks or [], key=lambda t: (t.start_time or 0, t.attempt_number or 0)):
        result = t.state.result_state.value if t.state and t.state.result_state else t.state.life_cycle_state.value
        secs = ((t.end_time or 0) - (t.start_time or 0)) / 1000 if t.start_time else 0
        print(f"  {t.task_key:<24} {t.attempt_number or 0:>7} {result:<10} {secs:>8.0f}s")
        if t.state and t.state.state_message and result not in ("SUCCESS",):
            print(f"      {t.state.state_message[:300]}")
    return bool(run.state.result_state and run.state.result_state.value == "SUCCESS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repair", type=int, metavar="RUN_ID", help="repair this run instead of starting one")
    parser.add_argument("--task", action="append", help="with --repair: task key to re-run (repeatable)")
    args = parser.parse_args()
    try:
        w, _ = connect()
        if args.repair:
            if args.task:
                w.jobs.repair_run(args.repair, rerun_tasks=args.task, rerun_dependent_tasks=True)
            else:
                w.jobs.repair_run(args.repair, rerun_all_failed_tasks=True)
            run_id = args.repair
        else:
            run_id = w.jobs.run_now(job_id(w)).run_id
        return 0 if report(wait(w, run_id)) else 1
    except Stop as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
