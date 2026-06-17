from __future__ import annotations

from .contract import WebRequest, WebResponse, WebSurface, html_response, json_response, text_response
from .server import serve_web_surface

__all__ = [
    "WebRequest",
    "WebResponse",
    "WebSurface",
    "html_response",
    "json_response",
    "text_response",
    "serve_web_surface",
]
