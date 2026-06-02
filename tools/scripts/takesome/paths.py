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
    """Return the project root that owns a Take Some suite directory.

    The project root and the suite root are intentionally different:
    `project_root/.takesome` is the script-suite working area, while
    `project_root` remains the source/workspace root.
    """
    return suite.resolve().parent


def suite_root(project_root: Path) -> Path:
    """Canonical Take Some script-suite working root.

    All generated script-plane state must be rooted here, never beside the
    project root through ad-hoc `.takesome` concatenation.
    """
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
