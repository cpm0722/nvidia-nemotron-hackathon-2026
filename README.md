# AI Product Feedback Aggregator

An agentic system that collects and summarizes both official performance data (benchmarks, papers) and real user reactions to newly released AI products (models, APIs, frameworks, features).

Built for the **2026 NVIDIA Nemotron Hackathon — Track A: Creative Agentic Systems**.  
Backbone models: [Nemotron-3-Nano-30B-A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard) and [Nemotron-3-Super-120B-A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard).

---

## Description

Given a natural language query (Korean or English), the system:

1. Extracts AI product/model names from the query (query-generator, LLM)
2. Runs 7 **collectors** in parallel — each collector is a Python pipeline that scrapes a source (extractor) and forwards the raw items to an LLM-based validator A2A service for relevance filtering
3. Reporter synthesizes all validated evidence into a structured markdown report (LLM)

---

## Architecture

```
user query
    │
    ▼
query-generator  (nemotron-nano, port 10001)
    │  product name(s)
    ├──────┬──────┬──────┬──────┬──────┬──────┐
    ▼      ▼      ▼      ▼      ▼      ▼      ▼   parallel collectors
┌──────────────────────────────── collector (one per source) ────────────────────────────┐
│  extractor  (LLM-less A2A workflow, ports 10010–10016)                                 │
│      │                                                                                 │
│      │  scrape → A2A(message/send) → validator                                         │
│      ▼                                                                                 │
│  validator  (chat_completion LLM A2A, ports 10020–10026)                               │
│      │  filtered ScrapeResult                                                          │
│      ▼                                                                                 │
│  extractor returns filtered ScrapeResult JSON                                          │
└────────────────────────────────────────────────────────────────────────────────────────┘
    │      │      │      │       │       │      │
    └──────┴──────┴──────┴───────┴───────┴──────┘
                               │
                               ▼
                         reporter  (nemotron-super, port 10002)
                               │
                               ▼
                    structured markdown report
```

The **e2e agent** (port 10000) is itself an LLM-less sequential workflow that calls
`query-generator → extractor×N (parallel) → reporter` in fixed order.

Each **collector** = one extractor A2A service + one validator A2A service. The
extractor orchestrates the per-source pipeline in plain Python (no ReAct): it
scrapes, then HTTP-calls the paired validator with the scraped items, then
returns the filtered result. Only the validator (and the reporter / query-generator)
use an LLM — the extractor and e2e layers are deterministic.

### Data Sources

| Source | Type | Extractor Port | Validator Port |
|---|---|---|---|
| ArcaLive | Korean community discussion | 10010 | 10020 |
| arXiv | Research papers | 10011 | 10021 |
| Benchmark (AA + HuggingFace) | Leaderboard / eval results | 10012 | 10022 |
| GeekNews | Korean tech news | 10013 | 10023 |
| Lobsters | Tech community discussion | 10014 | 10024 |
| OpenAI Blog | Official announcements | 10015 | 10025 |
| Reddit | English community discussion | 10016 | 10026 |

### Agent Port Map

| Agent | Port | Uses LLM? |
|---|---|---|
| e2e | 10000 | no (sequential Python) |
| query-generator | 10001 | nemotron-nano |
| reporter | 10002 | nemotron-super |
| extractors (arcalive–reddit) | 10010–10016 | no (scrape + A2A call) |
| validators (arcalive–reddit) | 10020–10026 | nemotron-super (chat_completion) |

### Model Assignment

| Role | Model |
|---|---|
| query-generator | `nvidia/nemotron-3-nano-30b-a3b` |
| validators, reporter | `nvidia/nemotron-3-super-120b-a12b` |
| extractors, e2e | none (LLM-less Python orchestration) |

---

## Setup

**Requirements:** Python 3.11–3.13, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/cpm0722/nvidia-nemotron-hackathon-2026
cd nvidia-nemotron-hackathon-2026
uv sync
```

Model endpoints are on-premise NIM servers deployed on Brev (H100 × 4).  
No API key is required — set `api_key: empty` in `config.yml`.

| Model | Base URL |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | `https://model-server-uya78rbya.brevlab.com/v1` |
| `nvidia/nemotron-3-nano-30b-a3b` | `https://model-server-4dfr8gv78.brevlab.com/v1` |

---

## Quick Start

### Run via `docker compose` (recommended)

Brings up all 17 A2A agents (7 extractors + 7 validators + query-generator + reporter + e2e) in the correct dependency order from a single shared image.

```bash
cp .env.example .env             # edit model endpoints if yours differ
docker compose up -d --build     # first run builds the shared image
docker compose ps                # wait until every service is 'healthy'
curl http://localhost:10000/.well-known/agent-card.json  # e2e is up

# send a query
cd agents/e2e && ./scripts/a2a_client.sh "GPT5와 Gemma4 비교해줘"
```

Startup order is enforced by `depends_on: condition: service_healthy`:

```
L1: 7 validators + query-generator + reporter   (talk to Brev NIM only)
L2: 7 extractors                                  (each depends on its own validator)
L3: e2e                                           (depends on every L1/L2 service)
```

Only the e2e front-end (port `10000`) is published to the host. Intra-stack traffic stays on the `ari-net` bridge via compose DNS (`http://arcalive-validator:10020`, etc.). Override the host port with `E2E_HOST_PORT` in `.env`.

### Run the full e2e pipeline manually

Start all agents (each in a separate terminal), then call the e2e agent:

