from __future__ import annotations

import os
from pathlib import Path

from ..logs import TeeLog, run_process
from ..paths import rel
from .descriptors import ToolDescriptor, discover_tools, expand_tool_args, target_exe
from ..cargo.process import cargo_exe


def build_tool_descriptor(repo_root: Path, tool: ToolDescriptor, *, release: bool, log: TeeLog) -> int:
    if tool.kind != "rust-cli":
        log.emit(f"[WARN] Tool is not buildable by Cargo: {tool.id} kind={tool.kind}")
        return 0
    if tool.cargo_manifest is None or not tool.cargo_manifest.exists():
        log.emit(f"[ERROR] Tool Cargo manifest is missing: {tool.id}")
        return 1
    args = [cargo_exe() or "cargo", "build", "--manifest-path", str(tool.cargo_manifest)]
    if release:
        args.append("--release")
    env = os.environ.copy()
    env.setdefault("CARGO_TERM_COLOR", "never")
    code = run_process(args, cwd=tool.root, log=log, env=env)
    if code != 0:
        return code
    exe = target_exe(tool, release)
    log.emit(f"[OK] Tool built: {rel(repo_root, exe)}")
    return 0


def run_tool_validation(repo_root: Path, tool: ToolDescriptor, *, release: bool, log: TeeLog) -> int:
    if not tool.build_validation:
        return 0
    exe = target_exe(tool, release)
    if not exe.exists():
        log.emit(f"[ERROR] Build validation tool is not built: {tool.id} expected={rel(repo_root, exe)}")
        return 1
    args = list(tool.validation_args or tool.default_args)
    if not args:
        args = ["doctor", "--root", "$repo_root"]
    expanded = expand_tool_args(repo_root, tool, args)
    log.emit(f"[CHECK] Running tool validation: {tool.id}")
    return run_process([str(exe), *expanded], cwd=repo_root, log=log)


def build_registered_tools(repo_root: Path, *, release: bool, only_safe: bool, validate: bool, log: TeeLog) -> int:
    tools, warnings = discover_tools(repo_root)
    if warnings:
        for warning in warnings:
            log.emit(f"[ERROR] {warning}")
        return 1
    candidates = [tool for tool in tools if tool.kind == "rust-cli"]
    if only_safe:
        candidates = [tool for tool in candidates if tool.safe_for_build or tool.build_validation]
    if not candidates:
        log.emit("[WARN] No buildable native Rust tools discovered.")
        return 0
    profile = "release" if release else "debug"
    log.emit(f"[BUILD] Native tool build surface: {len(candidates)} tool(s), profile={profile}")
    for tool in candidates:
        rc = build_tool_descriptor(repo_root, tool, release=release, log=log)
        if rc != 0:
            return rc
    if validate:
        for tool in candidates:
            rc = run_tool_validation(repo_root, tool, release=release, log=log)
            if rc != 0:
                return rc
    return 0
