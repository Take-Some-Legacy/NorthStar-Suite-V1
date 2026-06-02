from __future__ import annotations

import platform as py_platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .paths import suite_path, engine_core_root


@dataclass(frozen=True)
class BuildPlatform:
    """A build target platform selected by the workspace UI.

    The platform is a first-class build dimension. It decides the Rust target
    triple, dynamic-library extension, status/stamp partition and where non-host
    artifacts are staged.
    """

    id: str
    label: str
    detail: str
    rust_target: str | None
    library_ext: str
    host: bool = False


def _machine_family() -> str:
    machine = (py_platform.machine() or "").lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86", "i386", "i686"}:
        return "x86"
    return machine or "unknown"


def host_platform_id() -> str:
    machine = _machine_family()
    if sys.platform.startswith("win"):
        if machine == "arm64":
            return "windows-arm64-msvc"
        if machine == "x86":
            return "windows-x86-msvc"
        return "windows-x64-msvc"
    if sys.platform == "darwin":
        return "macos-arm64" if machine == "arm64" else "macos-x64"
    if sys.platform.startswith("linux"):
        return "linux-arm64-gnu" if machine == "arm64" else "linux-x64-gnu"
    return f"host-{machine}"


def _standard_platforms() -> dict[str, BuildPlatform]:
    host_id = host_platform_id()
    specs = {
        "windows-x64-msvc": BuildPlatform("windows-x64-msvc", "Windows x64 MSVC", "x86_64-pc-windows-msvc; produces .dll", "x86_64-pc-windows-msvc", ".dll"),
        "windows-arm64-msvc": BuildPlatform("windows-arm64-msvc", "Windows ARM64 MSVC", "aarch64-pc-windows-msvc; produces .dll", "aarch64-pc-windows-msvc", ".dll"),
        "linux-x64-gnu": BuildPlatform("linux-x64-gnu", "Linux x64 GNU", "x86_64-unknown-linux-gnu; produces .so", "x86_64-unknown-linux-gnu", ".so"),
        "linux-arm64-gnu": BuildPlatform("linux-arm64-gnu", "Linux ARM64 GNU", "aarch64-unknown-linux-gnu; produces .so", "aarch64-unknown-linux-gnu", ".so"),
        "macos-arm64": BuildPlatform("macos-arm64", "macOS ARM64", "aarch64-apple-darwin; produces .dylib", "aarch64-apple-darwin", ".dylib"),
        "macos-x64": BuildPlatform("macos-x64", "macOS x64", "x86_64-apple-darwin; produces .dylib", "x86_64-apple-darwin", ".dylib"),
    }
    if host_id in specs:
        hp = specs[host_id]
        specs[host_id] = BuildPlatform(hp.id, hp.label, hp.detail + "; current host", None, hp.library_ext, True)
    else:
        ext = ".dll" if sys.platform.startswith("win") else (".dylib" if sys.platform == "darwin" else ".so")
        specs[host_id] = BuildPlatform(host_id, f"Current host ({host_id})", "current host target; no Cargo --target override", None, ext, True)
    return specs


def available_build_platforms() -> list[BuildPlatform]:
    specs = _standard_platforms()
    host_id = host_platform_id()
    order = [host_id, "windows-x64-msvc", "linux-x64-gnu", "macos-arm64", "macos-x64", "windows-arm64-msvc", "linux-arm64-gnu"]
    seen: set[str] = set()
    result: list[BuildPlatform] = []
    for key in order:
        if key in specs and key not in seen:
            seen.add(key)
            result.append(specs[key])
    for key in sorted(specs):
        if key not in seen:
            result.append(specs[key])
    return result


def _ext_for_target(target: str | None) -> str:
    text = (target or "").lower()
    if "windows" in text:
        return ".dll"
    if "apple-darwin" in text or "darwin" in text:
        return ".dylib"
    return ".so"


