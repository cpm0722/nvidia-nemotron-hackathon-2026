# AI Product Feedback Aggregator

An agentic system that collects and summarizes both official performance data (benchmarks, papers) and real user reactions to newly released AI products (models, APIs, frameworks, features).

Built for the **2026 NVIDIA Nemotron Hackathon — Track A: Creative Agentic Systems**.  
Backbone models: [Nemotron-3-Nano-30B-A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard) and [Nemotron-3-Super-120B-A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard).

---

## Description

Given a natural language query (Korean or English), the system:

1. Extracts AI product/model names from the query
2. Runs 7 extractors in parallel — each scrapes a data source and validates results
3. Reporter synthesizes all validated evidence into a structured markdown report

---

## Architecture

```
user query
    │
    ▼
query-generator  (nemotron-nano, port 10001)
    │  product name(s)
    ├──────┬──────┬──────┬──────┬──────┬──────┐
    ▼      ▼      ▼      ▼      ▼      ▼      ▼   parallel
arcalive arxiv bench geeknews lobsters openai reddit
(10010) (10011)(10012) (10013) (10014) (10015)(10016)
    │      │      │      │       │       │      │
    ▼      ▼      ▼      ▼       ▼       ▼      ▼
validator validator ...  (each extractor calls its own validator internally)
(10020) (10021)(10022) (10023) (10024) (10025)(10026)
    │      │      │      │       │       │      │
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

| Agent | Port | Model |
|---|---|---|
| e2e | 10000 | nemotron-nano |
| query-generator | 10001 | nemotron-nano |
| reporter | 10002 | nemotron-super |
| extractor (arcalive–reddit) | 10010–10016 | nemotron-nano |
| validator (arcalive–reddit) | 10020–10026 | nemotron-super |

### Model Assignment

| Role | Model |
|---|---|
| query-generator, extractors, e2e | `nvidia/nemotron-3-nano-30b-a3b` |
| validators, reporter | `nvidia/nemotron-3-super-120b-a12b` |

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

# Terminal 2–8 — extractors (one per source)
cd agents/arcalive/extractor && ./scripts/a2a_server.sh
cd agents/arxiv/extractor    && ./scripts/a2a_server.sh
# ... repeat for benchmark, geeknews, lobsters, openai, reddit

# Terminal 9–15 — validators (one per source)
cd agents/arcalive/validator && ./scripts/a2a_server.sh
# ... repeat for the other 6

# Terminal 16 — reporter
cd agents/reporter && ./scripts/a2a_server.sh

# Terminal 17 — e2e orchestrator
cd agents/e2e && ./scripts/a2a_server.sh

# Send a query
cd agents/e2e && ./scripts/a2a_client.sh "GPT5와 Gemma4 비교해줘"
```

### Run a single extractor directly

```bash
cd agents/reddit/extractor
./scripts/run.sh "GPT-5"
```

---

## Usage

### Running an individual agent

Every agent under `agents/` follows the same script interface:

```bash
cd agents/{source}/{extractor|validator}

# Direct run (development)
./scripts/run.sh "<product name>"

# A2A server mode
./scripts/a2a_server.sh

# Test client (requires server running)
./scripts/a2a_client.sh "<product name>"
```

### Configuration

Each agent's behavior is controlled by `configs/config.yml`:

```yaml
llms:
  primary_llm:
    model_name: nvidia/nemotron-3-nano-30b-a3b
    base_url: https://<model-server-url>/v1

function_groups:
  {source}_scraper:
    board: alpaca      # source-specific options
    max_pages: 2
```

The e2e agent's `config.yml` lists all extractor URLs — update them if you deploy agents on different hosts:

```yaml
function_groups:
  pipeline:
    query_generator_url: http://localhost:10001
    extractor_urls:
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
│   ├── e2e/                        # Full pipeline orchestrator (port 10000)
│   │   ├── configs/config.yml
│   │   ├── prompts/system_prompt.txt
│   │   ├── scripts/
│   │   └── src/nat_e2e/register.py  # FunctionGroup: generate_queries/collect_evidence/generate_report
│   ├── query-generator/            # Product name extractor (port 10001)
│   ├── reporter/                   # Evidence synthesizer → markdown report (port 10002)
│   ├── arcalive/
│   │   ├── extractor/              # port 10010
│   │   └── validator/              # port 10020
│   ├── arxiv/
│   │   ├── extractor/              # port 10011
│   │   └── validator/              # port 10021
│   ├── benchmark/
│   │   ├── extractor/              # port 10012
│   │   └── validator/              # port 10022
│   ├── geeknews/
│   │   ├── extractor/              # port 10013
│   │   └── validator/              # port 10023
│   ├── lobsters/
│   │   ├── extractor/              # port 10014
│   │   └── validator/              # port 10024
│   ├── openai/
│   │   ├── extractor/              # port 10015
│   │   └── validator/              # port 10025
│   └── reddit/
│       ├── extractor/              # port 10016
│       └── validator/              # port 10026
├── libs/
│   ├── ari-core/                   # Shared scraper schemas (EvidenceItem, ScrapeResult)
│   └── validator-core/             # ValidatorCallerConfig — forwards to validator A2A
├── docs/                           # Internal reference documents
├── task-histories/                 # Branch plans and completion reports
├── pyproject.toml                  # uv workspace root
└── CLAUDE.md                       # Project instructions for Claude Code
```
