from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

ENGINE_REPO_ENV = "NORTHSTAR_ENGINE_REPO"
LEGACY_REPO_ENV = "NEWENGINE_REPO_ROOT"
SUITE_ROOT_ENVS = ("NORTHSTAR_SUITE_ROOT", "NEWENGINE_SUITE_ROOT", "TAKESOME_SUITE_ROOT")
DEFAULT_EXTERNAL_SUITE_ROOTS = (Path(r"D:\\TakeSomeData"),)
DEFAULT_REPOS_ROOT = Path(r"C:\\Users\\HUAWEI\\Documents\\Repos")


def _valid_external_suite_root(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and (path / "dataSet").exists()
    except OSError:
        return False


def repo_root_from_script() -> Path:
    # noesis/suite/paths.py -> <repo>/noesis/suite/paths.py
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    env = os.environ.get(LEGACY_REPO_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return repo_root_from_script()


def engine_repo_root(project_root: Path | None = None) -> Path:
    """Authoritative EngineRepo root.

    `NORTHSTAR_ENGINE_REPO` is the future-proof source repository location for
    engine code and providers. During migration it may point either at
    `<workspace>/EngineRepo` or at the current repository root. A nested
    `EngineRepo/` is accepted only after it contains real source markers; an
    empty scaffolding directory must never shadow the current working layout.
    """
    root = (project_root or repo_root()).resolve()
    env = os.environ.get(ENGINE_REPO_ENV)
    if env:
        candidate = Path(env).expanduser().resolve()
        if _is_engine_repo(candidate):
            return candidate
        fallback = _legacy_engine_repo_root(root)
        if fallback != candidate:
            return fallback
        return candidate
    nested = root / "EngineRepo"
    if _is_engine_repo(nested):
        return nested.resolve()
    return _legacy_engine_repo_root(root)


def _legacy_engine_repo_root(root: Path) -> Path:
    return root.resolve()


def _is_engine_repo(path: Path) -> bool:
    return (path / "NewEngine" / "neocore2" / "Cargo.toml").exists() and (path / "Plugins" / "build_manifest.json").exists()


def engine_core_root(project_root: Path | None = None) -> Path:
    return engine_repo_root(project_root) / "NewEngine" / "neocore2"


def plugins_root(project_root: Path | None = None) -> Path:
    return engine_repo_root(project_root) / "Plugins"


def importers_root(project_root: Path | None = None) -> Path:
    return engine_repo_root(project_root) / "Importers"


def engine_repo_path(project_root: Path | None, *parts: str) -> Path:
    return engine_repo_root(project_root).joinpath(*parts)


def project_root_from_suite(suite: Path) -> Path:
    """Return the Suite host/workspace root associated with a suite directory."""
    env = os.environ.get(LEGACY_REPO_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return suite.resolve().parent


def suite_root(project_root: Path) -> Path:
    """Canonical NorthStarSuite working root.

    `NORTHSTAR_SUITE_ROOT` / `NEWENGINE_SUITE_ROOT` / `TAKESOME_SUITE_ROOT` may
    point to a directory outside the engine source repository.  This lets the
    dataset, logs, incidents and status caches live on a separate disk while
    `EngineRepo` remains a clean source tree.
    """
    for name in SUITE_ROOT_ENVS:
        env = os.environ.get(name)
        if env:
            return Path(env).expanduser().resolve()
    for candidate in DEFAULT_EXTERNAL_SUITE_ROOTS:
        if _valid_external_suite_root(candidate):
            return candidate.resolve()
    return project_root.resolve() / ".takesome"


def suite_path(project_root: Path, *parts: str) -> Path:
    return suite_root(project_root).joinpath(*parts)


def repos_root() -> Path:
    """Canonical root for repository artifacts and working repos."""
    return DEFAULT_REPOS_ROOT.resolve()


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
