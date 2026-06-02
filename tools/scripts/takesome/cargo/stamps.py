from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..logs import TeeLog
from ..paths import rel, utc_iso
from .profiles import build_state_root


def fingerprint_workspace(root: Path) -> str:
    excluded = {"target", "build-state", "logs", "cache", ".git", ".northstar", ".takesome", "__pycache__"}
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if any(part in excluded for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        rp = path.relative_to(root).as_posix()
        h.update(rp.encode("utf-8", "surrogateescape"))
        h.update(str(st.st_size).encode())
        h.update(str(st.st_mtime_ns).encode())
    return h.hexdigest()


def stamp_path(root: Path, kind: str, display_name: str, canonical_dll: str, *, platform_id: str = "host") -> Path:
    safe_platform = (platform_id or "host").replace("/", "-").replace("\\", "-")
    return build_state_root(root) / "stamps" / safe_platform / kind / display_name / f"{canonical_dll}.stamp.json"


def stamp_matches(path: Path, *, fingerprint: str, output_dll: Path, build_type: str, package_name: str, version: str, platform_id: str = "host", rust_target: str = "") -> bool:
    if not output_dll.exists() or not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        data.get("fingerprint") == fingerprint
        and data.get("build_type") == build_type
        and data.get("package_name") == package_name
        and data.get("version") == version
        and data.get("platform") == platform_id
        and str(data.get("rust_target", "")) == rust_target
    )


def write_stamp(path: Path, *, fingerprint: str, output_dll: Path, build_type: str, package_name: str, version: str, kind: str, display_name: str, platform_id: str = "host", rust_target: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "tools/scripts/takesome.py",
        "updated_utc": utc_iso(),
        "display_name": display_name,
        "kind": kind,
        "build_type": build_type,
        "platform": platform_id,
        "rust_target": rust_target,
        "package_name": package_name,
        "version": version,
        "output_dll": str(output_dll),
        "fingerprint": fingerprint,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def cleanup_old_stamps(root: Path, kind: str, display_name: str, keep_stamp: Path, log: TeeLog, *, platform_id: str = "host") -> None:
    safe_platform = (platform_id or "host").replace("/", "-").replace("\\", "-")
    directory = build_state_root(root) / "stamps" / safe_platform / kind / display_name
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.stamp.json")):
        if path.resolve() == keep_stamp.resolve():
            continue
        try:
            log.emit(f"[CLEAN] deleting old build stamp: {rel(root, path)}")
            path.unlink()
        except OSError as exc:
            log.emit(f"[WARN] Failed to delete stamp {path}: {exc}")
