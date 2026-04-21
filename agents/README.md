# Agents

This directory contains all agents in the pipeline. Each agent is an independent A2A service managed as a member of the root-level uv workspace.

## Pipeline

```
user query → query-generator → [extractor + validator] × N (parallel) → aggregator
```

## Standard Directory Structure

Every agent must follow this layout:

```
agents/{agent-name}/
├── configs/
│   └── config.yml          # NAT agent config: LLM, function groups, workflow
├── prompts/
│   └── system_prompt.txt   # System prompt for the ReAct agent
├── scripts/
│   ├── a2a_server.sh       # Start the agent as an A2A server
│   ├── a2a_client.sh       # Send a test request to the running A2A server
│   └── run.sh              # Run the agent directly (no A2A, for development)
├── src/
│   └── {package_name}/
│       ├── __init__.py
│       ├── models.py       # Pydantic I/O models
│       ├── register.py     # NAT FunctionGroup registration (entry point)
│       └── ...             # Agent-specific implementation modules
├── tests/
│   ├── __init__.py
│   ├── fixtures/           # Static snapshots for unit tests
│   ├── unit/               # Unit tests (no external calls)
│   └── integration/        # Integration tests (marked, opt-in)
└── pyproject.toml
```

## pyproject.toml Conventions

```toml
[project]
name = "nat_{agent_name}"               # e.g. nat_extractor_arcalive
version = "0.1.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "nvidia-nat[a2a,langchain]",
    # agent-specific deps...
]

[project.entry-points."nat.components"]
nat_{agent_name} = "nat_{agent_name}.register"
```

The `nat.components` entry point is required for NAT to discover and load the agent's `FunctionGroup`.

## config.yml Structure

```yaml
general:
  front_end:
    _type: a2a
    name: "{Source} Extractor Agent"
    host: 0.0.0.0
    port: 10000          # each agent uses a unique port

llms:
  primary_llm:
    _type: openai
    model_name: nvidia/nemotron-3-nano-30b-a3b     # extractors use nemotron-nano
    base_url: https://<model-server-url>/v1
    api_key: empty
    temperature: 0.0
    max_tokens: 4096

function_groups:
  {source}_scraper:
    _type: {source}_scraper
    # source-specific config fields...

workflow:
  _type: react_agent
  llm_name: primary_llm
  tool_names:
    - {source}_scraper__search_posts
  system_prompt: file://../prompts/system_prompt.txt
  verbose: true
  retry_agent_response_parsing_errors: true
  parse_agent_response_max_retries: 3
```

## Model Assignment

| Agent type | Model |
|---|---|
| query-generator | `nvidia/nemotron-3-nano` |
| extractor | `nvidia/nemotron-3-nano` |
| validator | `nvidia/nemotron-3-super-120b-a12b` |
| aggregator | `nvidia/nemotron-3-super-120b-a12b` |

## Adding a New Agent

1. Create `agents/{agent-name}/` following the structure above.
2. Implement `models.py`, `register.py`, and any agent-specific modules under `src/nat_{agent_name}/`.
3. Write `configs/config.yml` and `prompts/system_prompt.txt`.
4. Add shell scripts under `scripts/`.
5. Register the new member in the root `pyproject.toml`:
   ```toml
   [tool.uv.workspace]
   members = [
       "agents/extractor-arcalive",
       "agents/{agent-name}",   # add here
   ]
   ```
6. Run `uv sync` at the project root to update `uv.lock`.
7. Write unit tests under `tests/unit/` using fixtures in `tests/fixtures/`.

## Running an Agent

```bash
# Start as A2A server
./scripts/a2a_server.sh

# Send a test request to the running server
./scripts/a2a_client.sh "GPT-5"

# Run directly without A2A (development)
./scripts/run.sh "GPT-5"
```

## Existing Agents

| Agent | Role | Source | Port |
|---|---|---|---|
| `extractor-arcalive` | extractor | [arca.live](https://arca.live) — Korean community | 10000 |
