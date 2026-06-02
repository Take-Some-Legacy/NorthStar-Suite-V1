from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .paths import rel
from .cargo.process import cargo_exe

ENGINE_REL = Path("EngineRepo") / "NewEngine" / "neocore2"
IMPORTER_DESCRIPTOR = ENGINE_REL / "config" / "importers" / "importer_descriptors.v1.json"
PIPELINE_GRAPH = ENGINE_REL / "config" / "assets" / "import_pipeline.generated_graph.v1.json"
INVALIDATION_PLAN = ENGINE_REL / "config" / "assets" / "import_pipeline.invalidation_plan.v1.json"
NEUI_PACKER_MANIFEST = Path("tools") / "northstar" / "neui_packer" / "Cargo.toml"


@dataclass(frozen=True)
class ImportWorkerResult:
    worker_id: str
    source_ref: str
    target_ref: str
    cache_key: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class ImportManifestContext:
    path: Path
    data: dict[str, Any]
    descriptor: dict[str, Any]
    rel_path: str
    content_hash: str
    settings_hash: str


def deterministic_cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    h.update(b"northstar.assets.import.cache_key.v1\0")
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def combined_source_hash(root: Path, manifest_path: Path, manifest: dict[str, Any]) -> str:
    """Hash the manifest plus declared local source inputs.

    This keeps deterministic cache keys sensitive to font/source edits without letting
    runtime consumers parse those source formats. Missing optional inputs contribute a
    stable marker; missing required inputs also contribute a marker and are reported by
    the dedicated importer when executed.
    """
    h = hashlib.sha256()
    h.update(b"northstar.assets.source_hash.v1\0")
    h.update(file_hash(manifest_path).encode("ascii"))
    h.update(b"\0")
    for source in declared_local_inputs(root, manifest):
        h.update(source["ref"].encode("utf-8"))
        h.update(b"\0")
        source_path = root / ENGINE_REL / source["ref"]
        if source_path.exists() and source_path.is_file():
            h.update(file_hash(source_path).encode("ascii"))
        else:
            marker = "missing_optional" if source.get("optional") else "missing_required"
            h.update(marker.encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


def load_importer_descriptors(root: Path) -> dict[str, Any]:
    path = root / IMPORTER_DESCRIPTOR
    return json.loads(path.read_text(encoding="utf-8"))


def importer_descriptor_by_suffix(root: Path) -> list[tuple[str, dict[str, Any]]]:
    descriptors = load_importer_descriptors(root).get("importers", [])
    pairs: list[tuple[str, dict[str, Any]]] = []
    for descriptor in descriptors:
        for ext in descriptor.get("source_extensions", []):
            suffix = str(ext).lower().lstrip(".")
            if suffix:
                pairs.append((suffix, descriptor))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


def match_importer(path: Path, suffixes: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    name = path.name.lower()
    path_text = str(path).replace("\\", "/").lower()
    for suffix, descriptor in suffixes:
        if name.endswith(suffix) or path_text.endswith(suffix):
            return descriptor
    return None


def discover_import_manifests(root: Path) -> list[Path]:
    base = root / ENGINE_REL / "assets"
    if not base.exists():
        return []
    return sorted(
        path
        for path in base.rglob("*.import.json")
        if path.is_file() and ".import." in path.name
    )


def load_manifest_contexts(root: Path) -> list[ImportManifestContext]:
    suffixes = importer_descriptor_by_suffix(root)
    contexts: list[ImportManifestContext] = []
    for path in discover_import_manifests(root):
        descriptor = match_importer(path, suffixes)
        if descriptor is None:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rel_path = rel(root, path)
        content_hash = combined_source_hash(root, path, data)
        settings_hash = stable_json_hash(data)
        contexts.append(ImportManifestContext(
            path=path,
            data=data,
            descriptor=descriptor,
            rel_path=rel_path,
            content_hash=content_hash,
            settings_hash=settings_hash,
        ))
    return contexts


def neui_packer_exe(root: Path) -> Path | None:
    name = "northstar-neui-packer.exe" if os.name == "nt" else "northstar-neui-packer"
    candidates = [
        root / "tools" / "exe" / name,
        root / "tools" / "northstar" / "neui_packer" / "target" / "debug" / name,
        root / "tools" / "northstar" / "neui_packer" / "target" / "release" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run_neui_packer(root: Path, check: bool = False) -> int:
    exe = neui_packer_exe(root)
    if exe is not None:
        cmd = [str(exe), "--root", str(root), "--all"]
        if check:
            cmd.append("--check")
    else:
        manifest = root / NEUI_PACKER_MANIFEST
        if not manifest.exists():
            print(f"[ERROR] NEUI packer manifest missing: {rel(root, manifest)}")
            return 2
        cmd = [cargo_exe() or "cargo", "run", "--manifest-path", str(manifest), "--", "--root", str(root), "--all"]
        if check:
            cmd.append("--check")
    print("[CMD] " + " ".join(cmd))
    try:
        return subprocess.call(cmd, cwd=root)
    except FileNotFoundError as exc:
        print(f"[ERROR] NEUI packer requires cargo or a built northstar-neui-packer executable: {exc}")
        return 127


def build_runtime_graph(root: Path) -> dict[str, Any]:
    contexts = load_manifest_contexts(root)
    sources: list[dict[str, Any]] = []
    runtime_assets: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    cache_keys: list[dict[str, Any]] = []
    worker_results: list[ImportWorkerResult] = []

    for ctx in contexts:
        importer_id = str(ctx.descriptor.get("importer_id", ""))
        importer_version = str(ctx.descriptor.get("version", ctx.descriptor.get("importer_version", "1")))
        source_kind = first_or_default(ctx.descriptor.get("source_content_kinds"), str(ctx.data.get("content_kind", "source.import_descriptor")))
        target_ref, runtime_kind, owner_gateway = runtime_target_for_manifest(ctx)
        cache_key = deterministic_cache_key(
            ctx.rel_path,
            ctx.content_hash,
            importer_id,
            importer_version,
            ctx.settings_hash,
            sys.platform,
        )
        sources.append({
            "source_ref": ctx.rel_path,
            "content_hash": ctx.content_hash,
            "content_kind": source_kind,
            "importer_id": importer_id,
            "importer_version": importer_version,
        })
        runtime_assets.append({
            "asset_ref": target_ref,
            "content_kind": runtime_kind,
            "owner_gateway": owner_gateway,
            "cache_key": cache_key,
        })
        cache_keys.append({
            "schema": "northstar.assets.cache_key.v1",
            "source_ref": ctx.rel_path,
            "source_hash": ctx.content_hash,
            "importer_id": importer_id,
            "importer_version": importer_version,
            "settings_hash": ctx.settings_hash,
            "platform": sys.platform,
            "cache_key": cache_key,
        })
        worker_results.append(ImportWorkerResult(
            worker_id=importer_id,
            source_ref=ctx.rel_path,
            target_ref=target_ref,
            cache_key=cache_key,
            status="planned",
            detail="descriptor-driven import worker plan",
        ))
        for dep in dependencies_from_manifest(root, ctx):
            dependencies.append({"from_ref": target_ref, "to_ref": dep, "reason": "import_descriptor_dependency"})

    dependencies = sorted(dedup_dicts(dependencies), key=lambda d: (d["from_ref"], d["to_ref"], d["reason"]))
    graph = {
        "schema": "northstar.assets.runtime_graph.generated.v1",
        "sources": sorted(sources, key=lambda d: d["source_ref"]),
        "runtime_assets": sorted(runtime_assets, key=lambda d: d["asset_ref"]),
        "dependencies": dependencies,
        "cache_keys": sorted(cache_keys, key=lambda d: d["source_ref"]),
        "invalidation_index": build_invalidation_index(sources, runtime_assets, dependencies),
        "worker_results": [asdict(item) for item in sorted(worker_results, key=lambda r: (r.source_ref, r.target_ref))],
        "cache_key_policy": {
            "algorithm": "sha256",
            "namespace": "northstar.assets.import.cache_key.v1",
            "inputs": [
                "source_ref",
                "source_hash",
                "importer_id",
                "importer_version",
                "settings_hash",
                "target_platform",
            ],
            "deterministic": True,
        },
    }
    return graph


def runtime_target_for_manifest(ctx: ImportManifestContext) -> tuple[str, str, str]:
    importer_id = str(ctx.descriptor.get("importer_id", ""))
    data = ctx.data
    if importer_id == "northstar.importer.neui.v1":
        target = data.get("target_asset", "ui/editor/generated.neui")
        target_ref = f"assets/{str(target).removeprefix('assets/')}@{entry_name(data)}"
        return target_ref, "ui_dictionary", "engine.assets.ui"
    if importer_id == "northstar.importer.yft_font.v1":
        target = str(data.get("target_asset", "ui/fonts/editor.yft"))
        default_face = str(data.get("runtime", {}).get("default_face", "")).split("@")[-1] or "font_dictionary"
        target_ref = f"assets/{target.removeprefix('assets/')}@{default_face}"
        return target_ref, "font_dictionary", str(data.get("semantic_gateway", "engine.ui.text"))
    target = data.get("target_asset", ctx.path.with_suffix("").name)
    target_ref = f"assets/{str(target).removeprefix('assets/')}@runtime"
    return target_ref, first_or_default(ctx.descriptor.get("runtime_outputs"), "runtime_asset"), str(ctx.descriptor.get("owner_gateway", "engine.assets"))


def first_or_default(value: Any, default: str) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str) and value:
        return value
    return default


def entry_name(data: dict[str, Any]) -> str:
    entry_ref = str(data.get("entry_ref", ""))
    if "@" in entry_ref:
        return entry_ref.rsplit("@", 1)[1]
    return str(data.get("entry", "surface"))


def declared_local_inputs(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for face in manifest.get("faces", []):
        if not isinstance(face, dict):
            continue
        source = str(face.get("source", "")).strip()
        if source:
            out.append({"ref": source.replace("\\", "/"), "optional": bool(face.get("optional", False))})
    return sorted(out, key=lambda item: item["ref"])


def dependencies_from_manifest(root: Path, ctx: ImportManifestContext) -> list[str]:
    data = ctx.data
    out: list[str] = []
    theme = data.get("theme_ref")
    if isinstance(theme, str) and theme:
        out.append(theme)
    font_dictionary = data.get("font_dictionary")
    if isinstance(font_dictionary, str) and font_dictionary:
        out.append(font_dictionary)
    for key in ("component_libraries", "imports", "runtime_outputs"):
        for value in data.get(key, []):
            if isinstance(value, str) and value:
                out.append(value)
    for source in declared_local_inputs(root, data):
        out.append(f"source:{source['ref']}")
    fallback_stack = data.get("runtime", {}).get("fallback_stack", []) if isinstance(data.get("runtime"), dict) else []
    for value in fallback_stack:
        if isinstance(value, str) and value.startswith("ui/"):
            out.append(value)
    return sorted(set(out))


def dedup_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def build_invalidation_index(sources: list[dict[str, Any]], runtime_assets: list[dict[str, Any]], dependencies: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, list[str]] = {}
    by_dependency: dict[str, list[str]] = {}
    for source, runtime in zip(sorted(sources, key=lambda d: d["source_ref"]), sorted(runtime_assets, key=lambda d: d["asset_ref"])):
        by_source.setdefault(source["source_ref"], []).append(runtime["asset_ref"])
    for dep in dependencies:
        by_dependency.setdefault(dep["to_ref"], []).append(dep["from_ref"])
    return {
        "schema": "northstar.assets.invalidation_index.v1",
        "strategy": "reverse_dependency_walk",
        "source_to_runtime": {k: sorted(set(v)) for k, v in sorted(by_source.items())},
        "dependency_to_runtime": {k: sorted(set(v)) for k, v in sorted(by_dependency.items())},
    }


def plan_invalidation(graph: dict[str, Any], changed_sources: list[str]) -> dict[str, Any]:
    index = graph.get("invalidation_index", {})
    source_to_runtime = index.get("source_to_runtime", {}) if isinstance(index, dict) else {}
    dependency_to_runtime = index.get("dependency_to_runtime", {}) if isinstance(index, dict) else {}
    affected: set[str] = set()
    for changed in changed_sources:
        normalized = changed.replace("\\", "/").lstrip("./")
        variants = {normalized}
        engine_prefix = str(ENGINE_REL).replace("\\", "/") + "/"
        if normalized.startswith(engine_prefix):
            variants.add(normalized[len(engine_prefix):])
        variants.add(f"source:{normalized}")
        for candidate in list(variants):
            if candidate.startswith(engine_prefix):
                variants.add("source:" + candidate[len(engine_prefix):])
        for candidate in variants:
            affected.update(source_to_runtime.get(candidate, []))
            affected.update(dependency_to_runtime.get(candidate, []))
    cache_by_asset = {asset.get("asset_ref"): asset.get("cache_key") for asset in graph.get("runtime_assets", []) if isinstance(asset, dict)}
    invalidated_keys = sorted({str(cache_by_asset.get(asset)) for asset in affected if cache_by_asset.get(asset)})
    return {
        "schema": "northstar.assets.invalidation_plan.v1",
        "changed_sources": sorted(changed_sources),
        "invalidated_cache_keys": invalidated_keys,
        "affected_runtime_assets": sorted(affected),
        "reason": "descriptor reverse dependency invalidation",
    }


def import_pipeline_command(root: Path, ns: argparse.Namespace) -> int:
    check = bool(getattr(ns, "check", False))
    changed_sources = list(getattr(ns, "changed_source", []) or [])
    graph = build_runtime_graph(root)
    out = root / PIPELINE_GRAPH
    if not check:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[OK] runtime asset graph written: {rel(root, out)}")
    else:
        print(f"[CHECK] runtime asset graph sources={len(graph['sources'])} nodes={len(graph['runtime_assets'])} dependencies={len(graph['dependencies'])}")
    if changed_sources:
        plan = plan_invalidation(graph, changed_sources)
        plan_path = root / INVALIDATION_PLAN
        if not check or bool(getattr(ns, "write_invalidation_plan", False)):
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"[OK] invalidation plan written: {rel(root, plan_path)}")
        else:
            print(f"[CHECK] invalidation affected={len(plan['affected_runtime_assets'])} cache_keys={len(plan['invalidated_cache_keys'])}")
    if getattr(ns, "skip_neui", False):
        print("[SKIP] .neui packing skipped by request")
        return 0
    return run_neui_packer(root, check=check)
