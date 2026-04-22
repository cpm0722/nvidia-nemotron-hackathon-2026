"""Minimal A2A v0.3 JSON-RPC client used by extractors and the orchestrator.

The A2A protocol allows agents to exchange messages over HTTP. We only need
the happy-path ``message/send`` call and extraction of the response text from
either a Message-shaped or a Task-shaped reply. The full spec is not modelled
here on purpose — all of our agents speak the same narrow subset.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import requests

from ari_core.schemas import EvidenceItem


def a2a_send(url: str, message: str, timeout: int) -> str:
    """Send ``message`` to an A2A endpoint and return the response text.

    Handles both response shapes:
    - Task: ``{result: {artifacts: [{parts: [{text}]}]}}``
    - Message: ``{result: {parts: [{text}]}}``

    Args:
        url: Base A2A endpoint (e.g. ``http://localhost:10020``).
        message: Text payload for the agent (caller-defined format).
        timeout: HTTP timeout in seconds.

    Returns:
        The first text part of the response, or an empty string if absent.
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
        return parts[0].get("text", "") if parts else ""
    parts = result.get("parts", [])
    return parts[0].get("text", "") if parts else ""


_THINK_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.MULTILINE)


def parse_validator_response(
    text: str, fallback: list[EvidenceItem]
) -> list[EvidenceItem]:
    """Parse a validator agent's response into a list of EvidenceItem.

    Validators are chat_completion LLMs, so their output may be wrapped in
    ``<think>...</think>`` reasoning blocks, ```` ```json ```` fences, or be
    a JSON object whose first list value contains the items. Anything that
    does not parse into ≥1 EvidenceItem falls back to the unfiltered input so
    a validator hiccup never silently drops evidence.

    Args:
        text: Raw validator response text.
        fallback: Items to return when parsing yields nothing usable.

    Returns:
        Parsed EvidenceItem list, or ``fallback``.
    """
    cleaned = _THINK_RE.sub("", text).strip()
    cleaned = _FENCE_RE.sub("", cleaned).strip()

    parsed: Any = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return fallback

    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                parsed = value
                break
        else:
            return fallback

    if not isinstance(parsed, list):
        return fallback

    result: list[EvidenceItem] = []
    for obj in parsed:
        if not isinstance(obj, dict):
            continue
        try:
            result.append(EvidenceItem(**obj))
        except Exception:
            continue
    return result if result else fallback


def parse_collect_input(raw: str) -> tuple[str, str]:
    """Parse an extractor's A2A input into ``(product, run_id)``.

    Expected shape::

        {"product": "GPT-5", "run_id": "20260422-120000-deadbeef"}

    ``product_name`` is accepted as an alias for ``product`` so upstream
    callers can use either key.

    Raises:
        ValueError: if the input is not a JSON object with both required
            fields.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"extractor input must be JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("extractor input must be a JSON object")
    product = data.get("product") or data.get("product_name")
    run_id = data.get("run_id")
    if not product or not run_id:
        raise ValueError("extractor input missing 'product' or 'run_id'")
    return str(product), str(run_id)
