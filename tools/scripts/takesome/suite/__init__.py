"""Suite command-center package for Take Some().

Keep this package initializer intentionally lightweight. Import concrete Suite
surfaces from their modules (`suite.registry`, `suite.actions`, etc.) so utility
commands such as `collect-run` can read `suite.context` without constructing the
whole action registry and build pipeline.
"""

__all__: list[str] = []
