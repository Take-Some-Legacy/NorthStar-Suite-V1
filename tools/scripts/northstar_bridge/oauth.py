from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import time
import urllib.parse
from pathlib import Path
from typing import Any

from . import oauth_scopes

AUTH_ROOT = Path(".takesome/authority/oauth")
CODE_TTL_SEC = 300
TOKEN_TTL_SEC = 12 * 60 * 60


def _now() -> int:
    return int(time.time())


def _json_path(root: Path, *parts: str) -> Path:
    return root / AUTH_ROOT.joinpath(*parts)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_url(headers: Any) -> str:
    proto = str(headers.get("X-Forwarded-Proto", "") or "").split(",")[0].strip() or "https"
    host = str(headers.get("X-Forwarded-Host", "") or headers.get("Host", "") or "127.0.0.1:8797").split(",")[0].strip()
    # Local origin is usually reached through the named HTTPS tunnel.  If a direct
    # localhost request is used, keep http for developer smoke tests.
    if host.startswith("127.0.0.1") or host.startswith("localhost"):
        proto = "http"
    return f"{proto}://{host}".rstrip("/")




def _parse_body(body_bytes: bytes, content_type: str = "") -> dict[str, Any]:
    raw = body_bytes.decode("utf-8", errors="replace")
    ctype = content_type.split(";", 1)[0].strip().lower()
    if not raw.strip():
        return {}
    if ctype == "application/x-www-form-urlencoded":
        parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}
    if ctype == "application/json" or raw.lstrip().startswith("{"):
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    if parsed:
        return {key: values[-1] if values else "" for key, values in parsed.items()}
    return {}

def _encoded_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _client_id_for(metadata: dict[str, Any]) -> str:
    raw = json.dumps(metadata, sort_keys=True, ensure_ascii=False) + secrets.token_urlsafe(8)
    return "northstar-client-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def protected_resource_metadata(base: str, resource_path: str = "/mcp") -> dict[str, Any]:
    resource_path = resource_path if str(resource_path).startswith("/") else "/" + str(resource_path)
    resource = base.rstrip("/") + resource_path
    return {
        "resource": resource,
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": oauth_scopes.supported_scopes(),
        "resource_documentation": base.rstrip("/") + resource_path,
    }


def authorization_server_metadata(base: str) -> dict[str, Any]:
    return {
        "issuer": base,
        "authorization_endpoint": base + "/oauth/authorize",
        "token_endpoint": base + "/oauth/token",
        "registration_endpoint": base + "/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": oauth_scopes.supported_scopes(),
    }


