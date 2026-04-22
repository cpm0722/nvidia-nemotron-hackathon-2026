"""NAT workflow: arcalive extractor — scrape, write raw, validate via validator_core, write validated.

Input (A2A message text, JSON)::

    {"product": "GPT-5", "run_id": "20260422-120000-deadbeef",
     "job_id": "<ui-job>", "event_url": "http://ui:8080/api/events/<ui-job>"}

``job_id`` and ``event_url`` are optional — they arrive only when the e2e
orchestrator was itself invoked by the browser UI, and are forwarded so this
extractor can emit its own scraping/validation progress events back to the
same chat bubble.

Output: filesystem path to the validated result JSON (a single string).

Uses validator_core.validate_items for robust parsing (orphan </think>, balanced
bracket scan, truncation detection), URL-keyed merge of relevance decisions,
and slim-payload serialization (clipped text + match-centered comment windowing).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import (
    ScrapeInput,
    emit_event,
    parse_collect_input,
    parse_envelope,
    raw_path,
    set_event_context,
    validated_path,
    write_json,
)
from validator_core import ClientConfig, validate_items

from nat_extractor_arcalive.extractor import scrape as _scrape_arcalive

SOURCE_NAME = "arcalive"


class ArcaliveExtractorConfig(FunctionBaseConfig, name="arcalive_extractor"):
    """arcalive extractor 설정 (scrape → raw write → validator_core → validated write)."""

    board: str = Field(default="alpaca")
    max_pages: int = Field(default=2)
    limit: int = Field(default=5, ge=1, le=20)
    validator_url: str = Field(default="http://localhost:10020")
    validator_timeout_seconds: int = Field(default=120, ge=10, le=600)
    validator_max_text_chars: int = Field(default=2500, ge=200, le=8000,
        description="Clip item.text before sending to validator; controls prompt size.")
    validator_min_relevance_score: float = Field(default=0.5, ge=0.0, le=1.0,
        description="Drop items whose validator relevance_score is below this.")


@register_function(config_type=ArcaliveExtractorConfig)
async def arcalive_extractor(
    config: ArcaliveExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Scrape arcalive, persist raw + validated JSON, return validated path."""

    async def collect(raw_input: str) -> str:
        env = parse_envelope(raw_input)
        set_event_context(env.event_url, env.job_id)
        try:
            product, run_id = parse_collect_input(raw_input)
        except ValueError as exc:
            await emit_event(
                agent=SOURCE_NAME,
                event_type="error",
                phase="collect",
                message=f"{SOURCE_NAME}: bad input — {exc}",
            )
            raise

        await emit_event(
            agent=SOURCE_NAME,
            event_type="start",
            phase="collect",
            message=f"{SOURCE_NAME}: scraping board '{config.board}'…",
        )

        raw_file = raw_path(run_id, product, SOURCE_NAME)
        validated_file = validated_path(run_id, product, SOURCE_NAME)

        scrape_input = ScrapeInput(
            query=product,
            limit=config.limit,
            extra={
                "board": config.board,
                "max_pages": config.max_pages,
            }
        )
        try:
            result = await asyncio.to_thread(_scrape_arcalive, scrape_input)
        except Exception as exc:
            await emit_event(
                agent=SOURCE_NAME,
                event_type="error",
                phase="collect",
                message=f"{SOURCE_NAME}: scrape failed — {exc}",
            )
            raise
        write_json(raw_file, result.model_dump())

        scraped_count = len(result.items) if result.items else 0
        await emit_event(
            agent=SOURCE_NAME,
            event_type="progress",
            phase="collect",
            message=(
                f"{SOURCE_NAME}: {scraped_count} items scraped, validating…"
                if scraped_count
                else f"{SOURCE_NAME}: nothing to validate (empty scrape)"
            ),
            data={"scraped": scraped_count},
        )

        validated_count = scraped_count
        if result.ok and result.items:
            client_config = ClientConfig(
                url=config.validator_url,
                timeout_seconds=config.validator_timeout_seconds,
                max_text_chars=config.validator_max_text_chars,
                min_relevance_score=config.validator_min_relevance_score,
            )
            vresult = await asyncio.to_thread(
                validate_items, client_config, product, result.items
            )
            result.items = vresult.items
            validated_count = len(vresult.items)
            if vresult.status not in ("ok", "no_data"):
                result.error = (
                    f"validator={vresult.status}; "
                    f"kept={vresult.kept}/{vresult.total}; {vresult.note}"
                )

        write_json(validated_file, result.model_dump())
        await emit_event(
            agent=SOURCE_NAME,
            event_type="complete",
            phase="collect",
            message=f"{SOURCE_NAME}: {validated_count}/{scraped_count} validated",
            data={"scraped": scraped_count, "validated": validated_count},
        )
        return str(validated_file)

    yield FunctionInfo.from_fn(
        fn=collect,
        description=(
            "Scrape arcalive for an AI product, validate via validator_core, persist "
            "both raw and validated JSON under runs/{run_id}/, return validated path."
        ),
    )
