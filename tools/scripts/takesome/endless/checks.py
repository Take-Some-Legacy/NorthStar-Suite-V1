from __future__ import annotations

import os
from pathlib import Path

from .model import ScannerFinding

IGNORED_DIRS = {
    ".git", ".idea", ".vs", ".takesome", "target", "logs", "cache", "stamps",
    "node_modules", "bin", "obj", "out", "dist", "artifacts", "__pycache__",
}
SOURCE_ROOTS = ("NewEngine", "Plugins", "tools/scripts", "Importers")
SOURCE_EXTS = {".rs", ".toml", ".json", ".ron", ".py", ".bat", ".cmd", ".md"}
DIRECT_PROVIDER_IDS = ("render.api", "physics.api", "ui.api", "ai.api", "asset_manager.api")
LEGACY_PATTERNS = (".neytd", "NEYTD", "asset.codec.pak", "newengine.container.pak", "package.pak", "type = \"pak\"")
HIDDEN_FALLBACK_PATTERNS = ("InternalNull", "internal null", "hidden fallback", "unwrap_or_else", "unwrap_or_default", "unwrap_or(")
BOUNDARY_PATTERNS = ("&mut World", "native EntityId", "EntityId")

DIAGNOSTIC_PATTERN_ALLOWLIST = (
    "tools/scripts/takesome/endless/checks.py",
    "tools/scripts/takesome/tools/legacy_scan.py",
    "tools/scripts/northstar_bridge/operator_tools.py",
)


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _walk_root(root: Path, scan_root: Path, max_files: int):
    count = 0
    if not scan_root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(scan_root):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() not in SOURCE_EXTS:
                continue
            yield path
            count += 1
            if count >= max_files:
                return


def _iter_source_files(root: Path, *, max_files: int = 1500) -> list[Path]:
    files: list[Path] = []
    per_root_budget = max(100, max_files // len(SOURCE_ROOTS))
    for name in SOURCE_ROOTS:
        scan_root = root / name
        for path in _walk_root(root, scan_root, per_root_budget):
            files.append(path)
            if len(files) >= max_files:
                return files
    for name in ("README.md", "WORKSPACE.md"):
        path = root / name
        if path.exists():
            files.append(path)
    return files


def _scan_patterns(
    root: Path,
    *,
    scanner: str,
    severity: str,
    patterns: tuple[str, ...],
    max_findings: int,
    path_filter: tuple[str, ...] | None = None,
    max_files: int = 1500,
) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for path in _iter_source_files(root, max_files=max_files):
        rel = _rel(path, root)
        if rel in DIAGNOSTIC_PATTERN_ALLOWLIST:
            continue
        if path_filter and not any(token in rel for token in path_filter):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for pattern in patterns:
                if pattern in line:
                    findings.append(ScannerFinding(scanner, severity, rel, line_number, f"matched forbidden/suspicious pattern: {pattern}", line.strip()[:240]))
                    break
            if len(findings) >= max_findings:
                return findings
    return findings


def scan_no_legacy(root: Path, *, max_findings: int = 30) -> list[ScannerFinding]:
    return _scan_patterns(root, scanner="no_legacy_scan", severity="error", patterns=LEGACY_PATTERNS, max_findings=max_findings)


def scan_direct_provider_ids(root: Path, *, max_findings: int = 30) -> list[ScannerFinding]:
    return _scan_patterns(root, scanner="direct_provider_id_scan", severity="error", patterns=DIRECT_PROVIDER_IDS, max_findings=max_findings)


def scan_hidden_fallback(root: Path, *, max_findings: int = 30) -> list[ScannerFinding]:
    return _scan_patterns(root, scanner="hidden_fallback_scan", severity="warn", patterns=HIDDEN_FALLBACK_PATTERNS, max_findings=max_findings)


def scan_service_boundaries(root: Path, *, max_findings: int = 30) -> list[ScannerFinding]:
    return _scan_patterns(root, scanner="service_boundary_scan", severity="warn", patterns=BOUNDARY_PATTERNS, max_findings=max_findings)


def scan_large_modules(root: Path, *, max_findings: int = 30, threshold: int = 550) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for path in _iter_source_files(root, max_files=1500):
        if path.suffix.lower() != ".rs":
            continue
        try:
            line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
        if line_count > threshold:
            findings.append(ScannerFinding("large_module_scan", "warn", _rel(path, root), threshold + 1, f"Rust module is {line_count} LOC; split target is <= {threshold} LOC", ""))
            if len(findings) >= max_findings:
                break
    return findings


def run_foundation_scans(root: Path, *, max_findings_per_scan: int = 30) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    findings.extend(scan_no_legacy(root, max_findings=max_findings_per_scan))
    findings.extend(scan_direct_provider_ids(root, max_findings=max_findings_per_scan))
    findings.extend(scan_hidden_fallback(root, max_findings=max_findings_per_scan))
    findings.extend(scan_service_boundaries(root, max_findings=max_findings_per_scan))
    findings.extend(scan_large_modules(root, max_findings=max_findings_per_scan))
    return findings
