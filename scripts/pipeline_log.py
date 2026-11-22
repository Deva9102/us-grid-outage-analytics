"""Step logging for the pipeline runners (D49).

Each run writes logs/<name>_<YYYYmmdd_HHMMSS>.log (logs/ is gitignored) with one line per step:
start time, duration, row count and status. summary() prints the same as a table at the end.
Nothing secret is logged: callers log step names, table names and counts only.

Usage:
    log = RunLog("pipeline")
    with log.step("sql 02_silver.sql") as s:
        ...
        s.rows = 79_598_850
    log.summary()
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "logs"


@dataclass
class Step:
    name: str
    started: datetime
    seconds: float = 0.0
    rows: int | None = None
    status: str = "running"
    note: str = ""


class RunLog:
    def __init__(self, name: str) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        self.started = datetime.now(UTC)
        self.path = LOG_DIR / f"{name}_{self.started:%Y%m%d_%H%M%S}.log"
        self.steps: list[Step] = []
        self.logger = logging.getLogger(f"pipeline.{name}.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        handler = logging.FileHandler(self.path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S%z"))
        self.logger.addHandler(handler)
        self.logger.info("run %s started", name)

    def info(self, message: str, *args) -> None:
        self.logger.info(message, *args)

    @contextmanager
    def step(self, name: str):
        s = Step(name=name, started=datetime.now(UTC))
        self.steps.append(s)
        self.logger.info("step start  %s", name)
        t0 = time.perf_counter()
        try:
            yield s
            s.status = "ok"
        except BaseException as e:
            s.status = "FAILED"
            s.note = str(e).splitlines()[0][:120] if str(e) else type(e).__name__
            raise
        finally:
            s.seconds = time.perf_counter() - t0
            rows = "" if s.rows is None else f" rows={s.rows}"
            self.logger.info("step end    %s status=%s duration=%.1fs%s %s", name, s.status, s.seconds, rows, s.note)

    def table(self) -> str:
        head = f"{'step':<40} {'start (UTC)':<20} {'duration':>9} {'rows':>14}  status"
        lines = [head, "-" * len(head)]
        for s in self.steps:
            rows = "" if s.rows is None else f"{s.rows:,}"
            lines.append(f"{s.name[:40]:<40} {s.started:%Y-%m-%d %H:%M:%S}  {fmt_seconds(s.seconds):>9} {rows:>14}  {s.status}")
        total = sum(s.seconds for s in self.steps)
        lines.append(f"{'total':<40} {'':<20} {fmt_seconds(total):>9}")
        return "\n".join(lines)

    def summary(self) -> None:
        text = self.table()
        self.logger.info("summary\n%s", text)
        print("\n" + text)
        print(f"Log: {self.path.relative_to(REPO_ROOT)}")


def fmt_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}m{s:02d}s" if m < 60 else f"{m // 60}h{m % 60:02d}m"
