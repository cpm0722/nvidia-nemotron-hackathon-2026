from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import requests
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig
from pydantic import Field


class ValidatorCallerConfig(FunctionGroupBaseConfig, name="validator_caller"):
    """Config for the validator_caller function group.

    Provides the `validate` tool to extractor agents, forwarding scraped data
    to a source-specific validator A2A server for relevance filtering.
    """

    url: str = Field(default="http://localhost:10100")
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    include: list[str] = Field(default_factory=lambda: ["validate"])


def _a2a_send(url: str, message: str, timeout: int) -> str:
    """Send a message to an A2A server via message/send and return the text response.

    Handles both Task-shaped responses (with artifacts[]) and Message-shaped responses
    (with parts[] directly). Wire format uses camelCase per A2A v0.3 spec.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
            },
        },
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", {})
    artifacts = result.get("artifacts", [])
    if artifacts:
        parts = artifacts[0].get("parts", [])
        return parts[0].get("text", "") if parts else ""
    parts = result.get("parts", [])
    return parts[0].get("text", "") if parts else ""


@register_function_group(config_type=ValidatorCallerConfig)
async def validator_caller_group(config: ValidatorCallerConfig, _builder: Any):
    """Function group providing the `validate` tool for extractor agents."""
    group = FunctionGroup(config=config)

    async def validate(combined: str) -> str:
        """Filter scraped items for relevance to the queried product.

        Args:
            combined: "<product_name>|||<scraped_json>" — the product name and
                      the exact JSON string from the previous scraper observation.

        Returns:
            Filtered ScrapeResult JSON string, same schema as input.
            Falls back to the original scraped_json if the validator fails.
        """
        if "|||" in combined:
            product_name, scraped_json = combined.split("|||", 1)
            product_name = product_name.strip()
            scraped_json = scraped_json.strip()
        else:
            product_name = ""
            scraped_json = combined.strip()

        message = f"Product: {product_name}\n\nScraped data:\n{scraped_json}"
        try:
            result_text = await asyncio.to_thread(
                _a2a_send, config.url, message, config.timeout_seconds
            )
            json.loads(result_text)
            return result_text
        except Exception:
            return scraped_json

    group.add_function(name="validate", fn=validate, description=validate.__doc__)
    yield group
