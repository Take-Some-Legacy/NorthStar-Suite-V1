from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .paths import rel, suite_path, utc_iso
from .repository_index import default_repos_root, load_repository_index, validate_repository_index
from .status_cache import write_status_snapshot

_TOOL_GROUPS: dict[str, list[str]] = {
    "python": ["py", "python", "python3"],
    "java": ["java", "javac", "jshell"],
    "gradle_maven": ["gradle", "mvn"],
    "node": ["node", "npm", "npx", "pnpm", "yarn"],
    "rust": ["rustc", "cargo", "rustup"],
    "native": ["gcc", "g++", "clang", "clang++", "cmake", "ninja", "make"],
    "vcs": ["git"],
    "network": ["curl", "wget"],
    "archive": ["tar", "unzip", "zip", "7z"],
}


def register_env_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for command, mode in {
        "env-doctor": "doctor",
        "env-tools": "tools",
        "env-toolchains": "toolchains",
        "env-status": "status",
    }.items():
        parser = sub.add_parser(command, help=f"Write {mode} diagnostics for the OpenAI operator environment.")
        parser.set_defaults(env_mode=mode)
        parser.add_argument("--repo-dir", default=".", help="Repository root to inspect. Defaults to current Suite repo.")
        parser.add_argument("--index-file", default="", help="Explicit repository index path. Reserved for future use.")
        parser.add_argument("--json", action="store_true", help="Print the full JSON payload.")
        parser.add_argument("--no-write", action="store_true", help="Do not write reports to Suite or repo-local logs.")


