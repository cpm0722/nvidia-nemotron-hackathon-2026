"""Shared utilities for ARI extractor agents: schemas, HTTP base, async runner."""

from ari_core.a2a_client import a2a_send, parse_collect_input, parse_validator_response
from ari_core.async_runner import run_scraper_async
from ari_core.envelope import Envelope, parse_envelope, serialize_downstream_message
from ari_core.events import (
    build_event_payload,
    emit_event,
    get_event_context,
    set_event_context,
)
from ari_core.http_base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer, iso, since_timestamp
from ari_core.run_paths import (
    ensure_parent,
    new_run_id,
    query_path,
    raw_path,
    read_json,
    report_path,
    run_root,
    runs_root,
    slugify_product,
    validated_path,
    write_json,
    write_text,
)
from ari_core.schemas import EvidenceItem, ScrapeInput, ScrapeResult

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "Envelope",
    "EvidenceItem",
    "ScrapeInput",
    "ScrapeResult",
    "Timer",
    "USER_AGENT",
    "a2a_send",
    "build_event_payload",
    "emit_event",
    "ensure_parent",
    "get_event_context",
    "iso",
    "new_run_id",
    "parse_collect_input",
    "parse_envelope",
    "parse_validator_response",
    "query_path",
    "raw_path",
    "read_json",
    "report_path",
    "run_root",
    "run_scraper_async",
    "runs_root",
    "serialize_downstream_message",
    "set_event_context",
    "since_timestamp",
    "slugify_product",
    "validated_path",
    "write_json",
    "write_text",
]