```bash
# Terminal 1 — query-generator
cd agents/query-generator && ./scripts/a2a_server.sh

# Terminal 2–8 — extractors (one per source)
cd agents/collectors/arcalive/extractor && ./scripts/a2a_server.sh
cd agents/collectors/arxiv/extractor    && ./scripts/a2a_server.sh
# ... repeat for benchmark, geeknews, lobsters, openai, reddit

# Terminal 9–15 — validators (one per source)
cd agents/collectors/arcalive/validator && ./scripts/a2a_server.sh
# ... repeat for the other 6

# Terminal 16 — reporter
cd agents/reporter && ./scripts/a2a_server.sh

# Terminal 17 — e2e orchestrator
cd agents/e2e && ./scripts/a2a_server.sh

# Send a query
cd agents/e2e && ./scripts/a2a_client.sh "GPT5와 Gemma4 비교해줘"
```

### Scaled test (arcalive + geeknews only)

Use `configs/config_test.yml` when running e2e with only a subset of extractors:

```bash
cd agents/e2e && uv run nat a2a serve --config_file configs/config_test.yml
```

(Requires just arcalive + geeknews extractors + validators + query-generator + reporter running.)

### Run a single extractor directly

```bash
cd agents/collectors/reddit/extractor
./scripts/run.sh "GPT-5"
```

---

## Usage

### Running an individual agent

Every agent follows the same script interface:

```bash
# Extractors and validators are both under agents/collectors/{source}/
cd agents/collectors/{source}/{extractor|validator}

# Or the orchestrator / supporting agents
cd agents/{query-generator|reporter|e2e}

# A2A server mode
./scripts/a2a_server.sh

# Test client (requires server running)
./scripts/a2a_client.sh "<input>"

# Direct run (development — extractors, query-generator, reporter, e2e only)
./scripts/run.sh "<input>"
```

### Configuration

Extractor's `configs/config.yml` has no `llms:` section — it's a pure
Python workflow that hits the paired validator over A2A:

```yaml
general:
  front_end:
    _type: a2a
    port: 10010

workflow:
  _type: arcalive_extractor
  board: alpaca
  max_pages: 2
  limit: 5
  validator_url: http://localhost:10020
  validator_timeout_seconds: 120
```

The validator keeps the original chat_completion workflow and prompt; its
`config.yml` carries the LLM definition and `file://` prompt reference.

The e2e agent's `config.yml` lists all extractor URLs:

```yaml
workflow:
  _type: e2e_pipeline
  query_generator_url: http://localhost:10001
  collector_urls:
    - http://localhost:10010   # arcalive extractor
    - http://localhost:10011   # arxiv extractor
    # ...
  reporter_url: http://localhost:10002
```

---

## File Structure

```
nvidia-nemotron-hackathon-2026/
├── agents/
│   ├── e2e/                                    # Full pipeline orchestrator (port 10000)
│   │   ├── configs/
│   │   │   ├── config.yml                      # all 7 extractors
│   │   │   └── config_test.yml                 # arcalive + geeknews only
│   │   ├── scripts/
│   │   └── src/nat_e2e/register.py             # LLM-less sequential pipeline
│   ├── query-generator/                        # Product name extractor (port 10001)
│   ├── reporter/                               # Evidence synthesizer → markdown report (port 10002)
│   └── collectors/                             # per-source extractor + validator pairs
│       ├── arcalive/
│       │   ├── extractor/                      # port 10010 (no LLM)
│       │   │   ├── configs/config.yml
│       │   │   ├── scripts/{a2a_server,a2a_client,run}.sh
│       │   │   ├── src/nat_extractor_arcalive/
│       │   │   │   ├── extractor.py            # scraper
│       │   │   │   ├── register.py             # @register_function scrape → validator A2A
│       │   │   │   └── (crawler.py, parser.py, models.py)
│       │   │   ├── tests/
│       │   │   └── pyproject.toml
│       │   └── validator/                      # port 10020 (chat_completion LLM)
│       │       ├── configs/config.yml
│       │       ├── prompts/system_prompt.txt
│       │       ├── scripts/{a2a_server,a2a_client}.sh
│       │       ├── src/nat_arcalive_validator/
│       │       └── pyproject.toml
│       ├── arxiv/     { extractor/, validator/ }    # ports 10011 / 10021
│       ├── benchmark/ { extractor/, validator/ }    # ports 10012 / 10022
│       ├── geeknews/  { extractor/, validator/ }    # ports 10013 / 10023
│       ├── lobsters/  { extractor/, validator/ }    # ports 10014 / 10024
│       ├── openai/    { extractor/, validator/ }    # ports 10015 / 10025
│       └── reddit/    { extractor/, validator/ }    # ports 10016 / 10026
├── libs/
│   ├── ari-core/                               # Shared scraper schemas (EvidenceItem, ScrapeResult)
│   └── validator-core/                         # Shared legacy validator_caller (kept for workspace refs)
├── docker/                                     # Shared image for all 17 A2A agents
│   ├── Dockerfile                              # uv-workspace install; entrypoint reads CONFIG_FILE
│   └── entrypoint.sh                           # cd to agent dir + `nat a2a serve`
├── docker-compose.yml                          # 17 services, 3-layer depends_on graph, healthchecks
├── .env.example                                # Brev model endpoints + E2E_HOST_PORT template
├── docs/                                       # Internal reference documents
├── task-histories/                             # Branch plans and completion reports
├── pyproject.toml                              # uv workspace root (14 collector subpackages + e2e/qgen/reporter)
└── CLAUDE.md                                   # Project instructions for Claude Code
```
