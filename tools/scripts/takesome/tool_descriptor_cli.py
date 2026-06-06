from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .cargo.process import cargo_exe
from .paths import rel


DEFAULT_DESCRIPTOR_GLOBS = (
    "tools/toolbelt/first_party/**/tool.json",
    "tools/toolbelt/third_party/**/tool.json",
)


def discover_suite_command_descriptors(root: Path, patterns: Iterable[str] = DEFAULT_DESCRIPTOR_GLOBS) -> tuple[str, ...]:
    descriptors: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            rel_path = path.relative_to(root).as_posix()
            if rel_path in seen:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            commands = data.get("suite_commands", [])
            if isinstance(commands, list) and any(isinstance(item, dict) and item.get("id") for item in commands):
                descriptors.append(rel_path)
                seen.add(rel_path)
    return tuple(descriptors)


def load_tool_descriptor(root: Path, descriptor_path: str | Path) -> dict[str, Any]:
    path = Path(descriptor_path)
    if not path.is_absolute():
        path = root / path
    return json.loads(path.read_text(encoding="utf-8"))


def iter_suite_commands(root: Path, descriptor_paths: Iterable[str | Path]) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    for descriptor_path in descriptor_paths:
        descriptor = load_tool_descriptor(root, descriptor_path)
        for command in descriptor.get("suite_commands", []) or []:
            if isinstance(command, dict) and command.get("id"):
                yield descriptor, command


def register_tool_descriptor_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser], root: Path, descriptor_paths: Iterable[str | Path]) -> None:
    existing = getattr(sub, "_name_parser_map", {})
    for _descriptor, command in iter_suite_commands(root, descriptor_paths):
        command_id = str(command["id"])
        if command_id in existing:
            continue
        parser = sub.add_parser(command_id, help=str(command.get("description") or command.get("title") or ""))
        existing = getattr(sub, "_name_parser_map", {})
        for argument in command.get("args", []) or []:
            _register_argument(parser, argument)


def dispatch_tool_descriptor_command(command_id: str, root: Path, ns: argparse.Namespace, descriptor_paths: Iterable[str | Path]) -> int | None:
    for descriptor, command in iter_suite_commands(root, descriptor_paths):
        if command.get("id") == command_id:
            return run_descriptor_command(root, descriptor, command, ns)
    return None


def run_descriptor_command(root: Path, descriptor: dict[str, Any], command: dict[str, Any], ns: argparse.Namespace) -> int:
    cmd_args = [str(item) for item in command.get("tool_args", []) or []]
    missing = _missing_required(command, ns)
    if missing:
        print(f"[ERROR] {command.get('id')} requires {', '.join(missing)}")
        return 2
    errors = _validate_requires_any(command, ns)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 2
    for rule in command.get("auto_flags_if_empty", []) or []:
        name = str(rule.get("name") or "")
        if name and _is_empty_value(getattr(ns, name, None)):
            cmd_args.extend(str(item) for item in rule.get("flags", []) or [])
    arg_values: dict[str, Any] = {}
    for argument in command.get("args", []) or []:
        name = str(argument.get("name") or "")
        if name:
            arg_values[name] = getattr(ns, name, None)
        if argument.get("positional"):
            continue
        cmd_args.extend(_argument_to_tool_args(root, argument, ns))
    for name in command.get("positional_args", []) or []:
        value = arg_values.get(str(name))
        if isinstance(value, list):
            cmd_args.extend(_convert_value(root, _find_argument(command, str(name)), item) for item in value)
        elif not _is_empty_value(value):
            cmd_args.append(_convert_value(root, _find_argument(command, str(name)), value))
    redirect_path = _redirect_output_path(root, command, ns)
    launch = descriptor_tool_command(root, descriptor, cmd_args)
    print(f"[INFO] {command.get('title') or command.get('id')} started")
    print("[CMD] " + " ".join(launch))
    try:
        if redirect_path is not None:
            redirect_path.parent.mkdir(parents=True, exist_ok=True)
            with redirect_path.open("w", encoding="utf-8", errors="replace") as out:
                completed = subprocess.run(launch, cwd=root, stdout=out)
        else:
            completed = subprocess.run(launch, cwd=root)
    except FileNotFoundError as exc:
        print(f"[ERROR] descriptor tool launch failed: {exc}")
        return 127
    if completed.returncode == 0:
        print(f"[OK] {command.get('id')} finished")
    else:
        print(f"[ERROR] {command.get('id')} failed exit_code={completed.returncode}")
    return int(completed.returncode)


