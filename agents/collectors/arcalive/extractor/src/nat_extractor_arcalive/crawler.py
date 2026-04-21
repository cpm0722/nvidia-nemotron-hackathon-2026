"""arca.live 크롤러 오케스트레이션.

주어진 쿼리로 검색 결과를 수집하고, 댓글 수·추천 수·최신 순으로 Top-5를 선택해
각 게시글의 본문과 댓글을 가져온 뒤 CrawlResult를 반환한다.

주의: 게시글·페이지 간 2~3초 랜덤 딜레이 필수.
"""

import random
import re
import time
from urllib.parse import urlencode

import requests

from nat_extractor_arcalive.models import CrawlResult, Post, SearchResultItem
from nat_extractor_arcalive.parser import parse_post, parse_search_results

BASE_URL = "https://arca.live"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}


def crawl(query: str, board: str, max_pages: int = 2, limit: int = 5) -> CrawlResult:
    """주어진 쿼리로 arca.live 채널을 검색해 Top-N 게시글을 수집한다.

    검색 결과 1~max_pages 페이지를 순회하며 일반 게시글을 수집한 뒤,
    댓글 수 → 추천 수 → 최신 순으로 정렬해 Top-N을 선택한다.
    각 게시글 요청 사이에 2~3초 랜덤 딜레이를 둔다.

    Args:
        query: 검색어 (AI 프러덕트 이름, e.g. "GPT-5", "Claude 4")
        board: 검색할 arca.live 채널 슬러그 (e.g. "aiservice", "alpaca")
        max_pages: 검색 결과 최대 페이지 수 (기본 2)
        limit: 반환할 최대 게시글 수 (기본 5)
    Returns:
        CrawlResult (query + top-N posts with comments)
    """
    candidates = _collect_search_results(query, board, max_pages)
    topn = _select_topn(candidates, query, limit)

    posts: list[Post] = []
    for rank, item in enumerate(topn, start=1):
        html = _fetch(item.url, board)
        body, like, dislike, comments = parse_post(html)

        posts.append(
            Post(
                rank=rank,
                title=item.title,
                url=item.url,
                like=like,
                dislike=dislike,
                num_comments=item.num_comments,
                time=item.time,
                body=body,
                comments=comments,
            )
        )

        if rank < len(topn):
            time.sleep(random.uniform(2, 3))

    return CrawlResult(query=query, result=posts)


def _collect_search_results(query: str, board: str, max_pages: int) -> list[SearchResultItem]:
    """1~max_pages 페이지를 순회하며 검색 결과를 모두 수집한다."""
    all_items: list[SearchResultItem] = []

    for page in range(1, max_pages + 1):
        url = _search_url(query, board, page)
        html = _fetch(url, board)
        items = parse_search_results(html, board)
        all_items.extend(items)

        if page < max_pages:
            time.sleep(random.uniform(2, 3))

    return all_items


def _select_topn(items: list[SearchResultItem], query: str, limit: int) -> list[SearchResultItem]:
    """query가 제목에 포함된 게시글만 추린 뒤, 댓글 수 → 추천 수 → 최신 순으로 Top-N을 반환한다.

    query·title 모두 공백·특수문자 제거 후 lowercase로 정규화해 비교한다.
    """
    norm_query = _normalize(query)
    matched = [it for it in items if norm_query in _normalize(it.title)]
    return sorted(
        matched,
        key=lambda p: (-p.num_comments, -p.like, -p.time.timestamp()),
    )[:limit]


def _normalize(text: str) -> str:
    """공백·특수문자를 모두 제거하고 lowercase로 변환한다."""
    return re.sub(r"[^a-z0-9가-힣]", "", text.lower())


def _search_url(query: str, board: str, page: int) -> str:
    params = urlencode({"target": "title_body", "keyword": query, "p": page})
    return f"{BASE_URL}/b/{board}?{params}"


def _fetch(url: str, board: str) -> str:
    headers = {**HEADERS, "Referer": f"{BASE_URL}/b/{board}"}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.text
