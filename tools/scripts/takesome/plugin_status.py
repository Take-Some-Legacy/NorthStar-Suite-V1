from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cargo import (
    build_state_root,
    codec_enabled,
    fingerprint_workspace,
    read_text,
    select_runtime_crate,
    stamp_path,
)
from .paths import now_stamp, rel, utc_iso, engine_core_root, plugins_root
from .status_cache import write_status_snapshot
from .platforms import BuildPlatform, normalize_build_platform, platform_artifact_root
from .console import (
    ANSI_BOLD,
    ANSI_BRIGHT_CYAN,
    ANSI_BRIGHT_GREEN,
    ANSI_BRIGHT_MAGENTA,
    ANSI_BRIGHT_RED,
    ANSI_BRIGHT_WHITE,
    ANSI_BRIGHT_YELLOW,
    ANSI_DARK_GRAY,
    ANSI_DIM,
    color_enabled,
    console_emit,
    paint,
)

_VALID_BUILD_TYPES = {"dev", "debug", "release"}


def _read_build_manifest(root: Path) -> dict[str, Any]:
    path = plugins_root(root) / "build_manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _discover_plugin_names(root: Path) -> list[str]:
    m = _read_build_manifest(root)
    names = [str(item) for item in m.get("plugins", []) if str(item).strip()]
    if names:
        return names
    plugins_dir = plugins_root(root)
    if not plugins_dir.exists():
        return []
    return sorted(
        child.name
        for child in plugins_dir.iterdir()
        if child.is_dir() and (child / "Cargo.toml").exists()
    )


def _discover_codec_worker_names(root: Path) -> list[str]:
    m = _read_build_manifest(root)
    names = [str(item) for item in m.get("codecWorkers", []) if str(item).strip()]
    if names:
        return names
    codecs_dir = plugins_root(root) / "AssetManager" / "codecs"
    if not codecs_dir.exists():
        return []
    return sorted(
        child.name
        for child in codecs_dir.iterdir()
        if child.is_dir() and (child / "Cargo.toml").exists()
    )


def normalize_build_type(build_type: str) -> str:
    low = (build_type or "dev").lower()
    return low if low in _VALID_BUILD_TYPES else "dev"


def _engine_root(root: Path) -> Path:
    return engine_core_root(root)


def _plugin_out_dir(root: Path, kind: str, platform: BuildPlatform) -> Path:
    base = platform_artifact_root(root, platform)
    return base / "codecs" if kind == "codec-worker" else base


def _target_workspace(root: Path, kind: str, name: str) -> Path:
    if kind == "codec-worker":
        return plugins_root(root) / "AssetManager" / "codecs" / name
    return plugins_root(root) / name


