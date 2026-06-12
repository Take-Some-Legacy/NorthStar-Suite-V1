from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

WORKSPACE_CONFIG_REL = Path("config") / "suite" / "workspace.v1.json"
WORKSPACE_ROOT_ENVS = ("NORTHSTAR_WORKSPACE_ROOT", "NORTHSTAR_SUITE_WORKSPACE_ROOT", "TAKESOME_WORKSPACE_ROOT")
TOOL_ROOT_ENVS = ("NORTHSTAR_TOOL_ROOT", "NORTHSTAR_SUITE_TOOL_ROOT", "TAKESOME_TOOL_ROOT")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_workspace_config(launch_root: Path, config_path: str | Path | None = None) -> dict[str, Any]:
    raw = str(config_path or os.environ.get("NORTHSTAR_SUITE_WORKSPACE_CONFIG") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (launch_root / path).resolve()
    else:
        path = (launch_root / WORKSPACE_CONFIG_REL).resolve()
    data = _read_json(path)
    if data:
        data.setdefault("_config_path", str(path))
    return data


def _resolve_config_path(launch_root: Path, raw: object) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = os.path.expandvars(text)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (launch_root / path).resolve()
    return path


def resolve_workspace_root(launch_root: Path, cli_root: str | Path | None, config: dict[str, Any]) -> Path:
    raw_cli = str(cli_root or "").strip()
    # Explicit CLI root wins. Empty/auto/defer means config owns the workspace.
    if raw_cli and raw_cli.lower() not in {"auto", "config", "configured"}:
        return Path(raw_cli).expanduser().resolve()

    for name in WORKSPACE_ROOT_ENVS:
        raw = os.environ.get(name, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()

    workspace = config.get("workspace") if isinstance(config.get("workspace"), dict) else {}
    configured = _resolve_config_path(launch_root, workspace.get("root"))
    return configured or launch_root.resolve()


def resolve_tool_root(launch_root: Path, config: dict[str, Any]) -> Path:
    """Return the suite/tool host root, separate from the edited workspace root.

    In site-worker mode the editable project can be TakeSomeWebsite while the
    bridge implementation and tools/toolbelt remain in the NorthStar suite tree.
    """
    for name in TOOL_ROOT_ENVS:
        raw = os.environ.get(name, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()

    workspace = config.get("workspace") if isinstance(config.get("workspace"), dict) else {}
    configured = _resolve_config_path(launch_root, workspace.get("tool_root") or config.get("tool_root"))
    return configured or launch_root.resolve()


def _setdefault_bool_env(name: str, value: object) -> None:
    if name in os.environ:
        return
    if isinstance(value, bool):
        os.environ[name] = "1" if value else "0"
    elif value is not None:
        text = str(value).strip()
        if text:
            os.environ[name] = text


def _setdefault_env(name: str, value: object) -> None:
    if name in os.environ:
        return
    text = str(value or "").strip()
    if text:
        os.environ[name] = text


def _set_env(name: str, value: object) -> None:
    text = str(value or "").strip()
    if text:
        os.environ[name] = text


def apply_workspace_environment(root: Path, config: dict[str, Any], tool_root: Path | None = None) -> None:
    workspace = config.get("workspace") if isinstance(config.get("workspace"), dict) else {}
    script_env = config.get("script_env") if isinstance(config.get("script_env"), dict) else {}
    bridge = config.get("bridge") if isinstance(config.get("bridge"), dict) else {}
    intelligence = config.get("suite_intelligence") if isinstance(config.get("suite_intelligence"), dict) else {}
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    console = config.get("console") if isinstance(config.get("console"), dict) else {}
    console_selection = console.get("selection") if isinstance(console.get("selection"), dict) else {}

    root = root.resolve()
    tool_root = (tool_root or root).resolve()

    # These describe the project being edited. They must not be inherited from a
    # stale script-env generated for the suite host.
    _set_env("NORTHSTAR_WORKSPACE_ROOT", str(root))
    _set_env("NORTHSTAR_SUITE_WORKSPACE_ROOT", str(root))
    _set_env("TAKESOME_WORKSPACE_ROOT", str(root))
    _set_env("NEWENGINE_PROJECT_ROOT", str(root))

    # These describe where the bridge implementation and tools/toolbelt live.
    _set_env("NORTHSTAR_TOOL_ROOT", str(tool_root))
    _set_env("NORTHSTAR_SUITE_TOOL_ROOT", str(tool_root))
    _set_env("TAKESOME_TOOL_ROOT", str(tool_root))

    _setdefault_env("NORTHSTAR_SUITE_WORKSPACE_KIND", workspace.get("kind"))
    _setdefault_env("NORTHSTAR_BRIDGE_EXPOSURE_MODE", workspace.get("exposure_mode"))

    env_file = script_env.get("file")
    if env_file:
        env_path = Path(str(env_file)).expanduser()
        if not env_path.is_absolute():
            env_path = root / env_path
        _set_env("NEWENGINE_SCRIPT_ENV_FILE", str(env_path))

    _setdefault_bool_env("NORTHSTAR_BRIDGE_AUTO_TRUST", bridge.get("auto_trust"))
    _setdefault_bool_env("NORTHSTAR_AI_BRIDGE_SKIP_ORIGIN_PREFLIGHT", bridge.get("skip_origin_preflight"))

    _setdefault_bool_env("NORTHSTAR_SUITE_INTELLIGENCE_AUTOSTART", intelligence.get("autostart"))
    _setdefault_bool_env("NORTHSTAR_SUITE_INTELLIGENCE_NO_OPENAI", intelligence.get("no_openai"))
    _setdefault_env("NORTHSTAR_SUITE_INTELLIGENCE_INTERVAL_SEC", intelligence.get("interval_sec"))
    _setdefault_env("NORTHSTAR_SUITE_INTELLIGENCE_OPENAI_EVERY", intelligence.get("openai_every"))

    _setdefault_env("NORTHSTAR_SUITE_LLM_PROVIDER", llm.get("provider"))
    _setdefault_env("NORTHSTAR_SUITE_LLM_PYTHON", llm.get("python"))
    _setdefault_env("NORTHSTAR_LOCAL_MODEL_ROOT", llm.get("model_root"))

    _setdefault_env("NORTHSTAR_CONSOLE_SELECTION_MODE", console_selection.get("mode") or console.get("selection_mode"))
    _setdefault_bool_env("NORTHSTAR_CONSOLE_ANSI", console.get("ansi"))
