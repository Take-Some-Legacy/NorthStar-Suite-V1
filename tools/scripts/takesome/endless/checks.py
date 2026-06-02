from __future__ import annotations

from pathlib import Path

from .model import ScannerFinding


IGNORED_DIRS = {
    ".git",
    ".idea",
    ".vs",
    ".takesome",
    "target",
    "logs",
    "cache",
    "stamps",
    "node_modules",
    "bin",
    "obj",
    "out",
    "dist",
    "artifacts",
    "__pycache__",
}

SOURCE_EXTS = {
    ".rs",
    ".toml",
    ".json",
    ".ron",
    ".py",
    ".bat",
    ".cmd",
    ".md",
}

RUNTIME_PATH_HINTS = (
    "NewEngine/",
    "Plugins/",
    "tools/scripts/",
    "Importers/",
)

DIRECT_PROVIDER_IDS = (
    "render.api",
    "physics.api",
    "ui.api",
    "ai.api",
    "asset_manager.api",
)

LEGACY_PATTERNS = (
    ".neytd",
    "NEYTD",
    "asset.codec.pak",
    "newengine.container.pak",
    "package.pak",
    "type = \"pak\"",
)

HIDDEN_FALLBACK_PATTERNS = (
    "InternalNull",
    "internal null",
    "hidden fallback",
    "unwrap_or_else",
    "unwrap_or_default",
    "unwrap_or(",
)

BOUNDARY_PATTERNS = (
    "&mut World",
    "native EntityId",
    "EntityId",
)


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _ignored(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return any(part in IGNORED_DIRS for part in rel.parts)


def _iter_source_files(root: Path, *, max_files: int = 6000) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _ignored(path, root):
            continue
        if path.suffix.lower() not in SOURCE_EXTS:
            continue
        rel = _rel(path, root)
        if not rel.startswith(RUNTIME_PATH_HINTS) and path.name not in {"README.md", "WORKSPACE.md"}:
            continue
        files.append(path)
        if len(files) >= max_files:
            break
    return files


def _scan_patterns(
    root: Path,
    *,
    scanner: str,
    severity: str,
    patterns: tuple[str, ...],
    max_findings: int,
    path_filter: tuple[str, ...] | None = None,
) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for path in _iter_source_files(root):
        rel = _rel(path, root)
        if path_filter and not any(token in rel for token in path_filter):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for pattern in patterns:
                if pattern in line:
                    findings.append(
                        ScannerFinding(
                            scanner=scanner,
                            severity=severity,
                            path=rel,
                            line=line_number,
                            message=f"matched forbidden/suspicious pattern: {pattern}",
                            sample=line.strip()[:240],
                        )
                    )
                    break
            if len(findings) >= max_findings:
                return findings
    return findings


def scan_no_legacy(root: Path, *, max_findings: int = 40) -> list[ScannerFinding]:
    return _scan_patterns(
        root,
        scanner="no_legacy_scan",
        severity="error",
        patterns=LEGACY_PATTERNS,
        max_findings=max_findings,
    )


def scan_direct_provider_ids(root: Path, *, max_findings: int = 40) -> list[ScannerFinding]:
    return _scan_patterns(
        root,
        scanner="direct_provider_id_scan",
        severity="error",
        patterns=DIRECT_PROVIDER_IDS,
        max_findings=max_findings,
        path_filter=("runtime", "Runtime", "NewEngine", "Plugins", "tools/scripts"),
    )


def scan_hidden_fallback(root: Path, *, max_findings: int = 40) -> list[ScannerFinding]:
    return _scan_patterns(
        root,
        scanner="hidden_fallback_scan",
        severity="warn",
        patterns=HIDDEN_FALLBACK_PATTERNS,
        max_findings=max_findings,
        path_filter=("runtime", "Runtime", "host", "gateway", "provider", "NewEngine"),
    )


def scan_service_boundaries(root: Path, *, max_findings: int = 40) -> list[ScannerFinding]:
    return _scan_patterns(
        root,
        scanner="service_boundary_scan",
        severity="warn",
        patterns=BOUNDARY_PATTERNS,
        max_findings=max_findings,
        path_filter=("service", "provider", "gateway", "api", "runtime", "Runtime", "NewEngine", "Plugins"),
    )


def scan_large_modules(root: Path, *, max_findings: int = 40, threshold: int = 550) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    for path in _iter_source_files(root):
        if path.suffix.lower() != ".rs":
            continue
        try:
            line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
        if line_count > threshold:
            findings.append(
                ScannerFinding(
                    scanner="large_module_scan",
                    severity="warn",
                    path=_rel(path, root),
                    line=threshold + 1,
                    message=f"Rust module is {line_count} LOC; split target is <= {threshold} LOC",
                    sample="",
                )
            )
            if len(findings) >= max_findings:
                break
    return findings


def run_foundation_scans(root: Path, *, max_findings_per_scan: int = 40) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    findings.extend(scan_no_legacy(root, max_findings=max_findings_per_scan))
    findings.extend(scan_direct_provider_ids(root, max_findings=max_findings_per_scan))
    findings.extend(scan_hidden_fallback(root, max_findings=max_findings_per_scan))
    findings.extend(scan_service_boundaries(root, max_findings=max_findings_per_scan))
    findings.extend(scan_large_modules(root, max_findings=max_findings_per_scan))
    return findings
