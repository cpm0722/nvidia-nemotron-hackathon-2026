# NeMoBriefing

An agentic system that collects and summarizes both official performance data (benchmarks, papers) and real user reactions to newly released AI products (models, APIs, frameworks, features).

Built for the **2026 NVIDIA Nemotron Hackathon — Track A: Creative Agentic Systems**.  
Backbone models: [Nemotron-3-Nano-30B-A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard) and [Nemotron-3-Super-120B-A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard).

---

## Description

Given a natural language query (Korean or English), the **orchestrator** — a ReAct agent powered by Nemotron-3-Super — autonomously invokes three tools to produce a report per product:

1. **`plan_query`** — asks the query-generator to extract AI product names and allocates a new `run_id`, persisting `runs/{run_id}/query.json`.
2. **`collect_evidence`** — fans out `{product, run_id}` to every collector A2A endpoint in parallel. Each collector scrapes, calls its paired validator, writes both the raw and validated JSON to `runs/{run_id}/raw/{product}/{source}.json` and `runs/{run_id}/validated/{product}/{source}.json`, and returns the validated file path.
3. **`write_report`** — delegates to the reporter agent, which reads every validated file, synthesizes a per-product report, and writes it as a pair: a markdown narrative `runs/{run_id}/report_{product}.md` and a structured JSON sidecar `runs/{run_id}/report_{product}.json`.

All inter-agent data flows through files under `runs/{run_id}/`; agents exchange paths, not payloads.

---

## Architecture

```
user query
    │
    ▼
orchestrator      (react_agent, nemotron-super, port 10000)
    │  tool: plan_query
    ▼
query-generator  (nemotron-nano, port 10001)
    │  -> runs/{run_id}/query.json  +  product list
    │
    │  tool: collect_evidence  (fans out in parallel for one product)
    ├──────┬──────┬──────┬──────┬──────┬──────┐
    ▼      ▼      ▼      ▼      ▼      ▼      ▼
┌──────────────────────────────── collector (one per source) ────────────────────────────┐
│  extractor  (LLM-less, ports 10010–10016)                                              │
│      │                                                                                 │
│      │  scrape → write raw/{product}/{source}.json                                     │
│      │  → A2A(message/send) → validator                                                │
│      ▼                                                                                 │
│  validator  (chat_completion LLM A2A, ports 10020–10026)                               │
│      │  filtered EvidenceItem list                                                     │
│      ▼                                                                                 │
│  extractor writes validated/{product}/{source}.json and returns the path               │
└────────────────────────────────────────────────────────────────────────────────────────┘
    │      │      │      │       │       │      │
    └──────┴──────┴──────┴───────┴───────┴──────┘
                               │
                               │  tool: write_report  (one call per product)
                               ▼
                         reporter  (nemotron-super, port 10002)
                               │  reads every validated file path,
                               │  writes runs/{run_id}/report_{product}.{md,json}
                               ▼
                         report file path(s) returned to the user
```

The **orchestrator agent** (port 10000) is a `react_agent` workflow powered by Nemotron-3-Super.
It autonomously drives three tools — `plan_query`, `collect_evidence`, `write_report` —
and iterates over every product returned by `plan_query`.

Each **collector** = one extractor A2A service + one validator A2A service. The
extractor is still LLM-less Python: it scrapes, writes the raw JSON file, calls
the paired validator, writes the validated JSON file, and returns the validated
path. Only `query-generator`, `validator`, `reporter`, and the `orchestrator`
use an LLM — extractor layers remain deterministic.

### Filesystem layout per run

