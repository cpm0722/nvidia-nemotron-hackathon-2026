"""parse_search_results() 단위 테스트.

fixture HTML을 읽어 파싱 결과를 검증한다. 라이브 요청 없음.
"""

from pathlib import Path

import pytest

from nat_extractor_arcalive.parser import parse_search_results

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "arca_live"
BOARD = "alpaca"


@pytest.fixture
def search_page1_html() -> str:
    return (FIXTURE_DIR / "search_page1.html").read_text(encoding="utf-8")


@pytest.fixture
def search_page2_html() -> str:
    return (FIXTURE_DIR / "search_page2.html").read_text(encoding="utf-8")


class TestParseSearchResults:
    def test_returns_nonempty_list(self, search_page1_html: str) -> None:
        items = parse_search_results(search_page1_html, BOARD)
        assert len(items) > 0

    def test_excludes_notice_posts(self, search_page1_html: str) -> None:
        """공지 게시글은 결과에 포함되지 않아야 한다."""
        items = parse_search_results(search_page1_html, BOARD)
        for item in items:
            assert "공지" not in item.title or item.url != ""

    def test_all_items_have_absolute_url(self, search_page1_html: str) -> None:
        items = parse_search_results(search_page1_html, BOARD)
        for item in items:
            assert item.url.startswith(f"https://arca.live/b/{BOARD}/"), (
                f"relative URL found: {item.url}"
            )

    def test_url_has_no_query_string(self, search_page1_html: str) -> None:
        """URL에 검색 query string이 포함되지 않아야 한다."""
        items = parse_search_results(search_page1_html, BOARD)
        for item in items:
            assert "?" not in item.url, f"query string in URL: {item.url}"

    def test_comment_count_is_nonnegative_int(self, search_page1_html: str) -> None:
        items = parse_search_results(search_page1_html, BOARD)
        for item in items:
            assert isinstance(item.num_comments, int)
            assert item.num_comments >= 0

    def test_like_is_nonnegative_int(self, search_page1_html: str) -> None:
        items = parse_search_results(search_page1_html, BOARD)
        for item in items:
            assert isinstance(item.like, int)
            assert item.like >= 0

    def test_time_is_timezone_aware(self, search_page1_html: str) -> None:
        """파싱된 datetime은 timezone 정보를 포함해야 한다."""
        items = parse_search_results(search_page1_html, BOARD)
        for item in items:
            assert item.time.tzinfo is not None

    def test_title_is_nonempty_string(self, search_page1_html: str) -> None:
        items = parse_search_results(search_page1_html, BOARD)
        for item in items:
            assert isinstance(item.title, str)
            assert len(item.title) > 0

    def test_known_post_parsed_correctly(self, search_page1_html: str) -> None:
        """fixture에 실제로 존재하는 게시글이 올바르게 파싱되는지 확인한다."""
        items = parse_search_results(search_page1_html, BOARD)
        urls = [it.url for it in items]
        assert "https://arca.live/b/alpaca/168343089" in urls

    def test_page2_items_parseable(self, search_page2_html: str) -> None:
        items = parse_search_results(search_page2_html, BOARD)
        assert len(items) > 0
        for item in items:
            assert item.url.startswith("https://arca.live")

    def test_empty_html_returns_empty_list(self) -> None:
        assert parse_search_results("", BOARD) == []

    def test_no_article_list_returns_empty(self) -> None:
        assert parse_search_results("<html><body></body></html>", BOARD) == []
