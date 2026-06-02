"""Status-provider package for Suite dashboards and collect-run health snapshots.

The initializer stays lightweight to avoid importing interactive/build actions
when non-interactive diagnostics only need one status provider.
"""

__all__: list[str] = []
