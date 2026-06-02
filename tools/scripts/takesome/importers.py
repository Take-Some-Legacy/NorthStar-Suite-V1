from __future__ import annotations

from pathlib import Path

from .build_info import build_log_dir
from .constants import WIN
from .logs import TeeLog, run_process
from .migration import apply_delete_list
from .paths import now_stamp, rel
from .progress import progress_configure, progress_update

def _importer_profile(args: list[str]) -> str:
    for arg in args:
        low = arg.lower()
        if low in {"dev", "debug", "release"}:
            return low
    return "dev"


def build_importers(root: Path, args: list[str]) -> int:
    apply_delete_list(root)
    profile = _importer_profile(args)
    log_dir = build_log_dir(root)
    current_log = log_dir / f"importers-{now_stamp()}.log"
    latest_log = log_dir / "importers-latest.log"
    with TeeLog(current_log, latest_log) as log:
        log.emit("[LOG] North Star importer build log")
        log.emit(f"[LOG] script=tools/scripts/takesome.py build-importers")
        log.emit(f"[LOG] args={' '.join(args)}")
        log.emit(f"[STATE] importer profile={profile}")
        log.emit(f"[INFO] Importer build log: {rel(root, current_log)}")
        importers = root / "Importers"
        if not importers.exists():
            log.emit("[WARN] Importers directory not found; nothing to build.")
            log.emit(f"[INFO] Latest importer build log: {rel(root, latest_log)}")
            return 0
        buildable_importers = sorted(p for p in importers.iterdir() if p.is_dir() and (p / "Cargo.toml").exists())
        progress_configure(total=max(1, len(buildable_importers)), current=0, unit="importer", phase="importer build plan resolved")
        built = 0
        for index, child in enumerate(buildable_importers, start=1):
            progress_update(current=index - 1, phase=f"building importer {child.name}")
            log.emit(f"[BUILD] importer {child.name}")
            cmd = ["cargo", "build"]
            if profile == "release":
                cmd.append("--release")
            code = run_process(cmd, cwd=child, log=log)
            if code != 0:
                log.emit(f"[ERROR] Importer build failed: {child.name} exit_code={code}")
                log.emit(f"[INFO] Latest importer build log: {rel(root, latest_log)}")
                return code
            built += 1
            progress_update(current=index, phase=f"finished importer {child.name}")
        if built == 0:
            log.emit("[WARN] No buildable importer Cargo workspaces were found under Importers.")
            log.emit("[WARN] Importers/ytyp_xml_importer is source-only in this snapshot; nothing to build.")
        else:
            log.emit(f"[OK] Built {built} importer workspace(s).")
        log.emit(f"[INFO] Latest importer build log: {rel(root, latest_log)}")
    return 0
def _cargo_package_name(cargo_toml: Path, fallback: str) -> str:
    text = cargo_toml.read_text(encoding="utf-8", errors="replace") if cargo_toml.exists() else ""
    in_package = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_package = line == "[package]"
            continue
        if in_package and line.startswith("name") and "=" in line:
            return line.split("=", 1)[1].strip().strip(chr(34)).strip("'")
    return fallback

def build_tool(root: Path, tool_dir: Path, release: bool) -> int:
    apply_delete_list(root)
    log = TeeLog()
    resolved = tool_dir.resolve()
    args = ["cargo", "build"]
    if release:
        args.append("--release")
    code = run_process(args, cwd=resolved, log=log)
    if code == 0:
        package_name = _cargo_package_name(resolved / "Cargo.toml", resolved.name)
        exe_name = f"{package_name}.exe" if WIN else package_name
        exe = resolved / "target" / ("release" if release else "debug") / exe_name
        log.emit(f"[OK] Tool built: {exe}")
    return code