```
runs/{run_id}/                         # run_id = YYYYMMDD-HHMMSS-{8-char uuid}
  query.json                           # {user_query, products}
  raw/{product}/{source}.json          # extractor scrape result
  validated/{product}/{source}.json    # validator filtered result
  report_{product}.md                  # reporter output — markdown narrative
  report_{product}.json                # reporter output — structured JSON sidecar
```

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
| orchestrator | 10000 | nemotron-super (react_agent) |
| query-generator | 10001 | nemotron-nano |
| reporter | 10002 | nemotron-super (custom file-based workflow) |
| extractors (arcalive–reddit) | 10010–10016 | no (scrape + file I/O + A2A call) |
| validators (arcalive–reddit) | 10020–10026 | nemotron-super (chat_completion) |

### Model Assignment

| Role | Model |
|---|---|
| query-generator | `nvidia/nemotron-3-nano-30b-a3b` |
| orchestrator, validators, reporter | `nvidia/nemotron-3-super-120b-a12b` |
| extractors | none (LLM-less Python scrape + validator delegation) |

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

Brings up all 17 A2A agents (7 extractors + 7 validators + query-generator + reporter + orchestrator) in the correct dependency order from a single shared image.

```bash
cp .env.example .env             # edit model endpoints if yours differ
docker compose up -d --build     # first run builds the shared image
docker compose ps                # wait until every service is 'healthy'
curl http://localhost:10000/.well-known/agent-card.json  # orchestrator is up

# send a query
cd agents/orchestrator && ./scripts/a2a_client.sh "GPT5와 Gemma4 비교해줘"
```

Startup order is enforced by `depends_on: condition: service_healthy`:

```
L1: 7 validators + query-generator + reporter   (talk to Brev NIM only)
L2: 7 extractors                                  (each depends on its own validator)
L3: orchestrator                                  (depends on every L1/L2 service)
```

Only the orchestrator front-end (port `10000`) is published to the host. Intra-stack traffic stays on the `ari-net` bridge via compose DNS (`http://arcalive-validator:10020`, etc.). Override the host port with `ORCHESTRATOR_HOST_PORT` in `.env`.

#### Deploy a subset of collectors

Each collector's validator+extractor pair is tagged with two compose profiles — the collector's own name and `all` — so you can start only the ones you need. `orchestrator`, `query-generator`, and `reporter` are untagged and always run.

Two `.env` variables control this and **must be kept in sync**:

| Variable | Purpose |
|---|---|
| `COMPOSE_PROFILES` | Which collector services docker compose starts. |
| `ENABLED_COLLECTORS` | Which collectors the orchestrator agent's `collect_evidence` tool fans out to. |

Valid collector names: `arcalive`, `arxiv`, `benchmark`, `geeknews`, `lobsters`, `openai`, `reddit`.

```bash
# Full stack (17 services) — default in .env.example
COMPOSE_PROFILES=all
ENABLED_COLLECTORS=arcalive,arxiv,benchmark,geeknews,lobsters,openai,reddit

# Minimal two-collector deploy
COMPOSE_PROFILES=arcalive,geeknews
ENABLED_COLLECTORS=arcalive,geeknews
```

`orchestrator.depends_on` marks each extractor with `required: false`, so any collector absent from `COMPOSE_PROFILES` is skipped rather than aborting compose. If you list a name in `ENABLED_COLLECTORS` that `collect_evidence` does not know about, config load fails fast with a `ValueError` — this is the typo guard, so a missing collector never silently drops.

### Run the full orchestrator pipeline manually

Each agent script `cd`s into its own agent directory, so without an explicit override every agent would write `runs/` under a different cwd. Export an absolute `ARI_RUNS_ROOT` (pointing at the repo-root `runs/`) in every terminal first so all agents share the same pipeline artefacts:

```bash
export ARI_RUNS_ROOT="$(git rev-parse --show-toplevel)/runs"
```

Then start all agents (each in a separate terminal with `ARI_RUNS_ROOT` exported), then call the orchestrator agent:

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

# Terminal 17 — orchestrator
cd agents/orchestrator && ./scripts/a2a_server.sh

