from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..logs import TeeLog
from ..paths import rel


def _run_engine_script(repo_root: Path, script_name: str, args: list[str], *, log: TeeLog | None = None) -> int:
    own_log = log or TeeLog()
    script = repo_root / "NewEngine" / "neocore2" / "scripts" / script_name
    if not script.exists():
        own_log.emit(f"[ERROR] Engine scanner missing: {rel(repo_root, script)}")
        return 1
    cmd = [sys.executable, str(script), *args]
    own_log.emit("[CMD] " + " ".join(cmd))
    completed = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)
    if completed.stdout:
        for line in completed.stdout.splitlines():
            own_log.emit(line)
    if completed.stderr:
        for line in completed.stderr.splitlines():
            own_log.emit(f"[STDERR] {line}")
    return int(completed.returncode)


def run_p0_invariant_scan(
    repo_root: Path,
    *,
    strict_large_files: bool = False,
    strict_boundaries: bool = False,
    fail_tracked_large_debt: bool = False,
    log: TeeLog | None = None,
) -> int:
    """Run the source-level P0 invariant gate."""

    args: list[str] = []
    if strict_large_files:
        args.append("--strict-large-files")
    if strict_boundaries:
        args.append("--strict-boundaries")
    if fail_tracked_large_debt:
        args.append("--fail-tracked-large-debt")
    return _run_engine_script(repo_root, "p0_invariant_scan.py", args, log=log)


def run_p1_capability_conformance_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P1 capability matrix + provider conformance source harness."""

    return _run_engine_script(repo_root, "p1_capability_conformance_scan.py", [], log=log)


def run_p2_schema_property_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P2 schema/property/resource foundation source harness."""

    return _run_engine_script(repo_root, "p2_schema_property_scan.py", [], log=log)


def run_p21_schema_runtime_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P2.1 live schema runtime provider source harness."""

    return _run_engine_script(repo_root, "p21_schema_runtime_scan.py", [], log=log)


def run_p3_editor_shell_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P3 editor shell source harness."""

    return _run_engine_script(repo_root, "p3_editor_shell_scan.py", [], log=log)


def run_p4_import_pipeline_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P4 import/reimport/package pipeline source harness."""

    return _run_engine_script(repo_root, "p4_import_pipeline_scan.py", [], log=log)


def run_p5_world_scene_save_load_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P5 world/scene/save-load/prefab parity source harness."""

    return _run_engine_script(repo_root, "p5_world_scene_save_load_scan.py", [], log=log)

def run_p6_gameplay_foundation_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P6 gameplay foundation source harness."""

    return _run_engine_script(repo_root, "p6_gameplay_foundation_scan.py", [], log=log)



def run_p7_rendering_maturity_scan(
    repo_root: Path,
    *,
    log: TeeLog | None = None,
) -> int:
    """Run the P7 rendering maturity source harness."""

    return _run_engine_script(repo_root, "p7_rendering_maturity_scan.py", [], log=log)


def run_p8_reference_module_completeness_scan(
    repo_root: Path,
    *,
    strict_reference_parity: bool = False,
    log: TeeLog | None = None,
) -> int:
    """Run the P8 reference-module completeness source harness."""

    args: list[str] = []
    if strict_reference_parity:
        args.append("--strict-reference-parity")
    return _run_engine_script(repo_root, "p8_reference_module_completeness_scan.py", args, log=log)


def run_dataset_maturity_scan(
    repo_root: Path,
    *,
    write_index: bool = True,
    strict: bool = False,
    log: TeeLog | None = None,
) -> int:
    """Run the index-first dataSet maturity scanner."""

    args: list[str] = []
    if write_index:
        args.append("--write")
    if strict:
        args.append("--strict")
    return _run_engine_script(repo_root, "dataset_maturity_scan.py", args, log=log)


# Compatibility name used by older P9 Suite actions.
def run_p9_dataset_maturity_scan(
    repo_root: Path,
    *,
    write_index: bool = True,
    strict: bool = False,
    log: TeeLog | None = None,
) -> int:
    return run_dataset_maturity_scan(repo_root, write_index=write_index, strict=strict, log=log)
