"""Scrapers for the AI Release Intelligence Agent.

Each scraper module exposes a `scrape(ScrapeInput) -> ScrapeResult` callable
so NAT function wrappers can invoke them uniformly.
"""

from ari_agent.scrapers.arxiv import scrape as scrape_arxiv
from ari_agent.scrapers.github import scrape as scrape_github
from ari_agent.scrapers.hackernews import scrape as scrape_hackernews
from ari_agent.scrapers.huggingface import scrape as scrape_huggingface
from ari_agent.scrapers.reddit import scrape as scrape_reddit
from ari_agent.scrapers.rss import scrape as scrape_rss

__all__ = [
    "scrape_arxiv",
    "scrape_github",
    "scrape_hackernews",
    "scrape_huggingface",
    "scrape_reddit",
    "scrape_rss",
]
