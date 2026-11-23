"""Load config/pipeline.yml and substitute its values into SQL (D47).

SQL files reference configuration values as ${section.key}. render() replaces each placeholder
with its value formatted as a SQL literal: numbers as written, strings as is, lists of strings
as a quoted comma-separated list. A placeholder that has no value stops the run.

Derived values (not set in the file) are added by derive(): the volume path, the first and
last year, the gap rule in 15-minute runs, percentage labels for comments, band labels, and
whether the incremental load years cover every year (a full rebuild).

Usage from other scripts:
    import pipeline_config
    cfg = pipeline_config.load()
    sql = pipeline_config.render(text)
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "pipeline.yml"

# EAGLE-I reports in fixed 15-minute collection runs. This is a property of the source, not a
# tunable, so it is a named constant here and not a config value (D47).
RUN_MINUTES = 15

PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][\w.]*)\}")


class ConfigError(Exception):
    """The configuration file is missing a value or holds an invalid one."""


def _require(cfg: dict, path: str) -> Any:
    node: Any = cfg
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"{CONFIG_PATH.name}: missing {path}")
        node = node[part]
    return node


def _pct(share: float) -> str:
    return f"{share * 100:g}"


def _sql_list(values: list) -> str:
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


def validate(cfg: dict) -> None:
    """Check types and ranges so a typo fails before any SQL runs."""
    def number(path: str, lo: float | None = None, hi: float | None = None, lo_open: bool = False) -> float:
        v = _require(cfg, path)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigError(f"{path} must be a number, got {v!r}")
        if lo is not None and (v <= lo if lo_open else v < lo):
            raise ConfigError(f"{path} = {v} is below its allowed range")
        if hi is not None and v > hi:
            raise ConfigError(f"{path} = {v} is above its allowed range")
        return v

    for key in ("catalog", "schema", "volume"):
        if not re.fullmatch(r"[A-Za-z_]\w*", str(_require(cfg, f"project.{key}"))):
            raise ConfigError(f"project.{key} must be a plain identifier")
    years = _require(cfg, "years")
    if not years or any(not isinstance(y, int) for y in years) or sorted(set(years)) != years:
        raise ConfigError("years must be a sorted list of distinct integers")
    load_years = _require(cfg, "incremental.load_years")
    if (not load_years or any(not isinstance(y, int) for y in load_years)
            or sorted(set(load_years)) != load_years or not set(load_years) <= set(years)):
        raise ConfigError("incremental.load_years must be a sorted, non-empty subset of years")
    lookback = number("incremental.lookback_days", 1)
    if not isinstance(lookback, int):
        raise ConfigError("incremental.lookback_days must be a whole number of days")
    number("denominator.mismatch_ratio", 1, lo_open=True)
    base = _require(cfg, "denominator.base_years")
    if not base or not set(base) <= set(years) or sorted(set(base)) != base:
        raise ConfigError("denominator.base_years must be a sorted, non-empty subset of years")
    number("calibration.eia_year", 2000)
    number("calibration.state_ratio", 1, lo_open=True)
    number("calibration.peak_skip_ratio", 1, lo_open=True)
    number("events.threshold_share", 0, 1, lo_open=True)
    number("events.min_customers_out", 1)
    gap = number("events.max_gap_hours", 0, lo_open=True)
    if (gap * 60) % RUN_MINUTES:
        raise ConfigError(f"events.max_gap_hours must be a multiple of {RUN_MINUTES} minutes")
    number("events.large_outage_customers", _require(cfg, "events.min_customers_out"), lo_open=True)
    number("dropouts.drop_below_share", 0, 1, lo_open=True)
    number("dropouts.recovery_share", 0, 1, lo_open=True)
    runs = number("dropouts.recovery_max_runs", 1, 5)
    if not isinstance(runs, int):
        raise ConfigError("dropouts.recovery_max_runs must be an integer from 1 to 5")
    number("coverage.min_customer_coverage", 0, 1)
    number("ranking.min_customers", 0)
    number("ranking.ranked_jurisdictions", 1)
    number("ranking.max_share_without_denominator", 0, 1)
    number("storm_match.window_before_hours", 0)
    number("storm_match.window_after_hours", 0)
    number("oe417_check.start_window_hours", 0, lo_open=True)
    edges = _require(cfg, "oe417_check.band_edges")
    if len(edges) != 2 or not edges[0] < edges[1]:
        raise ConfigError("oe417_check.band_edges must be two increasing numbers")
    number("footnotes.capped_share", 0, 1)
    number("footnotes.peak_to_customers", 1)
    for key in ("min_county_customers_out", "min_readings", "min_events", "min_readings_per_event",
                "min_neighbour_size_ratio"):
        number(f"exclusions.{key}", 1)
    number("exclusions.max_cv_between_events", 0, lo_open=True)
    bands = _require(cfg, "utilities.size_band_edges")
    if len(bands) != 3 or sorted(bands) != bands:
        raise ConfigError("utilities.size_band_edges must be three increasing numbers")
    number("utilities.source_error_customer_share", 0, 1, lo_open=True)
    for key in ("eversource_ids", "national_grid_ids"):
        if not all(isinstance(v, str) for v in _require(cfg, f"utilities.{key}")):
            raise ConfigError(f"utilities.{key} must be quoted strings (EIA utility numbers)")
    number("quality.row_count_tolerance", 0, 1)
    number("export.max_file_mb", 1)
    if not _require(cfg, "export.tables"):
        raise ConfigError("export.tables must list at least one table")
    number("quality.float_tolerance", 0, 1)
    if not isinstance(number("quality.results_retention_days", 1), int):
        raise ConfigError("quality.results_retention_days must be a whole number of days")
    if not all(isinstance(v, int) and v >= 0 for v in _require(cfg, "quality.expected_rows").values()):
        raise ConfigError("quality.expected_rows must map table names to non-negative integers")


def derive(cfg: dict) -> dict:
    """Add the derived values that SQL comments and statements reference."""
    p, e, d = cfg["project"], cfg["events"], cfg["dropouts"]
    p["volume_path"] = f"/Volumes/{p['catalog']}/{p['schema']}/{p['volume']}"
    years = cfg["years"]
    cfg["years"] = {"list": years, "first": years[0], "last": years[-1], "sql": ", ".join(map(str, years))}
    inc = cfg["incremental"]
    inc["full_rebuild"] = inc["load_years"] == years
    e["max_gap_runs"] = int(e["max_gap_hours"] * 60 // RUN_MINUTES)
    d["drop_below_pct"] = _pct(d["drop_below_share"])
    d["recovery_pct"] = _pct(d["recovery_share"])
    d["recovery_max_minutes"] = d["recovery_max_runs"] * RUN_MINUTES
    cov = cfg["coverage"]
    cov["min_customer_coverage_pct"] = _pct(cov["min_customer_coverage"])
    r = cfg["ranking"]
    r["min_customers_label"] = f"{r['min_customers']:,}"
    r["max_share_without_denominator_pct"] = _pct(r["max_share_without_denominator"])
    o = cfg["oe417_check"]
    lo, hi = o["band_edges"]
    o["band_low"], o["band_high"] = lo, hi
    o["band_low_label"] = f"1-{lo - 1:,}"
    o["band_mid_label"] = f"{lo:,}-{hi - 1:,}"
    o["band_high_label"] = f"{hi:,}+"
    f = cfg["footnotes"]
    f["capped_share_pct"] = _pct(f["capped_share"])
    f["peak_to_customers_label"] = f"{f['peak_to_customers']:g}"
    u = cfg["utilities"]
    u["size_band_small"], u["size_band_medium"], u["size_band_large"] = u["size_band_edges"]
    u["eversource_ids_sql"] = _sql_list(u["eversource_ids"])
    u["national_grid_ids_sql"] = _sql_list(u["national_grid_ids"])
    return cfg


@lru_cache(maxsize=1)
def _load_cached() -> dict:
    if not CONFIG_PATH.exists():
        raise ConfigError(f"Missing {CONFIG_PATH.relative_to(REPO_ROOT)}")
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    validate(cfg)
    return derive(cfg)


def load() -> dict:
    """The validated configuration with derived values. Callers must not modify it."""
    return _load_cached()


def get(path: str, overrides: dict[str, Any] | None = None) -> Any:
    if overrides and path in overrides:
        return overrides[path]
    return _require(load(), path)


def load_years(overrides: dict[str, Any] | None = None) -> list[int]:
    """EAGLE-I years whose Bronze table and Silver partition this run rebuilds (D56)."""
    return list(get("incremental.load_years", overrides))


def literal(value: Any) -> str:
    """A configuration value as SQL text."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        if value and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            return ", ".join(map(str, value))  # numbers stay numbers, e.g. year IN (2024, 2025)
        return _sql_list(value)
    if isinstance(value, dict):
        raise ConfigError("a placeholder must name a single value, not a section")
    return str(value)


def render(sql: str, overrides: dict[str, Any] | None = None) -> str:
    """Replace every ${section.key} in sql. overrides maps a key to a value for one run."""
    def sub(m: re.Match) -> str:
        return literal(get(m.group(1), overrides))

    return PLACEHOLDER.sub(sub, sql)


if __name__ == "__main__":
    cfg = load()
    print(f"{CONFIG_PATH.relative_to(REPO_ROOT)} is valid: years {cfg['years']['sql']}, "
          f"{cfg['project']['catalog']}.{cfg['project']['schema']}, "
          f"{len(cfg['quality']['expected_rows'])} expected row counts")
