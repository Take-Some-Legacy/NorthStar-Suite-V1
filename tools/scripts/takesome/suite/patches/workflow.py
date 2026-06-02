from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ...console import console_emit
from ...console_menu import ConsoleChoice, ConsoleMenuOption, interactive_menu_enabled, run_action_menu, run_confirm_button
from ...filesystem import best_effort_remove_path
from ...migration import apply_delete_list
from ...paths import now_stamp, rel, safe_repo_path, suite_root, utc_iso

PATCH_SCHEMA = "takesome.patchWorkflow.v1"
BACKUP_SCHEMA = "takesome.patchBackup.v1"


@dataclass(frozen=True)
class PatchEntry:
    archive_name: str
    repo_path: str
    kind: str
    size: int


@dataclass(frozen=True)
class PatchInspection:
    zip_path: Path
    entries: tuple[PatchEntry, ...]
    unsafe_entries: tuple[str, ...]
    delete_list_entries: tuple[str, ...]
    file_to_directory_migrations: tuple[str, ...]

    @property
    def valid_entries(self) -> tuple[PatchEntry, ...]:
        return tuple(entry for entry in self.entries if entry.kind == "file")

    @property
    def changed_files(self) -> tuple[str, ...]:
        return tuple(entry.repo_path for entry in self.valid_entries)


def _patch_root(root: Path) -> Path:
    return suite_root(root) / "patches"


def _backup_root(root: Path) -> Path:
    return suite_root(root) / "patch-backups"


def _latest_state_path(root: Path) -> Path:
    return _backup_root(root) / "latest.json"


def _report_latest_path(root: Path) -> Path:
    return _patch_root(root) / "patch-latest.md"


def _safe_component(value: str, fallback: str = "patch") -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value.strip())
    safe = safe.strip("-._")
    return safe or fallback


def _is_ignored_zip_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        return False
    parts = [part for part in normalized.split("/") if part]
    return any(part == "__MACOSX" for part in parts) or PurePosixPath(normalized).name == ".DS_Store"


def _normalize_zip_member(name: str) -> str | None:
    normalized = name.replace("\\", "/").strip()
    if not normalized:
        return None
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"..", ""} for part in path.parts):
        return None
    return path.as_posix().rstrip("/")


def _safe_target(root: Path, repo_path: str) -> Path | None:
    try:
        return safe_repo_path(root, repo_path)
    except ValueError:
        return None


def _read_delete_entries_from_zip(zip_path: Path) -> tuple[str, ...]:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                repo_path = _normalize_zip_member(name)
                if repo_path and repo_path.lower() == "delete_files.txt":
                    raw = zf.read(name).decode("utf-8-sig", errors="replace")
                    entries: list[str] = []
                    for line in raw.splitlines():
                        stripped = line.strip().strip('"').strip("'")
                        if not stripped or stripped.startswith("#"):
                            continue
                        entries.append(stripped.replace("\\", "/"))
                    return tuple(entries)
    except (OSError, zipfile.BadZipFile):
        return ()
    return ()


def inspect_patch(zip_path: Path, root: Path) -> PatchInspection:
    entries: list[PatchEntry] = []
    unsafe: list[str] = []
    migrations: set[str] = set()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            normalized_files: set[str] = set()
            for info in zf.infolist():
                repo_path = _normalize_zip_member(info.filename)
                if repo_path is None:
                    unsafe.append(info.filename)
                    continue
                if _is_ignored_zip_member(info.filename):
                    continue
                kind = "dir" if info.is_dir() else "file"
                entries.append(PatchEntry(info.filename, repo_path, kind, int(info.file_size)))
                if kind == "file":
                    normalized_files.add(repo_path)
            for repo_path in normalized_files:
                parts = PurePosixPath(repo_path).parts
                for depth in range(1, len(parts)):
                    parent = "/".join(parts[:depth])
                    target = _safe_target(root, parent)
                    if target is not None and target.exists() and target.is_file():
                        migrations.add(parent)
    except zipfile.BadZipFile:
        unsafe.append(f"{zip_path.name}: not a zip file")
    except OSError as exc:
        unsafe.append(f"{zip_path.name}: {exc}")
    delete_entries = _read_delete_entries_from_zip(zip_path)
    for delete_path in delete_entries:
        target = _safe_target(root, delete_path)
        if target is None:
            unsafe.append(f"DELETE_FILES.txt: unsafe path {delete_path}")
    return PatchInspection(zip_path.resolve(), tuple(entries), tuple(unsafe), tuple(delete_entries), tuple(sorted(migrations)))


