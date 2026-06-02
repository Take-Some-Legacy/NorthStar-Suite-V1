from __future__ import annotations

import subprocess
from pathlib import Path

from .console import console_emit
from .filesystem import best_effort_remove_path
from .paths import rel, safe_repo_path


def apply_delete_list(root: Path, *, emit=console_emit) -> int:
    """Apply root DELETE_FILES.txt as a best-effort migration hook.

    Locked files/directories must not block build/dev workflows. Unsafe entries are
    warned and skipped; failed deletions are kept for the next sync pass.
    """
    delete_file = root / "DELETE_FILES.txt"
    if not delete_file.exists():
        return 0

    emit(f"[MIGRATE] Applying {delete_file.name}")
    deleted = 0
    skipped = 0
    warnings = 0
    pending: list[str] = []
    lines = delete_file.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    for line_no, line in enumerate(lines, 1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            pending.append(line)
            continue
        try:
            target = safe_repo_path(root, raw)
            if target is None:
                skipped += 1
                warnings += 1
                pending.append(line)
                emit(f"[WARN] DELETE_FILES.txt:{line_no}: unsafe or root-escaped path skipped: {raw}")
                continue
            if target == delete_file.resolve():
                skipped += 1
                emit(f"[SKIP] DELETE_FILES.txt cannot delete itself through an entry: {raw}")
                continue
            was_dir = target.is_dir() and not target.is_symlink()
            result = best_effort_remove_path(root, target, quarantine_on_failure=True)
            if result.status == "deleted":
                deleted += 1
                kind = "dir " if was_dir else "file"
                suffix = f" ({result.message})" if result.message else ""
                emit(f"[DELETE] {kind} {rel(root, target)}{suffix}")
            elif result.status == "quarantined":
                deleted += 1
                emit(f"[MOVE] legacy path quarantined: {rel(root, target)} -> {result.message}")
            elif result.status == "missing":
                skipped += 1
                emit(f"[SKIP] missing {raw}")
            else:
                skipped += 1
                warnings += 1
                pending.append(line)
                emit(f"[WARN] Could not delete {rel(root, target)}: {result.message}; keeping entry and continuing")
        except Exception as exc:
            skipped += 1
            warnings += 1
            pending.append(line)
            emit(f"[WARN] DELETE_FILES.txt:{line_no}: {exc}; keeping entry and continuing")
    emit(f"[MIGRATE] DELETE_FILES.txt summary: deleted={deleted} skipped={skipped} warnings={warnings}")

    live_pending = [line for line in pending if line.strip() and not line.strip().startswith("#")]
    if live_pending:
        kept = ["# Entries below could not be deleted yet; next sync/build will retry them.", *live_pending]
        try:
            delete_file.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
            emit(f"[WARN] DELETE_FILES.txt kept with {len(live_pending)} pending entr{'y' if len(live_pending) == 1 else 'ies'}.")
        except OSError as exc:
            emit(f"[WARN] Failed to rewrite DELETE_FILES.txt: {exc}")
        return 0

    try:
        delete_file.unlink()
        emit("[DELETE] DELETE_FILES.txt")
    except OSError as exc:
        emit(f"[WARN] Failed to delete DELETE_FILES.txt: {exc}; continuing")
    return 0


def root_patch_files(root: Path) -> list[Path]:
    return sorted((p for p in root.glob("*.patch") if p.is_file()), key=lambda p: p.name.lower())


def apply_patch_files(root: Path, *, emit=console_emit) -> int:
    patches = root_patch_files(root)
    if not patches:
        emit("[SKIP] no root .patch files found")
        return 0

    errors = 0
    for patch in patches:
        emit(f"[PATCH] Applying {patch.name} from repository root")
        try:
            result = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(patch)],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            emit("[ERROR] git was not found; cannot apply .patch files")
            return 127
        if result.stdout.strip():
            for line in result.stdout.splitlines():
                emit(f"[PATCH] {line}")
        if result.returncode != 0:
            errors += 1
            emit(f"[ERROR] Failed to apply patch: {patch.name} exit_code={result.returncode}")
            for line in result.stderr.splitlines():
                emit(f"[ERROR] {line}")
            emit(f"[WARN] Patch kept for review: {patch.name}")
            continue
        if result.stderr.strip():
            for line in result.stderr.splitlines():
                emit(f"[WARN] {line}")
        try:
            patch.unlink()
            emit(f"[DELETE] patch {patch.name}")
        except OSError as exc:
            errors += 1
            emit(f"[WARN] Patch applied but could not be deleted: {patch.name}: {exc}")
    if errors:
        emit(f"[WARN] Patch sync completed with {errors} warning/error(s).")
        return 1
    emit(f"[OK] Applied {len(patches)} patch file(s).")
    return 0


def sync_workspace_state(root: Path, *, emit=console_emit) -> int:
    emit("[SYNC] North Star workspace sync started")
    delete_code = apply_delete_list(root, emit=emit)
    patch_code = apply_patch_files(root, emit=emit)
    post_delete_code = apply_delete_list(root, emit=emit) if patch_code == 0 else 0
    code = delete_code or patch_code or post_delete_code
    if code == 0:
        emit("[OK] Workspace sync completed")
    else:
        emit(f"[WARN] Workspace sync completed with exit_code={code}")
    return code
