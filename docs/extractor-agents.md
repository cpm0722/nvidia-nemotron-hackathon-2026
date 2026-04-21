# Extractor Agents — per-source A2A design

> Five NAT-based A2A extractor agents that collect AI-product signals from Reddit, arXiv, OpenAI blog, Lobsters, and GeekNews. Each agent is an independently installable package under `agents/extractor-<source>/`, sharing schemas via `libs/ari-core/`.

## Layout

```
nvidia-nemotron-hackathon-2026/
├── libs/
│   └── ari-core/                         # Shared schemas + HTTP helpers
│       ├── pyproject.toml
│       └── src/ari_core/
│           ├── __init__.py               # re-exports
│           ├── schemas.py                # EvidenceItem, ScrapeInput, ScrapeResult
│           ├── http_base.py              # Timer, USER_AGENT, DEFAULT_TIMEOUT_SECONDS
│           └── async_runner.py           # run_scraper_async()
│
└── agents/
    ├── extractor-arcalive/    (port 10000)  # (separate PR)
    ├── extractor-reddit/      (port 10001)
    ├── extractor-arxiv/       (port 10002)
    ├── extractor-openai/      (port 10003)
    ├── extractor-lobsters/    (port 10004)
    └── extractor-geeknews/    (port 10005)
```

Each `extractor-*/` follows the `extractor-arcalive` template:

```
agents/extractor-<source>/
├── .gitignore
├── pyproject.toml                        # nat.components entry point
├── configs/config.yml                    # general.front_end + llms + function_groups + workflow
├── prompts/system_prompt.txt             # English ReAct prompt (loaded via file://)
├── src/nat_extractor_<source>/
│   ├── __init__.py
│   ├── register.py                       # FunctionGroup registration
│   └── scraper.py                        # HTTP + parse logic
└── scripts/
    ├── run.sh                            # uv run nat run ...
    ├── a2a_server.sh                     # uv run nat a2a serve ...
    └── a2a_client.sh                     # uv run nat a2a client call ...
```

## Function group → tool naming

Each agent exposes a single `FunctionGroup` with one function. The NAT tool reference is `{group_name}__{function_name}`:

| Agent | Group (type) | Tool reference |
|---|---|---|
| extractor-reddit | `reddit_scraper` | `reddit_scraper__search_posts` |
| extractor-arxiv | `arxiv_scraper` | `arxiv_scraper__search_papers` |
| extractor-openai | `openai_scraper` | `openai_scraper__search_posts` |
| extractor-lobsters | `lobsters_scraper` | `lobsters_scraper__search_posts` |
| extractor-geeknews | `geeknews_scraper` | `geeknews_scraper__search_posts` |

## Per-source collection notes

### extractor-reddit
- Endpoint: `old.reddit.com/r/<sub>/search.json` (unauthenticated `.json` fallback; OAuth new-app creation is blocked since 2025-11).
- Default subreddits: `LocalLLaMA`, `MachineLearning`, `ClaudeAI`, `singularity`.
- Enrichment: optional top-comment fetch per post (`/comments/{id}.json`, parallel 3 workers) → `metadata.comments = [{author, body, score}]`.

### extractor-arxiv
- Endpoint: `export.arxiv.org/api/query` (no auth, 1 req / 3 sec throttle per ToS).
- Returns Atom XML parsed with feedparser.
- Fields: title, abstract, authors, `metadata.arxiv_id`, `metadata.categories`. Sorted by submittedDate descending.

### extractor-openai
- Feed: `https://openai.com/news/rss.xml` (fixed).
- Client-side substring filter on title + summary. Empty keyword returns latest posts.

### extractor-lobsters
- RSS feed + per-story JSON API (`https://lobste.rs/s/{short_id}.json`) in parallel (4 workers).
- Enrichment: `description_plain`, real story score, comment count, and top comments with `{author, body, score, depth}`.
- `metadata.tags` promoted from RSS tags (e.g. `["ai", "programming"]`).

