"""Robust parser for Nemotron-style validator output.

Nemotron-Super emits reasoning ending with a lone `</think>` (no opening `<think>`
tag). Reasoning prose often contains pseudo-structured JSON examples that break
greedy regex extraction. This parser handles those patterns and never silently
claims success on broken output.

Strategy:
1. Strip reasoning by taking everything after the last `</think>` (if any).
2. Try a fenced ```json``` block at the tail end.
3. Try the last balanced `[...]` block via bracket-depth scanning.
4. Try the last balanced `{...}` block (for dict-wrapped arrays).
5. Report status: `ok`, `truncated` (finish_reason=length + partial salvage),
   `parse_failed`, `no_data`.

Callers must NOT silently fall back to original inputs on failure — they should
propagate the status so downstream stages can distinguish "validator said keep
all" from "validator crashed".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_THINK_CLOSE_RE = re.compile(r"</think>", flags=re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", flags=re.MULTILINE)


@dataclass
class ValidatorParseResult:
    """Structured result from parsing an LLM validator response.

    Attributes:
        items: decisions parsed from the LLM output (each typically has fields
            like `url`, `keep`, `relevance_score`, `reason`). May be empty on
            partial-salvage or parse failure.
        status: one of `ok`, `truncated`, `parse_failed`, `no_data`.
            - `ok`: normal successful parse.
            - `truncated`: LLM hit `finish_reason=length`; items may be partial.
            - `parse_failed`: no parseable JSON anywhere in output.
            - `no_data`: input text was empty.
        strategy: which extraction strategy succeeded (`fenced`, `tail_array`,
            `tail_object`, or `none`).
        raw_trailer: last ~300 chars of raw text, for debugging.
    """

    items: list[dict] = field(default_factory=list)
    status: str = "no_data"
    strategy: str = "none"
    raw_trailer: str = ""


def _strip_reasoning(text: str) -> str:
    """Take content after the last `</think>` close tag, if present.

    Handles Nemotron's lone-close-tag pattern: reasoning prose then `</think>`
    then the actual structured output. Also handles full `<think>...</think>`.
    If no `</think>`, returns the input unchanged.
    """
    matches = list(_THINK_CLOSE_RE.finditer(text))
    if matches:
        return text[matches[-1].end():].strip()
    return text.strip()


def _try_fenced_json(text: str) -> Any | None:
    """Return parsed contents of the last ```json fenced block, if valid."""
    blocks = _FENCE_RE.findall(text)
    for block in reversed(blocks):
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue
    return None


def _try_tail_balanced(text: str, open_ch: str, close_ch: str) -> Any | None:
    """Find the last balanced block [...]/{...} at text end and parse it.

    Scans from the last close char backwards, tracking depth. When depth
    returns to 0 we have a balanced candidate — try json.loads; if that fails,
    continue scanning for earlier matches (reasoning may contain inline blocks).
    """
    last_close = text.rfind(close_ch)
    if last_close < 0:
        return None

    depth = 0
    i = last_close
    while i >= 0:
        c = text[i]
        if c == close_ch:
            depth += 1
        elif c == open_ch:
            depth -= 1
            if depth == 0:
                candidate = text[i : last_close + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Try an earlier occurrence of open_ch; advance to next left char
                    pass
        i -= 1
    return None


def _unwrap_list(parsed: Any) -> list[dict] | None:
    """Accept either `[{...}, ...]` or `{"items": [{...}, ...]}` shapes."""
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        for v in parsed.values():
            if isinstance(v, list):
                inner = [x for x in v if isinstance(x, dict)]
                if inner:
                    return inner
    return None


def parse_validator_response(
    raw_text: str,
    finish_reason: str | None = None,
) -> ValidatorParseResult:
    """Parse Nemotron validator output into a structured result.

    Args:
        raw_text: raw assistant content from the LLM.
        finish_reason: OpenAI-compat `finish_reason`. If `length`, we downgrade
            status to `truncated` even on successful extraction (partial data).

    Returns:
        `ValidatorParseResult` with status and items. Never raises.
    """
    if not raw_text or not raw_text.strip():
        return ValidatorParseResult([], "no_data", "none", "")

    trailer = raw_text[-300:]
    stripped = _strip_reasoning(raw_text)

    for strategy, parser in (
        ("fenced", _try_fenced_json),
        ("tail_array", lambda t: _try_tail_balanced(t, "[", "]")),
        ("tail_object", lambda t: _try_tail_balanced(t, "{", "}")),
    ):
        parsed = parser(stripped)
        if parsed is not None:
            items = _unwrap_list(parsed)
            if items is not None:
                status = "truncated" if finish_reason == "length" else "ok"
                return ValidatorParseResult(items, status, strategy, trailer)

    status = "truncated" if finish_reason == "length" else "parse_failed"
    return ValidatorParseResult([], status, "none", trailer)
