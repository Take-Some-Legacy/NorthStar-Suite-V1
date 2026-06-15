from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RULES_SCHEMA = "noesis.suite.operator_response_rules.v1"
RULES_FILE_NAME = "operator-response-rules.md"
_FENCE_RE = re.compile(r"```(?:json|jsonc)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_RULE_CACHE: dict[str, dict[str, Any]] = {}


def _module_rules_path() -> Path:
    return Path(__file__).resolve().parent / "rules" / RULES_FILE_NAME


def _workspace_rules_path(root: Path | None) -> Path | None:
    return (root / ".takesome" / "config" / RULES_FILE_NAME) if isinstance(root, Path) else None


def rules_candidates(root: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    workspace = _workspace_rules_path(root)
    if workspace is not None:
        candidates.append(workspace)
    candidates.append(_module_rules_path())
    return candidates


def _extract_json_from_markdown(text: str, path: Path) -> dict[str, Any]:
    match = _FENCE_RE.search(text)
    if not match:
        raise ValueError(f"No fenced JSON rule block found in {path}")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise ValueError(f"Rule block must be a JSON object: {path}")
    return payload


def load_operator_rules(root: Path | None = None, *, refresh: bool = False) -> dict[str, Any]:
    for path in rules_candidates(root):
        if not path.exists():
            continue
        key = str(path.resolve())
        if not refresh and key in _RULE_CACHE:
            return _RULE_CACHE[key]
        payload = _extract_json_from_markdown(path.read_text(encoding="utf-8"), path)
        payload.setdefault("source", str(path))
        _RULE_CACHE[key] = payload
        return payload
    searched = ", ".join(str(path) for path in rules_candidates(root))
    raise FileNotFoundError(f"No {RULES_FILE_NAME} found. Searched: {searched}")


def _text(value: Any) -> str:
    return str(value or "")


def normalize_operator_text(value: Any, *, root: Path | None = None, rules: dict[str, Any] | None = None) -> str:
    payload = rules if isinstance(rules, dict) else load_operator_rules(root)
    text = _text(value)
    normalization = payload.get("normalization") if isinstance(payload.get("normalization"), dict) else {}
    for item in normalization.get("replace", []) or []:
        if isinstance(item, dict):
            text = text.replace(_text(item.get("from")), _text(item.get("to")))
    for codepoint in normalization.get("remove_codepoints", []) or []:
        if isinstance(codepoint, str):
            text = text.replace(codepoint, "")
    if normalization.get("strip", True):
        text = text.strip()
    return text


def _regex_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _search(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE) is not None


def match_rule(text: str, match: dict[str, Any] | None) -> bool:
    if not isinstance(match, dict) or not match:
        return True
    regexes = _regex_list(match.get("regex"))
    if regexes and not all(_search(pattern, text) for pattern in regexes):
        return False
    any_regexes = _regex_list(match.get("any_regex"))
    if any_regexes and not any(_search(pattern, text) for pattern in any_regexes):
        return False
    all_regexes = _regex_list(match.get("all_regex"))
    if all_regexes and not all(_search(pattern, text) for pattern in all_regexes):
        return False
    none_regexes = _regex_list(match.get("none_regex"))
    if none_regexes and any(_search(pattern, text) for pattern in none_regexes):
        return False
    return True


def _matches_from_rule(text: str, rule: dict[str, Any]) -> dict[str, str]:
    captures: dict[str, str] = {}
    extract = rule.get("extract") if isinstance(rule.get("extract"), dict) else {}
    for name, pattern in extract.items():
        if not isinstance(pattern, str):
            continue
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if not match:
            continue
        if name in match.groupdict():
            captures[name] = (match.group(name) or "").strip()
        elif match.groups():
            captures[name] = (match.group(1) or "").strip()
        else:
            captures[name] = (match.group(0) or "").strip()
    return captures


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return value.format_map(_SafeFormat({key: _text(val) for key, val in context.items()})).strip()
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    if isinstance(value, dict):
        rendered: dict[str, Any] = {}
        for key, item in value.items():
            target_key = key[:-9] if key.endswith("_template") else key
            rendered[target_key] = _render_value(item, context)
        return rendered
    return value


def _special_response(payload: dict[str, Any], key: str, *, text: str = "") -> dict[str, Any]:
    special = payload.get("special") if isinstance(payload.get("special"), dict) else {}
    data = special.get(key) if isinstance(special.get(key), dict) else {}
    return {
        "schema": payload.get("schema", RULES_SCHEMA),
        "available": bool(data.get("available", False)),
        "kind": data.get("kind", key),
        "summary": data.get("summary", key),
        "text": text,
        "normalized_text": text,
        "intent": data.get("intent", ""),
        "intents": [],
        "stage": data.get("stage", ""),
        "state": data.get("state", "waiting"),
        "ready_to_assign": bool(data.get("ready_to_assign", False)),
        "busy": bool(data.get("busy", False)),
        "blocked": bool(data.get("blocked", False)),
        "candidate": None,
        "policy": data.get("policy", {}),
        "rules_source": payload.get("source", ""),
        "reasons": list(data.get("reasons") or []),
    }


def _first_matching_kind(payload: dict[str, Any], text: str) -> dict[str, Any]:
    for rule in payload.get("response_kinds", []) or []:
        if isinstance(rule, dict) and match_rule(text, rule.get("match")):
            return rule
    fallback = payload.get("fallback_kind") if isinstance(payload.get("fallback_kind"), dict) else {}
    return fallback or {"kind": "freeform", "summary": "operator supplied freeform response"}


def _matching_intents(payload: dict[str, Any], text: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for rule in payload.get("intent_rules", []) or []:
        if isinstance(rule, dict) and match_rule(text, rule.get("match")):
            matches.append(rule)
    matches.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
    return matches


def evaluate_operator_response(value: Any, *, root: Path | None = None, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = rules if isinstance(rules, dict) else load_operator_rules(root)
    response = value if isinstance(value, dict) else {"available": bool(_text(value)), "text": _text(value)}
    if response.get("timed_out"):
        return _special_response(payload, "timed_out", text=_text(response.get("text")))
    if not response.get("available"):
        return _special_response(payload, "missing", text=_text(response.get("text")))

    normalized = normalize_operator_text(response.get("text"), rules=payload)
    if not normalized:
        return _special_response(payload, "missing", text="")

    kind_rule = _first_matching_kind(payload, normalized)
    intent_rules = _matching_intents(payload, normalized)
    primary_intent = intent_rules[0] if intent_rules else {}
    chosen = primary_intent or kind_rule
    captures = {}
    captures.update(_matches_from_rule(normalized, kind_rule))
    captures.update(_matches_from_rule(normalized, primary_intent))
    context = {"text": normalized, **captures}
    candidate = chosen.get("candidate") if isinstance(chosen.get("candidate"), dict) else None
    rendered_candidate = _render_value(candidate, context) if candidate else None
    if isinstance(rendered_candidate, dict) and not rendered_candidate.get("action_id"):
        rendered_candidate = None

    policy = chosen.get("policy") if isinstance(chosen.get("policy"), dict) else kind_rule.get("policy", {})
    reasons = []
    for source in (kind_rule, primary_intent):
        if isinstance(source, dict) and isinstance(source.get("reasons"), list):
            reasons.extend(str(item) for item in source.get("reasons") if item)

    return {
        "schema": payload.get("schema", RULES_SCHEMA),
        "available": True,
        "kind": kind_rule.get("kind", "freeform"),
        "summary": chosen.get("summary") or kind_rule.get("summary") or "operator response matched markdown rules",
        "text": response.get("text", ""),
        "normalized_text": normalized,
        "intent": primary_intent.get("id", ""),
        "intents": [item.get("id", "") for item in intent_rules if item.get("id")],
        "stage": chosen.get("stage") or kind_rule.get("stage", ""),
        "state": chosen.get("state") or kind_rule.get("state", "waiting"),
        "ready_to_assign": bool(chosen.get("ready_to_assign", kind_rule.get("ready_to_assign", True))),
        "busy": bool(chosen.get("busy", kind_rule.get("busy", False))),
        "blocked": bool(chosen.get("blocked", kind_rule.get("blocked", False))),
        "candidate": rendered_candidate,
        "policy": policy if isinstance(policy, dict) else {},
        "rules_source": payload.get("source", ""),
        "reasons": reasons,
    }


def classify_operator_response(response: dict[str, Any] | None, *, root: Path | None = None) -> dict[str, Any]:
    evaluation = evaluate_operator_response(response, root=root)
    return {
        "state": evaluation.get("state", "waiting"),
        "kind": evaluation.get("kind", "missing"),
        "intent": evaluation.get("intent", ""),
        "available": bool(evaluation.get("available")),
        "summary": evaluation.get("summary", ""),
        "stage": evaluation.get("stage", ""),
        "ready_to_assign": bool(evaluation.get("ready_to_assign")),
        "candidate": evaluation.get("candidate"),
        "rules_source": evaluation.get("rules_source", ""),
    }


def operator_response_kind(value: Any, *, root: Path | None = None) -> str:
    return str(evaluate_operator_response(value, root=root).get("kind") or "missing")


def response_candidate(value: Any, *, root: Path | None = None) -> dict[str, Any] | None:
    candidate = evaluate_operator_response(value, root=root).get("candidate")
    return candidate if isinstance(candidate, dict) else None


def default_assignment_candidate(*, root: Path | None = None) -> dict[str, Any]:
    payload = load_operator_rules(root)
    candidate = payload.get("default_assignment") if isinstance(payload.get("default_assignment"), dict) else {}
    return dict(candidate)


def scoring_rules(*, root: Path | None = None) -> list[dict[str, Any]]:
    payload = load_operator_rules(root)
    return [item for item in payload.get("scoring_rules", []) or [] if isinstance(item, dict)]
