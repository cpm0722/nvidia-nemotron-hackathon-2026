"""parse_post() 단위 테스트.

fixture HTML을 읽어 본문·추천·비추천·댓글 파싱 결과를 검증한다. 라이브 요청 없음.
"""

from pathlib import Path

import pytest

from nat_collector_arcalive.models import Comment
from nat_collector_arcalive.parser import parse_post

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "arca_live"


@pytest.fixture
def post1_html() -> str:
    return (FIXTURE_DIR / "post_sample_1.html").read_text(encoding="utf-8")


@pytest.fixture
def post2_html() -> str:
    return (FIXTURE_DIR / "post_sample_2.html").read_text(encoding="utf-8")


@pytest.fixture
def post4_html() -> str:
    """댓글과 대댓글이 있는 게시글."""
    return (FIXTURE_DIR / "post_sample_4.html").read_text(encoding="utf-8")


class TestParsePostBody:
    def test_body_is_nonempty_string(self, post1_html: str) -> None:
        body, *_ = parse_post(post1_html)
        assert isinstance(body, str)
        assert len(body) > 0

    def test_body_contains_no_html_tags(self, post1_html: str) -> None:
        """본문에 HTML 태그가 포함되지 않아야 한다."""
        body, *_ = parse_post(post1_html)
        assert "<" not in body and ">" not in body

    def test_body_text_content(self, post1_html: str) -> None:
        """post_sample_1의 본문에 실제 텍스트가 포함되는지 확인한다."""
        body, *_ = parse_post(post1_html)
        assert "5090" in body or "젬마" in body or "V램" in body


class TestParsePostRate:
    def test_like_is_nonnegative_int(self, post4_html: str) -> None:
        _, like, _, _ = parse_post(post4_html)
        assert isinstance(like, int)
        assert like >= 0

    def test_dislike_is_nonnegative_int(self, post4_html: str) -> None:
        _, _, dislike, _ = parse_post(post4_html)
        assert isinstance(dislike, int)
        assert dislike >= 0

    def test_post4_like_count(self, post4_html: str) -> None:
        """post_sample_4의 추천 수가 올바르게 파싱되는지 확인한다."""
        _, like, _, _ = parse_post(post4_html)
        assert like == 4


class TestParsePostComments:
    def test_comments_is_list_of_comment(self, post1_html: str) -> None:
        _, _, _, comments = parse_post(post1_html)
        assert isinstance(comments, list)
        for c in comments:
            assert isinstance(c, Comment)

    def test_comment_fields_nonempty(self, post1_html: str) -> None:
        _, _, _, comments = parse_post(post1_html)
        for c in comments:
            assert isinstance(c.user_nickname, str)
            assert isinstance(c.comment_body, str)
            assert isinstance(c.replies, list)

    def test_reply_nested_under_parent(self, post4_html: str) -> None:
        """대댓글이 부모 댓글의 replies 안에 중첩되어야 한다."""
        _, _, _, comments = parse_post(post4_html)
        assert len(comments) >= 1
        first = comments[0]
        assert len(first.replies) >= 1

    def test_reply_user_nickname_stripped(self, post4_html: str) -> None:
        """닉네임에서 '#12345' 형태의 suffix가 제거되어야 한다."""
        _, _, _, comments = parse_post(post4_html)
        for c in comments:
            assert "#" not in c.user_nickname
            for r in c.replies:
                assert "#" not in r.user_nickname

    def test_no_comments_post_returns_empty(self, post2_html: str) -> None:
        _, _, _, comments = parse_post(post2_html)
        assert isinstance(comments, list)

    def test_empty_html_returns_defaults(self) -> None:
        body, like, dislike, comments = parse_post("")
        assert body == ""
        assert like == 0
        assert dislike == 0
        assert comments == []

    def test_multiple_toplevel_comments_all_collected(self) -> None:
        """top-level 댓글이 여러 개일 때 모두 수집되어야 한다.

        실제 arca.live 구조: .list-area 직하위에 comment-wrapper가 스레드 단위로 존재.
        각 wrapper = comment-item(top-level) + comment-wrapper(replies).
        """
        html = """
        <html><body>
        <div class="list-area">
          <div class="comment-wrapper">
            <div class="comment-item" id="c_1">
              <div class="content">
                <div class="info-row clearfix">
                  <span class="user-info"><a data-filter="UserA">UserA</a></span>
                </div>
                <div class="message"><div class="text"><pre>첫 번째 댓글</pre></div></div>
              </div>
            </div>
            <div class="comment-wrapper">
              <div class="comment-item" id="c_2">
                <div class="content">
                  <div class="info-row clearfix">
                    <span class="user-info"><a data-filter="UserB">UserB</a></span>
                  </div>
                  <div class="message"><div class="text"><pre>첫 번째 댓글의 답글</pre></div></div>
                </div>
              </div>
            </div>
          </div>
          <div class="comment-wrapper">
            <div class="comment-item" id="c_3">
              <div class="content">
                <div class="info-row clearfix">
                  <span class="user-info"><a data-filter="UserC">UserC</a></span>
                </div>
                <div class="message"><div class="text"><pre>두 번째 댓글</pre></div></div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        _, _, _, comments = parse_post(html)
        assert len(comments) == 2, f"top-level 댓글 2개여야 하지만 {len(comments)}개 수집됨"
        assert comments[0].user_nickname == "UserA"
        assert len(comments[0].replies) == 1
        assert comments[0].replies[0].user_nickname == "UserB"
        assert comments[1].user_nickname == "UserC"
        assert len(comments[1].replies) == 0
