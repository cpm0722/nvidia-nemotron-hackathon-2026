"""NAT tool: collect_evidence.

Fans out a ``{product, run_id}`` message to every *enabled* collector A2A
endpoint in parallel. Each collector (extractor) internally scrapes, calls
its paired validator, persists both raw and validated JSON files under
``runs/{run_id}/``, and returns the validated file path as its response.

The tool aggregates those path strings into JSON
``{"run_id", "product", "paths"}`` for the orchestrator LLM. Individual
collector failures are silently dropped (best-effort) so one dead source
does not stop a run.

``collector_urls`` is a ``name -> url`` map of every known collector, while
``enabled_collectors`` selects the subset to call at runtime. This lets
docker compose ``profiles`` and the e2e agent share a single list so a
deploy-time subset (e.g. ``ENABLED_COLLECTORS=arcalive,geeknews``) only
starts those collectors *and* only routes evidence calls to them.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

from pydantic import BaseModel, Field, field_validator, model_validator

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import a2a_send


DEFAULT_COLLECTOR_URLS: dict[str, str] = {
    "arcalive": "http://localhost:10010",
    "arxiv": "http://localhost:10011",
    "benchmark": "http://localhost:10012",
    "geeknews": "http://localhost:10013",
    "lobsters": "http://localhost:10014",
    "openai": "http://localhost:10015",
    "reddit": "http://localhost:10016",
}


class CollectEvidenceConfig(FunctionBaseConfig, name="collect_evidence"):
    """collect_evidence tool config.

    Args:
        collector_urls: ``name -> A2A URL`` map of every known collector
            (extractor). The map is the universe of possible collectors; the
            actually-called subset is selected by ``enabled_collectors``.
        enabled_collectors: Names of collectors to invoke on each run. Must
            all be keys of ``collector_urls`` — unknown names raise at config
            load so a typo fails fast instead of silently skipping a source.
            Accepts a comma-separated string (NAT env interpolation delivers
            ``ENABLED_COLLECTORS=a,b,c`` as a string), which is parsed to a
            list.
        timeout_seconds: Per-collector HTTP timeout. Collectors scrape, then
            call an LLM validator, so 180–300s is typical.
    """

    collector_urls: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_COLLECTOR_URLS)
    )
    enabled_collectors: list[str] = Field(
        default_factory=lambda: list(DEFAULT_COLLECTOR_URLS.keys())
    )
    timeout_seconds: int = Field(default=300, ge=30, le=1200)

    @field_validator("enabled_collectors", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        # NAT env interpolation feeds `ENABLED_COLLECTORS=arcalive,geeknews`
        # in as a single string. Split it here so downstream code always
        # sees a list.
        if isinstance(value, str):
            return [name.strip() for name in value.split(",") if name.strip()]
        return value

    @model_validator(mode="after")
    def _check_enabled_subset(self) -> "CollectEvidenceConfig":
        unknown = [
            name for name in self.enabled_collectors if name not in self.collector_urls
        ]
        if unknown:
            raise ValueError(
                f"enabled_collectors contains names missing from collector_urls: "
                f"{unknown}. Known collectors: {sorted(self.collector_urls)}"
            )
        return self


class CollectEvidenceInput(BaseModel):
    """Input schema exposed to the react_agent."""

    run_id: str = Field(description="The run_id returned by plan_query.")
    product: str = Field(
        description="AI product/model name to collect evidence for (one name per call)."
    )


@register_function(config_type=CollectEvidenceConfig)
async def collect_evidence(
    config: CollectEvidenceConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Register the collect_evidence tool."""

    async def _call(url: str, message: str) -> str | None:
        try:
            return await asyncio.to_thread(
                a2a_send, url, message, config.timeout_seconds
            )
        except Exception:
            return None

    async def run(req: CollectEvidenceInput) -> str:
        message = json.dumps(
            {"product": req.product, "run_id": req.run_id}, ensure_ascii=False
        )
        active_urls = [
            config.collector_urls[name] for name in config.enabled_collectors
        ]
        results = await asyncio.gather(
            *[_call(url, message) for url in active_urls]
        )
        paths = [r.strip() for r in results if r and r.strip()]
        return json.dumps(
            {"run_id": req.run_id, "product": req.product, "paths": paths},
            ensure_ascii=False,
        )

    yield FunctionInfo.from_fn(
        fn=run,
        description=(
            "Run all enabled collector agents in parallel for an AI product. Each "
            "collector writes raw + validated JSON files under runs/{run_id}/ and "
            "returns the validated file path. Returns JSON {run_id, product, paths} "
            "with the list of validated file paths."
        ),
    )
