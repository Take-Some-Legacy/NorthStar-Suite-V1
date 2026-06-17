from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from noesis.web.publishing import write_json, write_publish_manifest, write_text

from .ui import render_html


DASHBOARD_SURFACE = "dashboard.runs"


def publish_dashboard(root: Path, payload: dict[str, Any], *, html_enabled: bool = True) -> dict[str, Any]:
    """Publish static dashboard artifacts.

    The dashboard can be opened via file:// or served by noesis.web.server.
    Publishing is observational and must not alter readiness decisions.
    """

    artifacts = [
        write_json(root / ".noesis" / "index" / "runs.json", payload, kind="runs-index-json"),
    ]
    if html_enabled:
        artifacts.append(write_text(root / ".noesis" / "dashboard" / "index.html", render_html(payload), kind="dashboard-html"))
    manifest_path = write_publish_manifest(root, DASHBOARD_SURFACE, artifacts)
    payload.setdefault("publishing", {})
    payload["publishing"].update(
        {
            "schema": "noesis.dashboard.publish.v1",
            "surface": DASHBOARD_SURFACE,
            "manifest": str(manifest_path),
            "artifacts": [artifact.to_json() for artifact in artifacts],
        }
    )
    # Keep runs.json in sync with the publishing block too.
    (root / ".noesis" / "index" / "runs.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload
