from __future__ import annotations

BRIDGE_RELEASE_NAME = "dev mode"
BRIDGE_RELEASE_NOTES = "dev-2"
BRIDGE_PUBLIC_TITLE = "North Star Suite V2"
BRIDGE_PUBLIC_DESCRIPTION = (
    "North Star Engine operator and workspace bridge for diagnostics, OAuth-secured "
    "Suite commands, dataset search, and controlled local workspace maintenance."
)


def metadata() -> dict[str, str]:
    return {
        "release_name": BRIDGE_RELEASE_NAME,
        "release_notes": BRIDGE_RELEASE_NOTES,
        "title": BRIDGE_PUBLIC_TITLE,
        "description": BRIDGE_PUBLIC_DESCRIPTION,
    }
