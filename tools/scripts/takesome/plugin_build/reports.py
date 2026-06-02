from __future__ import annotations

from pathlib import Path

from ..build_info import write_plugin_build_info
from ..logs import TeeLog
from ..paths import rel


def write_report_block(root: Path, *, log: TeeLog, run_stamp: str, started_utc: str, finished_utc: str, args: list[str], build_type: str, exit_code: int, records: list[dict], current_log: Path, latest_log: Path, root_last_log: Path, log_archive: Path | None = None) -> None:
    try:
        json_path, md_path = write_plugin_build_info(
            root,
            run_stamp=run_stamp,
            started_utc=started_utc,
            finished_utc=finished_utc,
            args=args,
            build_type=build_type,
            exit_code=exit_code,
            records=records,
            current_log=current_log,
            latest_log=latest_log,
            root_last_log=root_last_log,
            log_archive=log_archive,
        )
        log.emit(f"[INFO] BuildInfo registry: {rel(root, json_path)}")
        log.emit(f"[INFO] BuildInfo report: {rel(root, md_path)}")
    except Exception as exc:
        log.emit(f"[WARN] Failed to write buildInfo registry: {exc}")
