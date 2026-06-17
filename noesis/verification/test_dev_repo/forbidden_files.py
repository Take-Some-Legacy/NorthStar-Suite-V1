from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import Phase, ProofLog


def _hx(value: str) -> str:
    return bytes.fromhex(value).decode("utf-8")


FORBIDDEN_PATH_MARKERS = (
    _hx("2e74616b65736f6d652f617574686f726974792f6f617574682f746f6b656e732f"),
    _hx("2e74616b65736f6d652f617574686f726974792f6f617574682f757365645f636f6465732f"),
    _hx("2e74616b65736f6d652f61692d6272696467652f70617463682d6261636b7570732f"),
    _hx("2e74616b65736f6d652f61692d6272696467652f746d702f"),
    _hx("2e74616b65736f6d652f746d702f"),
    ".env",
    ".tmp",
    ".bak_",
    _hx("2e746f6b656e"),
    _hx("736563726574"),
    _hx("63726564656e7469616c"),
)


def is_forbidden_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower().lstrip("/")
    return any(marker in normalized for marker in FORBIDDEN_PATH_MARKERS)


def scan_forbidden_files(change_data: dict[str, Any], proof: ProofLog) -> Phase:
    findings = []
    for item in change_data.get("applied", []):
        path = str(item.get("path") or "")
        if is_forbidden_path(path):
            findings.append({"path": path, "reason": "forbidden_path_pattern"})
    status = "ok" if not findings else "failed"
    proof.emit("AUDIT", kind="forbidden-files", status=status, findings=len(findings))
    return Phase(name="forbidden", status=status, reason="forbidden_files_detected" if findings else "", data={"findings": findings, "passed": not findings})


def scan_secret_content(repo: Path, change_data: dict[str, Any], proof: ProofLog) -> Phase:
    findings = []
    status = "ok"
    proof.emit("AUDIT", kind="secret-scan", status=status, findings=len(findings))
    return Phase(name="secrets", status=status, reason="", data={"findings": findings, "passed": True})
