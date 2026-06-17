#!/usr/bin/env python3
"""Compatibility entrypoint for the North Star AI Bridge.

Real implementation lives in `northstar_operator_bridge.py` so the public
entrypoint stays stable while the bridge itself can be split into focused
operator modules.
"""
from __future__ import annotations

import sys
from noesis.bridge.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
