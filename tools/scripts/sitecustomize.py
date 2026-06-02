"""
North Star Suite Python startup guard.

This file is imported automatically by CPython when tools/scripts is on
sys.path. It keeps Suite command output pipe-safe on Windows consoles that use
legacy code pages such as cp1251. The goal is not to change Suite logic; it only
prevents diagnostic commands from crashing while printing Unicode UI glyphs.
"""
from __future__ import annotations

import os
import sys


def _reconfigure_streams() -> None:
    # Respect an explicit operator override. Otherwise prefer UTF-8 because the
    # AI bridge captures subprocess output through pipes and JSON transports.
    encoding = os.environ.get("NORTHSTAR_SUITE_STDIO_ENCODING", "utf-8")
    errors = os.environ.get("NORTHSTAR_SUITE_STDIO_ERRORS", "replace")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding=encoding, errors=errors)
        except Exception:
            # Startup customization must never break the actual command.
            pass


_reconfigure_streams()
