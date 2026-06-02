from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import rel, suite_path, utc_iso


TEMP_DIR_NAMES = {"_split_stage"}
TEMP_FILE_NAMES = {"split_staging.rs"}
GENERATED_WARN_EXTS = {".dll", ".pdb", ".exp", ".lib"}


@dataclass(frozen=True)
class CleanupFinding:
    repo: str
    path: str
    kind: str
    action: str
    reason: str


def _plugin_repositories(root: Path) -> list[Path]:
    plugins = root / "Plugins"
    if not plugins.exists():
        return []
    return [p for p in sorted(plugins.iterdir(), key=lambda item: item.name.lower()) if p.is_dir() and (p / ".git").exists()]


def _scan_repo(root: Path, repo: Path) -> list[CleanupFinding]:
    findings: list[CleanupFinding] = []
    for path in repo.rglob("*"):
        if ".git" in path.parts:
            continue
        if path.is_dir() and path.name in TEMP_DIR_NAMES:
            findings.append(CleanupFinding(repo=repo.name, path=rel(root, path), kind="temp_dir", action="delete", reason="temporary split staging directory"))
        elif path.is_file() and path.name in TEMP_FILE_NAMES:
            findings.append(CleanupFinding(repo=repo.name, path=rel(root, path), kind="temp_file", action="delete", reason="temporary split staging source file"))
        elif path.is_file() and path.suffix.lower() in GENERATED_WARN_EXTS and path.parent == repo:
            findings.append(CleanupFinding(repo=repo.name, path=rel(root, path), kind="generated_binary", action="warn_only", reason="plugin root binary artifact; verify tracking policy before commit"))
        elif path.is_file() and path.name == ".rustc_info.json" and "target" in path.parts:
            findings.append(CleanupFinding(repo=repo.name, path=rel(root, path), kind="generated_metadata", action="warn_only", reason="Cargo target metadata; should not be committed unless explicitly tracked"))
    return findings


def scan_plugin_cleanup(root: Path) -> dict[str, Any]:
    root = root.resolve()
    repos = _plugin_repositories(root)
    findings: list[CleanupFinding] = []
    for repo in repos:
        findings.extend(_scan_repo(root, repo))
    return {
        "schema": "northstar.plugins.cleanup.v1",
        "generated_at": utc_iso(),
        "repo_root": str(root),
        "plugin_repositories": [rel(root, repo) for repo in repos],
        "findings": [finding.__dict__ for finding in findings],
        "delete_candidates": [finding.__dict__ for finding in findings if finding.action == "delete"],
        "warn_only": [finding.__dict__ for finding in findings if finding.action == "warn_only"],
    }


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def apply_plugin_cleanup(root: Path, payload: dict[str, Any]) -> list[str]:
    deleted: list[str] = []
    root = root.resolve()
    for finding in payload.get("delete_candidates", []):
        rel_path = str(finding.get("path", ""))
        if not rel_path:
            continue
        path = root / rel_path
        if path.exists():
            _delete_path(path)
            deleted.append(rel_path)
    return deleted


def _render_markdown(payload: dict[str, Any], *, apply: bool, deleted: list[str]) -> str:
    delete_candidates = payload.get("delete_candidates", [])
    warn_only = payload.get("warn_only", [])
    md: list[str] = []
    md.append(f"# Plugin Cleanup Report — {payload['generated_at']}\n\n")
    md.append("> [!INFO] INFO BLOCK — scope\n")
    md.append("> **У нас сейчас:** report scans plugin repositories for temporary split-stage artifacts and generated build artifacts.\n>\n")
    md.append("> **Technical details (EN):** delete whitelist: `_split_stage/`, `split_staging.rs`; DLL/Cargo target artifacts are warn-only.\n\n")
    md.append(f"- **Mode:** `{'apply' if apply else 'dry-run'}`\n")
    md.append(f"- **Plugin repositories:** `{len(payload.get('plugin_repositories', []))}`\n")
    md.append(f"- **Delete candidates:** `{len(delete_candidates)}`\n")
    md.append(f"- **Warn-only artifacts:** `{len(warn_only)}`\n")
    md.append(f"- **Deleted:** `{len(deleted)}`\n\n")

    md.append("## Delete candidates\n\n| Repo | Path | Reason |\n|---|---|---|\n")
    if delete_candidates:
        for finding in delete_candidates:
            md.append(f"| `{finding['repo']}` | `{finding['path']}` | {finding['reason']} |\n")
    else:
        md.append("| none | none | none |\n")
    md.append("\n## Warn-only artifacts\n\n| Repo | Path | Reason |\n|---|---|---|\n")
    if warn_only:
        for finding in warn_only:
            md.append(f"| `{finding['repo']}` | `{finding['path']}` | {finding['reason']} |\n")
    else:
        md.append("| none | none | none |\n")
    if deleted:
        md.append("\n## Deleted\n\n")
        for path in deleted:
            md.append(f"- `{path}`\n")
    md.append("\n## Guardrail\n\nGenerated binaries are not deleted by this command. A plugin may intentionally track runtime DLLs; that decision must be repo-local and explicit.\n")
    return "".join(md)


def plugin_cleanup_command(root: Path, args: Any | None = None) -> int:
    apply = bool(getattr(args, "apply", False))
    payload = scan_plugin_cleanup(root)
    deleted = apply_plugin_cleanup(root, payload) if apply else []
    payload["deleted"] = deleted
    reports = suite_path(root, "reports")
    reports.mkdir(parents=True, exist_ok=True)
    latest_json = reports / "plugin-cleanup-latest.json"
    latest_md = reports / "plugin-cleanup-latest.md"
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(_render_markdown(payload, apply=apply, deleted=deleted), encoding="utf-8")
    print(f"[OK] Plugin cleanup report: {latest_md}")
    print(f"[INFO] Delete candidates: {len(payload.get('delete_candidates', []))}")
    print(f"[INFO] Warn-only artifacts: {len(payload.get('warn_only', []))}")
    print(f"[INFO] Deleted: {len(deleted)}")
    return 0
