"""HuggingFace Hub 스크래퍼.

on-demand 단건 조회 API:
  - fetch_benchmarks_for_model(name) : 모델명으로 모델 카드의 벤치마크 점수 조회
  - fetch_discussions(model_id)      : 모델의 최신 토론(본문 + 댓글) 조회
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import httpx
from bs4 import BeautifulSoup

_NON_BENCHMARK_ROWS = {
    "architecture", "total params", "active params", "context length",
    "parameters", "vocab size", "release date", "license", "language",
}

TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
HEADERS = {"User-Agent": "Mozilla/5.0"}

BENCH_SECTION_RE = re.compile(
    r"#+\s*(benchmark|evaluation|performance|result|metric|score)",
    re.IGNORECASE,
)
TABLE_ROW_RE = re.compile(r"^\|(.+\|){2,}$")


def _normalize(s: str) -> str:
    return re.sub(r"[\s\-_.]", "", s).lower()


def _fetch_model_card(model_id: str) -> Optional[str]:
    url = f"https://huggingface.co/{model_id}/resolve/main/README.md"
    try:
        r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 200:
            return r.text
    except Exception:
        pass
    return None


def _has_benchmark_table(text: str) -> bool:
    return bool(BENCH_SECTION_RE.search(text)) or "| --- |" in text or "|---|" in text


def _parse_markdown_tables(text: str) -> list[dict]:
    """마크다운 테이블에서 벤치마크 행 추출. 반환: [{"name", "score_str", "score"}]"""
    results = []
    lines = text.split("\n")
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not TABLE_ROW_RE.match(stripped):
            in_table = False
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        if all(re.match(r"^[-: ]+$", c) for c in cells if c):
            continue

        if not in_table:
            in_table = True
            continue

        if len(cells) >= 2:
            bench_name = re.sub(r"\*+|`", "", cells[0]).strip()
            if not bench_name or bench_name.startswith("-"):
                continue
            if "[" in bench_name:
                continue

            score_str = cells[1].strip()
            if score_str in ["-", "—", "N/A", ""]:
                continue
            if re.search(r"\d{1,2}/\d{1,2}/\d{4}", score_str):
                continue
            if re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d", score_str, re.IGNORECASE):
                continue
            if re.search(r"^\d+(\.\d+)?\s*[TBGMKtbgmk]b?$", score_str):
                continue

            non_numeric = re.sub(r"[\d.,% ]", "", score_str)
            if len(non_numeric) > 5 or not re.search(r"\d", score_str):
                continue

            score_match = re.search(r"(\d+\.?\d*)", score_str)
            score = float(score_match.group(1)) if score_match else None

            if bench_name and score is not None:
                results.append({"name": bench_name, "score_str": score_str, "score": score})

    return results


def _parse_html_tables(html: str, model_name: str = "") -> list[dict]:
    """HTML <table>에서 벤치마크 점수를 추출한다. model_name과 가장 유사한 컬럼을 읽는다."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    model_norm = _normalize(model_name) if model_name else ""

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [cell.get_text(strip=True) for cell in rows[0].find_all(["th", "td"])]

        model_col = 1
        if model_norm and len(headers) > 1:
            best_col_score = -1.0
            for i, h in enumerate(headers[1:], start=1):
                h_norm = _normalize(h)
                if model_norm in h_norm or h_norm in model_norm:
                    score = len(model_norm) / max(len(h_norm), 1)
                    if score > best_col_score:
                        best_col_score = score
                        model_col = i

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
            if len(cells) <= model_col:
                continue

            bench_name = re.sub(r"\s+", " ", cells[0]).strip()
            score_str = cells[model_col].strip()

            if not bench_name or score_str in ["-", "—", "N/A", ""]:
                continue
            if bench_name.lower() in _NON_BENCHMARK_ROWS:
                continue
            if "[" in bench_name:
                continue
            if re.search(r"\d{1,2}/\d{1,2}/\d{4}", score_str):
                continue
            if re.search(r"^\d+(\.\d+)?\s*[TBGMKtbgmk]b?$", score_str):
                continue

            score_match = re.search(r"(\d+\.?\d*)", score_str)
            score = float(score_match.group(1)) if score_match else None

            if score is not None:
                results.append({"name": bench_name, "score_str": score_str, "score": score})

    return results


