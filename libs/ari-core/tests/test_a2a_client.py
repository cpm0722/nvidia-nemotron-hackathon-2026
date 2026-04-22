"""Unit tests for ari_core.a2a_client."""

from __future__ import annotations

import pytest

from ari_core.a2a_client import (
    parse_collect_input,
    parse_validator_response,
)
from ari_core.schemas import EvidenceItem


def _item(url: str = "https://x/1", text: str = "hi") -> EvidenceItem:
    return EvidenceItem(source="x", source_detail="x", url=url, text=text)


class TestParseCollectInput:
    def test_accepts_product_and_run_id(self) -> None:
        assert parse_collect_input('{"product": "GPT-5", "run_id": "abc"}') == (
            "GPT-5",
            "abc",
        )

    def test_accepts_product_name_alias(self) -> None:
        assert parse_collect_input('{"product_name": "젬마4", "run_id": "r1"}') == (
            "젬마4",
            "r1",
        )

    def test_rejects_non_object(self) -> None:
        with pytest.raises(ValueError):
            parse_collect_input('"just a string"')

    def test_rejects_missing_fields(self) -> None:
        with pytest.raises(ValueError):
            parse_collect_input('{"product": "X"}')
        with pytest.raises(ValueError):
            parse_collect_input('{"run_id": "r1"}')

    def test_rejects_non_json(self) -> None:
        with pytest.raises(ValueError):
            parse_collect_input("not json at all")


class TestParseValidatorResponse:
    def test_strips_think_and_fences(self) -> None:
        payload = (
            '<think>let me think</think>\n'
            '```json\n'
            '[{"source":"reddit","source_detail":"r/LocalLLaMA","url":"https://u/1","text":"t"}]\n'
            '```'
        )
        items = parse_validator_response(payload, fallback=[_item()])
        assert len(items) == 1
        assert items[0].url == "https://u/1"

    def test_accepts_object_wrapping_list(self) -> None:
        payload = (
            '{"filtered": [{"source":"x","source_detail":"y","url":"https://u/2","text":"t2"}]}'
        )
        items = parse_validator_response(payload, fallback=[_item()])
        assert len(items) == 1
        assert items[0].url == "https://u/2"

    def test_unparseable_falls_back(self) -> None:
        fb = [_item(url="https://fallback/1")]
        assert parse_validator_response("not json anywhere", fb) == fb

    def test_empty_parsed_list_falls_back(self) -> None:
        fb = [_item(url="https://fallback/2")]
        assert parse_validator_response("[]", fb) == fb

    def test_extracts_array_embedded_in_noise(self) -> None:
        payload = 'Sure! Here is the result:\n[{"source":"a","source_detail":"b","url":"https://u/3","text":"t3"}]\n(done)'
        items = parse_validator_response(payload, fallback=[_item()])
        assert len(items) == 1
        assert items[0].url == "https://u/3"
