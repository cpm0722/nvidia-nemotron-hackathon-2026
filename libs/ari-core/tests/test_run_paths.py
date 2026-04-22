"""Unit tests for ari_core.run_paths."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ari_core.run_paths import (
    new_run_id,
    query_path,
    raw_path,
    read_json,
    report_path,
    run_root,
    slugify_product,
    validated_path,
    write_json,
    write_text,
)


class TestSlugifyProduct:
    def test_lowercases_and_dashes_runs_of_non_alnum(self) -> None:
        assert slugify_product("GPT-5 Turbo") == "gpt-5-turbo"

    def test_strips_leading_and_trailing_separators(self) -> None:
        assert slugify_product("  Claude 4.7  ") == "claude-4-7"

    def test_collapses_special_chars_and_korean_to_dashes(self) -> None:
        # 한글/특수문자 전부 non-alnum 이므로 하나의 dash 로 압축되고, 앞뒤는 strip.
        assert slugify_product("젬마4!!!") == "4"

    def test_empty_or_all_special_falls_back_to_product(self) -> None:
        assert slugify_product("") == "product"
        assert slugify_product("   !!!   ") == "product"


class TestNewRunId:
    def test_matches_expected_format(self) -> None:
        rid = new_run_id()
        assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{8}", rid), rid

    def test_is_unique(self) -> None:
        ids = {new_run_id() for _ in range(50)}
        assert len(ids) == 50


class TestPathHelpers:
    def test_paths_are_composed_under_run_root(self, tmp_path: Path) -> None:
        run_id = "20260422-120000-deadbeef"
        rr = run_root(run_id, root=tmp_path)
        assert rr == tmp_path / run_id

        assert query_path(run_id, root=tmp_path) == rr / "query.json"
        assert raw_path(run_id, "GPT-5", "reddit", root=tmp_path) == (
            rr / "raw" / "gpt-5" / "reddit.json"
        )
        assert validated_path(run_id, "GPT-5", "reddit", root=tmp_path) == (
            rr / "validated" / "gpt-5" / "reddit.json"
        )
        assert report_path(run_id, "GPT-5", root=tmp_path) == rr / "report_gpt-5.md"

    def test_default_root_is_runs_directory(self) -> None:
        assert run_root("abc") == Path("runs") / "abc"


class TestWriteJsonReadJson:
    def test_round_trips_unicode_content(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "file.json"
        payload = {"q": "젬마4 성능", "items": [1, 2, 3]}
        returned = write_json(target, payload)
        assert returned == target
        assert target.exists()
        assert read_json(target) == payload

    def test_uses_default_str_for_unserializable_values(self, tmp_path: Path) -> None:
        from datetime import datetime

        target = tmp_path / "x.json"
        write_json(target, {"t": datetime(2026, 4, 22, 12, 0, 0)})
        data = json.loads(target.read_text(encoding="utf-8"))
        # datetime 은 문자열로 직렬화되어야 한다 (정확한 포맷은 str(datetime) 기반).
        assert "2026-04-22" in data["t"]

    def test_atomic_write_leaves_no_tmp_suffix(self, tmp_path: Path) -> None:
        target = tmp_path / "file.json"
        write_json(target, {"a": 1})
        assert target.exists()
        assert not (tmp_path / "file.json.tmp").exists()


class TestWriteText:
    def test_creates_parents_and_writes(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c.md"
        write_text(target, "# 보고서")
        assert target.read_text(encoding="utf-8") == "# 보고서"


@pytest.fixture(autouse=True)
def _no_stray_cwd_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard: any accidental write to default ``runs/`` lands under tmp_path."""
    monkeypatch.chdir(tmp_path)
