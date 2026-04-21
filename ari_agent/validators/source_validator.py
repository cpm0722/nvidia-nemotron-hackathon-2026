"""Rule-based Source Validator (v1).

Computes two of the four planned axes for each `EvidenceItem`:

  • Authority      — domain whitelist + author signals (verified/staff/karma)
  • Verifiability  — count of outbound links + numeric mentions in body

Each axis returns a 0.0~5.0 float plus a `reasons` list explaining the score
("Why this number?"). Reasons are critical: blackbox scores get attacked at
demo time.

The two LLM-backed axes (Track Record, Independence) are deferred to v2 once
NIM is wired — they need historical lookups (past predictions vs outcomes,
author affiliations) that don't fit a pure rule-based pass.

Aggregate score = mean(axes), clipped to [0.0, 5.0].
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ari_agent.schemas import EvidenceItem

# ---------------------------------------------------------------------------
# Authority — domain whitelist (higher = more authoritative)
# ---------------------------------------------------------------------------

# Tier breakdown is intentionally explicit so reviewers can audit each call.
# Adjust by editing this dict — every value is a tuple (score, label).
DOMAIN_AUTHORITY: dict[str, tuple[float, str]] = {
    # Primary research / vendor official
    "arxiv.org": (5.0, "primary research archive"),
    "openreview.net": (5.0, "peer-reviewed venue"),
    "huggingface.co": (4.5, "first-party model registry"),
    "github.com": (4.0, "first-party code/issue tracker"),
    "anthropic.com": (5.0, "vendor official"),
    "openai.com": (5.0, "vendor official"),
    "deepmind.google": (5.0, "vendor official"),
    "blogs.nvidia.com": (5.0, "vendor official"),
    "developer.nvidia.com": (5.0, "vendor official docs"),
    "build.nvidia.com": (5.0, "vendor model catalog"),
    # Established expert blogs
    "simonwillison.net": (4.0, "well-cited expert blog"),
    "lilianweng.github.io": (4.5, "former OAI researcher blog"),
    "magazine.sebastianraschka.com": (4.0, "established expert blog"),
    "www.latent.space": (4.0, "established practitioner publication"),
    # Skeptic / methodological scrutiny
    "garymarcus.substack.com": (3.5, "AI critic, well-known but opinionated"),
    "www.normaltech.ai": (4.0, "Princeton academic blog (AI Snake Oil)"),
    "bounded-regret.ghost.io": (4.0, "UC Berkeley faculty blog"),
    # Trade press
    "techcrunch.com": (3.0, "trade press, mixed depth"),
    "www.theinformation.com": (3.5, "paid trade press, solid sourcing"),
    # Community discussion
    "news.ycombinator.com": (3.0, "developer discussion forum"),
    "lobste.rs": (3.5, "curated developer forum"),
    "reddit.com": (2.5, "open community, signal/noise varies"),
    "old.reddit.com": (2.5, "open community, signal/noise varies"),
    # Korean
    "news.hada.io": (3.5, "Korean curated developer news"),
    "kakaoenterprise.github.io": (4.0, "Korean enterprise tech blog"),
    # Default for everything else
    "_default": (2.0, "unknown domain"),
}

KOREAN_KAKAO_GUARD = "kakaoenterprise.github.io"  # match `*.github.io` only when explicit


def _domain_authority(url: str) -> tuple[float, str]:
    if not url:
        return DOMAIN_AUTHORITY["_default"]
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return DOMAIN_AUTHORITY["_default"]
    # Exact host match first
    if host in DOMAIN_AUTHORITY:
        return DOMAIN_AUTHORITY[host]
    # Strip leading `www.`
    stripped = host.removeprefix("www.")
    if stripped in DOMAIN_AUTHORITY:
        return DOMAIN_AUTHORITY[stripped]
    return DOMAIN_AUTHORITY["_default"]


# ---------------------------------------------------------------------------
# Authority — author signals (Reddit Flair, GitHub bot suffix, etc.)
# ---------------------------------------------------------------------------

BOT_AUTHOR_PATTERNS = (
    re.compile(r"\bbot\b", re.I),
    re.compile(r"\[bot\]$", re.I),
    re.compile(r"-bot$", re.I),
    re.compile(r"^stainless-app", re.I),
)


def _author_adjustment(item: EvidenceItem) -> tuple[float, str]:
    author = (item.author or "").strip()
    if not author or author == "익명/미상":
        return -0.5, "no author"
    for pat in BOT_AUTHOR_PATTERNS:
        if pat.search(author):
            return -1.0, f"bot account ({author})"
    # Reddit-specific: low score => recent / unestablished poster
    score = item.score or 0
    if item.source == "reddit" and score >= 100:
        return +0.5, f"high-upvote Reddit post ({score})"
    if item.source == "hackernews" and score >= 200:
        return +0.5, f"front-page HN ({score})"
    return 0.0, ""


# ---------------------------------------------------------------------------
# Verifiability — outbound links + numeric mentions in body
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+", re.I)
_NUMERIC_RE = re.compile(r"(?<![\w])(\d{1,3}(?:[.,]\d+)?)(?:%|[kKmMbB]?\b|[a-zA-Z]+)?")


def _verifiability(item: EvidenceItem) -> tuple[float, str]:
    body = item.body_full or item.text or ""
    n_links = len(_URL_RE.findall(body))
    n_numbers = len(_NUMERIC_RE.findall(body))
    score = 1.0  # baseline

    if n_links >= 5:
        score += 2.0
    elif n_links >= 2:
        score += 1.0
    elif n_links >= 1:
        score += 0.5

    if n_numbers >= 8:
        score += 2.0
    elif n_numbers >= 3:
        score += 1.0

    score = min(score, 5.0)
    return score, f"{n_links} outbound links, {n_numbers} numeric mentions"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AxisScore:
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationResult:
    url: str
    authority: AxisScore
    verifiability: AxisScore
    aggregate: float

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "authority": {"score": self.authority.score, "reasons": self.authority.reasons},
            "verifiability": {"score": self.verifiability.score, "reasons": self.verifiability.reasons},
            "aggregate": self.aggregate,
        }


def validate_one(item: EvidenceItem) -> ValidationResult:
    dom_score, dom_label = _domain_authority(item.url)
    auth_adj, auth_label = _author_adjustment(item)
    auth_score = max(0.0, min(5.0, dom_score + auth_adj))
    auth_reasons = [f"domain: {dom_label} ({dom_score:.1f})"]
    if auth_label:
        auth_reasons.append(f"author: {auth_label} ({auth_adj:+.1f})")

    ver_score, ver_label = _verifiability(item)
    ver_reasons = [ver_label]

    aggregate = round((auth_score + ver_score) / 2, 2)
    return ValidationResult(
        url=item.url,
        authority=AxisScore(score=round(auth_score, 2), reasons=auth_reasons),
        verifiability=AxisScore(score=round(ver_score, 2), reasons=ver_reasons),
        aggregate=aggregate,
    )


def validate_many(items: list[EvidenceItem]) -> list[ValidationResult]:
    return [validate_one(it) for it in items]
