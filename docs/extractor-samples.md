# Extractor Agents — real-call sample outputs

> JSON returned by each scraper when called directly. Every item conforms to `ari_core.schemas.ScrapeResult` → serialized via `.model_dump()`.

## Common envelope

```json
{
  "source": "<source tag>",
  "ok": true | false,
  "items": [EvidenceItem, ...],
  "error": null | "message",
  "latency_ms": int,
  "fetched_at": "ISO 8601 UTC"
}
```

**EvidenceItem**: `{source, source_detail, url, author, title, text, body_full, timestamp, score, metadata}`

**metadata.comments** (reddit / lobsters / geeknews): `[{author, body, score?, depth?, cid?}, ...]`

---

## 1. reddit_scraper

**Call:** `query="Claude"`, `limit=2`, `subreddits=["ClaudeAI"]`, `max_comments_per_post=3`, `max_comment_chars=400`

```json
{
  "source": "reddit",
  "ok": true,
  "items": [
    {
      "source": "reddit",
      "source_detail": "r/ClaudeAI",
      "url": "https://reddit.com/r/ClaudeAI/comments/1srmjlo/i_need_to_stop_here/",
      "author": "TPIronside",
      "title": "I need to stop here...?",
      "text": "https://preview.redd.it/nu2xb0awfjwg1.png?... I cannot believe that we've actually become insensitive to this kind of bullshit from these language models 😭 ... NOTE: This is Opus 4.6 on CC btw",
      "timestamp": "2026-04-21T12:43:11Z",
      "score": 1,
      "metadata": {
        "num_comments": 2,
        "upvote_ratio": 0.67,
        "link_flair_text": "Humor",
        "comments": [
          { "author": "Ok-Clerk7116", "body": "This is crazy lmao what happend to claude", "score": 1 }
        ]
      }
    },
    {
      "source": "reddit",
      "source_detail": "r/ClaudeAI",
      "url": "https://reddit.com/r/ClaudeAI/comments/1srmhg5/hardware_set_up_advice/",
      "author": "morphector",
      "title": "Hardware set up advice",
      "text": "I have recently obtained a decent budget for AI at the company I work at...  1) give the team the ability to work remotely on a decent PC laptop ... 2) have some power users remote into a desktop ...",
      "timestamp": "2026-04-21T12:40:33Z",
      "score": 2,
      "metadata": {
        "num_comments": 4,
        "upvote_ratio": 1.0,
        "link_flair_text": "Question",
        "comments": [
          {
            "author": "token-tensor",
            "body": "for the power user desktop, an M4 Max MacBook Pro or M4 Ultra Mac Studio gives you the best agent-per-watt ratio for Claude cowork and local LLM work...",
            "score": 2
          }
        ]
      }
    }
  ],
  "error": null,
  "latency_ms": 684
}
```

**Notes**
- `metadata.comments[]` — top comments via `/comments/{id}.json` (sort=top).
- Extra HTTP call per post. Parallel via `comment_workers` (default 3).
- Disable with `include_comments: false` in config.

---

## 2. arxiv_scraper

**Call:** `keyword="nemotron"`, `limit=2`

```json
{
  "source": "arxiv",
  "ok": true,
  "items": [
    {
      "source": "arxiv",
      "source_detail": "arxiv.org",
      "url": "https://arxiv.org/abs/2604.17429v1",
      "author": "George Drayson",
      "title": "Jupiter-N Technical Report",
      "text": "We present Jupiter-N, a hybrid reasoning model post-trained from Nemotron 3 Super, a fully open-source 120 billion parameter LLM...",
      "timestamp": "2026-04-19T13:18:51Z",
      "score": null,
      "metadata": {
        "arxiv_id": "2604.17429v1",
        "categories": ["cs.CL", "cs.AI"]
      }
    },
    {
      "source": "arxiv",
      "source_detail": "arxiv.org",
      "url": "https://arxiv.org/abs/2604.14493v2",
      "author": "Nenad Banfic, David Fan, Kunal Vaishnavi, ...",
      "title": "Pushing the Limits of On-Device Streaming ASR...",
      "text": "Deploying high-quality automatic speech recognition (ASR) on edge devices requires models that jointly optimize accuracy, latency, and memory footprint...",
      "timestamp": "2026-04-16T00:04:32Z",
      "metadata": {
        "arxiv_id": "2604.14493v2",
        "categories": ["cs.AI"]
      }
    }
  ],
  "latency_ms": 81
}
```

