"""End-to-end validator call: A2A send → robust parse → merge into items.

Replaces the inline `_a2a_send` + `_parse_validator_response` pattern previously
duplicated in every extractor's register.py. Consolidates three improvements:

1. Input clipping: trims item.text to ~1500 chars and drops noisy metadata
   (comments, flair, body_full) before serializing → prompt tokens shrink 3-5x.
2. Robust parsing: via `validator_core.parser.parse_validator_response`.
3. Observable failures: LLM errors / parse failures are tagged into item
   metadata (`validator_status`) instead of being silently swallowed. Caller
   can distinguish "validator said keep all" from "validator crashed".

URL-keyed merge: the new validator prompt returns decisions like
    [{"url": ..., "keep": bool, "relevance_score": float, "reason": str}, ...]
We look decisions up by URL and annotate the original EvidenceItem. Items the
validator omitted are kept conservatively (score unknown, status marks this).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

import requests

from ari_core import EvidenceItem
from validator_core.parser import parse_validator_response

_NON_ALNUM_RE = re.compile(r"[^0-9a-z가-힣]+")


def _normalize(s: str) -> str:
    """Lowercase + collapse non-alphanumeric (ASCII + Hangul)."""
    return _NON_ALNUM_RE.sub("", s.lower())


def _find_approx(body: str, query: str) -> int:
    """Case-insensitive positional find for `query` in `body`, tolerant of
    hyphen / space variants. Returns byte index in `body`, or -1.
    """
    if not query:
        return -1
    bl = body.lower()
    for form in (
        query.lower(),
        query.lower().replace("-", " "),
        query.lower().replace(" ", "-"),
        query.lower().replace("-", ""),
        query.lower().replace(" ", ""),
    ):
        if not form:
            continue
        idx = bl.find(form)
        if idx >= 0:
            return idx
    # Fall back to the first token of a hyphen/space-delimited query
    first = re.split(r"[-\s]+", query.strip(), maxsplit=1)[0].lower()
    if first and first != query.lower():
        idx = bl.find(first)
        if idx >= 0:
            return idx
    return -1


def _window_around_match(body: str, query: str, window_chars: int) -> str:
    """Return up to `window_chars` chars of `body` centered on the query match.

    If the match is found, pad half the window on each side and add ellipses.
    If not found, return the prefix (simple `body[:window_chars]`).
    """
    pos = _find_approx(body, query)
    if pos < 0 or window_chars >= len(body):
        return body[:window_chars]
    half = max(window_chars // 2, 200)
    start = max(0, pos - half)
    end = min(len(body), start + window_chars)
    # If we truncated at end, try pulling start back
    if end - start < window_chars and start > 0:
        start = max(0, end - window_chars)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return prefix + body[start:end] + suffix


@dataclass
class ClientConfig:
    """Per-source validator-call parameters."""

    url: str
    timeout_seconds: int = 120
    min_relevance_score: float = 0.5
    max_text_chars: int = 2500


@dataclass
class ValidateResult:
    """Summary of a validator call.

    Attributes:
        items: items the caller should forward downstream (kept + conservatively-
            kept "uncertain" items from the LLM's omission).
        status: one of `ok` / `truncated` / `parse_failed` / `no_data` /
            `http_error`. Propagate to reporter so demo observability is honest.
        note: free-form diagnostic string (strategy used, last trailer chars,
            HTTP error message).
        kept: size of `items`.
        total: input item count.
    """

    items: list[EvidenceItem]
    status: str
    note: str
    kept: int
    total: int


def _slim_item(item: EvidenceItem, max_chars: int, query: str = "") -> dict:
    """Relevance-relevant subset only.

    Merges body + top comment bodies into a single `text` field under `max_chars`.
    For sources like reddit / geeknews / lobsters the queried product often
    appears in comments, not the body. Dropping comments caused false negatives.

    Two quality levers:
    1. Budget split: 50/50 body/comments when comments exist.
    2. Query-keyword prioritization: comments whose normalized body contains
       the normalized query are emitted FIRST; remaining comments fill the
       leftover budget. Without this, the first few comments hog the budget
       even when later comments carry the real signal (observed on geeknews
       topic 28470 where comment[2] contains a detailed Nemotron-3 discussion).

    Comments are not individually clipped at a small per-comment cap; they
    consume remaining budget naturally, so long signal-carrying comments are
    preserved intact when they match the query.
    """
    md = item.metadata or {}
    body = item.text or ""
    comments = md.get("comments") or []
    q_norm = _normalize(query) if query else ""

    if comments and isinstance(comments, list):
        body_budget = max_chars // 2
        comm_budget = max_chars - body_budget
        body_part = body[:body_budget]

        # Partition comments: query-hit first, others after (both in original order).
        hits: list[dict] = []
        others: list[dict] = []
        for c in comments[:20]:
            if not isinstance(c, dict):
                continue
            cb = (c.get("body") or "").strip()
            if not cb:
                continue
            bucket = hits if (q_norm and q_norm in _normalize(cb)) else others
            bucket.append(c)

        comm_parts: list[str] = []
        remaining = comm_budget
        # Hit comments: window around the match so trailing mentions survive
        for c in hits:
            if remaining <= 0:
                break
            cb = (c.get("body") or "").strip()
            windowed = _window_around_match(cb, query, min(remaining, 1400))
            snippet = f"- {windowed}"
            if len(snippet) > remaining:
                snippet = snippet[:remaining]
            if len(snippet) > 3:
                comm_parts.append(snippet)
                remaining -= len(snippet) + 1
        # Filler comments: normal prefix-clip
        for c in others:
            if remaining <= 0:
                break
            cb = (c.get("body") or "").strip()
            snippet = f"- {cb}"
            if len(snippet) > remaining:
                snippet = snippet[:remaining]
            if len(snippet) > 3:
                comm_parts.append(snippet)
                remaining -= len(snippet) + 1
        text = body_part + ("\n\nComments:\n" + "\n".join(comm_parts) if comm_parts else "")
    else:
        text = body[:max_chars]

    slim_md: dict[str, Any] = {}
    for k in ("author", "subreddit", "topic_id", "upvotes", "comments_count"):
        if k in md:
            slim_md[k] = md[k]
    return {
        "url": item.url,
        "title": item.title or "",
        "text": text,
        "score": item.score,
        "metadata": slim_md,
    }


def _build_user_message(product_name: str, items: list[EvidenceItem], max_chars: int) -> str:
    slim = [_slim_item(it, max_chars, query=product_name) for it in items]
    items_json = json.dumps(slim, ensure_ascii=False, default=str)
    return f"Product: {product_name}\n\nScraped data:\n{items_json}"


def _a2a_send(url: str, message: str, timeout: int) -> tuple[str, str | None]:
    """A2A v0.3 message/send; returns (assistant_text, finish_reason).

    NAT's a2a front end doesn't currently expose `finish_reason` over the wire.
    We return None; the parser treats None as normal (only downgrades to
    `truncated` when caller passes `length` explicitly).
    """
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
            },
        },
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", {})
    artifacts = result.get("artifacts", [])
    if artifacts:
        parts = artifacts[0].get("parts", [])
        if parts:
            return (parts[0].get("text") or ""), None
    parts = result.get("parts", [])
    if parts:
        return (parts[0].get("text") or ""), None
    return "", None


def _annotate(
    item: EvidenceItem,
    score: float | None,
    reason: str | None,
    status: str,
) -> EvidenceItem:
    meta = dict(item.metadata or {})
    meta["validator_status"] = status
    if score is not None:
        meta["validator_score"] = score
    if reason:
        meta["validator_reason"] = reason
    return item.model_copy(update={"metadata": meta})


def _decisions_by_url(decisions: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in decisions:
        u = d.get("url")
        if isinstance(u, str) and u:
            out[u] = d
    return out


def validate_items(
    config: ClientConfig,
    product_name: str,
    items: list[EvidenceItem],
) -> ValidateResult:
    """Send scraped items to validator, parse decisions, merge into items.

    Returns `ValidateResult` — never raises. On transport or parse failure the
    items pass through untouched with `validator_status` set accordingly, so
    downstream layers can detect and report the failure instead of silently
    processing unfiltered data.
    """
    if not items:
        return ValidateResult(items=[], status="no_data", note="no input items",
                              kept=0, total=0)

    message = _build_user_message(product_name, items, config.max_text_chars)

    try:
        raw_text, finish_reason = _a2a_send(config.url, message, config.timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        tagged = [_annotate(it, None, None, "http_error") for it in items]
        return ValidateResult(items=tagged, status="http_error", note=f"{type(exc).__name__}: {exc}",
                              kept=len(tagged), total=len(items))

    parsed = parse_validator_response(raw_text, finish_reason)

    if parsed.status in ("parse_failed", "no_data"):
        tagged = [_annotate(it, None, None, parsed.status) for it in items]
        note = f"strategy={parsed.strategy} trailer={parsed.raw_trailer[-120:]!r}"
        return ValidateResult(items=tagged, status=parsed.status, note=note,
                              kept=len(tagged), total=len(items))

    decisions = _decisions_by_url(parsed.items)
    filtered: list[EvidenceItem] = []
    for item in items:
        d = decisions.get(item.url)
        if d is None:
            # Validator didn't emit a decision for this URL — keep conservatively.
            filtered.append(_annotate(item, None, None, parsed.status))
            continue

        keep = bool(d.get("keep", True))
        raw_score = d.get("relevance_score")
        try:
            score = float(raw_score) if raw_score is not None else None
        except (TypeError, ValueError):
            score = None
        reason = (d.get("reason") or "")[:120]

        if not keep:
            continue
        if score is not None and score < config.min_relevance_score:
            continue
        filtered.append(_annotate(item, score, reason, parsed.status))

    return ValidateResult(items=filtered, status=parsed.status,
                          note=f"strategy={parsed.strategy}",
                          kept=len(filtered), total=len(items))