def _candidate_patch_zips(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in root.glob("*.zip"):
        name = path.name.lower()
        if not path.is_file():
            continue
        if name.startswith("northstar-engine-source") or name.startswith("run-bundle-"):
            continue
        if "changed-files" in name or "patch" in name or "pass" in name:
            candidates.append(path)
    return sorted(candidates, key=lambda p: (p.stat().st_mtime, p.name.lower()), reverse=True)


def _choose_patch_zip(root: Path) -> Path | None:
    candidates = _candidate_patch_zips(root)
    if not candidates:
        console_emit("[PATCH] No root changed-files patch zip found.")
        console_emit("[PATCH] Put a *changed-files*.zip or *patch*.zip in the repository root and run this action again.")
        return None
    if len(candidates) == 1 or not interactive_menu_enabled():
        return candidates[0]
    choices = [
        ConsoleChoice(value=path, number=index, label=path.name, detail=f"{path.stat().st_size} bytes", marker="PATCH")
        for index, path in enumerate(candidates[:20], start=1)
    ]
    result = run_action_menu(
        title="Select changed-files patch zip",
        choices=choices,
        footer="↑/↓ move  Enter inspect/apply  number focus  Esc cancel",
    )
    if result.cancelled or result.selected_value is None:
        return None
    return result.selected_value


def _copy_existing_to_backup(root: Path, backup_before: Path, repo_path: str, manifest_entries: list[dict[str, Any]]) -> None:
    target = _safe_target(root, repo_path)
    if target is None:
        return
    backup = backup_before / repo_path
    existed = target.exists() or target.is_symlink()
    entry: dict[str, Any] = {
        "path": repo_path,
        "existed": existed,
        "kind": "missing",
    }
    if existed:
        backup.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir() and not target.is_symlink():
            shutil.copytree(target, backup, dirs_exist_ok=True)
            entry["kind"] = "dir"
        else:
            shutil.copy2(target, backup)
            entry["kind"] = "file"
        entry["backup"] = str(backup.relative_to(backup_before.parent))
    manifest_entries.append(entry)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _relative_list(root: Path, paths: list[Path]) -> list[str]:
    return [rel(root, path) for path in paths]


def _run_suite_self_test(root: Path) -> tuple[int, list[str]]:
    commands = [
        [sys.executable, "-m", "compileall", "-q", "tools/scripts"],
        [sys.executable, "tools/scripts/takesome.py", "suite", "--list-actions"],
    ]
    output: list[str] = []
    final_code = 0
    env = os.environ.copy()
    env.setdefault("NEWENGINE_SUITE_NO_WAIT", "1")
    env.setdefault("NEWENGINE_SUITE_NO_CLEAR", "1")
    for command in commands:
        output.append(f"$ {' '.join(command)}")
        try:
            result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        except OSError as exc:
            output.append(f"[ERROR] {exc}")
            return 1, output
        if result.stdout:
            output.extend(result.stdout.splitlines()[-80:])
        output.append(f"exit_code={result.returncode}")
        if result.returncode != 0 and final_code == 0:
            final_code = result.returncode
    return final_code, output


def _render_inspection_markdown(root: Path, inspection: PatchInspection) -> str:
    files = [entry for entry in inspection.entries if entry.kind == "file"]
    dirs = [entry for entry in inspection.entries if entry.kind == "dir"]
    lines = [
        "# Patch Inspection",
        "",
        f"- zip: `{rel(root, inspection.zip_path)}`",
        f"- files: `{len(files)}`",
        f"- directories: `{len(dirs)}`",
        f"- unsafe_entries: `{len(inspection.unsafe_entries)}`",
        f"- delete_entries: `{len(inspection.delete_list_entries)}`",
        f"- file_to_directory_migrations: `{len(inspection.file_to_directory_migrations)}`",
        "",
    ]
    if inspection.unsafe_entries:
        lines.extend(["## Unsafe entries", ""])
        for item in inspection.unsafe_entries:
            lines.append(f"- `{item}`")
        lines.append("")
    if inspection.file_to_directory_migrations:
        lines.extend(["## File-to-directory migrations", ""])
        for item in inspection.file_to_directory_migrations:
            lines.append(f"- `{item}`")
        lines.append("")
    if inspection.delete_list_entries:
        lines.extend(["## DELETE_FILES.txt entries", ""])
        for item in inspection.delete_list_entries:
            lines.append(f"- `{item}`")
        lines.append("")
    lines.extend(["## Changed files", ""])
    for entry in files:
        lines.append(f"- `{entry.repo_path}` ({entry.size} bytes)")
    return "\n".join(lines).rstrip() + "\n"


def _write_inspection_report(root: Path, inspection: PatchInspection) -> Path:
    stamp = now_stamp()
    report = _patch_root(root) / f"patch-inspect-{stamp}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_render_inspection_markdown(root, inspection), encoding="utf-8")
    _report_latest_path(root).write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    return report


def inspect_patch_zip(root: Path) -> int:
    patch = _choose_patch_zip(root)
    if patch is None:
        return 1
    inspection = inspect_patch(patch, root)
    report = _write_inspection_report(root, inspection)
    console_emit(f"[PATCH] Inspect: {rel(root, patch)}")
    console_emit(f"[PATCH] Files: {len(inspection.valid_entries)}")
    if inspection.file_to_directory_migrations:
        console_emit(f"[PATCH] File-to-directory migrations: {', '.join(inspection.file_to_directory_migrations)}")
    if inspection.delete_list_entries:
        console_emit(f"[PATCH] DELETE_FILES entries: {len(inspection.delete_list_entries)}")
    if inspection.unsafe_entries:
        console_emit(f"[ERROR] Unsafe zip entries detected: {len(inspection.unsafe_entries)}")
        for item in inspection.unsafe_entries[:8]:
            console_emit(f"[ERROR] {item}")
    console_emit(f"[LOG] Patch inspection report: {rel(root, report)}")
    return 1 if inspection.unsafe_entries else 0


def _confirm_apply(root: Path, inspection: PatchInspection) -> bool:
    if suite_yes_enabled() and not inspection.unsafe_entries:
        print("[OK] Auto-approved changed-files patch via NORTHSTAR_SUITE_YES=1.")
        return True
    body = [
        f"zip: {rel(root, inspection.zip_path)}",
        f"files: {len(inspection.valid_entries)}",
        f"delete entries: {len(inspection.delete_list_entries)}",
        f"file-to-directory migrations: {len(inspection.file_to_directory_migrations)}",
        "backup: .takesome/patch-backups/<stamp>-<zip>",
        "verify: compileall + suite --list-actions",
    ]
    if inspection.file_to_directory_migrations:
        body.append("migrations: " + ", ".join(inspection.file_to_directory_migrations[:5]))
    if inspection.unsafe_entries:
        body.append("unsafe entries detected; apply is blocked")
    if not interactive_menu_enabled():
        return not inspection.unsafe_entries
    result = run_confirm_button(title="Apply changed-files patch", body_lines=body, confirm_label="APPLY PATCH")
    return result.confirmed and not result.cancelled and not inspection.unsafe_entries


def apply_changed_files_patch(root: Path) -> int:
    patch = _choose_patch_zip(root)
    if patch is None:
        return 1
    inspection = inspect_patch(patch, root)
    inspect_report = _write_inspection_report(root, inspection)
    if inspection.unsafe_entries:
        console_emit("[ERROR] Patch contains unsafe entries; apply blocked.")
        console_emit(f"[LOG] Patch inspection report: {rel(root, inspect_report)}")
        return 2
    if not _confirm_apply(root, inspection):
        console_emit("[PATCH] Apply cancelled.")
        return 0

    stamp = now_stamp()
    backup_dir = _backup_root(root) / f"patch-{stamp}-{_safe_component(patch.stem)}"
    before_dir = backup_dir / "before"
    before_entries: list[dict[str, Any]] = []
    applied_files: list[str] = []
    created_files: list[str] = []
    deleted_paths: list[str] = []
    backup_dir.mkdir(parents=True, exist_ok=True)

    paths_to_backup: list[str] = []
    for entry in inspection.valid_entries:
        paths_to_backup.append(entry.repo_path)
    paths_to_backup.extend(inspection.file_to_directory_migrations)
    paths_to_backup.extend(inspection.delete_list_entries)
    seen: set[str] = set()
    for repo_path in paths_to_backup:
        if repo_path in seen:
            continue
        seen.add(repo_path)
        _copy_existing_to_backup(root, before_dir, repo_path, before_entries)

    try:
        for migration_path in inspection.file_to_directory_migrations:
            target = _safe_target(root, migration_path)
            if target is not None and target.exists() and target.is_file():
                result = best_effort_remove_path(root, target, quarantine_on_failure=True)
                if result.status not in {"deleted", "quarantined", "missing"}:
                    raise OSError(f"could not remove file-to-directory migration target {migration_path}: {result.message}")
                deleted_paths.append(migration_path)

        with zipfile.ZipFile(patch) as zf:
            for entry in inspection.valid_entries:
                target = _safe_target(root, entry.repo_path)
                if target is None:
                    raise ValueError(f"unsafe target path: {entry.repo_path}")
                existed_before = target.exists() or target.is_symlink()
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(entry.archive_name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                applied_files.append(entry.repo_path)
                if not existed_before:
                    created_files.append(entry.repo_path)

        delete_file = root / "DELETE_FILES.txt"
        if delete_file.exists():
            apply_delete_list(root)
            deleted_paths.extend(inspection.delete_list_entries)

        self_test_code, self_test_output = _run_suite_self_test(root)
        manifest = {
            "schema": BACKUP_SCHEMA,
            "created_utc": utc_iso(),
            "zip": rel(root, patch) if patch.is_relative_to(root) else str(patch),
            "backup_dir": rel(root, backup_dir),
            "inspection_report": rel(root, inspect_report),
            "applied_files": applied_files,
            "created_files": created_files,
            "deleted_paths": deleted_paths,
            "before": before_entries,
            "self_test_exit_code": self_test_code,
        }
        _write_json(backup_dir / "patch-apply.json", manifest)
        _write_json(_latest_state_path(root), manifest)
        report = _render_apply_report(root, manifest, self_test_output)
        (backup_dir / "summary.md").write_text(report, encoding="utf-8")
        (root / "last-patch.md").write_text(report, encoding="utf-8")
        (root / "last-patch.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        console_emit(f"[PATCH] Applied: {rel(root, patch)}")
        console_emit(f"[PATCH] Backup: {rel(root, backup_dir)}")
        console_emit(f"[PATCH] Report: {rel(root, backup_dir / 'summary.md')}")
        if self_test_code != 0:
            console_emit(f"[ERROR] Suite self-test failed after patch: exit_code={self_test_code}")
            console_emit("[NEXT] Run [PATCH] Rollback last patch or inspect last-patch.md.")
            return self_test_code
        console_emit("[OK] Patch applied and Suite self-test passed.")
        return 0
    except Exception as exc:
        console_emit(f"[ERROR] Patch apply failed: {type(exc).__name__}: {exc}")
        console_emit(f"[PATCH] Backup kept for manual recovery: {rel(root, backup_dir)}")
        return 1


def _render_apply_report(root: Path, manifest: dict[str, Any], self_test_output: list[str]) -> str:
    lines = [
        "# Patch Apply Report",
        "",
        f"- schema: `{manifest.get('schema', '')}`",
        f"- created_utc: `{manifest.get('created_utc', '')}`",
        f"- zip: `{manifest.get('zip', '')}`",
        f"- backup_dir: `{manifest.get('backup_dir', '')}`",
        f"- applied_files: `{len(manifest.get('applied_files', []))}`",
        f"- created_files: `{len(manifest.get('created_files', []))}`",
        f"- deleted_paths: `{len(manifest.get('deleted_paths', []))}`",
        f"- self_test_exit_code: `{manifest.get('self_test_exit_code', '')}`",
        "",
        "## Applied files",
        "",
    ]
    for path in manifest.get("applied_files", []):
        lines.append(f"- `{path}`")
    if manifest.get("deleted_paths"):
        lines.extend(["", "## Deleted/migrated paths", ""])
        for path in manifest.get("deleted_paths", []):
            lines.append(f"- `{path}`")
    lines.extend(["", "## Suite self-test", "", "```text"])
    lines.extend(self_test_output[-160:])
    lines.append("```")
    return "\n".join(lines).rstrip() + "\n"


def verify_last_patch(root: Path) -> int:
    state = _read_latest_state(root)
    if not state:
        console_emit("[PATCH] No last patch state found.")
        return 1
    missing: list[str] = []
    for repo_path in state.get("applied_files", []):
        target = _safe_target(root, str(repo_path))
        if target is None or not target.exists():
            missing.append(str(repo_path))
    code, output = _run_suite_self_test(root)
    report = [
        "# Patch Verify Report",
        "",
        f"- verified_utc: `{utc_iso()}`",
        f"- zip: `{state.get('zip', '')}`",
        f"- missing_applied_files: `{len(missing)}`",
        f"- self_test_exit_code: `{code}`",
        "",
    ]
    if missing:
        report.extend(["## Missing applied files", ""])
        report.extend(f"- `{path}`" for path in missing)
        report.append("")
    report.extend(["## Suite self-test", "", "```text", *output[-160:], "```"])
    verify_path = _patch_root(root) / f"patch-verify-{now_stamp()}.md"
    verify_path.parent.mkdir(parents=True, exist_ok=True)
    verify_path.write_text("\n".join(report).rstrip() + "\n", encoding="utf-8")
    (root / "last-patch-verify.md").write_text(verify_path.read_text(encoding="utf-8"), encoding="utf-8")
    console_emit(f"[PATCH] Verify report: {rel(root, verify_path)}")
    if missing:
        console_emit(f"[ERROR] Missing applied files: {len(missing)}")
        return 1
    if code != 0:
        console_emit(f"[ERROR] Suite self-test failed: exit_code={code}")
        return code
    console_emit("[OK] Last patch verified.")
    return 0


def _read_latest_state(root: Path) -> dict[str, Any]:
    path = _latest_state_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def rollback_last_patch(root: Path) -> int:
    state = _read_latest_state(root)
    if not state:
        console_emit("[PATCH] No last patch state found.")
        return 1
    backup_dir = root / str(state.get("backup_dir", ""))
    before_root = backup_dir / "before"
    if not backup_dir.exists():
        console_emit(f"[ERROR] Patch backup directory not found: {state.get('backup_dir', '')}")
        return 1
    body = [
        f"zip: {state.get('zip', '')}",
        f"backup: {state.get('backup_dir', '')}",
        f"applied files: {len(state.get('applied_files', []))}",
        f"created files: {len(state.get('created_files', []))}",
        "rollback restores backed-up paths and removes files created by the patch",
    ]
    if interactive_menu_enabled():
        if suite_yes_enabled():
            print("[OK] Auto-approved patch rollback via NORTHSTAR_SUITE_YES=1.")
            return _restore_backup(root, backup)
        confirm = run_confirm_button(title="Rollback last changed-files patch", body_lines=body, confirm_label="ROLLBACK PATCH")
        if not confirm.confirmed or confirm.cancelled:
            console_emit("[PATCH] Rollback cancelled.")
            return 0

    errors = 0
    restored: list[str] = []
    removed: list[str] = []
    before_entries = state.get("before", []) if isinstance(state.get("before"), list) else []
    existed_by_path = {str(entry.get("path", "")): bool(entry.get("existed")) for entry in before_entries if isinstance(entry, dict)}

    # Remove created files first, deepest path first, so restored directories can be copied cleanly.
    for repo_path in sorted([str(path) for path in state.get("created_files", [])], key=lambda p: p.count("/"), reverse=True):
        if existed_by_path.get(repo_path):
            continue
        target = _safe_target(root, repo_path)
        if target is None:
            errors += 1
            continue
        result = best_effort_remove_path(root, target, quarantine_on_failure=True)
        if result.status in {"deleted", "missing", "quarantined"}:
            removed.append(repo_path)
        else:
            console_emit(f"[WARN] Could not remove created path {repo_path}: {result.message}")
            errors += 1

    for entry in before_entries:
        if not isinstance(entry, dict):
            continue
        repo_path = str(entry.get("path", ""))
        if not repo_path or not entry.get("existed"):
            continue
        target = _safe_target(root, repo_path)
        if target is None:
            errors += 1
            continue
        backup = before_root / repo_path
        if not backup.exists():
            console_emit(f"[WARN] Missing backup for {repo_path}")
            errors += 1
            continue
        if target.exists() or target.is_symlink():
            best_effort_remove_path(root, target, quarantine_on_failure=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        if backup.is_dir() and not backup.is_symlink():
            shutil.copytree(backup, target, dirs_exist_ok=True)
        else:
            shutil.copy2(backup, target)
        restored.append(repo_path)

    code, output = _run_suite_self_test(root)
    report = [
        "# Patch Rollback Report",
        "",
        f"- rolled_back_utc: `{utc_iso()}`",
        f"- zip: `{state.get('zip', '')}`",
        f"- restored: `{len(restored)}`",
        f"- removed: `{len(removed)}`",
        f"- errors: `{errors}`",
        f"- self_test_exit_code: `{code}`",
        "",
        "## Restored",
        "",
        *(f"- `{path}`" for path in restored),
        "",
        "## Removed created paths",
        "",
        *(f"- `{path}`" for path in removed),
        "",
        "## Suite self-test",
        "",
        "```text",
        *output[-160:],
        "```",
    ]
    report_path = backup_dir / "rollback.md"
    report_path.write_text("\n".join(report).rstrip() + "\n", encoding="utf-8")
    (root / "last-patch-rollback.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    console_emit(f"[PATCH] Rollback report: {rel(root, report_path)}")
    if errors:
        console_emit(f"[WARN] Rollback completed with {errors} warning(s).")
        return 1
    if code != 0:
        console_emit(f"[ERROR] Suite self-test failed after rollback: exit_code={code}")
        return code
    console_emit("[OK] Last patch rolled back.")
    return 0
