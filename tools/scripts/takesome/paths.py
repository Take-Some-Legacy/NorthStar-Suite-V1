from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]
def repo_root() -> Path:
    env = os.environ.get("NEWENGINE_REPO_ROOT")
    if env:
        return Path(env).resolve()
    return repo_root_from_script()


def project_root_from_suite(suite: Path) -> Path:
    """Return the source repository root associated with a suite directory.

    `EngineRepository` and `.takesome` are independent roots.  In the old local
    layout the suite lived at `repo/.takesome`, but relocation mode may place the
    suite/work state on another disk.  When that happens, `NEWENGINE_REPO_ROOT`
    is the only authoritative source root and the suite parent must not be used
    as duplicate authority.
    """
    env = os.environ.get("NEWENGINE_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return suite.resolve().parent


def suite_root(project_root: Path) -> Path:
    """Canonical Take Some script-suite working root.

    `NEWENGINE_SUITE_ROOT` / `TAKESOME_SUITE_ROOT` may point to a directory
    outside the source repository.  This lets the dataset, logs, incidents and
    status caches live on a separate disk while `EngineRepository` remains a
    clean source tree.
    """
    env = os.environ.get("NEWENGINE_SUITE_ROOT") or os.environ.get("TAKESOME_SUITE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return project_root.resolve() / ".takesome"


def suite_path(project_root: Path, *parts: str) -> Path:
    return suite_root(project_root).joinpath(*parts)

def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
def utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)
def safe_repo_path(root: Path, raw: str) -> Path | None:
    cleaned = raw.strip().strip('"').strip("'").replace("\\", "/")
    if not cleaned or cleaned.startswith("#"):
        return None
    if cleaned.startswith("/") or ":" in cleaned.split("/")[0] or cleaned == "." or cleaned == ".." or cleaned.startswith("../") or "/../" in cleaned:
        raise ValueError(f"Unsafe DELETE_FILES.txt entry: {raw!r}")
    target = (root / cleaned).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"DELETE_FILES.txt entry escapes repository root: {raw!r}")
    return target
