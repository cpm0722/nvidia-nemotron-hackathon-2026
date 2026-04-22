# Agents

This directory contains all agents in the pipeline. Each agent is an independent A2A service managed as a member of the root-level uv workspace.

## Pipeline

```
user query
    │
    ▼
orchestrator (generates run_id)
    │
    ▼
query-generator  ──▶  products.json
    │
    ▼  (fan out per product, 7 sources in parallel)
┌────────────────────────────────────────────────┐
│  collectors/{source}/extractor  (no LLM)        │
│      scrape → scraped.json  ──A2A──▶            │
│                                                 │
│  collectors/{source}/validator  (Nemotron-Super) │
│      filter + relevance_score → validated.json  │
└────────────────────────────────────────────────┘
    │
    ▼
reporter (Nemotron-Super)
    per-product loop → report.md + report.json
```

Agents: `orchestrator`, `query-generator`, `reporter`, and `collectors/{arcalive,arxiv,benchmark,geeknews,lobsters,openai,reddit}/{extractor,validator}` — 17 A2A services in total.

## Standard Directory Structure

Collectors are nested under `agents/collectors/{source}/`; orchestrator and top-level agents sit directly under `agents/`. Layout per agent:

```
agents/{agent-name}/                     # e.g. agents/orchestrator, agents/reporter
  or
agents/collectors/{source}/{extractor|validator}/
├── configs/
│   └── config.yml          # NAT agent config: front_end, (llms,) workflow
├── prompts/                # only for agents that use an LLM (not for extractors)
│   └── system_prompt.txt
├── scripts/
│   ├── a2a_server.sh       # Start as A2A server
│   ├── a2a_client.sh       # Send test request to running server
│   └── run.sh              # Direct run (no A2A, for development)
├── src/
│   └── {package_name}/     # e.g. nat_extractor_arxiv, nat_arxiv_validator
│       ├── __init__.py
│       ├── models.py       # Pydantic I/O models
│       ├── register.py     # NAT FunctionGroup / workflow entry point
│       └── ...
├── tests/                  # optional; present only in some agents
│   ├── fixtures/
│   ├── unit/
│   └── integration/
└── pyproject.toml
```

Extractors do not invoke an LLM, so they have no `prompts/` directory and register a custom Python function as their `workflow._type`. Validators, reporter, query-generator, and orchestrator all consume `prompts/system_prompt.txt`.

## pyproject.toml Conventions

```toml
[build-system]
build-backend = "setuptools.build_meta"
requires = ["setuptools>=64"]

[tool.setuptools.packages.find]
where = ["src"]

[project]
name = "nat_{agent_name}"                 # e.g. nat_extractor_arxiv, nat_arxiv_validator, nat_reporter
version = "0.1.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "nvidia-nat[a2a]",                    # validator/reporter/qgen use [a2a,langchain]
    "ari_core",
    # agent-specific deps (validators: "validator_core", sources: requests / feedparser / ...)
]

[tool.uv.sources]
ari_core = { path = "../../../../libs/ari-core", editable = true }   # adjust depth to match the agent's nesting
validator_core = { workspace = true }     # workspace members must use { workspace = true }

[project.entry-points."nat.components"]
nat_{agent_name} = "nat_{agent_name}.register"
```

- `ari_core` is declared as an editable path source (it is also a workspace member, so `{ workspace = true }` is an equivalent alternative).
- For any workspace-member local library such as `validator_core`, you **must** use `{ workspace = true }` — declaring it with `{ path = ... }` will make `uv sync` fail.
- The `nat.components` entry point is required for NAT to discover and load the agent's `FunctionGroup` or workflow.

## config.yml Structure

### Extractor (no LLM)

```yaml
general:
  front_end:
    _type: a2a
    name: "arXiv Extractor Agent"
    description: "arXiv scrape + validator A2A call"
    host: 0.0.0.0
    port: 10011                           # extractor ports: 10010–10016

workflow:
  _type: arxiv_extractor                  # custom workflow registration name
  limit: 10
  max_text_chars: 8000
  validator_url: ${VALIDATOR_URL:-http://localhost:10021}
  validator_timeout_seconds: 180
```

### Validator / Reporter / Query-generator (uses an LLM)

