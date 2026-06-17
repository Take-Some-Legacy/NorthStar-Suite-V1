from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _write_report(root: Path, name: str, payload: dict[str, Any]) -> Path:
    out_dir = root / ".takesome" / "endless" / "recipe-runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] recipe report: {path}")
    return path


def _run(root: Path, args: list[str]) -> int:
    return subprocess.run(args, cwd=root).returncode


def _replace_function(text: str, function_name: str, next_function_name: str, replacement: str) -> str:
    start = text.index("def " + function_name)
    end = text.index("\n\ndef " + next_function_name, start)
    return text[:start] + replacement + text[end:]


def fix_direct_provider_scan(root: Path) -> int:
    # Make direct-provider-id scan ignore legal descriptor/config/test references.
    path = root / "tools" / "scripts" / "takesome" / "endless" / "checks.py"
    text = path.read_text(encoding="utf-8")

    allow_name = "DIRECT_PROVIDER_ID_ALLOWLIST_PARTS"
    if allow_name not in text:
        diagnostic_anchor = (
            'DIAGNOSTIC_PATTERN_ALLOWLIST = (\n'
            '    "noesis/suite/endless/checks.py",\n'
            '    "noesis/suite/tools/legacy_scan.py",\n'
            '    "noesis/bridge/operator_tools.py",\n'
            ')\n'
        )
        allow_block = (
            "\n"
            "DIRECT_PROVIDER_ID_ALLOWLIST_PARTS = (\n"
            '    "/config/capabilities/",\n'
            '    "/config/conformance/",\n'
            '    "/tests/",\n'
            '    "/test/",\n'
            ")\n"
        )
        if diagnostic_anchor in text:
            text = text.replace(diagnostic_anchor, diagnostic_anchor + allow_block)
        else:
            boundary_anchor = 'BOUNDARY_PATTERNS = ("&mut World", "native EntityId", "EntityId")\n'
            if boundary_anchor not in text:
                raise RuntimeError("checks.py does not contain expected scanner constants anchor")
            text = text.replace(boundary_anchor, boundary_anchor + allow_block)

    replacement = """def scan_direct_provider_ids(root: Path, *, max_findings: int = 30) -> list[ScannerFinding]:
    findings = _scan_patterns(
        root,
        scanner="direct_provider_id_scan",
        severity="error",
        patterns=DIRECT_PROVIDER_IDS,
        max_findings=max_findings * 3,
    )
    filtered: list[ScannerFinding] = []
    for finding in findings:
        normalized = "/" + finding.path.replace("\\\\", "/")
        if any(part in normalized for part in DIRECT_PROVIDER_ID_ALLOWLIST_PARTS):
            continue
        filtered.append(finding)
        if len(filtered) >= max_findings:
            break
    return filtered
"""
    text = _replace_function(text, "scan_direct_provider_ids", "scan_hidden_fallback", replacement)
    path.write_text(text, encoding="utf-8")

    rc = _run(root, [sys.executable, "-m", "py_compile", str(path)])
    _write_report(
        root,
        "fix-direct-provider-scan",
        {
            "schema": "northstar.endless.recipe.v1",
            "recipe": "fix-direct-provider-scan",
            "ok": rc == 0,
            "exit_code": rc,
            "path": str(path.relative_to(root)),
        },
    )
    return rc


def full_cycle(root: Path) -> int:
    # Run one registered Endless Stream cycle without passing patch payload through chat.
    msg = (
        "Continue foundation series without waiting for operator. "
        "Stream steering only. Pick next scanner-backed P0/P1 task after local recipe execution."
    )
    rc = _run(
        root,
        [
            sys.executable,
            "python -m noesis suite",
            "endless-stream",
            "--message",
            msg,
        ],
    )
    _write_report(
        root,
        "full-cycle",
        {
            "schema": "northstar.endless.full_cycle.v1",
            "ok": rc == 0,
            "exit_code": rc,
        },
    )
    return rc


def loop(root: Path, max_cycles: int | None = None) -> int:
    """Run Endless Stream cycles until interrupted, stopped or failed.

    ``max_cycles`` is intentionally not used by the Suite action. It exists only
    as an explicit dev/test guard for local validation. ``None`` and values less
    than or equal to zero mean unbounded execution.
    """

    endless_dir = root / ".takesome" / "endless"
    stop_file = endless_dir / "STOP"
    bounded_max = max_cycles if max_cycles is not None and max_cycles > 0 else None
    cycle = 0

    def write_loop_report(state: str, rc: int) -> None:
        _write_report(
            root,
            "loop",
            {
                "schema": "northstar.endless.loop.v1",
                "ok": rc == 0,
                "state": state,
                "cycle": cycle,
                "max_cycles": bounded_max,
                "unbounded": bounded_max is None,
                "last_exit_code": rc,
                "stop_file": str(stop_file.relative_to(root)),
            },
        )

    try:
        while bounded_max is None or cycle < bounded_max:
            if stop_file.exists():
                print(f"[INFO] Endless Stream stop signal found: {stop_file}")
                write_loop_report("stopped_by_signal", 0)
                return 0

            cycle += 1
            print(f"[INFO] Endless Stream cycle {cycle} started")
            rc = full_cycle(root)
            write_loop_report("running" if rc == 0 else "failed", rc)
            if rc != 0:
                return rc

        write_loop_report("completed_dev_guard", 0)
        return 0
    except KeyboardInterrupt:
        print("[WARN] Endless Stream interrupted by operator")
        write_loop_report("interrupted", 130)
        return 130
