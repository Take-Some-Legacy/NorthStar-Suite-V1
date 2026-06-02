from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..platforms import BuildPlatform, is_build_platform_token, normalize_build_platform


@dataclass(frozen=True)
class BuildPluginArgs:
    selected: str | None
    build_type: str
    platform: BuildPlatform
    force: bool


def parse_build_plugin_args(args: list[str]) -> BuildPluginArgs:
    selected: str | None = None
    build_type = "dev"
    platform = normalize_build_platform(os.environ.get("NEWENGINE_BUILD_PLATFORM") or os.environ.get("NEWENGINE_PLUGIN_BUILD_PLATFORM"))
    force = bool(os.environ.get("NEWENGINE_FORCE_PLUGIN_REBUILD") == "1")
    index = 0
    while index < len(args):
        arg = args[index]
        low = arg.lower()
        if low in {"--force", "-f"}:
            force = True
        elif low in {"dev", "debug", "release"}:
            build_type = low
        elif low in {"--platform", "--build-platform"}:
            if index + 1 >= len(args):
                raise ValueError(f"{arg} expects a platform value")
            platform = normalize_build_platform(args[index + 1])
            index += 1
        elif low.startswith("--platform="):
            platform = normalize_build_platform(arg.split("=", 1)[1])
        elif low.startswith("--build-platform="):
            platform = normalize_build_platform(arg.split("=", 1)[1])
        elif low in {"--target", "--rust-target"}:
            if index + 1 >= len(args):
                raise ValueError(f"{arg} expects a Rust target triple")
            platform = normalize_build_platform(args[index + 1])
            index += 1
        elif low.startswith("--target="):
            platform = normalize_build_platform(arg.split("=", 1)[1])
        elif low.startswith("--rust-target="):
            platform = normalize_build_platform(arg.split("=", 1)[1])
        elif low in {"help", "--help", "-h"}:
            return BuildPluginArgs("__help__", build_type, platform, force)
        elif is_build_platform_token(arg):
            platform = normalize_build_platform(arg)
        elif selected is None:
            selected = arg
        else:
            raise ValueError(f"Unknown extra argument: {arg}")
        index += 1
    return BuildPluginArgs(selected, build_type, platform, force)


def looks_like_plugin_dir_arg(raw: str, plugin_dir: Path) -> bool:
    token = raw.strip().strip('"').strip("'")
    if not token:
        return False
    plugin_name = plugin_dir.resolve().name.lower()
    normalized = token.replace("\\", "/").rstrip("/")
    if normalized.lower().endswith("/" + plugin_name) or normalized.lower() == plugin_name:
        return True
    try:
        return Path(token).resolve() == plugin_dir.resolve()
    except Exception:
        return False


def normalize_plugin_entry_args(plugin_dir: Path, entry: str, args: list[str]) -> list[str]:
    cleaned = list(args)
    if cleaned and cleaned[0] == "--":
        cleaned = cleaned[1:]
    while cleaned:
        first = cleaned[0]
        low = first.strip().strip('"').strip("'").lower()
        if looks_like_plugin_dir_arg(first, plugin_dir):
            cleaned.pop(0)
            continue
        if low in {"build", entry.lower()} and low not in {"dev", "debug", "release", "--force", "-f"}:
            cleaned.pop(0)
            continue
        break
    return cleaned