def descriptor_tool_command(root: Path, descriptor: dict[str, Any], args: list[str]) -> list[str]:
    exe = descriptor_tool_exe(root, descriptor)
    if exe is not None:
        print(f"[INFO] descriptor executable: {rel(root, exe)}")
        return [str(exe), *args]
    manifest = descriptor.get("cargo_manifest")
    if manifest:
        return [cargo_exe() or "cargo", "run", "--manifest-path", str(root / str(manifest)), "--", *args]
    executable = descriptor.get("executable")
    if executable:
        return [str(root / str(executable)), *args]
    raise FileNotFoundError("descriptor has no executable/cargo_manifest")


def descriptor_tool_exe(root: Path, descriptor: dict[str, Any]) -> Path | None:
    candidates = []
    if descriptor.get("install_path"):
        candidates.append(root / str(descriptor["install_path"]))
    if descriptor.get("package_root") and descriptor.get("executable"):
        candidates.append(root / str(descriptor["package_root"]) / str(descriptor["executable"]))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _register_argument(parser: argparse.ArgumentParser, argument: dict[str, Any]) -> None:
    flags = [str(flag) for flag in argument.get("flags", []) or []] or ["--" + str(argument["name"]).replace("_", "-")]
    action = str(argument.get("action") or "")
    positional = bool(argument.get("positional")) or (len(flags) == 1 and not str(flags[0]).startswith("-"))
    kwargs: dict[str, Any] = {"help": str(argument.get("help") or "")}
    if not positional:
        kwargs["dest"] = str(argument.get("name") or flags[0].lstrip("-").replace("-", "_"))
    if action:
        kwargs["action"] = action
    if argument.get("nargs"):
        kwargs["nargs"] = argument.get("nargs")
    if not positional:
        if "default" in argument:
            kwargs["default"] = argument["default"]
        elif action == "append":
            kwargs["default"] = []
        elif action == "store_true":
            kwargs["default"] = False
        else:
            kwargs["default"] = ""
    parser.add_argument(*flags, **kwargs)


def _missing_required(command: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    return [str(a.get("name")) for a in command.get("args", []) or [] if a.get("required") and _is_empty_value(getattr(ns, str(a.get("name")), None))]


def _validate_requires_any(command: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    out = []
    for group in command.get("requires_any", []) or []:
        names = [str(item) for item in group]
        if not any(not _is_empty_value(getattr(ns, name, None)) for name in names):
            out.append(f"{command.get('id')} requires one of: {', '.join(names)}")
    return out


def _argument_to_tool_args(root: Path, argument: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    name = str(argument.get("name") or "")
    value = getattr(ns, name, None)
    if _is_empty_value(value) and argument.get("default_discover"):
        value = _resolve_discovered_default(root, dict(argument.get("default_discover") or {}))
        if value:
            print(f"[INFO] default {name}: {value}")
    if _is_empty_value(value):
        return []
    raw_tool_flag = argument.get("tool_flag")
    flag = "--" + name.replace("_", "-") if raw_tool_flag is None else str(raw_tool_flag)
    if flag == "":
        return []
    action = str(argument.get("action") or "")
    if action == "store_true":
        return [flag] if bool(value) else []
    if action == "append":
        out = []
        for item in value or []:
            out.extend([flag, _convert_value(root, argument, item)])
        return out
    return [flag, _convert_value(root, argument, value)]


def _convert_value(root: Path, argument: dict[str, Any], value: Any) -> str:
    if str(argument.get("kind") or "") == "path":
        path = Path(str(value))
        return str(path if path.is_absolute() else root / path)
    return str(value)


def _resolve_discovered_default(root: Path, spec: dict[str, Any]) -> str:
    for raw in spec.get("paths", []) or []:
        candidate = root / str(raw)
        if candidate.exists():
            return candidate.as_posix()
    pattern = str(spec.get("glob") or "*")
    for raw_root in spec.get("glob_roots", []) or []:
        base = root / str(raw_root)
        if base.exists():
            for candidate in sorted(base.rglob(pattern)):
                return candidate.as_posix()
    return ""


def _is_empty_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == () or value is False
