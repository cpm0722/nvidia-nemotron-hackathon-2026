# AI Product Feedback Aggregator

An agentic system that collects and summarizes both official performance data (benchmarks, papers) and real user reactions to newly released AI products (models, APIs, frameworks, features).

Built for the **2026 NVIDIA Nemotron Hackathon — Track A: Creative Agentic Systems**.  
Backbone models: [Nemotron-3-Nano-30B-A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard) and [Nemotron-3-Super-120B-A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard).

---

## Description

Given a natural language query (Korean or English), the system:

1. Extracts AI product/model names from the query (query-generator, LLM)
2. Runs 7 **collectors** in parallel — each scrapes a data source and filters items with a deterministic keyword match (no LLM)
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
arcalive arxiv bench geeknews lobsters openai reddit
(10010) (10011)(10012) (10013) (10014) (10015)(10016)
    │      │      │      │       │       │      │
    │ each collector: scrape → keyword-filter (LLM-less)
    │
    └──────┴──────┴──────┴───────┴───────┴──────┘
                               │
                               ▼
                         reporter  (nemotron-super, port 10002)
                               │
                               ▼
                    structured markdown report
```

The **e2e agent** (port 10000) orchestrates the entire flow above via three tools:
`generate_queries` → `collect_evidence` → `generate_report`.

Each **collector** is a single LLM-less A2A service that internally runs
`extractor.py` (source-specific scraper) → `validator.py` (alnum-normalized
substring match against `title + text`) and returns a `ScrapeResult` JSON.

### Data Sources

| Source | Type | Collector Port |
|---|---|---|
| ArcaLive | Korean community discussion | 10010 |
| arXiv | Research papers | 10011 |
| Benchmark (AA + HuggingFace) | Leaderboard / eval results | 10012 |
| GeekNews | Korean tech news | 10013 |
| Lobsters | Tech community discussion | 10014 |
| OpenAI Blog | Official announcements | 10015 |
| Reddit | English community discussion | 10016 |

### Agent Port Map

| Agent | Port | Uses LLM? |
|---|---|---|
| e2e | 10000 | nemotron-nano (ReAct) |
| query-generator | 10001 | nemotron-nano |
| reporter | 10002 | nemotron-super |
| collectors (arcalive–reddit) | 10010–10016 | **no — deterministic** |

### Model Assignment

| Role | Model |
|---|---|
| query-generator, e2e | `nvidia/nemotron-3-nano-30b-a3b` |
| reporter | `nvidia/nemotron-3-super-120b-a12b` |
| collectors | none (LLM-less scrape + keyword filter) |

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

### Run the full e2e pipeline

Start all agents (each in a separate terminal), then call the e2e agent:

```bash
# Terminal 1 — query-generator
cd agents/query-generator && ./scripts/a2a_server.sh

# Terminal 2–8 — collectors (one per source)
cd agents/collectors/arcalive && ./scripts/a2a_server.sh
cd agents/collectors/arxiv    && ./scripts/a2a_server.sh
# ... repeat for benchmark, geeknews, lobsters, openai, reddit

# Terminal 9 — reporter
cd agents/reporter && ./scripts/a2a_server.sh

# Terminal 10 — e2e orchestrator
cd agents/e2e && ./scripts/a2a_server.sh

# Send a query
cd agents/e2e && ./scripts/a2a_client.sh "GPT5와 Gemma4 비교해줘"
```

### Scaled test (arcalive + geeknews only)

Use `configs/config_test.yml` when running e2e with only a subset of collectors:

```bash
cd agents/e2e && uv run nat a2a serve --config_file configs/config_test.yml
```

### Run a single collector directly

```bash
cd agents/collectors/reddit
./scripts/run.sh "GPT-5"
```

---

## Usage

### Running an individual agent

Every agent under `agents/` follows the same script interface:

```bash
cd agents/{collectors/<source>|query-generator|reporter|e2e}

# Direct run (development)
./scripts/run.sh "<input>"

# A2A server mode
./scripts/a2a_server.sh

# Test client (requires server running)
./scripts/a2a_client.sh "<input>"
```

### Configuration

Each collector's behavior is controlled by `configs/config.yml`. Collectors have **no `llms:` section** — only the scraper tunables and A2A front-end settings:

```yaml
general:
  front_end:
    _type: a2a
    port: 10010

workflow:
  _type: arcalive_collector
  board: alpaca
  max_pages: 2
  limit: 5
```

The e2e agent's `config.yml` lists all collector URLs — update them if you deploy agents on different hosts:

```yaml
function_groups:
  pipeline:
    query_generator_url: http://localhost:10001
    collector_urls:
      - http://localhost:10010   # arcalive
      - http://localhost:10011   # arxiv
      # ...
    reporter_url: http://localhost:10002
```

---

## File Structure

```
nvidia-nemotron-hackathon-2026/
├── agents/
│   ├── e2e/                              # Full pipeline orchestrator (port 10000)
│   │   ├── configs/
│   │   │   ├── config.yml                # all 7 collectors
│   │   │   └── config_test.yml           # arcalive + geeknews only
│   │   ├── scripts/
│   │   └── src/nat_e2e/register.py       # generate_queries / collect_evidence / generate_report
│   ├── query-generator/                  # Product name extractor (port 10001)
│   ├── reporter/                         # Evidence synthesizer → markdown report (port 10002)
│   └── collectors/                       # 7 LLM-less collectors (scrape + keyword filter)
│       ├── arcalive/                     # port 10010
│       │   ├── configs/config.yml
│       │   ├── scripts/{a2a_server,a2a_client,run}.sh
│       │   ├── src/nat_collector_arcalive/
│       │   │   ├── extractor.py          # scraper logic
│       │   │   ├── validator.py          # alnum-normalized keyword match
│       │   │   ├── register.py           # @register_function collect()
│       │   │   └── (crawler.py, parser.py, models.py — source-specific)
│       │   └── pyproject.toml
│       ├── arxiv/                        # port 10011
│       ├── benchmark/                    # port 10012
│       ├── geeknews/                     # port 10013
│       ├── lobsters/                     # port 10014
│       ├── openai/                       # port 10015
│       └── reddit/                       # port 10016
├── libs/
│   ├── ari-core/                         # Shared scraper schemas (EvidenceItem, ScrapeResult)
│   └── validator-core/                   # (legacy — no longer used by collectors)
├── docs/                                 # Internal reference documents
├── task-histories/                       # Branch plans and completion reports
├── pyproject.toml                        # uv workspace root
└── CLAUDE.md                             # Project instructions for Claude Code
```
