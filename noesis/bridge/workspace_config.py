from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config_loader import CONFIG_ROOT_REL, load_config_json, resolve_user_path

WORKSPACE_CONFIG_NAME = "workspace.v1.json"
WORKSPACE_CONFIG_REL = CONFIG_ROOT_REL / WORKSPACE_CONFIG_NAME
WORKSPACE_ROOT_ENVS = ("NORTHSTAR_WORKSPACE_ROOT", "NORTHSTAR_SUITE_WORKSPACE_ROOT", "TAKESOME_WORKSPACE_ROOT")
TOOL_ROOT_ENVS = ("NORTHSTAR_TOOL_ROOT", "NORTHSTAR_SUITE_TOOL_ROOT", "TAKESOME_TOOL_ROOT")


def load_workspace_config(launch_root: Path, config_path: str | Path | None = None) -> dict[str, Any]:
    loaded = load_config_json(
        launch_root,
        WORKSPACE_CONFIG_NAME,
        explicit_path=config_path,
        env_var="NORTHSTAR_SUITE_WORKSPACE_CONFIG",
    )
    return loaded.with_metadata() if loaded.data else {}


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
    configured = resolve_user_path(launch_root, workspace.get("root"))
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
    configured = resolve_user_path(launch_root, workspace.get("tool_root") or config.get("tool_root"))
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


def _setdefault_path_env(name: str, root: Path, value: object) -> None:
    if name in os.environ:
        return
    text = str(value or "").strip()
    if not text:
        return
    text = os.path.expandvars(text)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    os.environ[name] = str(path)