**Notes**
- Primary-source research signal — no comments / discussion data.
- Abstract returned verbatim up to `max_text_chars` (8000).
- 1 req / 3s throttle enforced internally.

---

## 3. openai_scraper

**Call:** `keyword=""` (latest), `limit=2`

```json
{
  "source": "openai",
  "ok": true,
  "items": [
    {
      "source": "openai",
      "source_detail": "openai.com/news",
      "url": "https://openai.com/index/scaling-codex-to-enterprises-worldwide",
      "title": "Scaling Codex to enterprises worldwide",
      "text": "OpenAI launches Codex Transformation Partners, a program with Accenture, PwC, Infosys, and others to help enterprises deploy and scale Codex across the software development lifecycle.",
      "timestamp": "Tue, 21 Apr 2026 00:00:00 GMT",
      "metadata": {"feed_title": "OpenAI News"}
    },
    {
      "source": "openai",
      "source_detail": "openai.com/news",
      "url": "https://openai.com/index/hyatt-advances-ai-with-chatgpt-enterprise",
      "title": "OpenAI helps Hyatt advance AI among colleagues",
      "text": "Hyatt deploys ChatGPT Enterprise across its global workforce, using GPT-5.4 and Codex to improve productivity, operations, and guest experiences.",
      "timestamp": "Mon, 20 Apr 2026 00:00:00 GMT",
      "metadata": {"feed_title": "OpenAI News"}
    }
  ],
  "latency_ms": 897
}
```

**Notes**
- Blog RSS only — no comments upstream.
- `text` is the RSS summary; full body requires a downstream body enricher step.

---

## 4. lobsters_scraper

**Call:** `keyword=""`, `limit=2`, `max_comments_per_story=3`, `max_comment_chars=400`

```json
{
  "source": "lobsters",
  "ok": true,
  "items": [
    {
      "source": "lobsters",
      "source_detail": "lobste.rs",
      "url": "https://isaaccorbrey.com/notes/jujutsu-megamerges-for-fun-and-profit",
      "author": "isaaccorbrey.com via knl",
      "title": "Jujutsu megamerges for fun and profit",
      "text": "<p><a href=\"https://lobste.rs/s/etrtmp/jujutsu_megamerges_for_fun_profit\">Comments</a></p>",
      "timestamp": "Mon, 20 Apr 2026 17:08:39 -0500",
      "score": 52,
      "metadata": {
        "tags": ["vcs"],
        "comments_url": "https://lobste.rs/s/etrtmp/jujutsu_megamerges_for_fun_profit",
        "short_id": "etrtmp",
        "comments_count": 9,
        "comments": [
          { "author": "edwintorok", "body": "Megamerges are one of the reasons why I use Jujutsu...", "score": 10, "depth": 0 },
          { "author": "gasche",     "body": "You mention it in passing, but the ability to do `jj undo` to undo the last operation is pretty incredible when you are used to git.", "score": 8, "depth": 1 },
          { "author": "edwintorok", "body": "Yes, and there are also other nice features...", "score": 4, "depth": 2 }
        ]
      }
    },
    {
      "source": "lobsters",
      "source_detail": "lobste.rs",
      "url": "https://forgejo.org/2026-04-release-v15-0/",
      "author": "forgejo.org via jussi",
      "title": "Forgejo v15.0 is available",
      "text": "<p><a href=\"https://lobste.rs/s/uxkvmr/forgejo_v15_0_is_available\">Comments</a></p>",
      "timestamp": "Mon, 20 Apr 2026 08:06:15 -0500",
      "score": 99,
      "metadata": {
        "tags": ["release", "vcs"],
        "comments_url": "https://lobste.rs/s/uxkvmr/forgejo_v15_0_is_available",
        "short_id": "uxkvmr",
        "comments_count": 8,
        "comments": [
          { "author": "henrycatalinismith", "body": "This is the first Forgejo release with some of my work in it...", "score": 50, "depth": 0 },
          { "author": "lilac",               "body": "I've been maintaining a soft fork for months that I deploy to tree.ht, but I feel like a lot of it could/should be upstreamed...", "score": 4, "depth": 1 },
          { "author": "oliverpool",          "body": "> what's the process like?\\n\\nFairly standard, I think: ...", "score": 1, "depth": 2 }
        ]
      }
    }
  ],
  "latency_ms": 1582
}
```

**Notes**
- Per-story JSON API (`/s/{short_id}.json`) gives real score, full comment count, and threaded comments (`depth` 0 = top-level, 1 = reply, 2 = nested).
- When the story has no description (pure link post), `text` falls back to the RSS summary (a `<p><a>Comments</a></p>` stub).

---

## 5. geeknews_scraper

**Call:** `keyword=""`, `limit=2`, `enrich_html=True`, `max_comments_per_topic=3`, `max_comment_chars=400`

```json
{
  "source": "geeknews",
  "ok": true,
  "items": [
    {
      "source": "geeknews",
      "source_detail": "news.hada.io",
      "url": "https://news.hada.io/topic?id=28750",
      "title": "AI 레지스탕스가 성장중",
      "text": "AI 레지스탕스가 성장중",
      "timestamp": null,
      "score": 1,
      "metadata": {
        "feed_title": "GeekNews - 개발/기술/스타트업 뉴스 서비스",
        "topic_id": "28750",
        "upvotes": 1,
        "comments_count": 1,
        "comments": [
          {
            "cid": "55992",
            "author": "GN⁺",
            "body": "Hacker News 의견들 나는 이 사람이 커뮤니티 를 찾은 건 반갑지만, 집중된 관심 에 조금 매료된 면도 있어 보인다고 느낌음...",
            "depth": 0
          }
        ]
      }
    },
    {
      "source": "geeknews",
      "source_detail": "news.hada.io",
      "url": "https://news.hada.io/topic?id=28749",
      "title": "프로덕션 환경에서 바이브 코딩을 책임감 있게 하는 법 -  Vibe coding in prod | Code w/ Claude",
      "text": "<p>Anthropic의 코딩 에이전트 연구자 Eric이 바이브 코딩(AI에게 코드 작성을 전적으로 맡기는 방식)을 실제 서비스 환경에서 어떻게 안전하게 활용할 수 있는지를 다룬 발표입니다...</p>",
      "score": 15,
      "metadata": {
        "feed_title": "GeekNews - 개발/기술/스타트업 뉴스 서비스",
        "topic_id": "28749",
        "upvotes": 15,
        "comments_count": 0
      }
    }
  ],
  "latency_ms": 1255
}
```

**Notes**
- Comment parsing reuses the HTML already fetched for upvote/comment-count (no extra round-trip).
- 0-comment topics have no `comments` key; `comments_count: 0`.
- Comment `depth` reflects thread nesting from `style=--depth:N`.

---

## 6. A2A server — Agent Card

```bash
bash agents/extractor-reddit/scripts/a2a_server.sh &
curl -s http://localhost:10001/.well-known/agent.json | jq .
```

```json
{
  "capabilities": {"pushNotifications": false, "streaming": true},
  "defaultInputModes": ["text", "text/plain"],
  "defaultOutputModes": ["text", "text/plain"],
  "description": "Collects community reactions to AI products from Reddit (LocalLLaMA, MachineLearning, ClaudeAI, singularity).",
  "name": "Reddit Extractor Agent",
  "preferredTransport": "JSONRPC",
  "protocolVersion": "0.3.0",
  "skills": [
    {
      "id": "reddit_scraper__search_posts",
      "name": "Search Posts",
      "description": "Search Reddit for community reactions to an AI product...",
      "examples": [],
      "tags": []
    }
  ],
  "url": "http://127.0.0.1:10001/",
  "version": "1.0.0"
}
```

Client test (JSONRPC `message/send`):

```bash
bash agents/extractor-reddit/scripts/a2a_client.sh "Claude Opus 4.7"
```

---

## 7. Latency (Mac local, 2026-04-21)

| Agent | Without comments | With comments | Notes |
|---|---:|---:|---|
| reddit | 372 ms | 684 ms | +1 HTTP per post, 3 workers |
| arxiv | 475 ms | n/a | no comments; cached runs can dip to ~80 ms within throttle window |
| openai | 990 ms | n/a | RSS only |
| lobsters | 761 ms | 1582 ms | +1 JSON API per story, 4 workers |
| geeknews | 1194 ms | 1255 ms | HTML fetched once — comment parsing is free |

From Brev cloud IPs, Reddit often returns 403 (upstream cloud-IP block). Keep a `cache_file` fallback on the orchestrator side for demo-day stability.
