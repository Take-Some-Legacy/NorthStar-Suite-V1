from __future__ import annotations

from collections.abc import Iterable


def split_choice_tokens(choice: str | None) -> list[str]:
    if choice is None:
        return []
    return [token.strip().strip('"').strip("'") for token in choice.split(",") if token.strip()]


def lower_token_set(tokens: Iterable[str]) -> set[str]:
    return {token.lower() for token in tokens}


def unique_casefolded(tokens: Iterable[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(token)
    return selected


def exclusive_choice_kind(
    tokens: list[str],
    *,
    all_tokens: set[str] | None = None,
    none_tokens: set[str] | None = None,
    all_error: str = "all/0 cannot be mixed with explicit targets",
    none_error: str = "none/skip cannot be mixed with explicit targets",
) -> str:
    """Return 'all', 'none' or '' for a token list with exclusive commands."""

    lowered = lower_token_set(tokens)
    if all_tokens and lowered & all_tokens:
        if len(tokens) == 1:
            return "all"
        raise ValueError(all_error)
    if none_tokens and lowered & none_tokens:
        if len(tokens) == 1:
            return "none"
        raise ValueError(none_error)
    return ""