def _read_stamp(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _status_from_stamp(
    *,
    stamp: dict[str, Any],
    fingerprint: str,
    build_type: str,
    package_name: str,
    version: str,
    platform: BuildPlatform,
) -> tuple[bool, str]:
    if not stamp:
        return False, "stamp missing or unreadable"
    mismatches: list[str] = []
    if stamp.get("fingerprint") != fingerprint:
        mismatches.append("fingerprint changed")
    if stamp.get("build_type") != build_type:
        mismatches.append("build type changed")
    if stamp.get("package_name") != package_name:
        mismatches.append("package changed")
    if stamp.get("version") != version:
        mismatches.append("version changed")
    if stamp.get("platform") != platform.id:
        mismatches.append("platform changed")
    if str(stamp.get("rust_target", "")) != (platform.rust_target or ""):
        mismatches.append("Rust target changed")
    if mismatches:
        return False, ", ".join(mismatches)
    return True, "stamp matched installed artifact"


def plugin_status_record(root: Path, *, name: str, kind: str, build_type: str, force: bool = False, platform_id: str | None = None) -> dict[str, Any]:
    build_type = normalize_build_type(build_type)
    platform = normalize_build_platform(platform_id)
    workspace = _target_workspace(root, kind, name)
    out_dir = _plugin_out_dir(root, kind, platform)
    base: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "build_type": build_type,
        "platform": platform.id,
        "rust_target": platform.rust_target or "",
        "workspace": rel(root, workspace),
        "exists": workspace.exists(),
        "status": "need rebuild",
        "status_key": "need_rebuild",
        "needs_rebuild": True,
        "up_to_date": False,
        "reason": "not inspected",
        "package_name": "",
        "version": "",
        "artifact": "",
        "artifact_exists": False,
        "stamp": "",
        "stamp_exists": False,
        "fingerprint": "",
    }

    if not workspace.exists() or not (workspace / "Cargo.toml").exists():
        base.update({
            "status": "missing source",
            "status_key": "missing_source",
            "needs_rebuild": False,
            "reason": "workspace or Cargo.toml is missing",
        })
        return base

    if kind == "codec-worker" and not codec_enabled(read_text(workspace / "Cargo.toml")):
        base.update({
            "status": "disabled",
            "status_key": "disabled",
            "needs_rebuild": False,
            "reason": "package.metadata.newengine.codec.enabled=false",
        })
        return base

    try:
        meta = select_runtime_crate(workspace)
    except Exception as exc:
        base.update({
            "status": "invalid metadata",
            "status_key": "invalid_metadata",
            "needs_rebuild": True,
            "reason": str(exc),
        })
        return base

    install_stem = meta.runtime_install_stem
    canonical_dll = f"{install_stem}-{meta.version}-{build_type}{platform.library_ext}"
    output = out_dir / canonical_dll
    fingerprint = fingerprint_workspace(workspace)
    spath = stamp_path(root, kind, name, canonical_dll, platform_id=platform.id)
    stamp = _read_stamp(spath)
    stamp_ok, stamp_reason = _status_from_stamp(
        stamp=stamp,
        fingerprint=fingerprint,
        build_type=build_type,
        package_name=meta.package_name,
        version=meta.version,
        platform=platform,
    )

    base.update({
        "package_name": meta.package_name,
        "version": meta.version,
        "install_name": install_stem,
        "provider_route": meta.provider_route,
        "artifact": rel(root, output),
        "artifact_exists": output.exists(),
        "stamp": rel(root, spath),
        "stamp_exists": spath.exists(),
        "fingerprint": fingerprint,
    })

    if force:
        base.update({
            "status": "need rebuild",
            "status_key": "need_rebuild",
            "needs_rebuild": True,
            "up_to_date": False,
            "reason": "forced rebuild requested",
        })
        return base

    if not output.exists():
        base.update({
            "status": "need rebuild",
            "status_key": "need_rebuild",
            "needs_rebuild": True,
            "up_to_date": False,
            "reason": "installed runtime artifact is missing",
        })
        return base

    if not stamp_ok:
        base.update({
            "status": "need rebuild",
            "status_key": "need_rebuild",
            "needs_rebuild": True,
            "up_to_date": False,
            "reason": stamp_reason,
        })
        return base

    base.update({
        "status": "up to date",
        "status_key": "up_to_date",
        "needs_rebuild": False,
        "up_to_date": True,
        "reason": stamp_reason,
    })
    return base


def collect_plugin_status(root: Path, *, build_type: str = "dev", force: bool = False, platform_id: str | None = None) -> dict[str, Any]:
    build_type = normalize_build_type(build_type)
    platform = normalize_build_platform(platform_id)
    plugin_names = _discover_plugin_names(root)
    codec_names = _discover_codec_worker_names(root)
    records: list[dict[str, Any]] = []
    for name in plugin_names:
        records.append(plugin_status_record(root, name=name, kind="plugin", build_type=build_type, force=force, platform_id=platform.id))
    for name in codec_names:
        records.append(plugin_status_record(root, name=name, kind="codec-worker", build_type=build_type, force=force, platform_id=platform.id))

    summary = {
        "total": len(records),
        "plugins": sum(1 for r in records if r.get("kind") == "plugin"),
        "codec_workers": sum(1 for r in records if r.get("kind") == "codec-worker"),
        "up_to_date": sum(1 for r in records if r.get("status_key") == "up_to_date"),
        "need_rebuild": sum(1 for r in records if r.get("needs_rebuild")),
        "missing_source": sum(1 for r in records if r.get("status_key") == "missing_source"),
        "disabled": sum(1 for r in records if r.get("status_key") == "disabled"),
        "invalid_metadata": sum(1 for r in records if r.get("status_key") == "invalid_metadata"),
    }
    return {
        "schema": "takesome.pluginStatus.v1",
        "generated_utc": utc_iso(),
        "build_type": build_type,
        "platform": platform.id,
        "rust_target": platform.rust_target or "",
        "artifact_extension": platform.library_ext,
        "force": force,
        "summary": summary,
        "records": records,
    }


