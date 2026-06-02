from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .build_info import file_manifest, sha256_file
from .constants import DLL_EXT, ROOT_EXCLUDED_DIRS
from .git_tools import git_repo_info
from .paths import now_stamp, rel, suite_path, utc_iso
from .status_cache import write_status_snapshot
from .plugin_build.manifest import discover_plugin_names, manifest as plugin_manifest
from .tools.descriptors import discover_tools


DYNAMIC_LIBRARY_EXTENSIONS = {".dll", ".so", ".dylib"}


def _read_text(path: Path, limit: int = 1024 * 1024) -> str:
    try:
        data = path.read_bytes()[:limit]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _toml_value(line: str) -> str:
    if "=" not in line:
        return ""
    return line.split("=", 1)[1].strip().strip('"').strip("'")


def _parse_string_array(text: str, key: str) -> list[str]:
    # Tiny TOML subset parser for workspace members / crate-type. It handles the
    # shapes used in this repository without requiring Python 3.11 tomllib.
    result: list[str] = []
    lines = text.splitlines()
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line.startswith(key) or "=" not in line:
            continue
        rhs = line.split("=", 1)[1].strip()
        if rhs.startswith("[") and rhs.endswith("]"):
            inside = rhs.strip("[]")
        elif rhs.startswith("["):
            parts = [rhs]
            for follow in lines[index + 1 :]:
                parts.append(follow.strip())
                if "]" in follow:
                    break
            inside = "\n".join(parts).split("[", 1)[1].rsplit("]", 1)[0]
        else:
            continue
        for item in inside.replace("\n", ",").split(","):
            cleaned = item.strip().strip('"').strip("'")
            if cleaned:
                result.append(cleaned)
        break
    return result


def cargo_manifest_record(root: Path, cargo_toml: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": rel(root, cargo_toml),
        "exists": cargo_toml.exists(),
        "package_name": "",
        "package_version": "",
        "lib_name": "",
        "crate_type": [],
        "workspace_members": [],
        "kind": "missing",
        "hash": "",
    }
    if not cargo_toml.exists():
        return record
    text = _read_text(cargo_toml)
    record["hash"] = sha256_file(cargo_toml)
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]")
            continue
        if section == "package" and line.startswith("name") and "=" in line:
            record["package_name"] = _toml_value(line)
        elif section == "package" and line.startswith("version") and "=" in line:
            record["package_version"] = _toml_value(line)
        elif section == "lib" and line.startswith("name") and "=" in line:
            record["lib_name"] = _toml_value(line)
    record["workspace_members"] = _parse_string_array(text, "members")
    record["crate_type"] = _parse_string_array(text, "crate-type")
    if record["workspace_members"]:
        record["kind"] = "workspace"
    elif record["package_name"]:
        record["kind"] = "package"
    else:
        record["kind"] = "cargo"
    if not record["lib_name"] and record["package_name"]:
        record["lib_name"] = str(record["package_name"]).replace("-", "_")
    return record


