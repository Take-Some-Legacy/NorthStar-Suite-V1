#!/usr/bin/env python3
"""Compatibility wrapper for North Star AI Bridge split package.

Public callers may still import/call `northstar_operator_bridge.py`, but the
implementation now lives under `northstar_bridge/` by domain:
contracts, paths, auth, suite, dataset, memory, repo, status, workflow,
registry, rpc, server and cli.
"""
from __future__ import annotations

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from northstar_bridge.cli import Handler, build_tools, main, run_hello, run_http, run_once, run_stdio  # noqa: E402,F401

# Backward-compatible symbols for older console instrumentation/tests.
_tools = build_tools


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