def _id_for_target(target: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", target.strip().lower()).strip("-._")
    return clean or "custom-target"


def normalize_build_platform(raw: str | None = None) -> BuildPlatform:
    value = (raw or "").strip().strip('"').strip("'").lower()
    specs = _standard_platforms()
    aliases = {
        "": host_platform_id(),
        "host": host_platform_id(),
        "current": host_platform_id(),
        "native": host_platform_id(),
        "default": host_platform_id(),
        "win": "windows-x64-msvc",
        "windows": "windows-x64-msvc",
        "windows-x64": "windows-x64-msvc",
        "win64": "windows-x64-msvc",
        "msvc": "windows-x64-msvc",
        "windows-arm64": "windows-arm64-msvc",
        "linux": "linux-x64-gnu",
        "linux-x64": "linux-x64-gnu",
        "linux-gnu": "linux-x64-gnu",
        "linux-arm64": "linux-arm64-gnu",
        "mac": "macos-arm64",
        "macos": "macos-arm64",
        "darwin": "macos-arm64",
        "macos-aarch64": "macos-arm64",
        "macos-arm64": "macos-arm64",
        "macos-x64": "macos-x64",
        "macos-x86_64": "macos-x64",
    }
    key = aliases.get(value, value)
    if key in specs:
        return specs[key]
    for platform in specs.values():
        if platform.rust_target and value == platform.rust_target.lower():
            host = platform.id == host_platform_id()
            return BuildPlatform(platform.id, platform.label, platform.detail, None if host else platform.rust_target, platform.library_ext, host)
    if value:
        # Accept an explicit Rust target triple. This keeps the script-plane open
        # for toolchains not yet listed in the menu.
        ext = _ext_for_target(value)
        pid = _id_for_target(value)
        host = pid == host_platform_id()
        return BuildPlatform(pid, f"Custom target {value}", f"explicit Cargo --target {value}; produces {ext}", None if host else value, ext, host)
    return specs[host_platform_id()]



def build_platform_aliases() -> set[str]:
    aliases = {
        "host", "current", "native", "default",
        "win", "windows", "windows-x64", "win64", "msvc", "windows-arm64",
        "linux", "linux-x64", "linux-gnu", "linux-arm64",
        "mac", "macos", "darwin", "macos-aarch64", "macos-arm64", "macos-x64", "macos-x86_64",
    }
    specs = _standard_platforms()
    aliases.update(specs.keys())
    aliases.update(platform.rust_target for platform in specs.values() if platform.rust_target)
    return {str(item).lower() for item in aliases if item}


def is_build_platform_token(raw: str) -> bool:
    value = (raw or "").strip().strip('"').strip("'").lower()
    return value in build_platform_aliases()

def build_platform_from_args(args: list[str]) -> BuildPlatform:
    it = iter(range(len(args)))
    for i in it:
        arg = args[i]
        low = arg.lower()
        if low in {"--platform", "--build-platform"} and i + 1 < len(args):
            return normalize_build_platform(args[i + 1])
        if low.startswith("--platform="):
            return normalize_build_platform(arg.split("=", 1)[1])
        if low.startswith("--build-platform="):
            return normalize_build_platform(arg.split("=", 1)[1])
        if low in {"--target", "--rust-target"} and i + 1 < len(args):
            return normalize_build_platform(args[i + 1])
        if low.startswith("--target="):
            return normalize_build_platform(arg.split("=", 1)[1])
        if low.startswith("--rust-target="):
            return normalize_build_platform(arg.split("=", 1)[1])
    return normalize_build_platform(None)


def cargo_target_args(platform: BuildPlatform) -> list[str]:
    return ["--target", platform.rust_target] if platform.rust_target else []


def cargo_profile_dir(build_type: str, platform: BuildPlatform) -> str:
    profile = "release" if build_type == "release" else "debug"
    if platform.rust_target:
        return str(Path(platform.rust_target) / profile)
    return profile


def platform_artifact_root(root: Path, platform: BuildPlatform) -> Path:
    if platform.host:
        return engine_core_root(root) / "plugins"
    return suite_path(root, "build-artifacts", platform.id, "plugins")