def stale_sync_targets(status: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for record in status.get("records", []):
        if not record.get("needs_rebuild"):
            continue
        if record.get("status_key") in {"missing_source", "disabled"}:
            continue
        name = str(record.get("name", ""))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result


def status_report_paths(root: Path) -> tuple[Path, Path, Path, Path]:
    out_dir = build_state_root(root)
    stamp = now_stamp()
    json_path = out_dir / f"plugin-status-{stamp}.json"
    md_path = out_dir / f"plugin-status-{stamp}.md"
    latest_json = out_dir / "plugin-status-latest.json"
    latest_md = out_dir / "plugin-status-latest.md"
    return json_path, md_path, latest_json, latest_md


def _status_tone(status_key: str) -> str:
    if status_key == "up_to_date":
        return "OK"
    if status_key in {"disabled", "missing_source"}:
        return "SKIP"
    return "STALE"


def _status_style(status_key: str) -> str:
    if status_key == "up_to_date":
        return ANSI_BRIGHT_GREEN + ANSI_BOLD
    if status_key == "need_rebuild":
        return ANSI_BRIGHT_YELLOW + ANSI_BOLD
    if status_key == "invalid_metadata":
        return ANSI_BRIGHT_RED + ANSI_BOLD
    if status_key in {"disabled", "missing_source"}:
        return ANSI_DIM
    return ANSI_BRIGHT_CYAN


def _status_symbol(status_key: str) -> str:
    return {
        "up_to_date": "✓",
        "need_rebuild": "!",
        "invalid_metadata": "!",
        "disabled": "-",
        "missing_source": "?",
    }.get(status_key, "?")


def _status_label(status_key: str, status: str | None = None) -> str:
    clean = status or status_key.replace("_", " ")
    label = f"{_status_symbol(status_key)} {clean}"
    return paint(label, _status_style(status_key)) if color_enabled() else label


def _color_count(value: Any, status_key: str) -> str:
    text = str(value)
    return paint(text, _status_style(status_key)) if color_enabled() else text


def _color_path(path: Any) -> str:
    text = str(path)
    return paint(text, ANSI_DIM) if color_enabled() else text


def _color_name(name: Any) -> str:
    text = str(name)
    return paint(text, ANSI_BRIGHT_WHITE + ANSI_BOLD) if color_enabled() else text


def _color_reason(reason: Any) -> str:
    text = str(reason)
    return paint(text, ANSI_DARK_GRAY) if color_enabled() else text


def _emit_status_header(status: dict[str, Any], latest_json: Path, latest_md: Path) -> None:
    summary = status.get("summary", {})
    build_type = str(status.get("build_type", ""))
    platform_id = str(status.get("platform", ""))
    force = bool(status.get("force"))
    mode = "forced" if force else "normal"
    console_emit("[PLUGIN] Plugin status snapshot")
    print(
        "  "
        + "build_type="
        + (paint(build_type, ANSI_BRIGHT_MAGENTA + ANSI_BOLD) if color_enabled() else build_type)
        + "  platform="
        + (paint(platform_id, ANSI_BRIGHT_MAGENTA + ANSI_BOLD) if color_enabled() else platform_id)
        + "  mode="
        + (paint(mode, ANSI_BRIGHT_CYAN) if color_enabled() else mode)
    )
    print(
        "  "
        + "total="
        + _color_count(summary.get("total", 0), "")
        + "  up_to_date="
        + _color_count(summary.get("up_to_date", 0), "up_to_date")
        + "  need_rebuild="
        + _color_count(summary.get("need_rebuild", 0), "need_rebuild")
        + "  disabled="
        + _color_count(summary.get("disabled", 0), "disabled")
        + "  invalid="
        + _color_count(summary.get("invalid_metadata", 0), "invalid_metadata")
    )
    print("  json: " + _color_path(latest_json))
    print("  md:   " + _color_path(latest_md))


def _emit_status_groups(status: dict[str, Any]) -> None:
    records = list(status.get("records", []))
    groups = [
        ("need rebuild", "need_rebuild"),
        ("invalid metadata", "invalid_metadata"),
        ("missing source", "missing_source"),
        ("disabled", "disabled"),
        ("up to date", "up_to_date"),
    ]
    for title, key in groups:
        subset = [r for r in records if r.get("status_key") == key]
        if not subset:
            continue
        label = _status_label(key, title)
        print()
        print((paint("== ", ANSI_DARK_GRAY) if color_enabled() else "== ") + label + (paint(" ==", ANSI_DARK_GRAY) if color_enabled() else " =="))
        for record in subset:
            kind = str(record.get("kind", ""))
            name = str(record.get("name", ""))
            package = str(record.get("package_name", ""))
            version = str(record.get("version", ""))
            artifact = str(record.get("artifact", ""))
            reason = str(record.get("reason", ""))
            title_part = f"{kind}: " + _color_name(name)
            if package:
                title_part += "  " + (paint(package, ANSI_BRIGHT_CYAN) if color_enabled() else package)
            if version:
                title_part += " " + (paint("v" + version, ANSI_BRIGHT_MAGENTA) if color_enabled() else "v" + version)
            print("  " + title_part)
            if artifact:
                print("    artifact: " + _color_path(artifact))
            if reason:
                print("    reason:   " + _color_reason(reason))


def render_plugin_status_markdown(status: dict[str, Any]) -> str:
    summary = status.get("summary", {})
    lines = [
        "# Plugin Status",
        "",
        f"- generated_utc: `{status.get('generated_utc', '')}`",
        f"- build_type: `{status.get('build_type', '')}`",
        f"- platform: `{status.get('platform', '')}`",
        f"- rust_target: `{status.get('rust_target', '')}`",
        f"- artifact_extension: `{status.get('artifact_extension', '')}`",
        f"- total: `{summary.get('total', 0)}`",
        f"- plugins_up_to_date: `{summary.get('up_to_date', 0)}`",
        f"- plugins_need_rebuild: `{summary.get('need_rebuild', 0)}`",
        "",
        "| state | kind | name | package | version | artifact | stamp | reason |",
        "|---|---|---|---|---:|---|---|---|",
    ]
    for record in status.get("records", []):
        lines.append(
            "| {state} | {kind} | {name} | {package} | {version} | `{artifact}` | `{stamp}` | {reason} |".format(
                state=_status_tone(str(record.get("status_key", ""))),
                kind=record.get("kind", ""),
                name=record.get("name", ""),
                package=record.get("package_name", ""),
                version=record.get("version", ""),
                artifact=record.get("artifact", ""),
                stamp=record.get("stamp", ""),
                reason=str(record.get("reason", "")).replace("|", "/"),
            )
        )
    return "\n".join(lines) + "\n"


def write_plugin_status_report(root: Path, status: dict[str, Any] | None = None, *, build_type: str = "dev", force: bool = False, platform_id: str | None = None) -> tuple[Path, Path]:
    status = status or collect_plugin_status(root, build_type=build_type, force=force, platform_id=platform_id)
    json_path, md_path, latest_json, latest_md = status_report_paths(root)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(status, indent=2, ensure_ascii=False)
    md_text = render_plugin_status_markdown(status)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    write_status_snapshot(
        root,
        "plugin-status",
        status,
        summary_markdown=md_text,
        source="plugin_status.write_plugin_status_report",
    )
    return latest_json, latest_md


def plugin_status_command(root: Path, args: list[str]) -> int:
    build_type = "dev"
    force = False
    platform_id = None
    index = 0
    while index < len(args):
        arg = args[index]
        low = arg.lower()
        if low in _VALID_BUILD_TYPES:
            build_type = low
        elif low in {"--force", "-f"}:
            force = True
        elif low in {"--platform", "--build-platform", "--target", "--rust-target"}:
            if index + 1 >= len(args):
                print(f"[ERROR] {arg} expects a value")
                return 2
            platform_id = normalize_build_platform(args[index + 1]).id
            index += 1
        elif low.startswith(("--platform=", "--build-platform=", "--target=", "--rust-target=")):
            platform_id = normalize_build_platform(arg.split("=", 1)[1]).id
        elif low in {"help", "--help", "-h"}:
            print("Usage: takesome.py plugin-status [dev|debug|release] [--platform <id|target>] [--force]")
            return 0
        else:
            print(f"[ERROR] Unknown plugin-status argument: {arg}")
            return 2
        index += 1
    status = collect_plugin_status(root, build_type=build_type, force=force, platform_id=platform_id)
    latest_json, latest_md = write_plugin_status_report(root, status)
    _emit_status_header(status, latest_json, latest_md)
    _emit_status_groups(status)
    return 0
