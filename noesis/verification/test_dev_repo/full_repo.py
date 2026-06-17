from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from noesis.verification.test_dev_repo.common import Phase, ProofLog, run_cmd, write_json

TEXT_SUFFIXES = {
    ".bat", ".cmd", ".css", ".html", ".js", ".json", ".jsx", ".md",
    ".ps1", ".py", ".rs", ".toml", ".ts", ".tsx", ".txt", ".vue",
    ".xml", ".yaml", ".yml",
}

SKIP_DIRS = {
    ".git", ".noesis", ".takesome", "__pycache__", "node_modules", "target",
    "dist", "build", ".venv", "venv",
}

SECRET_NAME_MARKERS = (
    "secret", "token", "api_key", "apikey", "private_key", "client_secret", "password",
)

ALLOWED_SECRET_FILES = {".env.example", ".env.sample", "runtime.v1.json"}


def _iter_text_files(repo: Path, *, limit: int = 8000) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(repo):
        rel_root = Path(root).relative_to(repo)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".bak")]
        if any(part in SKIP_DIRS for part in rel_root.parts):
            continue
        for name in names:
            if len(files) >= limit:
                return files
            path = Path(root) / name
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    return files


def _looks_like_assigned_secret(line: str) -> bool:
    text = line.strip()
    lower = text.lower()
    if not text or text.startswith(("#", "//")):
        return False
    if "example" in lower or "placeholder" in lower or "changeme" in lower:
        return False
    if "=" not in text and ":" not in text:
        return False
    left, value = text.split("=", 1) if "=" in text else text.split(":", 1)
    if not any(marker in left.lower() for marker in SECRET_NAME_MARKERS):
        return False
    value = value.strip().rstrip(",")
    if not value or value.lower() in {"none", "null", "false", "true"}:
        return False
    if "os.getenv" in value or "os.environ" in value:
        return False
    if value.startswith(("$", "%", "{", "[", "(", "Path(", "str(", "bool(", "ctx.", "self.", "args.")):
        return False
    quoted = (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"'))
    value = value.strip("'\"")
    if value.startswith(("http://", "https://", "file:")):
        return False
    if value.upper() == value and "_" in value:
        return False
    if not quoted:
        return False
    if len(value) < 24:
        return False
    alnum = sum(ch.isalnum() for ch in value)
    unique = len(set(value))
    return alnum >= 20 and unique >= 12


def run_secret_scan(repo: Path, proof: ProofLog) -> Phase:
    proof.emit("FULL", phase="secret-scan", status="running")
    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in _iter_text_files(repo):
        scanned += 1
        rel = path.relative_to(repo).as_posix()
        if path.name in ALLOWED_SECRET_FILES:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:
            findings.append({"path": rel, "line": None, "kind": "read-error", "error": str(exc)})
            continue
        for line_no, line in enumerate(lines, start=1):
            if _looks_like_assigned_secret(line):
                findings.append({"path": rel, "line": line_no, "kind": "assigned-secret-like-value"})
                if len(findings) >= 50:
                    break
        if len(findings) >= 50:
            break
    status = "ok" if not findings else "failed"
    proof.emit("FULL", phase="secret-scan", status=status, scanned=scanned, findings=len(findings))
    return Phase("full.secret-scan", status, "secret-like values detected" if findings else "", {"scannedFiles": scanned, "findings": findings})


def run_bridge_hello(repo: Path, proof: ProofLog) -> Phase:
    proof.emit("FULL", phase="bridge-hello", status="running")
    config = repo / "config" / "noesis" / "runtime.v1.json"
    result = run_cmd([sys.executable, "-m", "noesis", "bridge", "--workspace-config", config.as_posix(), "--hello"], cwd=repo, timeout=90)
    proof.emit("FULL", phase="bridge-hello", status="ok" if result.ok else "failed", exit=result.exit_code)
    return Phase("full.bridge-hello", "ok" if result.ok else "failed", "" if result.ok else "bridge hello failed", {"command": result.to_json()})


def run_supervisor_smoke(repo: Path, proof: ProofLog) -> Phase:
    proof.emit("FULL", phase="supervisor-smoke", status="running")
    result = run_cmd([sys.executable, "-m", "noesis", "supervisor", "--help"], cwd=repo, timeout=90)
    proof.emit("FULL", phase="supervisor-smoke", status="ok" if result.ok else "failed", exit=result.exit_code)
    return Phase("full.supervisor-smoke", "ok" if result.ok else "failed", "" if result.ok else "supervisor smoke failed", {"command": result.to_json()})


def _package_jsons(repo: Path) -> list[Path]:
    result: list[Path] = []
    for root, dirs, names in os.walk(repo):
        rel_root = Path(root).relative_to(repo)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if any(part in SKIP_DIRS for part in rel_root.parts):
            continue
        if "package.json" in names:
            result.append(Path(root) / "package.json")
    return result


def run_site_checks(repo: Path, proof: ProofLog) -> Phase:
    proof.emit("FULL", phase="site-checks", status="running")
    packages = _package_jsons(repo)
    npm = shutil.which("npm")
    checks: list[dict[str, Any]] = []
    if not packages:
        proof.emit("FULL", phase="site-checks", status="ok", packages=0)
        return Phase("full.site-checks", "ok", "no package.json files detected", {"packageJsonFiles": [], "checks": []})
    for package in packages:
        rel = package.relative_to(repo).as_posix()
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
        except Exception as exc:
            checks.append({"path": rel, "status": "failed", "reason": f"package.json parse failed: {exc}"})
            continue
        scripts = data.get("scripts") if isinstance(data, dict) else {}
        script_names = sorted(scripts.keys()) if isinstance(scripts, dict) else []
        checks.append({"path": rel, "status": "detected", "scripts": script_names, "npmAvailable": bool(npm), "enforced": False})
    status = "ok" if all(item.get("status") != "failed" for item in checks) else "failed"
    proof.emit("FULL", phase="site-checks", status=status, packages=len(packages), npm=bool(npm))
    return Phase(
        "full.site-checks",
        status,
        "site packages detected; npm scripts are recorded but not enforced in skeleton mode",
        {"packageJsonFiles": [p.relative_to(repo).as_posix() for p in packages], "npmAvailable": bool(npm), "checks": checks, "enforcement": "record-only"},
    )


def run_full_repo_gate(repo: Path, run_dir: Path, proof: ProofLog) -> Phase:
    proof.emit("FULL", phase="start", status="running", mode="skeleton")
    phases = {
        "secretScan": run_secret_scan(repo, proof),
        "bridgeHello": run_bridge_hello(repo, proof),
        "supervisorSmoke": run_supervisor_smoke(repo, proof),
        "siteChecks": run_site_checks(repo, proof),
    }
    blocking = [name for name, phase in phases.items() if not phase.ok]
    data = {
        "schema": "noesis.full_repo_gate.v1",
        "mode": "skeleton",
        "enforcementReady": False,
        "blockingChecks": blocking,
        "requiredBeforeWholeRepositoryReady": [
            "secretScan.ok", "bridgeHello.ok", "supervisorSmoke.ok", "siteChecks.enforced", "fullBuild.ok", "fullTest.ok",
        ],
        "phases": {name: phase.to_json() for name, phase in phases.items()},
    }
    write_json(run_dir / "full-repo-report.json", data, proof, kind="full-repo-report")
    proof.emit("FULL", phase="done", status="skeleton", blocking=len(blocking), enforcementReady=False)
    return Phase("full-repo", "skeleton", "full-repo gate skeleton is present but not yet enforcement-ready", data)
