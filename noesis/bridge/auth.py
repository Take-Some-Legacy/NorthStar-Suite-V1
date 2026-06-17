from __future__ import annotations

import os
from typing import Any, Dict

from .contracts import BridgeContext, BridgeError, OPENAI_API_KEY_ENV, OPENAI_KEY_CACHE_REL

def mask_secret(value: str) -> str:
    return value[:7] + "..." + value[-4:] if len(value) > 14 else "configured"

def looks_like_key(value: str) -> bool:
    return value.startswith(("sk-", "sk-proj-", "sk-svcacct-")) and len(value) >= 20

def read_cached_key(ctx: BridgeContext) -> str:
    try:
        return ctx.openai_key_cache_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""

def write_cached_key(ctx: BridgeContext, key: str) -> None:
    if not looks_like_key(key):
        raise BridgeError("OpenAI API key does not look valid", "openai_key_invalid")
    ctx.openai_key_cache_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.openai_key_cache_path.write_text(key + "\n", encoding="utf-8")
    try:
        os.chmod(ctx.openai_key_cache_path, 0o600)
    except OSError:
        pass

def openai_status(ctx: BridgeContext) -> Dict[str, Any]:
    env = os.environ.get(OPENAI_API_KEY_ENV, "").strip()
    if env:
        return {"configured": looks_like_key(env), "source": "env", "env_var": OPENAI_API_KEY_ENV, "cache_path": OPENAI_KEY_CACHE_REL.as_posix(), "masked": mask_secret(env)}
    cached = read_cached_key(ctx)
    return {"configured": bool(cached), "source": "cache" if cached else "missing", "env_var": OPENAI_API_KEY_ENV, "cache_path": OPENAI_KEY_CACHE_REL.as_posix(), "cache_exists": ctx.openai_key_cache_path.exists(), "masked": "cached" if cached else ""}

def openai_env(ctx: BridgeContext, require: bool = False) -> Dict[str, str]:
    env = os.environ.get(OPENAI_API_KEY_ENV, "").strip()
    if env and looks_like_key(env):
        return {OPENAI_API_KEY_ENV: env}
    cached = read_cached_key(ctx)
    if cached:
        return {OPENAI_API_KEY_ENV: cached}
    if require:
        raise BridgeError("OpenAI API key is missing", "openai_key_missing", {"cache_path": OPENAI_KEY_CACHE_REL.as_posix()})
    return {}

def forget_key(ctx: BridgeContext) -> Dict[str, Any]:
    if not ctx.write_enabled and not ctx.interactive:
        raise BridgeError("forgetting key requires write mode or interactive console", "write_disabled")
    removed = False
    try:
        ctx.openai_key_cache_path.unlink()
        removed = True
    except FileNotFoundError:
        pass
    return {"ok": True, "removed": removed, "cache_path": OPENAI_KEY_CACHE_REL.as_posix()}
