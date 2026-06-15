from __future__ import annotations

import datetime as dt
import json
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Any

from .cluster_topology import cluster_summary
from .host_binding import DEFAULT_ENDPOINT_PATH, SuiteHostBinding, SuitePeerBinding
from .net_address import join_origin_path

REQUEST_OUTCOME_SCHEMA = "noesis.suite.request_outcome.v1"
CLUSTER_DOCTOR_SCHEMA = "noesis.suite.cluster_doctor.v1"
_DEFAULT_TIMEOUT_SEC = 1.5
_MAX_BODY_BYTES = 128 * 1024
_PREVIEW_CHARS = 900
_SECRET_KEY_PARTS = ("authorization", "credential", "password", "secret", "token", "key")


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_timeout(value: object, default: float = _DEFAULT_TIMEOUT_SEC) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except Exception:
        parsed = default
    return max(0.2, min(parsed, 15.0))


def _redact_text(value: str) -> str:
    lowered = value.lower()
    if any(part in lowered for part in _SECRET_KEY_PARTS):
        return "<redacted>"
    return value


def _scrub(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "<truncated-depth>"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if any(part in text_key.lower() for part in _SECRET_KEY_PARTS):
                out[text_key] = "<redacted>"
            else:
                out[text_key] = _scrub(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [_scrub(item, depth=depth + 1) for item in value[:30]]
    if isinstance(value, tuple):
        return [_scrub(item, depth=depth + 1) for item in value[:30]]
    if isinstance(value, str):
        if len(value) > _PREVIEW_CHARS:
            return _redact_text(value[:_PREVIEW_CHARS] + "...")
        return _redact_text(value)
    return value


def _json_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "top_level_type": "object",
            "schema": value.get("schema"),
            "keys": sorted(str(key) for key in value.keys())[:40],
        }
    if isinstance(value, list):
        return {"top_level_type": "array", "length": len(value)}
    return {"top_level_type": type(value).__name__}


def _preview(text: str) -> dict[str, Any]:
    compact = text.replace("\r", "\\r").replace("\n", "\\n")
    truncated = len(compact) > _PREVIEW_CHARS
    return {"text": _redact_text(compact[:_PREVIEW_CHARS]), "truncated": truncated}


@dataclass(frozen=True)
class ProbeTarget:
    machine_id: str
    role: str
    base_origin: str
    health_url: str
    status_url: str
    expected_cluster_id: str
    expected_endpoint_path: str = DEFAULT_ENDPOINT_PATH


def target_from_peer(peer: SuitePeerBinding, expected_cluster_id: str) -> ProbeTarget:
    return ProbeTarget(
        machine_id=peer.machine_id,
        role=peer.role,
        base_origin=peer.base_origin,
        health_url=peer.health_url,
        status_url=join_origin_path(peer.base_origin, "/status", default_path="/status"),
        expected_cluster_id=expected_cluster_id,
        expected_endpoint_path=peer.endpoint_path or DEFAULT_ENDPOINT_PATH,
    )


def _base_outcome(*, request_id: str, target: ProbeTarget, stage: str, url: str, timeout_sec: float, started_at: str) -> dict[str, Any]:
    return {
        "schema": REQUEST_OUTCOME_SCHEMA,
        "request_id": request_id,
        "target": {"machine_id": target.machine_id, "role": target.role, "base_origin": target.base_origin},
        "stage": stage,
        "method": "GET",
        "url": url,
        "started_at": started_at,
        "finished_at": None,
        "elapsed_ms": None,
        "timeout_sec": timeout_sec,
        "ok": False,
        "outcome": "not_started",
        "http": {"status": None, "reason": "", "content_type": "", "content_length": None, "bytes_read": 0},
        "json": {"parsed": False, "schema": None, "top_level_type": None, "keys": []},
        "body": {"preview": "", "truncated": False},
        "error": None,
    }


def probe_json_url(target: ProbeTarget, *, stage: str, url: str, timeout_sec: object = None, request_id: str = "") -> tuple[dict[str, Any], Any | None]:
    timeout = _safe_timeout(timeout_sec)
    started_at = _utc_now()
    started = time.perf_counter()
    rid = request_id or f"{target.machine_id}:{stage}"
    outcome = _base_outcome(request_id=rid, target=target, stage=stage, url=url, timeout_sec=timeout, started_at=started_at)
    body_bytes = b""
    status: int | None = None
    reason = ""
    headers: Any = {}
    error: BaseException | None = None

    parsed_url = urlparse(str(url or ""))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        outcome["finished_at"] = _utc_now()
        outcome["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        outcome["outcome"] = "invalid_url"
        outcome["error"] = {"type": "InvalidUrl", "message": f"URL must be absolute http(s): {url!r}"}
        return outcome, None

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "NoesisSuite-ClusterDoctor/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            reason = str(getattr(response, "reason", "") or "")
            headers = response.headers
            body_bytes = response.read(_MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        reason = str(exc.reason or "")
        headers = exc.headers
        body_bytes = exc.read(_MAX_BODY_BYTES + 1)
        error = exc
    except urllib.error.URLError as exc:
        error = exc
    except TimeoutError as exc:
        error = exc
    except socket.timeout as exc:
        error = exc
    except Exception as exc:  # noqa: BLE001 - diagnostic boundary must capture exact failure.
        error = exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    finished_at = _utc_now()
    content_type = ""
    content_length: int | None = None
    if headers:
        try:
            content_type = str(headers.get("Content-Type", "") or "")
            raw_length = headers.get("Content-Length")
            content_length = int(raw_length) if raw_length not in (None, "") else None
        except Exception:
            content_type = ""
            content_length = None
    truncated = len(body_bytes) > _MAX_BODY_BYTES
    if truncated:
        body_bytes = body_bytes[:_MAX_BODY_BYTES]
    body_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
    parsed_json: Any | None = None
    json_error = ""
    if body_text.strip():
        try:
            parsed_json = json.loads(body_text)
        except Exception as exc:  # noqa: BLE001
            json_error = f"{type(exc).__name__}: {exc}"

    outcome["finished_at"] = finished_at
    outcome["elapsed_ms"] = elapsed_ms
    outcome["http"] = {
        "status": status,
        "reason": reason,
        "content_type": content_type,
        "content_length": content_length,
        "bytes_read": len(body_bytes),
    }
    prev = _preview(body_text)
    outcome["body"] = {"preview": prev["text"], "truncated": bool(prev["truncated"] or truncated)}
    if parsed_json is not None:
        summary = _json_summary(parsed_json)
        outcome["json"] = {"parsed": True, **summary}
    else:
        outcome["json"] = {"parsed": False, "schema": None, "top_level_type": None, "keys": [], "error": json_error}

    if error is None:
        if status is not None and 200 <= status < 300:
            if body_text.strip() and parsed_json is None:
                outcome["outcome"] = "json_parse_error"
                outcome["error"] = {"type": "JsonParseError", "message": json_error}
            else:
                outcome["ok"] = True
                outcome["outcome"] = "ok"
        else:
            outcome["outcome"] = "http_error"
            outcome["error"] = {"type": "HttpStatusError", "message": f"HTTP {status} {reason}".strip()}
    else:
        error_name = type(error).__name__
        message = str(error)
        if isinstance(error, urllib.error.HTTPError):
            outcome["outcome"] = "http_error"
            outcome["error"] = {"type": "HTTPError", "message": f"HTTP {status} {reason}".strip()}
        elif isinstance(error, (TimeoutError, socket.timeout)) or "timed out" in message.lower():
            outcome["outcome"] = "timeout"
            outcome["error"] = {"type": error_name, "message": message or "request timed out"}
        elif isinstance(error, urllib.error.URLError):
            outcome["outcome"] = "connection_error"
            outcome["error"] = {"type": error_name, "message": message}
        else:
            outcome["outcome"] = "exception"
            outcome["error"] = {"type": error_name, "message": message}
    return outcome, _scrub(parsed_json) if parsed_json is not None else None


def _validate_health(target: ProbeTarget, outcome: dict[str, Any], body: Any | None) -> dict[str, Any]:
    diagnostics: list[str] = []
    if not outcome.get("ok"):
        diagnostics.append(f"health_request_{outcome.get('outcome')}")
    if body is None:
        diagnostics.append("health_body_missing_or_not_json")
    elif isinstance(body, dict):
        if body.get("ok") is False:
            diagnostics.append("health_reports_not_ok")
        remote_machine = body.get("machine_id") or body.get("host_id")
        if remote_machine and str(remote_machine) != target.machine_id:
            diagnostics.append(f"health_machine_id_mismatch:{remote_machine}")
        remote_cluster = body.get("cluster_id")
        if remote_cluster and target.expected_cluster_id and str(remote_cluster) != target.expected_cluster_id:
            diagnostics.append(f"health_cluster_id_mismatch:{remote_cluster}")
    return {"ok": not diagnostics, "diagnostics": diagnostics}


def _validate_status(target: ProbeTarget, outcome: dict[str, Any], body: Any | None) -> dict[str, Any]:
    diagnostics: list[str] = []
    remote: dict[str, Any] = {}
    if not outcome.get("ok"):
        diagnostics.append(f"status_request_{outcome.get('outcome')}")
    if body is None:
        diagnostics.append("status_body_missing_or_not_json")
    elif not isinstance(body, dict):
        diagnostics.append("status_body_not_object")
    else:
        schema = body.get("schema")
        if schema != "northstar.bridge.status.v2":
            diagnostics.append(f"status_schema_unexpected:{schema}")
        host_binding = body.get("host_binding") if isinstance(body.get("host_binding"), dict) else {}
        cluster = body.get("cluster") if isinstance(body.get("cluster"), dict) else {}
        bridge = body.get("bridge") if isinstance(body.get("bridge"), dict) else {}
        config = body.get("config") if isinstance(body.get("config"), dict) else {}
        mcp_route = config.get("mcp_route") if isinstance(config.get("mcp_route"), dict) else {}
        local_cluster = cluster.get("local") if isinstance(cluster.get("local"), dict) else {}
        remote_machine = host_binding.get("machine_id") or local_cluster.get("machine_id")
        remote_cluster = host_binding.get("cluster_id") or cluster.get("cluster_id")
        remote_endpoint = host_binding.get("endpoint_url") or local_cluster.get("endpoint_url")
        remote_paths = mcp_route.get("mcp_paths") if isinstance(mcp_route.get("mcp_paths"), list) else []
        remote = {
            "schema": schema,
            "bridge_version": bridge.get("version"),
            "machine_id": remote_machine,
            "cluster_id": remote_cluster,
            "endpoint_url": remote_endpoint,
            "mcp_paths": remote_paths[:20],
        }
        if remote_machine and str(remote_machine) != target.machine_id:
            diagnostics.append(f"status_machine_id_mismatch:{remote_machine}")
        if target.expected_cluster_id and remote_cluster and str(remote_cluster) != target.expected_cluster_id:
            diagnostics.append(f"status_cluster_id_mismatch:{remote_cluster}")
        if target.expected_endpoint_path and remote_paths and target.expected_endpoint_path not in [str(item) for item in remote_paths]:
            diagnostics.append(f"status_endpoint_path_missing:{target.expected_endpoint_path}")
    return {"ok": not diagnostics, "diagnostics": diagnostics, "remote": remote}


def run_cluster_doctor(binding: SuiteHostBinding | None, *, timeout_sec: object = None, include_status: bool = True, include_disabled: bool = False) -> dict[str, Any]:
    timeout = _safe_timeout(timeout_sec)
    generated_at = _utc_now()
    if binding is None:
        return {
            "schema": CLUSTER_DOCTOR_SCHEMA,
            "ok": False,
            "result": "unbound",
            "generated_at": generated_at,
            "timeout_sec": timeout,
            "topology": cluster_summary(None),
            "summary": {"peer_count": 0, "request_count": 0, "ok_count": 0, "failed_count": 0},
            "peers": [],
            "requests": [],
            "diagnostics": ["host_binding_missing"],
        }

    peers = [peer for peer in binding.peers if include_disabled or peer.enabled]
    requests: list[dict[str, Any]] = []
    peer_reports: list[dict[str, Any]] = []
    diagnostics: list[str] = list(binding.diagnostics)
    for index, peer in enumerate(peers, 1):
        if not peer.enabled:
            peer_reports.append({"machine_id": peer.machine_id, "role": peer.role, "enabled": False, "readiness": "disabled", "ok": False, "diagnostics": ["peer_disabled"], "requests": []})
            continue
        target = target_from_peer(peer, binding.cluster_id)
        health_outcome, health_body = probe_json_url(target, stage="health", url=target.health_url, timeout_sec=timeout, request_id=f"{index:03d}:{target.machine_id}:health")
        requests.append(health_outcome)
        health_validation = _validate_health(target, health_outcome, health_body)
        status_outcome: dict[str, Any] | None = None
        status_body: Any | None = None
        status_validation: dict[str, Any] = {"ok": True, "diagnostics": [], "remote": {}}
        if include_status:
            status_outcome, status_body = probe_json_url(target, stage="status", url=target.status_url, timeout_sec=timeout, request_id=f"{index:03d}:{target.machine_id}:status")
            requests.append(status_outcome)
            status_validation = _validate_status(target, status_outcome, status_body)
        peer_diags = [*health_validation["diagnostics"], *status_validation["diagnostics"]]
        if not health_outcome.get("ok"):
            readiness = "unreachable"
        elif peer_diags:
            readiness = "incompatible" if any("mismatch" in item or "unexpected" in item or "missing" in item for item in peer_diags) else "degraded"
        else:
            readiness = "ready"
        peer_reports.append(
            {
                "machine_id": peer.machine_id,
                "role": peer.role,
                "enabled": peer.enabled,
                "base_origin": peer.base_origin,
                "health_url": target.health_url,
                "status_url": target.status_url if include_status else None,
                "ok": readiness == "ready",
                "readiness": readiness,
                "diagnostics": peer_diags,
                "remote": status_validation.get("remote") or {},
                "requests": [health_outcome["request_id"], *([status_outcome["request_id"]] if status_outcome else [])],
            }
        )

    ok_peers = len([peer for peer in peer_reports if peer.get("ok")])
    failed_peers = len([peer for peer in peer_reports if peer.get("enabled") and not peer.get("ok")])
    ok_requests = len([request for request in requests if request.get("ok")])
    failed_requests = len(requests) - ok_requests
    if not binding.is_clustered or not peers:
        result = "standalone"
        ok = True
    elif failed_peers:
        result = "degraded" if ok_peers else "failed"
        ok = False
    else:
        result = "healthy"
        ok = True
    return {
        "schema": CLUSTER_DOCTOR_SCHEMA,
        "ok": ok,
        "result": result,
        "generated_at": generated_at,
        "timeout_sec": timeout,
        "include_status": bool(include_status),
        "topology": cluster_summary(binding),
        "summary": {
            "peer_count": len(peers),
            "enabled_peer_count": len([peer for peer in peers if peer.enabled]),
            "ready_peer_count": ok_peers,
            "failed_peer_count": failed_peers,
            "request_count": len(requests),
            "ok_request_count": ok_requests,
            "failed_request_count": failed_requests,
        },
        "peers": peer_reports,
        "requests": requests,
        "diagnostics": diagnostics,
    }


__all__ = ["CLUSTER_DOCTOR_SCHEMA", "REQUEST_OUTCOME_SCHEMA", "probe_json_url", "run_cluster_doctor", "target_from_peer"]