def _nested_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def _bool_text(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    text = str(value or "").strip()
    if not text:
        return ""
    return "1" if text.lower() in {"1", "true", "yes", "y", "on", "да"} else "0" if text.lower() in {"0", "false", "no", "n", "off", "нет"} else text


def apply_workspace_environment(root: Path, config: dict[str, Any], tool_root: Path | None = None) -> None:
    workspace = config.get("workspace") if isinstance(config.get("workspace"), dict) else {}
    script_env = config.get("script_env") if isinstance(config.get("script_env"), dict) else {}
    bridge = config.get("bridge") if isinstance(config.get("bridge"), dict) else {}
    intelligence = config.get("suite_intelligence") if isinstance(config.get("suite_intelligence"), dict) else {}
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    console = config.get("console") if isinstance(config.get("console"), dict) else {}
    console_selection = console.get("selection") if isinstance(console.get("selection"), dict) else {}
    cluster = config.get("cluster") if isinstance(config.get("cluster"), dict) else {}
    cloudflare = config.get("cloudflare") if isinstance(config.get("cloudflare"), dict) else {}
    dash_cfg = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    named_tunnel = _nested_dict(cloudflare, "named_tunnel")

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

    # Canonical runtime.v1 bridge identity.  These envs are consumed by both the
    # supervisor process and the bridge child process, so the runtime config
    # remains the single source of truth for MCP path, public origin and cluster
    # identity.  Without this bridge/supervisor silently fall back to /mcp,
    # cluster=local and trycloudflare quick routes.
    _setdefault_env("NORTHSTAR_BRIDGE_BIND_HOST", bridge.get("host"))
    _setdefault_env("NORTHSTAR_BRIDGE_BIND_PORT", bridge.get("port"))
    _setdefault_env("NORTHSTAR_MCP_ENDPOINT_PATH", bridge.get("endpoint") or _nested_dict(bridge, "routes").get("endpoint"))
    _setdefault_env("NORTHSTAR_PUBLIC_MCP_ENDPOINT", bridge.get("public_endpoint"))
    _setdefault_env("NORTHSTAR_BRIDGE_PUBLIC_ORIGIN", bridge.get("public_origin"))
    _setdefault_env("NORTHSTAR_BRIDGE_ADVERTISED_ORIGIN", bridge.get("advertised_origin") or bridge.get("public_origin"))

    _setdefault_env("NORTHSTAR_SUITE_CLUSTER_ID", cluster.get("cluster_id") or cluster.get("id"))
    _setdefault_env("NORTHSTAR_SUITE_MACHINE_ID", cluster.get("machine_id") or cluster.get("machine") or cluster.get("host_id"))
    _setdefault_env("NORTHSTAR_SUITE_MACHINE_ROLE", cluster.get("role"))

    _setdefault_env("NORTHSTAR_CLOUDFLARE_ROUTE_MODE", cloudflare.get("route_mode") or cloudflare.get("mode"))
    _setdefault_env("NORTHSTAR_CLOUDFLARE_TUNNEL", named_tunnel.get("tunnel_name") or named_tunnel.get("tunnel_id"))
    _setdefault_env("NORTHSTAR_PUBLIC_MCP_ENDPOINT", named_tunnel.get("public_endpoint") or bridge.get("public_endpoint"))
    _setdefault_env("NORTHSTAR_CLOUDFLARED_PROTOCOL", named_tunnel.get("protocol") or cloudflare.get("protocol"))
    _setdefault_env("NORTHSTAR_CLOUDFLARED_FALLBACK_PROTOCOLS", ",".join(map(str, cloudflare.get("fallback_protocols", []))) if isinstance(cloudflare.get("fallback_protocols"), list) else cloudflare.get("fallback_protocols"))
    _setdefault_env("NORTHSTAR_CLOUDFLARED_QUICK_PROTOCOL", cloudflare.get("quick_protocol"))
    _setdefault_env("NORTHSTAR_CLOUDFLARED_QUICK_FALLBACK_PROTOCOLS", ",".join(map(str, cloudflare.get("quick_fallback_protocols", []))) if isinstance(cloudflare.get("quick_fallback_protocols"), list) else cloudflare.get("quick_fallback_protocols"))
    _setdefault_env("NORTHSTAR_REQUIRE_NAMED_TUNNEL", _bool_text(named_tunnel.get("require_named_tunnel") if "require_named_tunnel" in named_tunnel else cloudflare.get("require_named_tunnel")))
    _setdefault_env("NORTHSTAR_QUICK_TUNNEL_FALLBACK", _bool_text(named_tunnel.get("quick_tunnel_fallback") if "quick_tunnel_fallback" in named_tunnel else cloudflare.get("quick_tunnel_fallback")))
    _setdefault_path_env("NORTHSTAR_CLOUDFLARE_CREDENTIALS_FILE", root, named_tunnel.get("credentials_file"))
    _setdefault_path_env("NORTHSTAR_CLOUDFLARE_ORIGIN_CERT", root, named_tunnel.get("origin_cert"))

    _setdefault_bool_env("NORTHSTAR_SUITE_INTELLIGENCE_AUTOSTART", intelligence.get("autostart"))
    _setdefault_bool_env("NORTHSTAR_SUITE_INTELLIGENCE_NO_OPENAI", intelligence.get("no_openai"))
    _setdefault_env("NORTHSTAR_SUITE_INTELLIGENCE_INTERVAL_SEC", intelligence.get("interval_sec"))
    _setdefault_env("NORTHSTAR_SUITE_INTELLIGENCE_OPENAI_EVERY", intelligence.get("openai_every"))

    _setdefault_env("NORTHSTAR_SUITE_LLM_PROVIDER", llm.get("provider"))
    _setdefault_env("NORTHSTAR_SUITE_LLM_PYTHON", llm.get("python"))
    _setdefault_env("NORTHSTAR_LOCAL_MODEL_ROOT", llm.get("model_root"))

    _setdefault_env("NORTHSTAR_CONSOLE_SELECTION_MODE", console_selection.get("mode") or console.get("selection_mode"))
    _setdefault_bool_env("NORTHSTAR_CONSOLE_ANSI", console.get("ansi"))