def fetch_benchmarks_for_model(model_name: str) -> tuple[list[dict], str, str, str, str]:
    """모델명으로 HuggingFace를 검색해 모델 카드의 벤치마크와 원본 카드 텍스트를 반환한다.

    Args:
        model_name: 검색할 모델명 (e.g. "gemma 3", "claude opus 4.7").

    Returns:
        (benchmarks, 매칭된_모델명, provider, model_id, model_card)
        - benchmarks: [{"name", "score", "score_str"}]
        - model_id: HF 토론 조회에 쓸 수 있는 "{org}/{name}" 형식
        - model_card: 모델 카드 README.md 원문 (없으면 빈 문자열)
    """
    try:
        r = httpx.get(
            "https://huggingface.co/api/models",
            params={"search": model_name, "limit": 20},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return [], "", "", "", ""
        candidates = r.json()
    except Exception as e:
        print(f"[HuggingFace] 검색 실패 ({model_name}): {e}")
        return [], "", "", "", ""

    if not candidates:
        return [], "", "", "", ""

    query = _normalize(model_name)

    scored: list[tuple[float, str]] = []
    for m in candidates:
        mid = m.get("id", "")
        name_part = _normalize(mid.split("/")[-1])

        if name_part == query:
            scored.append((2.0, mid))
        elif query in name_part or name_part in query:
            score = 1.0 + len(query) / max(len(name_part), 1)
            scored.append((score, mid))

    if not scored:
        return [], "", "", "", ""

    scored.sort(key=lambda x: x[0], reverse=True)

    for _, best_id in scored[:5]:
        provider = best_id.split("/")[0]
        model_display = best_id.split("/")[-1]

        card = _fetch_model_card(best_id)
        if not card or not _has_benchmark_table(card):
            continue

        benchmarks = _parse_markdown_tables(card)
        if not benchmarks:
            benchmarks = _parse_html_tables(card, model_display)
        if benchmarks:
            return benchmarks, model_display, provider, best_id, card

    best_id = scored[0][1]
    fallback_card = _fetch_model_card(best_id) or ""
    return [], best_id.split("/")[-1], best_id.split("/")[0], best_id, fallback_card


def _fetch_discussion_detail(model_id: str, num: int, comment_limit: int) -> tuple[str, list[dict]]:
    """단일 discussion의 본문과 댓글을 반환한다. 반환: (body, comments)"""
    try:
        r = httpx.get(
            f"https://huggingface.co/api/models/{model_id}/discussions/{num}",
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return "", []
        events = [e for e in r.json().get("events", []) if e.get("type") == "comment"]
    except Exception:
        return "", []

    body = ""
    comments = []
    for i, event in enumerate(events):
        text = (event.get("data") or {}).get("latest", {}).get("raw", "").strip()
        if i == 0:
            body = text
        elif len(comments) < comment_limit:
            author = event.get("author", {})
            comments.append({
                "author": author.get("name", "") if isinstance(author, dict) else str(author),
                "text": text,
                "created_at": event.get("createdAt", ""),
            })

    return body, comments


def fetch_discussions(model_id: str, limit: int = 10, comment_limit: int = 3) -> list[dict]:
    """HuggingFace 모델의 최신 토론을 본문·댓글 포함해서 반환한다.

    Args:
        model_id: "{org}/{name}" 형식의 HF 모델 ID.
        limit: 가져올 토론 수.
        comment_limit: 각 토론당 댓글 수 상한.

    Returns:
        [{"title", "num", "author", "created_at", "status", "num_comments", "url",
          "body", "comments": [{"author", "text", "created_at"}]}]
    """
    try:
        r = httpx.get(
            f"https://huggingface.co/api/models/{model_id}/discussions",
            params={"limit": limit},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        raw_list = [d for d in r.json().get("discussions", []) if not d.get("isPullRequest")][:limit]
    except Exception as e:
        print(f"[HuggingFace] 토론 목록 조회 실패 ({model_id}): {e}")
        return []

    results = []
    for d in raw_list:
        author = d.get("author", {})
        results.append({
            "title": d.get("title", ""),
            "num": d.get("num"),
            "author": author.get("name", "") if isinstance(author, dict) else str(author),
            "created_at": d.get("createdAt", ""),
            "status": d.get("status", ""),
            "num_comments": d.get("numComments", 0),
            "url": f"https://huggingface.co/{model_id}/discussions/{d.get('num', '')}",
            "body": "",
            "comments": [],
        })

    def _fetch(item: dict) -> dict:
        body, comments = _fetch_discussion_detail(model_id, item["num"], comment_limit)
        return {**item, "body": body, "comments": comments}

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(_fetch, results))

    return results