### extractor-geeknews
- Feed: `feeds.feedburner.com/geeknews-feed` (direct `news.hada.io/rss` is CloudFront UA-blocked).
- HTML enrichment: parallel fetch (4 workers) of each `news.hada.io/topic?id=<id>` page. Regex-based parsing — no extra HTML dependencies.
- Extracted: `metadata.upvotes`, `metadata.comments_count`, `metadata.comments = [{cid, author, body, depth}]`.
- Selectors (confirmed 2026-04-21):
  - Points: `<span id='tp{topic_id}'>N</span>`
  - Comment count: JSON-LD `"commentCount":N` (absent → defaulted to 0)
  - Comment open: `<div class=comment_row id=cid{N} ... style=--depth:{N}>`
  - Comment content: `<span id='contents{cid}' class='comment_contents'>...</span>`

## Running locally

Install `ari_core` once (shared dependency), then each agent:

```bash
# From repo root
uv pip install -e libs/ari-core
uv pip install -e agents/extractor-reddit \
               -e agents/extractor-arxiv \
               -e agents/extractor-openai \
               -e agents/extractor-lobsters \
               -e agents/extractor-geeknews
```

### Direct run (single request via console front-end)

```bash
bash agents/extractor-reddit/scripts/run.sh "Claude Opus 4.7"
bash agents/extractor-arxiv/scripts/run.sh "nemotron"
bash agents/extractor-geeknews/scripts/run.sh "Claude"
# etc.
```

### A2A server

```bash
bash agents/extractor-reddit/scripts/a2a_server.sh    # port 10001
bash agents/extractor-arxiv/scripts/a2a_server.sh     # port 10002
bash agents/extractor-openai/scripts/a2a_server.sh    # port 10003
bash agents/extractor-lobsters/scripts/a2a_server.sh  # port 10004
bash agents/extractor-geeknews/scripts/a2a_server.sh  # port 10005
```

Each server exposes an Agent Card at `http://<host>:<port>/.well-known/agent.json`.

### A2A client test

```bash
bash agents/extractor-reddit/scripts/a2a_client.sh "Claude Opus 4.7"
```

## Config knobs (override per agent in `configs/config.yml`)

| Knob | reddit | arxiv | openai | lobsters | geeknews | Default |
|---|---|---|---|---|---|---|
| `default_limit` | ✓ | ✓ | ✓ | ✓ | ✓ | 10 |
| `max_text_chars` | ✓ | ✓ | ✓ | ✓ | ✓ | 8000 |
| `include_comments` | ✓ | — | — | ✓ | ✓ | true |
| `max_comments_per_post` | ✓ | — | — | — | — | 5 |
| `max_comments_per_story` | — | — | — | ✓ | — | 10 |
| `max_comments_per_topic` | — | — | — | — | ✓ | 10 |
| `max_comment_chars` | ✓ | — | — | ✓ | ✓ | 1500 |
| `comment_workers` / `workers` / `html_workers` | ✓ | — | — | ✓ | ✓ | 3–4 |
| `default_subreddits` | ✓ | — | — | — | — | LocalLLaMA / MachineLearning / ClaudeAI / singularity |
| `enrich_json` | — | — | — | ✓ | — | true |
| `enrich_html` | — | — | — | — | ✓ | true |

Demo-day fast-fail: set `include_comments: false` (or `enrich_html: false` / `enrich_json: false`) if a source gets slow.

## LLM

Each agent uses `nvidia/nemotron-3-super-120b-a12b` via the team Brev endpoint (`https://model-server-uya78rbya.brevlab.com/v1`). Swap in any OpenAI-compatible base URL in `configs/config.yml` to point at vLLM, NVIDIA Build API, or a self-hosted NIM.

## Known constraints

- **Reddit from cloud IPs**: Brev is often 403'd by Reddit. Keep a `cache_file` fallback in the orchestrator for demo-day (not implemented here — Mac-local scrape works).
- **arXiv throttle**: 1 req / 3s per ToS. A single agent throttles itself; running multiple arxiv searches in parallel queues them.
- **GeekNews HTML drift**: Selectors (`tp{id}` span, `commentCount` JSON-LD, `comment_row` div) verified 2026-04-21. If the site changes, `enrich_html: false` degrades gracefully to RSS-only metadata.
