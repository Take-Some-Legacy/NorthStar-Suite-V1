"""NOESIS testDevRepo readiness contract.

Canonical home for scope-aware merge-readiness semantics.
"""
from __future__ import annotations

CORE_SCOPE = "noesis-core"
FULL_SCOPE = "full-repo"

def readiness_kind_for_scope(scope: str) -> str:
    return "global_merge_ready" if scope == FULL_SCOPE else "focused_merge_ready"

def scope_description(scope: str) -> str:
    if scope == FULL_SCOPE:
        return "Whole repository validation is requested, but readiness is denied until the full gate is implemented."
    return "Focused NOESIS/Suite/action-layer changes only."

def scope_warning(scope: str) -> str:
    if scope == FULL_SCOPE:
        return "Full repository gate is registered but intentionally rejects until full checks are implemented."
    return "Focused NOESIS-core gate; not whole repository readiness."
