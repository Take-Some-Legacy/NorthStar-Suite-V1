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
        for command in _as_list(descriptor.get("suite_commands")):
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
        for argument in _iter_argument_specs(command):
            _register_argument(parser, argument)


def dispatch_tool_descriptor_command(command_id: str, root: Path, ns: argparse.Namespace, descriptor_paths: Iterable[str | Path]) -> int | None:
    for descriptor, command in iter_suite_commands(root, descriptor_paths):
        if command.get("id") == command_id:
            return run_descriptor_command(root, descriptor, command, ns)
    return None


def run_descriptor_command(root: Path, descriptor: dict[str, Any], command: dict[str, Any], ns: argparse.Namespace) -> int:
    cmd_args = _as_str_list(command.get("tool_args"))
    cmd_args.extend(_as_str_list(command.get("fixed_args")))

    missing = _missing_required(command, ns)
    if missing:
        print(f"[ERROR] {command.get('id')} requires {', '.join(missing)}")
        return 2

    errors = _validate_requires_any(command, ns)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 2

    for rule in _as_list(command.get("auto_flags_if_empty")):
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("name") or "")
        if name and _is_empty_value(getattr(ns, name, None)):
            cmd_args.extend(_as_str_list(rule.get("flags")))

    arg_values: dict[str, Any] = {}
    for argument in _iter_argument_specs(command):
        name = str(argument.get("name") or "")
        if name:
            arg_values[name] = getattr(ns, name, None)
        if argument.get("positional"):
            continue
        cmd_args.extend(_argument_to_tool_args(root, argument, ns))

    for name in _as_str_list(command.get("positional_args")):
        value = arg_values.get(str(name))
        argument = _find_argument(command, str(name))
        if isinstance(value, list):
            cmd_args.extend(_convert_value(root, argument, item) for item in value)
        elif not _is_empty_value(value):
            cmd_args.append(_convert_value(root, argument, value))

    cmd_args.extend(_as_str_list(command.get("literal_args_before_output")))

    for name in _as_str_list(command.get("positional_args_after_literals")):
        value = arg_values.get(str(name))
        argument = _find_argument(command, str(name))
        if isinstance(value, list):
            cmd_args.extend(_convert_value(root, argument, item) for item in value)
        elif not _is_empty_value(value):
            cmd_args.append(_convert_value(root, argument, value))

    redirect_path = _redirect_output_path(root, command, ns)
    launch = descriptor_tool_command(root, descriptor, cmd_args)
    print(f"[INFO] {command.get('title') or command.get('id')} started")
    print("[CMD] " + " ".join(launch))
    try:
        if redirect_path is not None:
            redirect_path.parent.mkdir(parents=True, exist_ok=True)
            with redirect_path.open("w", encoding="utf-8", errors="replace") as out:
                completed = subprocess.run(launch, cwd=root, stdout=out, stderr=subprocess.STDOUT)
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
    candidates: list[Path] = []
    if descriptor.get("install_path"):
        candidates.append(root / str(descriptor["install_path"]))
    if descriptor.get("package_root") and descriptor.get("executable"):
        candidates.append(root / str(descriptor["package_root"]) / str(descriptor["executable"]))
    if descriptor.get("executable"):
        candidates.append(root / str(descriptor["executable"]))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _register_argument(parser: argparse.ArgumentParser, argument: dict[str, Any]) -> None:
    if not isinstance(argument, dict):
        return
    raw_flags = _as_str_list(argument.get("flags"))
    name = str(argument.get("name") or "")
    if not raw_flags and name:
        raw_flags = ["--" + name.replace("_", "-")]
    if not raw_flags:
        return

    flags = raw_flags
    action = str(argument.get("action") or "")
    positional = bool(argument.get("positional")) or (len(flags) == 1 and not str(flags[0]).startswith("-"))
    kwargs: dict[str, Any] = {"help": str(argument.get("help") or "")}
    if not positional:
        kwargs["dest"] = name or flags[0].lstrip("-").replace("-", "_")
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
    out: list[str] = []
    for argument in _iter_argument_specs(command):
        name = str(argument.get("name") or "")
        if argument.get("required") and name and _is_empty_value(getattr(ns, name, None)):
            out.append(name)
    return out


def _validate_requires_any(command: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    out = []
    for group in _as_list(command.get("requires_any")):
        names = _as_str_list(group)
        if names and not any(not _is_empty_value(getattr(ns, name, None)) for name in names):
            out.append(f"{command.get('id')} requires one of: {', '.join(names)}")
    return out


def _argument_to_tool_args(root: Path, argument: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    if not isinstance(argument, dict):
        return []
    name = str(argument.get("name") or "")
    if not name:
        return []
    value = getattr(ns, name, None)
    if _is_empty_value(value) and argument.get("default_discover"):
        default_discover = argument.get("default_discover")
        if isinstance(default_discover, dict):
            value = _resolve_discovered_default(root, default_discover)
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
        out: list[str] = []
        for item in _as_list(value):
            out.extend([flag, _convert_value(root, argument, item)])
        return out
    if isinstance(value, list) and str(argument.get("kind") or "") == "path_list":
        out: list[str] = []
        for item in value:
            out.extend([flag, _convert_value(root, argument, item)] if flag else [_convert_value(root, argument, item)])
        return out
    return [flag, _convert_value(root, argument, value)]


def _convert_value(root: Path, argument: dict[str, Any] | None, value: Any) -> str:
    argument = argument or {}
    if str(argument.get("kind") or "") in {"path", "path_list"}:
        path = Path(str(value))
        return str(path if path.is_absolute() else root / path)
    return str(value)


def _resolve_discovered_default(root: Path, spec: dict[str, Any]) -> str:
    for raw in _as_str_list(spec.get("paths")):
        candidate = root / raw
        if candidate.exists():
            return candidate.as_posix()
    pattern = str(spec.get("glob") or "*")
    for raw_root in _as_str_list(spec.get("glob_roots")):
        base = root / raw_root
        if base.exists():
            for candidate in sorted(base.rglob(pattern)):
                return candidate.as_posix()
    return ""


def _redirect_output_path(root: Path, command: dict[str, Any], ns: argparse.Namespace) -> Path | None:
    spec = command.get("redirect_stdout") or command.get("stdout") or command.get("output_redirect")
    if not spec:
        return None
    if isinstance(spec, str):
        raw = spec
    elif isinstance(spec, dict):
        raw = str(spec.get("path") or spec.get("name") or "")
        from_arg = str(spec.get("from_arg") or "")
        if from_arg:
            raw = str(getattr(ns, from_arg, "") or raw)
    else:
        return None
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _find_argument(command: dict[str, Any], name: str) -> dict[str, Any] | None:
    for argument in _iter_argument_specs(command):
        if str(argument.get("name") or "") == name:
            return argument
    return None


def _iter_argument_specs(command: dict[str, Any]) -> list[dict[str, Any]]:
    raw = command.get("args", [])
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _as_list(value: Any) -> list[Any]:
    if value is None or value is False:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_str_list(value: Any) -> list[str]:
    out: list[str] = []
    for item in _as_list(value):
        if item is None or item is False:
            continue
        if isinstance(item, (list, tuple)):
            out.extend(_as_str_list(list(item)))
        elif isinstance(item, dict):
            continue
        else:
            out.append(str(item))
    return out


def _is_empty_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == () or value is False