def register_client(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    client_id = _client_id_for(body)
    payload = {
        "client_id": client_id,
        "client_id_issued_at": _now(),
        "token_endpoint_auth_method": "none",
        "redirect_uris": body.get("redirect_uris", []),
        "client_name": body.get("client_name", "ChatGPT MCP Client"),
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
    }
    _write_json(_json_path(root, "clients", client_id + ".json"), payload)
    return payload


def _redirect(uri: str, params: dict[str, str]) -> str:
    parsed = urllib.parse.urlparse(uri)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(params.items())
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def authorize(root: Path, headers: Any, query: str) -> tuple[int, dict[str, str], bytes]:
    args = urllib.parse.parse_qs(query, keep_blank_values=True)
    response_type = (args.get("response_type") or [""])[0]
    client_id = (args.get("client_id") or [""])[0]
    redirect_uri = (args.get("redirect_uri") or [""])[0]
    state = (args.get("state") or [""])[0]
    scope = (args.get("scope") or ["northstar.read northstar.write"])[0]
    code_challenge = (args.get("code_challenge") or [""])[0]
    code_challenge_method = (args.get("code_challenge_method") or ["plain"])[0]
    if response_type != "code" or not client_id or not redirect_uri:
        body = b"invalid OAuth authorize request"
        return 400, {"Content-Type": "text/plain; charset=utf-8"}, body
    # Local owner model: if the bridge was started in trusted-owner mode, the
    # OAuth authorization request is approved by that local owner authority.  The
    # code is single-use and short-lived; token exchange still has to present it.
    code = secrets.token_urlsafe(32)
    _write_json(_json_path(root, "codes", code + ".json"), {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": oauth_scopes.default_granted_scope_string(scope),
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "issued_at": _now(),
        "expires_at": _now() + CODE_TTL_SEC,
    })
    location = _redirect(redirect_uri, {"code": code, **({"state": state} if state else {})})
    body = ("<html><body><p>North Star Suite connection authorized.</p>"
            f"<p>Redirecting to <code>{html.escape(redirect_uri)}</code>.</p>"
            f"<script>location.href={json.dumps(location)};</script>"
            f"<a href={json.dumps(location)}>Continue</a></body></html>").encode("utf-8")
    return 302, {"Location": location, "Content-Type": "text/html; charset=utf-8"}, body


def _token_response(access_token: str, scope: str) -> tuple[int, dict[str, str], dict[str, Any]]:
    return 200, {"Cache-Control": "no-store", "Pragma": "no-cache"}, {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL_SEC,
        "scope": oauth_scopes.default_granted_scope_string(scope),
    }


def token(root: Path, body_bytes: bytes, content_type: str = "") -> tuple[int, dict[str, str], dict[str, Any]]:
    data = _parse_body(body_bytes, content_type)
    grant_type = str(data.get("grant_type", ""))
    code = str(data.get("code", ""))
    redirect_uri = str(data.get("redirect_uri", ""))
    client_id = str(data.get("client_id", ""))
    code_verifier = str(data.get("code_verifier", ""))
    if grant_type != "authorization_code" or not code:
        return 400, {}, {"error": "unsupported_grant_type"}

    used_path = _json_path(root, "used_codes", code + ".json")
    if used_path.exists():
        used = _read_json(used_path)
        if int(used.get("replay_until", 0)) >= _now():
            return _token_response(str(used.get("access_token", "")), str(used.get("scope", "northstar.read")))
        return 400, {}, {"error": "invalid_grant"}

    code_path = _json_path(root, "codes", code + ".json")
    if not code_path.exists():
        return 400, {}, {"error": "invalid_grant"}
    saved = _read_json(code_path)
    try:
        code_path.unlink()
    except OSError:
        pass
    if int(saved.get("expires_at", 0)) < _now():
        return 400, {}, {"error": "invalid_grant", "error_description": "code expired"}
    if redirect_uri and redirect_uri != saved.get("redirect_uri"):
        return 400, {}, {"error": "invalid_grant", "error_description": "redirect_uri mismatch"}
    if client_id and client_id != saved.get("client_id"):
        return 400, {}, {"error": "invalid_client"}
    challenge = str(saved.get("code_challenge", ""))
    method = str(saved.get("code_challenge_method", "plain"))
    if challenge:
        expected = _encoded_challenge(code_verifier) if method == "S256" else code_verifier
        if expected != challenge:
            return 400, {}, {"error": "invalid_grant", "error_description": "pkce mismatch"}

    scope = oauth_scopes.default_granted_scope_string(str(saved.get("scope", "northstar.read northstar.write")))
    access_token = secrets.token_urlsafe(48)
    fingerprint = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    _write_json(_json_path(root, "tokens", fingerprint + ".json"), {
        "client_id": saved.get("client_id"),
        "scope": scope,
        "issued_at": _now(),
        "expires_at": _now() + TOKEN_TTL_SEC,
    })
    _write_json(used_path, {
        "client_id": saved.get("client_id"),
        "scope": scope,
        "access_token": access_token,
        "issued_at": _now(),
        "replay_until": _now() + 30,
    })
    return _token_response(access_token, scope)


def token_is_valid(root: Path, access_token: str) -> bool:
    if not access_token:
        return False
    fingerprint = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    path = _json_path(root, "tokens", fingerprint + ".json")
    if not path.exists():
        return False
    try:
        data = _read_json(path)
    except Exception:
        return False
    return int(data.get("expires_at", 0)) >= _now()


def is_well_known_path(path: str) -> bool:
    return path.startswith("/.well-known/oauth-protected-resource") or path.startswith("/.well-known/oauth-authorization-server") or path.startswith("/.well-known/openid-configuration") or path.endswith("/.well-known/oauth-protected-resource") or path.endswith("/.well-known/oauth-authorization-server") or path.endswith("/.well-known/openid-configuration")


def _protected_resource_path_from_well_known(path: str, default_resource_path: str = "/mcp") -> str:
    marker = "oauth-protected-resource"
    if marker not in path:
        return default_resource_path
    suffix = path.split(marker, 1)[1].strip("/")
    if suffix:
        return "/" + suffix
    # ChatGPT probes both /.well-known/oauth-protected-resource/mcp-v2 and
    # /mcp-v2/.well-known/oauth-protected-resource.  In the second form the
    # resource path is the prefix before /.well-known/.
    prefix = path.split("/.well-known/", 1)[0].strip("/")
    if prefix:
        return "/" + prefix
    return default_resource_path


def well_known_response(base: str, path: str, default_resource_path: str = "/mcp") -> tuple[int, dict[str, Any]]:
    if "oauth-protected-resource" in path:
        return 200, protected_resource_metadata(base, _protected_resource_path_from_well_known(path, default_resource_path))
    if "oauth-authorization-server" in path or "openid-configuration" in path:
        return 200, authorization_server_metadata(base)
    return 404, {"ok": False, "error": "not_found", "path": path}


def base_url_from_headers(headers: Any) -> str:
    return _base_url(headers)
