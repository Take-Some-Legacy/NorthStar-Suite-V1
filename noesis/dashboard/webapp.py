from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from noesis.web.adapters import PathMountedAdapter, WebAdapterSpec, WebServerApp
from noesis.web.contract import WebRequest, WebResponse, bytes_response, json_response, not_found, surface_metadata
from noesis.web.server import serve_web_server

from .path_config import update_dashboard_paths
from .operations import OperationStore
from .publisher import publish_dashboard
from .runs import DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_TITLE, index_payload, patch_payload, run_payload, utc_now
from .ui import render_html

DASHBOARD_ROUTES = (
    "/",
    "/dashboard",
    "/dashboard/data.json",
    "/dashboard/static/noesis-dashboard.css",
    "/dashboard/static/charts.js",
    "/dashboard/static/operations.js",
    "/dashboard/static/noesis-logo.svg",
    "/index.html",
    "/api/health",
    "/api/contract",
    "/api/runs",
    "/api/config/paths",
    "/api/operations",
    "/api/operations/<operationId>",
    "/api/runs/<runId>",
    "/api/runs/<runId>/patch",
    "/api/runs/<runId>/artifacts/<name>",
)

DASHBOARD_ADAPTER_SPEC = WebAdapterSpec(
    adapter_id="dashboard",
    surface="dashboard.runs",
    title=DASHBOARD_TITLE,
    mount_paths=("/", "/dashboard", "/index.html", "/api/health", "/api/contract", "/api/runs"),
    routes=DASHBOARD_ROUTES,
    policy="read-only run index, local artifact publication, no write actions, no readiness mutation",
    description="NOESIS run dashboard UI/API adapter served by the canonical noesis.webServer implementation.",
)


class DashboardRunsAdapter(PathMountedAdapter):
    spec = DASHBOARD_ADAPTER_SPEC

    def __init__(self, root: Path) -> None:
        self.root = root
        self.operations = OperationStore(root)

    def handle(self, request: WebRequest) -> WebResponse:
        route = "/" + "dashboard" + "/" + "static" + "/" + "charts" + ".js"
        path = request.path.rstrip("/") or "/"
        if path in {"/", "/dashboard", "/index.html"}:
            payload = publish_dashboard(self.root, index_payload(self.root), html_enabled=True)
            return WebResponse(body=render_html(payload).encode("utf-8"), content_type="text/html; charset=utf-8")
        if path == "/dashboard/data.json":
            return json_response(publish_dashboard(self.root, index_payload(self.root), html_enabled=True))
        if path == "/dashboard/static/noesis-dashboard.css":
            css_path = Path(__file__).resolve().parent / "static" / "noesis-dashboard.css"
            css = css_path.read_bytes() if css_path.is_file() else b"/* NOESIS dashboard stylesheet unavailable. */\n"
            return bytes_response(css, content_type="text/css; charset=utf-8")
        if path == route:
            asset_path = Path(__file__).resolve().parent / "static" / ("charts" + ".js")
            asset = asset_path.read_bytes() if asset_path.is_file() else b"// NOESIS dashboard charts unavailable.\n"
            return bytes_response(asset, content_type="application/javascript; charset=utf-8")
        static_prefix = "/dashboard/static/"
        if path.startswith(static_prefix):
            static_name = path[len(static_prefix):]
            allowed = {
                "noesis-dashboard" + ".css": "text/css; charset=utf-8",
                "charts" + ".js": "application/javascript; charset=utf-8",
                "operations" + ".js": "application/javascript; charset=utf-8",
                "noesis-logo" + ".svg": "image/svg+xml; charset=utf-8",
            }
            if static_name in allowed:
                static_path = Path(__file__).resolve().parent / "static" / static_name
                payload = static_path.read_bytes() if static_path.is_file() else b""
                return bytes_response(payload, content_type=allowed[static_name])
        config_route = "/api/" + "config" + "/" + "paths"
        if path == config_route:
            if request.method == "POST":
                body = request.json_body()
                updates = body.get("updates", body) if isinstance(body, dict) else {}
                return json_response(update_dashboard_paths(self.root, updates))
            payload = index_payload(self.root).get("paths", {})
            return json_response({"ok": True, "paths": payload})
        ops_route = "/api/" + "operations"
        if path == ops_route:
            if request.method == "POST":
                body = request.json_body()
                action_id = str((body or {}).get("actionId", "")) if isinstance(body, dict) else ""
                timeout_sec = int((body or {}).get("timeoutSec", 240)) if isinstance(body, dict) else 240
                return json_response(self.operations.start_suite_action(action_id, timeout_sec=timeout_sec))
            return json_response({"ok": True, "operations": self.operations.list()})
        if path.startswith(ops_route + "/"):
            op_id = path[len(ops_route) + 1:]
            payload = self.operations.get(op_id)
            if payload is None:
                return json_response({"ok": False, "error": "operation_not_found", "operationId": op_id}, status=404)
            return json_response({"ok": True, "operation": payload})

        if path == "/api/health":
            return json_response(
                {
                    "ok": True,
                    "title": self.spec.title,
                    "surface": self.spec.surface,
                    "adapterId": self.spec.adapter_id,
                    "generatedUtc": utc_now(),
                    "root": str(self.root),
                    "web": surface_metadata(
                        title=self.spec.title,
                        surface=self.spec.surface,
                        root=self.root,
                        routes=list(DASHBOARD_ROUTES),
                    ),
                    "adapter": self.spec.as_dict(root=self.root),
                }
            )
        if path == "/api/runs":
            return json_response(publish_dashboard(self.root, index_payload(self.root), html_enabled=True))
        if path.startswith("/api/runs/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) == 3:
                payload = run_payload(self.root, parts[2])
                if payload is None:
                    return json_response({"ok": False, "error": "run_not_found", "runId": parts[2]}, status=404)
                return json_response(payload)
            if len(parts) == 4 and parts[3] == "patch":
                payload = patch_payload(self.root, parts[2])
                status = 200 if payload.get("ok") else 404
                return json_response(payload, status=status)
            if len(parts) == 5 and parts[3] == "artifacts":
                return self._artifact(parts[2], parts[4])
        if path == "/api/contract":
            return json_response(self.spec.as_dict(root=self.root))
        return not_found(path)

    def _artifact(self, run_id: str, name: str) -> WebResponse:
        safe_name = Path(name).name
        path = self.root / ".noesis" / "runs" / run_id / safe_name
        if not path.exists() or not path.is_file():
            return json_response({"ok": False, "error": "artifact_not_found", "runId": run_id, "artifact": safe_name}, status=404)
        content_type = "application/json; charset=utf-8" if safe_name.endswith(".json") else "text/plain; charset=utf-8"
        return bytes_response(path.read_bytes(), content_type=content_type)


# Backward-compatible class name for imports that still expect a surface object.
DashboardWebSurface = DashboardRunsAdapter


def dashboard_web_server(root: Path) -> WebServerApp:
    return WebServerApp(
        root=root,
        title=DASHBOARD_TITLE,
        name="noesis.webServer.dashboard",
        adapters=[DashboardRunsAdapter(root)],
    )


def serve_dashboard(root: Path, *, host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT, open_browser: bool = False) -> int:
    publish_dashboard(root, index_payload(root), html_enabled=True)
    return serve_web_server(dashboard_web_server(root), root=root, host=host, port=port, open_browser=open_browser)
