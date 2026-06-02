from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BridgeContext, BridgeError
from .paths import load_config, norm_rel, rel

LOGIC_DIR_NAMES = {
    "src", "crates", "crate", "plugins", "plugin", "tools", "scripts", "app", "apps",
    "engine", "runtime", "core", "lib", "libs", "modules", "systems", "providers",
    "services", "registry", "registries", "schema", "schemas", "editor", "render", "physics",
    "assets", "world", "scene", "ecs", "input", "ui", "tests", "test", "examples",
}

KEY_FILE_NAMES = {
    "cargo.toml", "cargo.lock", "package.json", "pnpm-lock.yaml", "yarn.lock",
    "pyproject.toml", "requirements.txt", "setup.py", "cmakelists.txt", "makefile",
    "meson.build", "build.gradle", "settings.gradle", "pom.xml", "go.mod", "go.sum",
    "readme.md", "readme.txt", "license", "license.md", "changelog.md",
}

LOGIC_EXTENSIONS = {
    ".rs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".cpp", ".c", ".h", ".hpp",
    ".cs", ".java", ".kt", ".swift", ".lua", ".rb", ".php", ".sql", ".glsl", ".hlsl",
    ".wgsl", ".shader", ".toml", ".json", ".yaml", ".yml", ".xml", ".md", ".txt",
}


def dataset_root(ctx: BridgeContext) -> Path:
    config = load_config(ctx)
    raw = config.get("dataSetDirectory") or ".takesome/dataSet"
    path = Path(str(raw))
    return (ctx.root / path).resolve() if not path.is_absolute() else path.resolve()


def dataset_dirs(ctx: BridgeContext) -> Dict[str, Path]:
    root = dataset_root(ctx)
    return {"root": root, "archives": root / "archives", "extracted": root / "extracted", "index": root / "index"}


def safe_dataset_path(ctx: BridgeContext, rel_or_path: str, must_exist: bool = True) -> Path:
    ds = dataset_root(ctx)
    raw = str(rel_or_path).replace("\\", "/").strip().strip('"')
    if not raw:
        raise BridgeError("dataset path is empty", "invalid_path")
    path = Path(raw)
    if not path.is_absolute():
        path = ds / norm_rel(raw)
    path = path.resolve()
    try:
        path.relative_to(ds)
    except ValueError:
        raise BridgeError("dataset path escapes dataSetDirectory", "unsafe_path", {"path": raw})
    if must_exist and not path.exists():
        raise BridgeError("dataset path does not exist", "not_found", {"path": raw})
    return path


def safe_extracted_path(ctx: BridgeContext, rel_or_path: str = "", must_exist: bool = True) -> Path:
    base = dataset_dirs(ctx)["extracted"]
    raw = str(rel_or_path or "").replace("\\", "/").strip().strip('"')
    if raw in {"", ".", "extracted", ".takesome/dataSet/extracted"}:
        path = base
    else:
        if raw.startswith("extracted/"):
            raw = raw[len("extracted/"):]
        path = Path(raw)
        if not path.is_absolute():
            path = base / norm_rel(raw)
    path = path.resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        raise BridgeError("dataset browser path escapes extracted directory", "unsafe_path", {"path": raw})
    if must_exist and not path.exists():
        raise BridgeError("dataset browser path does not exist", "not_found", {"path": raw})
    return path


def iter_archives(ctx: BridgeContext, recursive: bool = True) -> List[Path]:
    dirs = dataset_dirs(ctx)
    found: List[Path] = []
    for base in (dirs["archives"], dirs["root"]):
        if base.exists():
            found.extend(base.rglob("*.zip") if recursive else base.glob("*.zip"))
    return sorted(set(p for p in found if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)


def archive_info(ctx: BridgeContext, archive: Path) -> Dict[str, Any]:
    st = archive.stat()
    ds = dataset_root(ctx)
    return {"path": rel(ctx.root, archive), "dataset_relative_path": rel(ds, archive), "size_bytes": st.st_size, "modified_utc": int(st.st_mtime)}



def top_extracted_dirs(ctx: BridgeContext, limit: int = 20) -> List[Path]:
    extracted = dataset_dirs(ctx)["extracted"]
    if not extracted.exists():
        return []
    dirs = [p for p in extracted.iterdir() if p.is_dir()]
    return sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def path_logic_signals(path: Path) -> List[str]:
    parts = {part.lower() for part in path.parts}
    signals = sorted(parts & LOGIC_DIR_NAMES)
    name = path.name.lower()
    if name in KEY_FILE_NAMES:
        signals.append("key_file")
    if path.suffix.lower() in LOGIC_EXTENSIONS:
        signals.append("logic_ext")
    return sorted(set(signals))


def score_file(path: Path) -> int:
    score = 0
    signals = path_logic_signals(path)
    score += 3 * len([s for s in signals if s in LOGIC_DIR_NAMES])
    if "key_file" in signals:
        score += 8
    if path.suffix.lower() in {".rs", ".py", ".ts", ".tsx", ".cpp", ".h", ".hpp", ".cs", ".go"}:
        score += 5
    elif path.suffix.lower() in {".toml", ".json", ".yaml", ".yml"}:
        score += 3
    elif path.suffix.lower() in {".md", ".txt"}:
        score += 1
    return score


def read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": str(exc)}
