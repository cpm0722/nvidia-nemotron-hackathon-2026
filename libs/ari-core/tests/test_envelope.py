"""Unit tests for ari_core.envelope."""

from __future__ import annotations

import json

from ari_core.envelope import Envelope, parse_envelope, serialize_downstream_message


class TestParseEnvelope:
    def test_parses_full_ui_envelope(self) -> None:
        raw = json.dumps(
            {
                "query": "GPT5와 Gemma4 비교",
                "job_id": "job-1",
                "event_url": "http://ui:8080/api/events/job-1",
                "work_dir": "/app/runs/job-1",
            }
        )
        env = parse_envelope(raw)
        assert env.query == "GPT5와 Gemma4 비교"
        assert env.job_id == "job-1"
        assert env.event_url == "http://ui:8080/api/events/job-1"
        assert env.work_dir == "/app/runs/job-1"

    def test_accepts_user_query_alias(self) -> None:
        raw = json.dumps({"user_query": "opus 4.7 review", "job_id": "j"})
        env = parse_envelope(raw)
        assert env.query == "opus 4.7 review"
        assert env.job_id == "j"

    def test_missing_optional_fields_default_to_none(self) -> None:
        env = parse_envelope(json.dumps({"query": "hi"}))
        assert env.query == "hi"
        assert env.job_id is None
        assert env.event_url is None
        assert env.work_dir is None

    def test_empty_strings_treated_as_none(self) -> None:
        env = parse_envelope(json.dumps({"query": "hi", "job_id": "", "event_url": "   "}))
        assert env.job_id is None
        assert env.event_url is None

    def test_bare_string_becomes_query_only(self) -> None:
        env = parse_envelope("just a plain query string")
        assert env.query == "just a plain query string"
        assert env.job_id is None
        assert env.event_url is None

    def test_invalid_json_falls_back_to_string_query(self) -> None:
        env = parse_envelope("not { valid } json")
        assert env.query == "not { valid } json"

    def test_non_object_json_becomes_query(self) -> None:
        env = parse_envelope(json.dumps(["a", "b"]))
        assert env.query.startswith("[")


class TestSerializeDownstreamMessage:
    def test_forwards_all_fields(self) -> None:
        env = Envelope(job_id="j1", event_url="http://ui/api/events/j1")
        msg = serialize_downstream_message(
            env, product="GPT-5", run_id="r1", paths=["a.json", "b.json"]
        )
        data = json.loads(msg)
        assert data == {
            "product": "GPT-5",
            "run_id": "r1",
            "paths": ["a.json", "b.json"],
            "job_id": "j1",
            "event_url": "http://ui/api/events/j1",
        }

    def test_omits_streaming_context_when_missing(self) -> None:
        env = Envelope()
        msg = serialize_downstream_message(env, product="X", run_id="r1")
        data = json.loads(msg)
        assert data == {"product": "X", "run_id": "r1"}

    def test_preserves_korean_product_names(self) -> None:
        env = Envelope(job_id="j", event_url="http://ui/api/events/j")
        msg = serialize_downstream_message(env, product="젬마4", run_id="r1")
        # ensure_ascii=False — no \uXXXX escapes.
        assert "젬마4" in msg
