# AI Product Feedback Aggregator

An agentic system that collects and summarizes both official performance data (benchmarks, papers) and real user reactions to newly released AI products (models, APIs, frameworks, features).

Built for the **2026 NVIDIA Nemotron Hackathon — Track A: Creative Agentic Systems**.  
Backbone models: [Nemotron-3-Nano-30B-A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard) and [Nemotron-3-Super-120B-A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard).

---

## Description

Given an AI product name, the system:

1. Generates structured search queries tailored to each data source
2. Runs extractors in parallel across 8 sources (community forums, benchmarks, papers, social media)
3. Validates and filters collected documents per source
4. Aggregates all results into a structured summary of official performance and user sentiment

---

## Architecture

```
user query
    │
    ▼
query-generator  (nemotron-nano)
    │
    ├──────────────────────────────────────────────────────────────────┐
    │  parallel                                                        │
    ▼                                                                  ▼
extractor-reddit          extractor-arcalive      extractor-rss      ...
    │                          │                       │
    ▼                          ▼                       ▼
validator-reddit          validator-arcalive      validator-rss      ...
    │                          │                       │
    └──────────────────────────┴───────────────────────┘
                               │
                               ▼
                          aggregator  (nemotron-super)
                               │
                               ▼
                     structured summary
```

### Data Sources

| Source | Type |
|---|---|
| Reddit | Community discussion |
| ArcaLive | Korean community discussion |
| RSS | Official blog / news feed |
| HuggingFace Community | Developer discussion |
| HuggingFace Benchmark | Leaderboard / eval results |
| GeekNews | Tech news aggregator |
| arxiv | Research papers |
| X (Twitter) | Social media reactions |

### Model Assignment

| Agent | Model |
|---|---|
| query-generator | `nvidia/nemotron-3-nano-30b-a3b` |
| extractor | `nvidia/nemotron-3-nano-30b-a3b` |
| validator | `nvidia/nemotron-3-super-120b-a12b` |
| aggregator | `nvidia/nemotron-3-super-120b-a12b` |

---

## Setup

**Requirements:** Python 3.11–3.13, [uv](https://docs.astral.sh/uv/)

```bash
# Clone and install all workspace members
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

Run the ArcaLive extractor directly against a product name:

```bash
cd agents/extractor-arcalive
./scripts/run.sh "GPT-5"
```

Start the extractor as an A2A server:

```bash
cd agents/extractor-arcalive
./scripts/a2a_server.sh
```

Send a request to the running server from another terminal:

```bash
cd agents/extractor-arcalive
./scripts/a2a_client.sh "GPT-5"
```

---

## Usage

### Running an individual extractor

Each extractor under `agents/` can be run independently:

```bash
cd agents/{extractor-name}

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

### Adding a new extractor

See [`agents/README.md`](agents/README.md) for the standard directory structure and step-by-step guide.

---

## File Structure

```
nvidia-nemotron-hackathon-2026/
├── agents/                         # All extractor agents (uv workspace members)
│   ├── README.md                   # Standard agent structure & conventions
│   └── extractor-arcalive/         # ArcaLive extractor (reference implementation)
│       ├── configs/
│       │   └── config.yml          # NAT config: LLM, tools, workflow
│       ├── prompts/
│       │   └── system_prompt.txt   # ReAct agent system prompt
│       ├── scripts/
│       │   ├── a2a_server.sh       # Start A2A server
│       │   ├── a2a_client.sh       # Send test request
│       │   └── run.sh              # Direct run (dev)
│       ├── src/
│       │   └── nat_extractor_arcalive/
│       │       ├── crawler.py      # Scraping logic
│       │       ├── models.py       # Pydantic I/O models
│       │       ├── parser.py       # HTML parsing
│       │       └── register.py     # NAT FunctionGroup entry point
│       ├── tests/
│       │   ├── fixtures/           # Static HTML snapshots
│       │   ├── unit/
│       │   └── integration/
│       └── pyproject.toml
├── docs/                           # Internal reference documents
│   ├── nemoclaw_guide.md           # NemoClaw setup & usage
│   ├── nemo_agent_toolkit_guide.md # NAT (NeMo Agent Toolkit) guide
│   ├── llm_apis.md                 # Model endpoints & API reference
│   └── how-to-deploy-nemotron.md  # Nemotron deployment guide
├── task-histories/                 # Branch plans and completion reports
├── pyproject.toml                  # uv workspace root
├── uv.lock                         # Pinned dependency lockfile
└── CLAUDE.md                       # Project instructions for Claude Code
```
