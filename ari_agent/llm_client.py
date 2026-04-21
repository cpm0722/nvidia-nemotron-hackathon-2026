"""Nemotron LLM client — single entry point for all LLM calls in cli subcommands.

Supports three providers via ARI_LLM_PROVIDER env var:
  - brev     : 팀원 Brev-hosted vLLM (OpenAI-compatible, no auth) [default]
  - build    : NVIDIA Build API (integrate.api.nvidia.com/v1), needs NVIDIA_API_KEY
  - local-nim: Self-host NIM on localhost:8000/v1

Thinking-mode handling differs per provider:
  - brev (vLLM chat_template) : extra_body={"chat_template_kwargs": {"enable_thinking": False}}
  - build / local-nim (NIM)   : omit extra_body to disable; thinking is opt-in per request

Env:
  ARI_LLM_PROVIDER     — brev | build | local-nim (default: brev)
  NEMOTRON_BASE_URL    — override base URL for the selected provider
  NVIDIA_API_KEY       — required for `build` (nvapi-...)
  ARI_NEMOTRON_SUPER   — model id for Super tier (default: nvidia/nemotron-3-super-120b-a12b)
  ARI_NEMOTRON_NANO    — model id for Nano tier (default: nvidia/nemotron-3-nano-30b-a3b)
"""

from __future__ import annotations

import os
from typing import Literal

from openai import OpenAI

Tier = Literal["super", "nano"]

_PROVIDER_DEFAULTS = {
    "brev": "https://model-server-uya78rbya.brevlab.com/v1/",
    "build": "https://integrate.api.nvidia.com/v1",
    "local-nim": "http://localhost:8000/v1",
}


def _provider() -> str:
    return os.environ.get("ARI_LLM_PROVIDER", "brev").strip().lower()


def _base_url() -> str:
    override = os.environ.get("NEMOTRON_BASE_URL")
    if override:
        return override
    return _PROVIDER_DEFAULTS.get(_provider(), _PROVIDER_DEFAULTS["brev"])


def _api_key() -> str:
    # build API requires a real key; brev/local-nim tolerate dummies but need non-empty.
    return os.environ.get("NVIDIA_API_KEY") or "unused-but-required"


def _model_for(tier: Tier) -> str:
    if tier == "super":
        return os.environ.get("ARI_NEMOTRON_SUPER", "nvidia/nemotron-3-super-120b-a12b")
    return os.environ.get("ARI_NEMOTRON_NANO", "nvidia/nemotron-3-nano-30b-a3b")


def _extra_body_disable_thinking() -> dict:
    """Provider-specific knob to suppress chain-of-thought in the output stream."""
    if _provider() == "brev":
        # vLLM chat_template path (Nemotron instruction tuned with this switch)
        return {"chat_template_kwargs": {"enable_thinking": False}}
    # NIM / Build API: omitting `extra_body.thinking` keeps thinking disabled by default
    return {}


def _client() -> OpenAI:
    return OpenAI(base_url=_base_url(), api_key=_api_key())


def call_nemotron(
    system: str,
    user: str,
    tier: Tier = "super",
    temperature: float = 0.2,
    max_tokens: int = 6000,
) -> str:
    """Blocking chat completion, returns assistant message text. Raises on API error."""
    client = _client()
    resp = client.chat.completions.create(
        model=_model_for(tier),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=_extra_body_disable_thinking(),
    )
    return (resp.choices[0].message.content or "").strip()


def describe() -> dict:
    """Inspect current LLM config — used by cli `health` subcommand."""
    return {
        "provider": _provider(),
        "base_url": _base_url(),
        "super_model": _model_for("super"),
        "nano_model": _model_for("nano"),
        "api_key_present": bool(os.environ.get("NVIDIA_API_KEY")),
    }
