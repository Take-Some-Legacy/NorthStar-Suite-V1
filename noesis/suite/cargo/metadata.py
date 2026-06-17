from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..logs import TeeLog
from .process import cargo_exe


@dataclass(frozen=True)
class CrateMeta:
    cargo_toml: Path
    crate_dir: Path
    package_name: str
    version: str
    lib_name: str
    is_cdylib: bool
    exports_plugin_root: bool
    provider_route: str
    install_name: str

    @property
    def cargo_output_stem(self) -> str:
        return self.lib_name or self.package_name.replace("-", "_")

    @property
    def runtime_install_stem(self) -> str:
        # Cargo package/lib names are cargo-safe build identities. Runtime plugin
        # filenames should expose the human implementation-purpose identity when a
        # plugin declares one, e.g. starVault-assetManager or gravitas-physics.
        # The full provider route remains in metadata (`engine.assets.starvault`,
        # `engine.physics.gravitas`) and diagnostics.
        return self.install_name or self.package_name


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def parse_toml_string(text: str, section: str, key: str) -> str:
    active = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            active = line.strip("[]").strip() == section
            continue
        if not active or not line.startswith(key):
            continue
        left, sep, right = line.partition("=")
        if not sep or left.strip() != key:
            continue
        right = right.strip()
        if right.startswith('"') and '"' in right[1:]:
            return right.split('"', 2)[1]
    return ""


def parse_toml_array_contains(text: str, key: str, needle: str) -> bool:
    compact = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    idx = compact.find(key)
    if idx < 0:
        return False
    bracket = compact.find("[", idx)
    if bracket < 0:
        return False
    end = compact.find("]", bracket)
    if end < 0:
        return False
    return needle in compact[bracket:end]


def codec_enabled(text: str) -> bool:
    marker = "[package.metadata.newengine.codec]"
    idx = text.find(marker)
    if idx < 0:
        return True
    tail = text[idx + len(marker):]
    next_section = tail.find("\n[")
    if next_section >= 0:
        tail = tail[:next_section]
    for raw in tail.splitlines():
        line = raw.strip().split("#", 1)[0].strip()
        if line == "enabled = false":
            return False
    return True


def candidate_from_toml(cargo_toml: Path) -> CrateMeta | None:
    text = read_text(cargo_toml)
    name = parse_toml_string(text, "package", "name")
    version = parse_toml_string(text, "package", "version")
    if not name or not version:
        return None
    lib_name = parse_toml_string(text, "lib", "name") or name.replace("-", "_")
    is_cdylib = parse_toml_array_contains(text, "crate-type", "cdylib")
    lib_text = read_text(cargo_toml.parent / "src" / "lib.rs")
    exports = any(token in lib_text for token in (
        "export_newengine_plugin!",
        "export_plugin_root!",
        "newengine_plugin_root_v1",
        "newengine_plugin_signature_v1",
    ))
    provider_route = parse_toml_string(text, "package.metadata.northstar.provider", "route")
    install_name = parse_toml_string(text, "package.metadata.northstar.provider", "install_name")
    return CrateMeta(
        cargo_toml.resolve(),
        cargo_toml.parent.resolve(),
        name,
        version,
        lib_name,
        is_cdylib,
        exports,
        provider_route,
        install_name,
    )


def select_runtime_crate(workspace_dir: Path) -> CrateMeta:
    cargo_tomls = sorted({
        p.resolve()
        for p in [workspace_dir / "Cargo.toml", *workspace_dir.rglob("Cargo.toml")]
        if p.exists()
    })
    candidates = [c for path in cargo_tomls if (c := candidate_from_toml(path))]
    if not candidates:
        raise RuntimeError(f"No Cargo package metadata found under {workspace_dir}")
    plugin_candidates = [c for c in candidates if c.is_cdylib or c.exports_plugin_root]
    pool = plugin_candidates or candidates

    def score(crate: CrateMeta) -> tuple[int, str, str]:
        route_score = (100 if crate.is_cdylib else 0) + (50 if crate.exports_plugin_root else 0)
        return (-route_score, crate.package_name.lower(), str(crate.cargo_toml).lower())

    selected = sorted(pool, key=score)[0]
    if not (selected.is_cdylib or selected.exports_plugin_root):
        raise RuntimeError(f"Selected package is not a runtime plugin cdylib and exports no plugin root: {selected.cargo_toml}")
    return selected


def cargo_target_dir(meta: CrateMeta, fallback_workspace_dir: Path, log: TeeLog | None = None) -> Path:
    try:
        proc = subprocess.run(
            [cargo_exe() or "cargo", "metadata", "--format-version", "1", "--no-deps", "--manifest-path", str(meta.cargo_toml)],
            cwd=str(fallback_workspace_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            target_dir = data.get("target_directory")
            if target_dir:
                return Path(target_dir).resolve()
        if log:
            log.emit(f"[WARN] cargo metadata failed for {meta.package_name}; falling back to workspace target")
            if proc.stderr.strip():
                log.emit(proc.stderr.strip())
    except Exception as exc:
        if log:
            log.emit(f"[WARN] cargo metadata failed for {meta.package_name}: {exc}")
    return (fallback_workspace_dir / "target").resolve()
