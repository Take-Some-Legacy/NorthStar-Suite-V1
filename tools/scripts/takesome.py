#!/usr/bin/env python3
"""Thin launcher for the layered Take Some / North Star Engine script plane."""

from __future__ import annotations

import sys

from takesome.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
