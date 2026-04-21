"""arca.live 크롤러의 Pydantic 데이터 모델."""

from datetime import datetime

from pydantic import BaseModel


class Comment(BaseModel):
    """댓글 한 건. replies에 대댓글을 재귀적으로 중첩한다."""

    user_nickname: str
    comment_body: str
    replies: list["Comment"] = []


class SearchResultItem(BaseModel):
    """검색 결과 한 행의 파싱 중간 데이터.

    Top-5 선택 후 Post로 변환된다.
    """

    title: str
    url: str
    num_comments: int
    like: int
    time: datetime


class Post(BaseModel):
    """Top-N에 선정된 게시글 한 건의 최종 데이터."""

    rank: int
    title: str
    url: str
    like: int
    dislike: int
    num_comments: int
    time: datetime
    body: str
    comments: list[Comment]


class CrawlResult(BaseModel):
    """crawl() 함수의 최종 반환값. JSON 직렬화 대상."""

    query: str
    result: list[Post]