```yaml
general:
  front_end:
    _type: a2a
    name: "arXiv Validator Agent"
    host: 0.0.0.0
    port: 10021                           # validator ports: 10020–10026

llms:
  primary_llm:
    _type: openai
    model_name: nvidia/nemotron-3-super-120b-a12b
    base_url: ${SUPER_MODEL_BASE_URL:-https://model-server-uya78rbya.brevlab.com/v1}
    api_key: ${SUPER_MODEL_API_KEY:-empty}
    temperature: 0.0
    max_tokens: 8192

workflow:
  _type: chat_completion                  # reporter/validator: chat_completion; qgen/orchestrator: react_agent, etc.
  llm_name: primary_llm
  system_prompt: file://../prompts/system_prompt.txt
```

Brev endpoints and API keys are injected via env vars (`SUPER_MODEL_BASE_URL`, `NANO_MODEL_BASE_URL`, `*_API_KEY`).

## Model Assignment

| Agent type | Model | Brev endpoint |
|---|---|---|
| orchestrator | Nemotron-Super (react_agent) | Super |
| query-generator | `nvidia/nemotron-3-nano-30b-a3b` | Nano |
| collectors/{source}/extractor | — (no LLM; scrape + A2A call only) | — |
| collectors/{source}/validator | `nvidia/nemotron-3-super-120b-a12b` | Super |
| reporter | `nvidia/nemotron-3-super-120b-a12b` | Super |

## Adding a New Agent

1. Choose the location:
   - New source collector → `agents/collectors/{source}/{extractor,validator}/`
   - Any other top-level agent → `agents/{agent-name}/`
2. Create the files following the Standard Directory Structure above. Under `src/nat_{agent_name}/`, add `register.py` (required), `models.py`, and any implementation modules.
3. Add `configs/config.yml` and — if the agent uses an LLM — `prompts/system_prompt.txt`.
4. Add `scripts/a2a_server.sh`, `a2a_client.sh`, and `run.sh`.
5. Register the path in the root `pyproject.toml` under `[tool.uv.workspace].members` (e.g. `agents/collectors/mynewsrc/extractor`).
6. Run `uv sync` at the repo root to update `uv.lock`.
7. Put unit tests under `tests/unit/` with fixtures in `tests/fixtures/`.

## Running an Agent

```bash
# Start as A2A server (port is fixed in the agent's config.yml)
./scripts/a2a_server.sh

# Send a test request to the running server
./scripts/a2a_client.sh "GPT-5"

# Direct run without A2A (development)
./scripts/run.sh "GPT-5"

# Check the Agent Card
curl -s http://localhost:10021/.well-known/agent.json | jq .
```

## Existing Agents (Port Map)

| Agent | Role | Source / purpose | Port |
|---|---|---|---|
| `orchestrator` | orchestrator | allocates run_id, drives the whole pipeline | 10000 |
| `query-generator` | qgen | user query → product list | 10001 |
| `reporter` | reporter | per-product report generation | 10002 |
| `collectors/arcalive/extractor` | extractor | arca.live (Korean community) | 10010 |
| `collectors/arxiv/extractor` | extractor | arXiv | 10011 |
| `collectors/benchmark/extractor` | extractor | Artificial Analysis + HF leaderboard | 10012 |
| `collectors/geeknews/extractor` | extractor | GeekNews (Korean) | 10013 |
| `collectors/lobsters/extractor` | extractor | Lobsters | 10014 |
| `collectors/openai/extractor` | extractor | OpenAI official | 10015 |
| `collectors/reddit/extractor` | extractor | Reddit | 10016 |
| `collectors/arcalive/validator` | validator | arcalive relevance filter | 10020 |
| `collectors/arxiv/validator` | validator | arxiv relevance filter | 10021 |
| `collectors/benchmark/validator` | validator | benchmark relevance filter | 10022 |
| `collectors/geeknews/validator` | validator | geeknews relevance filter | 10023 |
| `collectors/lobsters/validator` | validator | lobsters relevance filter | 10024 |
| `collectors/openai/validator` | validator | openai relevance filter | 10025 |
| `collectors/reddit/validator` | validator | reddit relevance filter | 10026 |
