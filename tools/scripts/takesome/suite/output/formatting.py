from __future__ import annotations

import json
from typing import Any


def json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def text_block(text: str) -> str:
    return "```text\n" + text.rstrip() + "\n```"


def format_json_or_text_block(text: str, *, width: int = 180) -> str:
    if not text:
        return text_block("<empty>")
    stripped = text.strip()
    parsed = try_parse_json(stripped)
    if parsed is not None:
        return json_block(parsed)
    return text_block(wrap_long_lines(text.rstrip(), width=width))


def try_parse_json(text: str) -> Any | None:
    if not text:
        return None
    if text[0] not in "[{\"":
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def wrap_long_lines(text: str, *, width: int = 180) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if len(line) <= width:
            out.append(line)
            continue
        current = line
        while len(current) > width:
            out.append(current[:width] + " ↩")
            current = "    " + current[width:]
        out.append(current)
    return "\n".join(out)


def stream_markdown_section(name: str, text: str, *, byte_count: int | None = None, truncated: bool = False) -> list[str]:
    line_count = len(text.splitlines()) if text else 0
    byte_label = byte_count if byte_count is not None else len(text.encode("utf-8", errors="replace"))
    return [
        f"### {name}",
        "",
        f"- bytes: `{byte_label}`",
        f"- lines: `{line_count}`",
        f"- truncated: `{str(truncated).lower()}`",
        "",
        format_json_or_text_block(text),
        "",
    ]