# Send a query
cd agents/orchestrator && ./scripts/a2a_client.sh "GPT5와 Gemma4 비교해줘"
```

### Scaled test (arcalive + geeknews only)

Use `configs/config_test.yml` when running the orchestrator with only a subset of extractors:

```bash
cd agents/orchestrator && uv run nat a2a serve --config_file configs/config_test.yml
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
cd agents/{query-generator|reporter|orchestrator}

# A2A server mode
./scripts/a2a_server.sh

# Test client (requires server running)
./scripts/a2a_client.sh "<input>"

# Direct run (development — extractors, query-generator, reporter, orchestrator only)
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

The orchestrator agent's `config.yml` declares the `react_agent` workflow, its LLM, and the three tools it can call. Endpoints are configured per-tool:

```yaml
llms:
  primary_llm:
    _type: openai
    model_name: nvidia/nemotron-3-super-120b-a12b
    base_url: https://model-server-uya78rbya.brevlab.com/v1
    api_key: empty

functions:
  plan_query:
    _type: plan_query
    query_generator_url: http://localhost:10001
  collect_evidence:
    _type: collect_evidence
    collector_urls:
      - http://localhost:10010   # arcalive
      - http://localhost:10011   # arxiv
      # ...
  write_report:
    _type: write_report
    reporter_url: http://localhost:10002

workflow:
  _type: react_agent
  llm_name: primary_llm
  tool_names: [plan_query, collect_evidence, write_report]
  system_prompt: file://../prompts/system_prompt.txt
```

---

## File Structure

```
nvidia-nemotron-hackathon-2026/
├── agents/
│   ├── orchestrator/                           # ReAct orchestrator (port 10000, nemotron-super)
│   │   ├── configs/
│   │   │   ├── config.yml                      # all 7 collectors
│   │   │   └── config_test.yml                 # arcalive + geeknews only
│   │   ├── prompts/system_prompt.txt           # react_agent prompt with {tool_names}
│   │   ├── scripts/
│   │   └── src/nat_orchestrator/
│   │       ├── register.py                     # imports the 3 tool modules to trigger registration
│   │       ├── tool_plan_query.py              # query-generator + run_id allocation
│   │       ├── tool_collect_evidence.py        # parallel collector fan-out
│   │       └── tool_write_report.py            # reporter delegation
│   ├── query-generator/                        # Product name extractor (port 10001)
│   ├── reporter/                               # Evidence synthesizer → markdown report (port 10002)
│   └── collectors/                             # per-source extractor + validator pairs
│       ├── arcalive/
│       │   ├── extractor/                      # port 10010 (no LLM)
│       │   │   ├── configs/config.yml
│       │   │   ├── scripts/{a2a_server,a2a_client,run}.sh
│       │   │   ├── src/nat_extractor_arcalive/
│       │   │   │   ├── extractor.py            # scraper
│       │   │   │   ├── register.py             # scrape → write raw → validator A2A → write validated
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
│   ├── ari-core/                               # Shared schemas + a2a_client + run_paths (file-layout helpers)
│   └── validator-core/                         # Shared validator A2A client helper used by every extractor
├── runs/                                       # Per-run artefacts: query.json, raw/, validated/, report_*.md (gitignored, shared volume in Docker)
├── docker/                                     # Shared image for all 17 A2A agents
│   ├── Dockerfile                              # uv-workspace install; entrypoint reads CONFIG_FILE
│   └── entrypoint.sh                           # cd to agent dir + `nat a2a serve`
├── docker-compose.yml                          # 17 services, 3-layer depends_on graph, healthchecks, shared runs/ volume
├── .env.example                                # Brev model endpoints + ORCHESTRATOR_HOST_PORT template
├── docs/                                       # Internal reference documents
├── task-histories/                             # Branch plans and completion reports (gitignored)
├── pyproject.toml                              # uv workspace root (14 collector subpackages + orchestrator/qgen/reporter)
└── CLAUDE.md                                   # Project instructions for Claude Code
```
