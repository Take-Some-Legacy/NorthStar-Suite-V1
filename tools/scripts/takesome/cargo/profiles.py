from __future__ import annotations

from pathlib import Path

from ..paths import suite_path


def build_state_root(root: Path) -> Path:
    """Generated plugin/codecs build stamps live in .takesome, not Plugins/."""
    return suite_path(root, "build-state")
