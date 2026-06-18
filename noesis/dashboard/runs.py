from __future__ import annotations

from .runs_cli import (
    _coerce_summary,
    build_parser,
    command_failures,
    command_list,
    command_patch,
    command_serve,
    command_show,
    main,
    print_table,
)
from .runs_constants import DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_TITLE
from .runs_index import (
    checksum_count,
    dashboard_insights,
    first_failed_phase,
    index_payload,
    load_runs,
    summarize_run,
    write_index,
)
from .runs_io import artifact_links, parse_utc, read_json, read_text, utc_now
from .runs_model import RunSummary
from .runs_patch import patch_candidates, patch_commands, patch_payload, patch_stats, run_payload
from .providers import cluster_payload, load_suite_actions, operator_tasks_payload, paths_payload, worker_payload

__all__ = [
    "DASHBOARD_HOST",
    "DASHBOARD_PORT",
    "DASHBOARD_TITLE",
    "RunSummary",
    "artifact_links",
    "build_parser",
    "checksum_count",
    "command_failures",
    "command_list",
    "command_patch",
    "command_serve",
    "command_show",
    "dashboard_insights",
    "first_failed_phase",
    "index_payload",
    "load_runs",
    "main",
    "parse_utc",
    "patch_candidates",
    "patch_commands",
    "patch_payload",
    "patch_stats",
    "print_table",
    "read_json",
    "read_text",
    "run_payload",
    "summarize_run",
    "utc_now",
    "cluster_payload",
    "worker_payload",
    "paths_payload",
    "load_suite_actions",
    "operator_tasks_payload",
    "write_index",
]


if __name__ == "__main__":
    raise SystemExit(main())
