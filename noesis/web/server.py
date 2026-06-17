from __future__ import annotations

import http.server
import socketserver
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .adapters import WebServerApp
from .contract import WebRequest, WebResponse, WebSurface, noesis_web_headers, parse_query, text_response


class NoesisWebServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_class: type[http.server.BaseHTTPRequestHandler], *, app: WebSurface | WebServerApp, root: Path) -> None:
        super().__init__(server_address, handler_class)
        self.app = app
        self.root = root


class NoesisWebHandler(http.server.BaseHTTPRequestHandler):
    server: NoesisWebServer

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[noesis-web:{self.server.app.name}] {self.address_string()} - {fmt % args}")

    def do_OPTIONS(self) -> None:
        self._write_response(text_response("", status=204))

    def do_HEAD(self) -> None:
        request = self._request(body=b"")
        response = self.server.app.handle(request)
        self._write_response(WebResponse(status=response.status, body=b"", content_type=response.content_type, headers=response.headers))

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def _handle(self) -> None:
        try:
            response = self.server.app.handle(self._request())
        except Exception as exc:
            response = text_response(f"NOESIS web surface error: {exc}", status=500)
        self._write_response(response)

    def _request(self, *, body: bytes | None = None) -> WebRequest:
        parsed = urlparse(self.path)
        raw_body = body if body is not None else self._read_body()
        return WebRequest(
            method=self.command.upper(),
            path=parsed.path or "/",
            query=parse_query(parsed.query),
            headers={key: value for key, value in self.headers.items()},
            body=raw_body,
            root=self.server.root,
        )

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _write_response(self, response: WebResponse) -> None:
        body = response.body or b""
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization")
        for key, value in noesis_web_headers(title=self.server.app.title, surface=self.server.app.name).items():
            self.send_header(key, value)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        if body and self.command.upper() != "HEAD":
            self.wfile.write(body)


def serve_web_surface(app: WebSurface | WebServerApp, *, root: Path, host: str, port: int, open_browser: bool = False) -> int:
    server = NoesisWebServer((host, port), NoesisWebHandler, app=app, root=root)
    url = f"http://{host}:{port}/"
    print(f"{app.title}: {url}")
    print("Web contract: noesis.web.v1")
    if isinstance(app, WebServerApp):
        print(f"Web server: {app.name}")
        print("Adapters:")
        for adapter in app.adapters:
            mounts = ", ".join(adapter.spec.normalized_mounts())
            print(f"  - {adapter.spec.adapter_id}: {adapter.spec.surface} [{mounts}]")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{app.title} stopped.")
    finally:
        server.server_close()
    return 0


def serve_web_server(app: WebServerApp, *, root: Path, host: str, port: int, open_browser: bool = False) -> int:
    return serve_web_surface(app, root=root, host=host, port=port, open_browser=open_browser)
