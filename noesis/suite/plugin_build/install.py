from __future__ import annotations

from pathlib import Path

from ..cargo import build_state_root, cleanup_old_versions
from ..logs import TeeLog
from ..paths import engine_core_root, rel


def cleanup_deprecated_artifacts(root: Path, log: TeeLog) -> None:
    plugin_dir = engine_core_root(root) / "plugins"
    stamp_root = build_state_root(root) / "stamps"
    patterns = [
        "game_ready_map*.dll", "newengine_modules_game_ready_map*.dll",
        "audioimporter-*.dll", "fontImporter-*.dll", "geometryImporter-*.dll", "imageImporter-*.dll", "textimporter-*.dll",
        "eguiUiProvider-*.dll", "egui_ui_provider*.dll", "aurelia_ui_provider.dll", "*.stamp.json",
        "aurelia-[0-9]*.dll", "engine.ui.aurelia-*.dll", "engine-ui-aurelia-*.dll",
        "vulkan-[0-9]*.dll", "engine.render.vulkan-*.dll", "engine-render-vulkan-*.dll",
        "starvault-[0-9]*.dll", "engine.assets.starvault-*.dll", "engine-assets-starvault-*.dll", "assetManager-*.dll",
        "compass-[0-9]*.dll", "engine.input.compass-*.dll", "engine-input-compass-*.dll",
        "constellation-[0-9]*.dll", "engine.ecs.constellation-*.dll", "engine-ecs-constellation-*.dll",
        "gravitas-[0-9]*.dll", "engine.physics.gravitas-*.dll", "engine-physics-gravitas-*.dll",
        "chronicle-[0-9]*.dll", "engine.logging.chronicle-*.dll", "engine-logging-chronicle-*.dll",
        "starprofiler-[0-9]*.dll", "starProfiler-[0-9]*.dll", "engine.profiler.starprofiler-*.dll", "engine-profiler-starprofiler-*.dll",
        "winit-[0-9]*.dll", "platform-winit-*.dll", "winit-platform-plugin-*.dll", "engine.platform.winit-*.dll", "engine-platform-winit-*.dll",
        "codecs/*.stamp.json", "codecs/newengine-codec-firstparty-*.dll", "codecs/newengine_codec_firstparty*.dll",
        "importers/*.stamp.json", "platforms/*.stamp.json",
        "platforms/platform-winit*.dll", "platforms/winit-platform-plugin*.dll", "platforms/*winit*.dll",
    ]
    for pattern in patterns:
        for path in plugin_dir.glob(pattern):
            if path.is_file():
                try:
                    log.emit(f"[CLEAN] deprecated artifact: {rel(root, path)}")
                    path.unlink()
                except OSError as exc:
                    log.emit(f"[WARN] Failed to delete {path}: {exc}")
    for pattern in [
        "plugin/EguiUiProvider/eguiUiProvider-*.stamp.json",
        "plugin/NewEngineUiProvider/*.stamp.json",
        "plugin/egui_ui_provider/*.stamp.json",
    ]:
        for path in stamp_root.glob(pattern):
            if path.is_file():
                try:
                    log.emit(f"[CLEAN] deprecated stamp: {rel(root, path)}")
                    path.unlink()
                except OSError as exc:
                    log.emit(f"[WARN] Failed to delete {path}: {exc}")


def cleanup_winit_platform_alias(root: Path, log: TeeLog) -> None:
    """winit-platform-plugin is installed only into plugins/, not plugins/platforms/."""
    platform_dir = engine_core_root(root) / "plugins" / "platforms"
    if not platform_dir.exists():
        return
    for pattern in ["platform-winit*.dll", "winit-platform-plugin*.dll", "*winit*.dll", "*.stamp.json"]:
        for path in platform_dir.glob(pattern):
            if path.is_file():
                try:
                    log.emit(f"[CLEAN] removed winit platform duplicate: {rel(root, path)}")
                    path.unlink()
                except OSError as exc:
                    log.emit(f"[WARN] Failed to delete {path}: {exc}")
    cleanup_old_versions(platform_dir, "platform-winit", "", log)
