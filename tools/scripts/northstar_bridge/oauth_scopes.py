from __future__ import annotations

from typing import Iterable

READ_SCOPE = "northstar.read"
WRITE_SCOPE = "northstar.write"
EXEC_SCOPE = "northstar.exec"
ADMIN_SCOPE = "northstar.admin"

ALL_SCOPES = (READ_SCOPE, WRITE_SCOPE, EXEC_SCOPE, ADMIN_SCOPE)

WRITE_TOOLS = {
    "write_text_file",
    "delete_path",
    "repo_patch_apply",
    "repo_split_python_module",
    "archive_patch",
    "archive_changed_files_zip",
    "archive_full_zip",
}

EXEC_TOOLS = {
    "python",
    "py",
    "cargo",
    "git",
    "find",
    "execute_suite_command",
    "tool_northstar_devspace",
    "tool_northstar_neui_packer",
}

ADMIN_TOOLS = {
    "reload_bridge_origin",
    "restart_bridge_origin",
}

READ_ONLY_PROJECT_TOOLS = {
    "tool_registry",
    "grep",
    "rg",
    "awk",
    "fd",
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
}

DANGEROUS_TOOLS = {
    "delete_path",
    "rm",
}


def required_scopes(public_name: str) -> list[str]:
    name = public_name.strip()
    scopes: list[str] = [READ_SCOPE]
    if name in WRITE_TOOLS:
        scopes.append(WRITE_SCOPE)
    if name in EXEC_TOOLS:
        scopes.extend([WRITE_SCOPE, EXEC_SCOPE])
    if name in ADMIN_TOOLS:
        scopes.extend([WRITE_SCOPE, ADMIN_SCOPE])
    return list(dict.fromkeys(scopes))


def supported_scopes() -> list[str]:
    return list(ALL_SCOPES)


def default_granted_scope_string(requested_scope: str = "") -> str:
    requested = [part for part in requested_scope.split() if part in ALL_SCOPES]
    if not requested:
        requested = [READ_SCOPE, WRITE_SCOPE]
    return " ".join(dict.fromkeys(requested))


def risk_tier(public_name: str, *, suite_sudo_active: bool, is_public_static_tool: bool) -> str:
    name = public_name.strip()
    if name in DANGEROUS_TOOLS or name in ADMIN_TOOLS:
        return "sudo_write" if suite_sudo_active else "dangerous"
    if name in WRITE_TOOLS:
        return "sudo_write" if suite_sudo_active else "write"
    if name in EXEC_TOOLS:
        return "sudo_write" if suite_sudo_active else "exec"
    if not is_public_static_tool and name not in READ_ONLY_PROJECT_TOOLS:
        return "sudo_write" if suite_sudo_active else "write"
    return "read_only"