def _direct_dylibs(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file() and child.suffix.lower() in DYNAMIC_LIBRARY_EXTENSIONS:
            result.append({
                "name": child.name,
                "size_bytes": child.stat().st_size,
                "modified_utc": _mtime_utc(child),
            })
    return result


def _mtime_utc(path: Path) -> str:
    try:
        import datetime as _dt

        return _dt.datetime.fromtimestamp(path.stat().st_mtime, _dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except OSError:
        return ""


def _count_files(directory: Path) -> dict[str, int]:
    files = dirs = cargo = rust = toml = json_files = md = bat = 0
    if not directory.exists() or not directory.is_dir():
        return {
            "files": 0,
            "dirs": 0,
            "cargo_toml": 0,
            "rust": 0,
            "toml": 0,
            "json": 0,
            "markdown": 0,
            "bat_cmd": 0,
        }
    for current, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames if d not in ROOT_EXCLUDED_DIRS and d not in {".git", "target", "node_modules", "__pycache__"}]
        dirs += len(dirnames)
        files += len(filenames)
        for name in filenames:
            suffix = Path(name).suffix.lower()
            if name == "Cargo.toml":
                cargo += 1
            if suffix == ".rs":
                rust += 1
            elif suffix == ".toml":
                toml += 1
            elif suffix == ".json":
                json_files += 1
            elif suffix in {".md", ".markdown"}:
                md += 1
            elif suffix in {".bat", ".cmd"}:
                bat += 1
    return {
        "files": files,
        "dirs": dirs,
        "cargo_toml": cargo,
        "rust": rust,
        "toml": toml,
        "json": json_files,
        "markdown": md,
        "bat_cmd": bat,
    }


def _cargo_packages_under(root: Path, directory: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not directory.exists():
        return result
    for cargo in sorted(directory.rglob("Cargo.toml"), key=lambda p: p.as_posix().lower()):
        if any(part in ROOT_EXCLUDED_DIRS or part in {"target", ".git"} for part in cargo.parts):
            continue
        rec = cargo_manifest_record(root, cargo)
        if rec.get("kind") == "package":
            result.append(rec)
    return result


def plugin_record(root: Path, plugin_name: str, manifest_plugins: set[str]) -> dict[str, Any]:
    plugin_dir = root / "Plugins" / plugin_name
    root_cargo = cargo_manifest_record(root, plugin_dir / "Cargo.toml")
    packages = _cargo_packages_under(root, plugin_dir)
    cdylib_packages = [p for p in packages if "cdylib" in p.get("crate_type", [])]
    target = plugin_dir / "target"
    return {
        "name": plugin_name,
        "path": rel(root, plugin_dir),
        "exists": plugin_dir.exists(),
        "declared_in_build_manifest": plugin_name in manifest_plugins,
        "git": git_repo_info(root, plugin_dir),
        "root_cargo": root_cargo,
        "packages": packages,
        "package_count": len(packages),
        "cdylib_package_count": len(cdylib_packages),
        "cdylib_packages": [p.get("package_name", "") for p in cdylib_packages],
        "build_entrypoints": sorted([p.name for p in plugin_dir.glob("build*.bat")]) if plugin_dir.exists() else [],
        "readme": rel(root, plugin_dir / "README.md") if (plugin_dir / "README.md").exists() else "",
        "target_present": target.exists(),
        "target_debug_dylibs": _direct_dylibs(target / "debug"),
        "target_release_dylibs": _direct_dylibs(target / "release"),
    }


def codec_worker_record(root: Path, name: str, manifest_codecs: set[str]) -> dict[str, Any]:
    codec_dir = root / "Plugins" / "AssetManager" / "codecs" / name
    cargo = cargo_manifest_record(root, codec_dir / "Cargo.toml")
    target = codec_dir / "target"
    return {
        "name": name,
        "path": rel(root, codec_dir),
        "exists": codec_dir.exists(),
        "declared_in_build_manifest": name in manifest_codecs,
        "git": git_repo_info(root, codec_dir),
        "cargo": cargo,
        "is_cdylib": "cdylib" in cargo.get("crate_type", []),
        "target_present": target.exists(),
        "target_debug_dylibs": _direct_dylibs(target / "debug"),
        "target_release_dylibs": _direct_dylibs(target / "release"),
    }


def directory_record(root: Path, label: str, path: Path, category: str) -> dict[str, Any]:
    return {
        "label": label,
        "category": category,
        "path": rel(root, path),
        "exists": path.exists(),
        "git": git_repo_info(root, path),
        "cargo": cargo_manifest_record(root, path / "Cargo.toml") if (path / "Cargo.toml").exists() else None,
        "counts": _count_files(path),
    }


def build_workspace_registry(root: Path) -> dict[str, Any]:
    m = plugin_manifest(root)
    declared_plugins = {str(x) for x in m.get("plugins", [])}
    declared_codecs = {str(x) for x in m.get("codecWorkers", [])}
    plugin_names = discover_plugin_names(root)
    codec_root = root / "Plugins" / "AssetManager" / "codecs"
    discovered_codecs = [p.name for p in sorted(codec_root.iterdir(), key=lambda p: p.name.lower()) if p.is_dir() and (p / "Cargo.toml").exists()] if codec_root.exists() else []
    codec_names = []
    seen_codecs: set[str] = set()
    for name in [*m.get("codecWorkers", []), *discovered_codecs]:
        key = str(name).lower()
        if key in seen_codecs:
            continue
        seen_codecs.add(key)
        codec_names.append(str(name))

    tools, tool_warnings = discover_tools(root)
    engine_root = root / "NewEngine" / "neocore2"
    runtime_plugin_dir = engine_root / "plugins"
    runtime_codec_dir = runtime_plugin_dir / "codecs"
    root_entries = [
        directory_record(root, "workspace-root", root, "root"),
        directory_record(root, "engine", engine_root, "engine"),
        directory_record(root, "plugins-source", root / "Plugins", "plugins"),
        directory_record(root, "importers", root / "Importers", "importers"),
        directory_record(root, "tools", root / "tools", "tools"),
        directory_record(root, "docs", root / "docs", "docs"),
    ]
    payload = {
        "schema": "takesome.workspaceRegistry.v1",
        "generated_utc": utc_iso(),
        "root": str(root.resolve()),
        "repo_name": root.name,
        "git": git_repo_info(root, root),
        "summary": {
            "plugin_count": len(plugin_names),
            "declared_plugin_count": len(declared_plugins),
            "codec_worker_count": len(codec_names),
            "tool_descriptor_count": len(tools),
            "runtime_plugin_dylib_count": len(_direct_dylibs(runtime_plugin_dir)),
            "runtime_codec_dylib_count": len(_direct_dylibs(runtime_codec_dir)),
        },
        "plugin_manifest": {
            "path": rel(root, root / "Plugins" / "build_manifest.json"),
            "file": file_manifest(root, root / "Plugins" / "build_manifest.json"),
            "declared_plugins": sorted(declared_plugins, key=str.lower),
            "declared_codec_workers": sorted(declared_codecs, key=str.lower),
        },
        "directories": root_entries,
        "plugins": [plugin_record(root, name, declared_plugins) for name in plugin_names],
        "codec_workers": [codec_worker_record(root, name, declared_codecs) for name in codec_names],
        "runtime_artifacts": {
            "plugin_dir": rel(root, runtime_plugin_dir),
            "codec_dir": rel(root, runtime_codec_dir),
            "plugins": _direct_dylibs(runtime_plugin_dir),
            "codecs": _direct_dylibs(runtime_codec_dir),
        },
        "tools": {
            "warnings": tool_warnings,
            "descriptors": [tool.as_record(root) for tool in tools],
        },
    }
    return payload


def write_registry_files(root: Path, payload: dict[str, Any], *, output: str = "") -> tuple[Path, Path]:
    out_dir = Path(output).resolve() if output else suite_path(root, "workspace")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    json_path = out_dir / f"workspace-registry-{stamp}.json"
    md_path = out_dir / f"workspace-registry-{stamp}.md"
    latest_json = out_dir / "workspace-registry-latest.json"
    latest_md = out_dir / "workspace-registry-latest.md"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    lines = [
        "# North Star / Take Some workspace registry",
        "",
        f"- generated_utc: `{payload.get('generated_utc', '')}`",
        f"- root: `{payload.get('root', '')}`",
        f"- git_status: `{payload.get('git', {}).get('status', '')}`",
        f"- git_branch: `{payload.get('git', {}).get('branch', '')}`",
        "",
        "## Summary",
        "",
    ]
    summary = payload.get("summary", {})
    for key in sorted(summary):
        lines.append(f"- {key}: `{summary[key]}`")
    lines.extend([
        "",
        "## Plugins",
        "",
        "| name | manifest | git | packages | cdylib | target | path |",
        "|---|---:|---|---:|---:|---|---|",
    ])
    for item in payload.get("plugins", []):
        lines.append(
            "| {name} | {manifest} | {git} | {packages} | {cdylib} | {target} | `{path}` |".format(
                name=item.get("name", ""),
                manifest="yes" if item.get("declared_in_build_manifest") else "no",
                git=item.get("git", {}).get("status", ""),
                packages=item.get("package_count", 0),
                cdylib=item.get("cdylib_package_count", 0),
                target="yes" if item.get("target_present") else "no",
                path=item.get("path", ""),
            )
        )
    lines.extend([
        "",
        "## Codec workers",
        "",
        "| name | manifest | git | cdylib | target | path |",
        "|---|---:|---|---:|---|---|",
    ])
    for item in payload.get("codec_workers", []):
        lines.append(
            "| {name} | {manifest} | {git} | {cdylib} | {target} | `{path}` |".format(
                name=item.get("name", ""),
                manifest="yes" if item.get("declared_in_build_manifest") else "no",
                git=item.get("git", {}).get("status", ""),
                cdylib="yes" if item.get("is_cdylib") else "no",
                target="yes" if item.get("target_present") else "no",
                path=item.get("path", ""),
            )
        )
    lines.extend([
        "",
        "## Workspace directories",
        "",
        "| label | category | exists | git | files | Cargo.toml | path |",
        "|---|---|---:|---|---:|---:|---|",
    ])
    for item in payload.get("directories", []):
        counts = item.get("counts", {}) or {}
        lines.append(
            "| {label} | {category} | {exists} | {git} | {files} | {cargo} | `{path}` |".format(
                label=item.get("label", ""),
                category=item.get("category", ""),
                exists="yes" if item.get("exists") else "no",
                git=item.get("git", {}).get("status", ""),
                files=counts.get("files", 0),
                cargo=counts.get("cargo_toml", 0),
                path=item.get("path", ""),
            )
        )
    tool_warnings = payload.get("tools", {}).get("warnings", [])
    if tool_warnings:
        lines.extend(["", "## Tool descriptor warnings", ""])
        for warning in tool_warnings:
            lines.append(f"- `{warning}`")
    md_text = "\n".join(lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    write_status_snapshot(
        root,
        "workspace-registry",
        payload,
        summary_markdown=md_text,
        source="workspace_registry.write_registry_files",
    )
    return json_path, md_path


def workspace_registry_command(root: Path, ns: argparse.Namespace) -> int:
    payload = build_workspace_registry(root)
    json_path, md_path = write_registry_files(root, payload, output=getattr(ns, "output", "") or "")
    print(f"[OK] Workspace registry JSON: {rel(root, json_path)}")
    print(f"[OK] Workspace registry MD  : {rel(root, md_path)}")
    print(f"[STATE] plugins={payload['summary']['plugin_count']} codecs={payload['summary']['codec_worker_count']} tools={payload['summary']['tool_descriptor_count']}")
    git_status = payload.get("git", {}).get("status", "")
    print(f"[STATE] root_git={git_status}")
    return 0
