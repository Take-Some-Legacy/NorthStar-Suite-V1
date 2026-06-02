from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

from .console import (
    ANSI_BOLD,
    ANSI_BRIGHT_CYAN,
    ANSI_BRIGHT_GREEN,
    ANSI_BRIGHT_RED,
    ANSI_BRIGHT_WHITE,
    ANSI_BRIGHT_YELLOW,
    ANSI_DARK_GRAY,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_YELLOW,
    color_enabled,
    paint,
    strip_ansi,
)
from .constants import DLL_EXT
from .platforms import normalize_build_platform
from .paths import rel, plugins_root

DYNAMIC_LIBRARY_EXTENSIONS = {".dll", ".so", ".dylib"}
DEFAULT_ARTIFACT_SCAN_DIRS = ("", "debug", "release", "debug/deps", "release/deps")


@dataclass(frozen=True)
class WorkspaceRowSubject:
    """Path facts for one selectable workspace row.

    Actions own what a row means. Status rendering owns how that row is
    inspected. This keeps build/clean/importer menus from copying status logic.
    """

    key: str
    label: str
    category: str
    workspace_dir: Path
    target_dir: Path
    detail_path: Path | None = None
    artifact_scan_dirs: tuple[str, ...] = DEFAULT_ARTIFACT_SCAN_DIRS


@dataclass(frozen=True)
class RowStatusPart:
    label: str
    value: str
    tone: str = "info"


class RowStatusProbe(Protocol):
    def __call__(self, root: Path, subject: WorkspaceRowSubject) -> RowStatusPart | None: ...


_STATUS_TONES: dict[str, str] = {
    "ok": ANSI_BRIGHT_GREEN + ANSI_BOLD,
    "good": ANSI_BRIGHT_GREEN + ANSI_BOLD,
    "info": ANSI_BRIGHT_CYAN,
    "warn": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
    "bad": ANSI_BRIGHT_RED + ANSI_BOLD,
    "muted": ANSI_DIM,
    "label": ANSI_DARK_GRAY,
    "path": ANSI_BRIGHT_WHITE,
    "category": ANSI_YELLOW,
    "count": ANSI_GREEN + ANSI_BOLD,
}


def _style_for_tone(tone: str) -> str:
    return _STATUS_TONES.get(tone, ANSI_BRIGHT_CYAN)


def render_status_part(part: RowStatusPart, *, colored: bool = True) -> str:
    text = f"{part.label}: {part.value}"
    if not colored or not color_enabled():
        return strip_ansi(text)
    return paint(f"{part.label}:", ANSI_DARK_GRAY) + " " + paint(part.value, _style_for_tone(part.tone))


def render_status_parts(parts: Sequence[RowStatusPart], *, colored: bool = True) -> str:
    return "  ".join(render_status_part(part, colored=colored) for part in parts if part is not None)


