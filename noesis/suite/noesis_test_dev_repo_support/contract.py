"""Compatibility wrapper for the migrated NOESIS testDevRepo contract.

Runtime logic lives in noesis.verification.test_dev_repo.contract.
"""
from noesis.verification.test_dev_repo.contract import (
    CORE_SCOPE,
    FULL_SCOPE,
    readiness_kind_for_scope,
    scope_description,
    scope_warning,
)

__all__ = [
    "CORE_SCOPE",
    "FULL_SCOPE",
    "readiness_kind_for_scope",
    "scope_description",
    "scope_warning",
]
