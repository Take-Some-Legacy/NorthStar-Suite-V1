from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


TEMPLATE_ROOT = Path(__file__).with_name("tpl")
_RAW_TOKEN = re.compile(r"\{\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}\}")
_ESCAPED_TOKEN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class TemplateRenderError(RuntimeError):
    """Raised when a dashboard template cannot be loaded or rendered."""


def _string_value(context: dict[str, Any], key: str) -> str:
    if key not in context:
        raise TemplateRenderError(f"missing template value: {key}")
    value = context[key]
    return "" if value is None else str(value)


def render_template(name: str, /, **context: Any) -> str:
    """Render a small dashboard template.

    The dashboard deliberately keeps a tiny dependency-free template layer:
    - ``{{name}}`` escapes HTML;
    - ``{{{name}}}`` injects already-safe/raw HTML fragments.
    """
    path = (TEMPLATE_ROOT / name).resolve()
    try:
        path.relative_to(TEMPLATE_ROOT.resolve())
    except ValueError as exc:
        raise TemplateRenderError(f"template escapes root: {name}") from exc
    if not path.is_file():
        raise TemplateRenderError(f"template not found: {name}")

    text = path.read_text(encoding="utf-8")

    def raw(match: re.Match[str]) -> str:
        return _string_value(context, match.group(1))

    def escaped(match: re.Match[str]) -> str:
        return html.escape(_string_value(context, match.group(1)), quote=True)

    text = _RAW_TOKEN.sub(raw, text)
    return _ESCAPED_TOKEN.sub(escaped, text)