def direct_dynamic_libraries(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    result: list[Path] = []
    for child in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if child.is_file() and child.suffix.lower() in DYNAMIC_LIBRARY_EXTENSIONS:
            result.append(child)
    return result


def dynamic_libraries_for_subject(subject: WorkspaceRowSubject) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for raw_subdir in subject.artifact_scan_dirs:
        directory = subject.target_dir / raw_subdir if raw_subdir else subject.target_dir
        for dll in direct_dynamic_libraries(directory):
            key = str(dll.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(dll)
    return result




class PluginSyncStatusProbe:
    def __init__(self, build_type: str = "dev", platform_id: str | None = None) -> None:
        low = (build_type or "dev").lower()
        self.build_type = low if low in {"dev", "debug", "release"} else "dev"
        self.platform = normalize_build_platform(platform_id)
        self._cache: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}

    def __call__(self, root: Path, subject: WorkspaceRowSubject) -> RowStatusPart | None:
        if subject.category not in {"plugin", "codec"}:
            return None
        # Lazy import: workspace_status is used by plugin_build.interactive, while
        # plugin_status needs plugin_build.manifest. Keeping this import local avoids
        # a package-initialization cycle.
        from .plugin_status import plugin_status_record

        kind = "codec-worker" if subject.category == "codec" else "plugin"
        name = subject.label
        # CleanTarget labels are user-facing strings such as "Plugin: X" and
        # "Codec: Y". Prefer the stable subject key when available so status
        # probes never inspect a fake package named "Plugin: X".
        if subject.key.startswith("plugin:") or subject.key.startswith("codec:"):
            name = subject.key.split(":", 1)[1]
        key = (str(root.resolve()), kind, name.lower(), self.build_type, self.platform.id)
        record = self._cache.get(key)
        if record is None:
            record = plugin_status_record(root, name=name, kind=kind, build_type=self.build_type, platform_id=self.platform.id)
            self._cache[key] = record
        if record.get("status_key") == "up_to_date":
            return RowStatusPart("plugins", "up to date", "ok")
        if record.get("needs_rebuild"):
            return RowStatusPart("plugins", "need rebuild", "warn")
        return RowStatusPart("plugins", str(record.get("status", "skip")), "muted")

class TargetPresenceProbe:
    def __call__(self, root: Path, subject: WorkspaceRowSubject) -> RowStatusPart:
        if subject.target_dir.exists():
            return RowStatusPart("target", "present", "ok")
        return RowStatusPart("target", "missing", "muted")


class TargetDllProbe:
    """Report whether a target directory contains dynamic libraries.

    Root-level DLLs are called out first because they usually mean a direct
    artifact folder. Cargo profile/deps folders are still counted so Rust builds
    do not appear dead merely because their artifacts live under debug/release.
    """

    def __call__(self, root: Path, subject: WorkspaceRowSubject) -> RowStatusPart:
        if not subject.target_dir.exists():
            return RowStatusPart("build", "n/a", "muted")
        root_dlls = direct_dynamic_libraries(subject.target_dir)
        all_dlls = dynamic_libraries_for_subject(subject)
        if root_dlls:
            suffix = "dll" if len(root_dlls) == 1 else "dlls"
            return RowStatusPart("build", f"{len(root_dlls)} root {suffix}", "ok")
        if all_dlls:
            suffix = "dll" if len(all_dlls) == 1 else "dlls"
            return RowStatusPart("build", f"{len(all_dlls)} profile {suffix}", "ok")
        return RowStatusPart("build", f"no {DLL_EXT}", "warn")


class DetailPathProbe:
    def __call__(self, root: Path, subject: WorkspaceRowSubject) -> RowStatusPart | None:
        path = subject.detail_path or subject.target_dir
        try:
            value = rel(root, path)
        except Exception:
            value = str(path)
        return RowStatusPart(subject.category, value, "path")


class WorkspaceRowStatusProvider:
    """Composite status provider for console rows.

    Menus pass row values in; probes decide what is displayed. Adding another
    status column should mean adding a probe, not editing every action.
    """

    def __init__(self, root: Path, probes: Iterable[RowStatusProbe] | None = None, *, build_type: str = "dev", platform_id: str | None = None) -> None:
        self.root = root
        low = (build_type or "dev").lower()
        self.build_type = low if low in {"dev", "debug", "release"} else "dev"
        self.platform = normalize_build_platform(platform_id)
        self.probes = tuple(probes or (PluginSyncStatusProbe(self.build_type, self.platform.id), TargetPresenceProbe(), TargetDllProbe(), DetailPathProbe()))

    def parts_for_subject(self, subject: WorkspaceRowSubject) -> list[RowStatusPart]:
        parts: list[RowStatusPart] = []
        for probe in self.probes:
            part = probe(self.root, subject)
            if part is not None:
                parts.append(part)
        return parts

    def render_subject(self, subject: WorkspaceRowSubject, *, colored: bool = True) -> str:
        return render_status_parts(self.parts_for_subject(subject), colored=colored)

    def __call__(self, row: Any, *, colored: bool = True) -> str:
        subject = workspace_row_subject(row, self.root)
        if subject is None:
            detail = getattr(row, "detail", "") or ""
            return detail if colored else strip_ansi(detail)
        return self.render_subject(subject, colored=colored)


def make_workspace_status_provider(root: Path, probes: Iterable[RowStatusProbe] | None = None, *, build_type: str = "dev", platform_id: str | None = None) -> WorkspaceRowStatusProvider:
    return WorkspaceRowStatusProvider(root, probes=probes, build_type=build_type, platform_id=platform_id)


def workspace_row_subject(row: Any, root: Path) -> WorkspaceRowSubject | None:
    """Convert common selectable values into a status subject.

    This intentionally accepts duck-typed rows so commands do not need to import
    one shared action-specific dataclass just to render statuses.
    """

    value = getattr(row, "value", row)
    if isinstance(value, WorkspaceRowSubject):
        return value

    # CleanTarget-like objects.
    if all(hasattr(value, name) for name in ("key", "label", "path", "category")):
        target_dir = Path(getattr(value, "path"))
        workspace_dir = Path(getattr(value, "workspace_dir", target_dir.parent))
        return WorkspaceRowSubject(
            key=str(getattr(value, "key")),
            label=str(getattr(value, "label")),
            category=str(getattr(value, "category")),
            workspace_dir=workspace_dir,
            target_dir=target_dir,
            detail_path=target_dir,
        )

    if isinstance(value, str) and value and not value.startswith("__"):
        plugin_dir = plugins_root(root) / value
        if plugin_dir.exists():
            return WorkspaceRowSubject(
                key=f"plugin:{value}",
                label=value,
                category="plugin",
                workspace_dir=plugin_dir,
                target_dir=plugin_dir / "target",
                detail_path=plugin_dir,
            )
        codec_dir = plugins_root(root) / "AssetManager" / "codecs" / value
        if codec_dir.exists():
            return WorkspaceRowSubject(
                key=f"codec:{value}",
                label=value,
                category="codec",
                workspace_dir=codec_dir,
                target_dir=codec_dir / "target",
                detail_path=codec_dir,
            )
    return None
