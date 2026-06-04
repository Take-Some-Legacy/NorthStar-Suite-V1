from __future__ import annotations

import hmac
import os
import secrets
import hashlib
from pathlib import Path

from .contracts import bridge_suite_root
from typing import Any

from . import oauth

TOKEN_REL = Path("authority/bridge_access_token.txt")


def token_path(root: Path) -> Path:
    return bridge_suite_root(root) / TOKEN_REL


def ensure_token(root: Path) -> str:
    path = token_path(root)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


def token_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return "sha256:" + digest[:16]


def configured_token(root: Path) -> str:
    env = os.environ.get("NORTHSTAR_BRIDGE_ACCESS_TOKEN", "").strip()
    if env:
        return env
    return ensure_token(root)


def status(root: Path) -> dict[str, Any]:
    token = configured_token(root)
    return {
        "enabled": True,
        "scheme": "bearer_or_x_northstar_bridge_token",
        "token_path": TOKEN_REL.as_posix(),
        "fingerprint": token_fingerprint(token),
    }


def extract_request_token(headers: Any) -> str:
    auth = str(headers.get("Authorization", "") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    direct = str(headers.get("X-NorthStar-Bridge-Token", "") or "").strip()
    return direct


def authorized(root: Path, headers: Any) -> bool:
    expected = configured_token(root)
    supplied = extract_request_token(headers)
    return bool(supplied) and (hmac.compare_digest(supplied, expected) or oauth.token_is_valid(root, supplied))
