from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PublishedWebArtifact:
    path: Path
    kind: str
    bytes_written: int

    def to_json(self) -> dict[str, Any]:
        return {"path": str(self.path), "kind": self.kind, "bytes": self.bytes_written}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_text(path: Path, text: str, *, kind: str) -> PublishedWebArtifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return PublishedWebArtifact(path=path, kind=kind, bytes_written=path.stat().st_size)


def write_json(path: Path, payload: Any, *, kind: str) -> PublishedWebArtifact:
    return write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), kind=kind)


def write_publish_manifest(root: Path, surface: str, artifacts: list[PublishedWebArtifact]) -> Path:
    manifest = {
        "schema": "noesis.web.publish_manifest.v1",
        "surface": surface,
        "generatedUtc": utc_now(),
        "artifacts": [artifact.to_json() for artifact in artifacts],
    }
    manifest_path = root / ".noesis" / "web" / surface / "publish-manifest.json"
    write_json(manifest_path, manifest, kind="publish-manifest")
    return manifest_path
