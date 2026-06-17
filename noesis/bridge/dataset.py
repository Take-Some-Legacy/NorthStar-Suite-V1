from __future__ import annotations

# Thin compatibility facade. Dataset ownership is split across:
# - dataset_core.py: paths, safety and scoring primitives
# - dataset_archive.py: archive/materialization/status operations
# - dataset_browser.py: directory-first browsing and search
# - dataset_index.py: dataset index and knowledge registry rebuild

from .dataset_archive import (
    list_archives,
    materialize_archives,
    purge_materialized_archives,
    read_archive_member,
    scan_archive,
    search_archives,
    status,
)
from .dataset_browser import (
    browse_directories,
    profile_directory,
    search_directories,
    search_logic,
)
from .dataset_index import rebuild_index
from .dataset_maturity import formal_manifest, maturity_scan, strict_findings, write_maturity_index

__all__ = [
    "status",
    "list_archives",
    "scan_archive",
    "read_archive_member",
    "search_archives",
    "materialize_archives",
    "purge_materialized_archives",
    "browse_directories",
    "profile_directory",
    "search_directories",
    "search_logic",
    "rebuild_index",
    "formal_manifest",
    "maturity_scan",
    "strict_findings",
    "write_maturity_index",
    "analyze_entries",
]

from .dataset_entry_value import analyze_entries
