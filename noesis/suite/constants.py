from __future__ import annotations

import os
import sys

WIN = os.name == "nt"
DLL_EXT = ".dll" if WIN else (".dylib" if sys.platform == "darwin" else ".so")

ROOT_EXCLUDED_DIRS = {
    ".git", ".idea", ".vs", ".northstar", ".takesome", "target", "logs", "cache", "stamps",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", "bin", "obj", "out", "dist", "artifacts",
}
SOURCE_ARCHIVE_EXCLUDED_EXTENSIONS = {
    ".dll", ".so", ".dylib", ".exe", ".pdb", ".ilk", ".obj", ".o", ".lib", ".exp",
    ".log", ".tmp", ".temp", ".bak", ".old", ".stamp", ".zip", ".7z", ".rar", ".tar", ".gz", ".xz", ".zst",
    ".woff", ".woff2",
}
SOURCE_ARCHIVE_EXCLUDED_FILENAMES = {"Thumbs.db", "desktop.ini", ".DS_Store"}
