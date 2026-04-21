"""arca.live HTML 파서.

실제 fixture HTML을 기반으로 검증된 CSS selector를 사용한다.
라이브 요청 없이 fixture HTML 문자열만 입력받아 동작한다.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from nat_collector_arcalive.models import Comment, SearchResultItem

BASE_URL = "https://arca.live"


def parse_search_results(html: str, board: str) -> list[SearchResultItem]:
    """검색 결과 페이지 HTML에서 일반 게시글 목록을 파싱한다.

    공지·광고 행은 제외하고, 일반 게시글만 반환한다.

    Args:
        html: arca.live 검색 결과 페이지의 HTML 문자열
        board: 검색 대상 채널 슬러그 (e.g. "aiservice", "alpaca")
    Returns:
        SearchResultItem 리스트 (순서는 페이지 상 등장 순서)
    """
    soup = BeautifulSoup(html, "lxml")
    art_list = soup.select_one(".article-list")
    if not art_list:
        return []

    items: list[SearchResultItem] = []
    for a_tag in art_list.select("a.vrow"):
        classes = a_tag.get("class") or []
        if "notice" in classes:
            continue

        href = a_tag.get("href", "")
        if not isinstance(href, str) or f"/b/{board}/" not in href:
            continue

        title = _parse_title(a_tag)
        url = BASE_URL + href.split("?")[0]
        num_comments = _parse_comment_count(a_tag)
        like = _parse_search_rate(a_tag)
        post_time = _parse_datetime(a_tag)

        if title and post_time:
            items.append(
                SearchResultItem(
                    title=title,
                    url=url,
                    num_comments=num_comments,
                    like=like,
                    time=post_time,
                )
            )
    return items


def parse_post(html: str) -> tuple[str, int, int, list[Comment]]:
    """게시글 페이지 HTML에서 본문·추천·비추천·댓글을 파싱한다.

    Args:
        html: arca.live 게시글 페이지의 HTML 문자열
    Returns:
        (body_text, like, dislike, comments) 튜플
        - body_text: HTML 태그 제거된 순수 텍스트
        - like: 추천 수
        - dislike: 비추천 수
        - comments: top-level Comment 리스트 (대댓글은 replies에 중첩)
    """
    soup = BeautifulSoup(html, "lxml")

    body = _parse_body(soup)
    like = _parse_int(soup.select_one("#ratingUp"))
    dislike = _parse_int(soup.select_one("#ratingDown"))
    comments = _parse_comments(soup)

    return body, like, dislike, comments


# --- private helpers ---


def _parse_title(row: Tag) -> str:
    """a.vrow에서 게시글 제목 텍스트를 추출한다."""
    title_span = row.select_one(".title")
    if not title_span:
        return ""
    # media-icon span 등 자식 태그의 텍스트를 제외하고 직접 텍스트 노드만 수집
    texts = [t for t in title_span.strings if t.strip()]
    return " ".join(texts).strip()


def _parse_comment_count(row: Tag) -> int:
    """a.vrow에서 댓글 수를 추출한다. 형식: '[10]' → 10"""
    cnt_el = row.select_one(".comment-count")
    if not cnt_el:
        return 0
    digits = re.sub(r"[^\d]", "", cnt_el.get_text())
    return int(digits) if digits else 0


def _parse_search_rate(row: Tag) -> int:
    """a.vrow에서 추천 수(col-rate)를 추출한다."""
    rate_el = row.select_one(".vcol.col-rate")
    if not rate_el:
        return 0
    return _parse_int(rate_el)


def _parse_datetime(row: Tag) -> datetime | None:
    """a.vrow의 time[datetime] 속성을 UTC datetime으로 파싱한다."""
    time_el = row.select_one("time[datetime]")
    if not time_el:
        return None
    dt_str = time_el.get("datetime", "")
    if not isinstance(dt_str, str):
        return None
    try:
        # 형식: "2026-04-21T09:23:26.000Z"
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_body(soup: BeautifulSoup) -> str:
    """게시글 본문 텍스트를 추출한다. 모든 HTML 태그를 제거하고 순수 텍스트만 반환한다."""
    content = soup.select_one(".fr-view.article-content")
    if not content:
        content = soup.select_one(".article-content")
    if not content:
        return ""
    return content.get_text(separator="\n", strip=True)


def _parse_comments(soup: BeautifulSoup) -> list[Comment]:
    """게시글 페이지에서 댓글 목록을 파싱한다.

    arca.live 실제 댓글 DOM 구조:
    - .list-area 직하위에 comment-wrapper가 스레드 단위(top-level 1개 + 답글)로 존재한다.
    - 각 comment-wrapper 안에 comment-item 1개 + 답글용 comment-wrapper 0/1개가 순서대로 온다.

    예:
      .list-area
        .comment-wrapper          ← 스레드 1
          .comment-item           ← top-level
          .comment-wrapper        ← replies
            .comment-item         ← reply
        .comment-wrapper          ← 스레드 2
    """
    list_area = soup.select_one(".list-area")
    if not list_area:
        return []

    result: list[Comment] = []
    for child in list_area.children:
        if not isinstance(child, Tag):
            continue
        if "comment-wrapper" in (child.get("class") or []):
            result.extend(_parse_comment_wrapper(child))
    return result


def _parse_comment_wrapper(wrapper: Tag) -> list[Comment]:
    """comment-wrapper를 재귀적으로 파싱해 Comment 리스트를 반환한다.

    직접 자식 요소를 순서대로 처리한다:
    - comment-item → 새 Comment 추가
    - comment-wrapper → 직전 Comment의 replies로 재귀 파싱
    """
    comments: list[Comment] = []
    for child in wrapper.children:
        if not isinstance(child, Tag):
            continue
        classes = child.get("class") or []
        if "comment-item" in classes:
            user = _extract_username(child)
            body = _extract_comment_body(child)
            comments.append(Comment(user_nickname=user, comment_body=body))
        elif "comment-wrapper" in classes and comments:
            comments[-1].replies.extend(_parse_comment_wrapper(child))
    return comments


def _extract_username(item: Tag) -> str:
    """comment-item에서 작성자 닉네임을 추출한다."""
    user_el = item.select_one(".user-info [data-filter]")
    if user_el:
        raw = user_el.get("data-filter", "")
        if isinstance(raw, str):
            # "닉네임#12345" 형태에서 # 뒤 숫자 제거
            return raw.split("#")[0]
    user_el = item.select_one(".user-info")
    return user_el.get_text(strip=True) if user_el else "알 수 없음"


def _extract_comment_body(item: Tag) -> str:
    """comment-item에서 댓글 본문을 추출한다."""
    text_el = item.select_one(".message .text")
    if not text_el:
        return ""
    return text_el.get_text(separator="\n", strip=True)


def _parse_int(tag: Tag | None) -> int:
    """태그의 텍스트를 정수로 변환한다. 변환 불가 시 0을 반환한다."""
    if not tag:
        return 0
    text = re.sub(r"[^\d]", "", tag.get_text())
    return int(text) if text else 0
