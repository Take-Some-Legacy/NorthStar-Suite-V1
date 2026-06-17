from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EditField:
    key: str
    label: str
    value: str
    kind: str = "text"
    editable: bool = False
    exists: bool | None = None
    group: str = "default"
    base: str = ""
    expression: str = ""

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "kind": self.kind,
            "editable": self.editable,
            "group": self.group,
        }
        if self.exists is not None:
            data["exists"] = self.exists
        if self.base:
            data["base"] = self.base
        if self.expression:
            data["expression"] = self.expression
        return data


def edit_model(target: str, fields: list[EditField | dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for field in fields:
        normalized.append(field.to_json() if isinstance(field, EditField) else dict(field))
    return {
        "schema": "noesis.ui.editModel.v1",
        "target": target,
        "fields": normalized,
    }
