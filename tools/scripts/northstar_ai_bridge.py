#!/usr/bin/env python3
"""Compatibility entrypoint for the North Star AI Bridge.

Real implementation lives in `northstar_operator_bridge.py` so the public
entrypoint stays stable while the bridge itself can be split into focused
operator modules.
"""
from __future__ import annotations

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from northstar_operator_bridge import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