def env_command(root: Path, args: argparse.Namespace) -> int:
    mode = str(getattr(args, "env_mode", "doctor") or "doctor")
    repo_dir = _resolve_repo_dir(root, str(getattr(args, "repo_dir", ".") or "."))
    payload = build_env_payload(root, repo_dir=repo_dir, mode=mode)
    if not bool(getattr(args, "no_write", False)):
        write_env_reports(root, payload, repo_dir=repo_dir, mode=mode)
    if bool(getattr(args, "json", False)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_summary(payload)
    return 0 if payload.get("status") in {"ok", "warn"} else 2


def build_env_payload(root: Path, *, repo_dir: Path, mode: str) -> dict[str, Any]:
    repo_index, index_diags = load_repository_index(repo_dir)
    index_validation = validate_repository_index(repo_index, list(index_diags))
    tools = discover_environment_tools()
    toolchains = summarize_toolchains(tools)
    repos_root = repo_index.repos_root if repo_index is not None else default_repos_root()

    required_tool_records: list[dict[str, Any]] = []
    missing_required: list[str] = []
    if repo_index is not None:
        tool_contract = repo_index.payload.get("tools") if isinstance(repo_index.payload.get("tools"), dict) else {}
        raw_required = tool_contract.get("required", []) if isinstance(tool_contract, dict) else []
        for item in raw_required if isinstance(raw_required, list) else []:
            if not isinstance(item, dict):
                continue
            command = str(item.get("command") or "").strip()
            record = {
                "id": str(item.get("id") or command),
                "command": command,
                "version_arg": str(item.get("version_arg") or ""),
                "reason": str(item.get("reason") or ""),
                "available": bool(_resolve_command(command, repo_index.execution_cwd)),
                "resolved": _resolve_command(command, repo_index.execution_cwd) or "",
            }
            if not record["available"]:
                missing_required.append(record["id"])
            required_tool_records.append(record)

    status = "ok"
    diagnostics: list[dict[str, Any]] = []
    if missing_required:
        status = "error"
        diagnostics.append({
            "severity": "error",
            "check": "repository.required_tools",
            "message": "Missing required repository tools: " + ", ".join(missing_required),
        })
    if not index_validation.get("ok"):
        missing_index = index_validation.get("status") == "missing"
        status = "warn" if status == "ok" and missing_index else "error"
        diagnostics.append({
            "severity": "warning" if missing_index else "error",
            "check": "repository.index",
            "message": "; ".join(str(x) for x in index_validation.get("diagnostics", [])[:8]),
        })
    if not repos_root.exists():
        if status == "ok":
            status = "warn"
        diagnostics.append({
            "severity": "warning",
            "check": "repos_root.access",
            "message": f"Configured repos root is not accessible from this process: {repos_root}",
        })

    payload: dict[str, Any] = {
        "schema": f"takesome.env.{mode}.v1",
        "generated_utc": utc_iso(),
        "mode": mode,
        "status": status,
        "process": {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": str(Path.cwd()),
        },
        "roots": {
            "suite_repo_root": str(root.resolve()),
            "repo_dir": str(repo_dir.resolve()),
            "repos_root": str(repos_root),
            "default_repos_root": str(default_repos_root()),
        },
        "repository_index": index_validation,
        "required_tools": required_tool_records,
        "missing_required_tools": missing_required,
        "toolchains": toolchains,
        "tools": tools,
        "diagnostics": diagnostics,
    }
    if mode == "tools":
        payload["toolchains"] = {}
        payload["repository_index"] = {}
    elif mode == "toolchains":
        payload["tools"] = {}
    elif mode == "status":
        payload["tools"] = {}
        payload["toolchains"] = {key: value for key, value in toolchains.items() if value.get("available")}
    return payload


def discover_environment_tools() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group, commands in _TOOL_GROUPS.items():
        for command in commands:
            if command in result:
                continue
            resolved = shutil.which(command)
            result[command] = {
                "group": group,
                "command": command,
                "available": bool(resolved),
                "path": resolved or "",
                "version": _tool_version(command, resolved),
            }
    return result


def summarize_toolchains(tools: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "python": _toolchain_record(tools, ["py", "python", "python3"]),
        "java": _toolchain_record(tools, ["java", "javac"]),
        "gradle_maven": _toolchain_record(tools, ["gradle", "mvn"]),
        "node": _toolchain_record(tools, ["node", "npm"]),
        "rust": _toolchain_record(tools, ["rustc", "cargo"]),
        "native": _toolchain_record(tools, ["gcc", "clang", "cmake", "ninja"]),
        "vcs": _toolchain_record(tools, ["git"]),
    }


def _toolchain_record(tools: dict[str, dict[str, Any]], commands: list[str]) -> dict[str, Any]:
    present = [cmd for cmd in commands if bool(tools.get(cmd, {}).get("available"))]
    return {
        "available": bool(present),
        "present": present,
        "missing": [cmd for cmd in commands if cmd not in present],
    }


def write_env_reports(root: Path, payload: dict[str, Any], *, repo_dir: Path, mode: str) -> list[str]:
    written: list[str] = []
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    global_dir = root / ".takesome" / "ai-bridge" / "knowledge"
    global_dir.mkdir(parents=True, exist_ok=True)
    global_path = global_dir / f"env-{mode}.json"
    global_path.write_text(text, encoding="utf-8")
    written.append(rel(root, global_path))

    repo_index, _ = load_repository_index(repo_dir)
    if repo_index is not None:
        repo_index.logs_dir.mkdir(parents=True, exist_ok=True)
        local_path = repo_index.logs_dir / f"env-{mode}.json"
        local_path.write_text(text, encoding="utf-8")
        written.append(repo_index.rel(local_path))

    write_status_snapshot(root, f"env-{mode}", payload, source="env_workspace.write_env_reports")
    return written


def _resolve_repo_dir(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _resolve_command(command: str, cwd: Path) -> str:
    if not command:
        return ""
    normalized = command.replace("\\", "/")
    if normalized.startswith("./") or normalized.startswith("../") or "/" in normalized:
        candidate = (cwd / normalized).resolve()
        return str(candidate) if candidate.exists() else ""
    return shutil.which(command) or ""


def _tool_version(command: str, resolved: str | None) -> str:
    if not resolved:
        return ""
    args = [command, "--version"]
    if command in {"java", "javac"}:
        args = [command, "-version"]
    try:
        completed = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return f"version probe failed: {type(exc).__name__}: {exc}"
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0] if output else ""


def _print_summary(payload: dict[str, Any]) -> None:
    print(f"[ENV] mode={payload.get('mode')} status={payload.get('status')}")
    roots = payload.get("roots") if isinstance(payload.get("roots"), dict) else {}
    print(f"[ENV] suite_repo_root={roots.get('suite_repo_root', '')}")
    print(f"[ENV] repos_root={roots.get('repos_root', '')}")
    missing = payload.get("missing_required_tools") if isinstance(payload.get("missing_required_tools"), list) else []
    if missing:
        print("[ENV] missing_required_tools=" + ", ".join(str(x) for x in missing))
    for diagnostic in payload.get("diagnostics", []) if isinstance(payload.get("diagnostics"), list) else []:
        print(f"[{str(diagnostic.get('severity', 'info')).upper()}] {diagnostic.get('check')}: {diagnostic.get('message')}")
