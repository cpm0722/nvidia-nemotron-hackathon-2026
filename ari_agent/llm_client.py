"""Nemotron LLM client — single entry point for all LLM calls in cli subcommands.

Supports four providers via ARI_LLM_PROVIDER env var:
  - brev     : 팀원 Brev-hosted vLLM (Nano + Super 각 별도 endpoint, no auth) [default]
  - build    : NVIDIA Build API (integrate.api.nvidia.com/v1), needs NVIDIA_API_KEY
  - local-nim: Self-host NIM on localhost:8000/v1 (Nano/Super 같은 포트)
  - friendli : Friendli Serverless (OpenAI-compatible w/ auth headers; Nemotron 미호스팅
               이므로 기본 tier→model 매핑은 Llama/Qwen 계열로 대체)

Thinking-mode handling differs per provider:
  - brev (vLLM chat_template) : extra_body={"chat_template_kwargs": {"enable_thinking": False}}
  - build / local-nim (NIM)   : omit extra_body (thinking is opt-in per request)
  - friendli                  : omit extra_body (model-specific)

Env:
  ARI_LLM_PROVIDER          brev | build | local-nim | friendli (default: brev)
  NEMOTRON_BASE_URL         override base URL (applies to both tiers — use for local-nim only)
  NEMOTRON_SUPER_BASE_URL   override Super tier only (brev에서 기본 분리됨)
  NEMOTRON_NANO_BASE_URL    override Nano tier only
  NVIDIA_API_KEY            required for `build` (nvapi-...)
  FRIENDLI_API_KEY          required for `friendli`
  FRIENDLI_TEAM_ID          required for `friendli`
  ARI_NEMOTRON_SUPER        Super tier model id (default: nvidia/nemotron-3-super-120b-a12b)
  ARI_NEMOTRON_NANO         Nano tier model id (default: nvidia/nemotron-3-nano-30b-a3b)
  ARI_FRIENDLI_SUPER        Friendli용 Super tier model (default: Qwen/Qwen3-235B-A22B-Instruct-2507)
  ARI_FRIENDLI_NANO         Friendli용 Nano tier model (default: meta-llama-3.3-70b-instruct)
"""

from __future__ import annotations

import os
from typing import Literal

from openai import OpenAI

Tier = Literal["super", "nano"]


# --- per-provider endpoints ---

_BREV_ENDPOINTS = {
    "super": "https://model-server-uya78rbya.brevlab.com/v1",
    "nano":  "https://model-server-4dfr8gv78.brevlab.com/v1",
}
_BUILD_ENDPOINT = "https://integrate.api.nvidia.com/v1"
_LOCAL_NIM_ENDPOINT = "http://localhost:8000/v1"
_FRIENDLI_ENDPOINT = "https://api.friendli.ai/serverless/v1"


def _provider() -> str:
    return os.environ.get("ARI_LLM_PROVIDER", "brev").strip().lower()


def _base_url(tier: Tier) -> str:
    # Highest-priority override: tier-specific env var
    tier_override = os.environ.get(f"NEMOTRON_{tier.upper()}_BASE_URL")
    if tier_override:
        return tier_override
    # Next: single-endpoint override (useful for local-nim)
    single_override = os.environ.get("NEMOTRON_BASE_URL")
    if single_override:
        return single_override

    prov = _provider()
    if prov == "brev":
        return _BREV_ENDPOINTS[tier]
    if prov == "build":
        return _BUILD_ENDPOINT
    if prov == "local-nim":
        return _LOCAL_NIM_ENDPOINT
    if prov == "friendli":
        return _FRIENDLI_ENDPOINT
    return _BREV_ENDPOINTS[tier]  # fall back to brev default


def _api_key() -> str:
    prov = _provider()
    if prov == "build":
        return os.environ.get("NVIDIA_API_KEY") or "missing-NVIDIA_API_KEY"
    if prov == "friendli":
        return os.environ.get("FRIENDLI_API_KEY") or "missing-FRIENDLI_API_KEY"
    # brev / local-nim accept empty but OpenAI SDK requires truthy string
    return "empty"


def _default_headers() -> dict[str, str] | None:
    if _provider() == "friendli":
        team = os.environ.get("FRIENDLI_TEAM_ID")
        if team:
            return {"X-Friendli-Team": team}
    return None


def _model_for(tier: Tier) -> str:
    prov = _provider()
    if prov == "friendli":
        if tier == "super":
            return os.environ.get("ARI_FRIENDLI_SUPER", "Qwen/Qwen3-235B-A22B-Instruct-2507")
        return os.environ.get("ARI_FRIENDLI_NANO", "meta-llama-3.3-70b-instruct")
    # brev / build / local-nim → Nemotron
    if tier == "super":
        return os.environ.get("ARI_NEMOTRON_SUPER", "nvidia/nemotron-3-super-120b-a12b")
    # Brev Nano endpoint exposes model id as `nvidia/nemotron-3-nano` (not -30b-a3b).
    # Build API/NIM container keep the full id. Use short id as default — it works on Brev
    # and `ARI_NEMOTRON_NANO=nvidia/nemotron-3-nano-30b-a3b` can override for build/NIM.
    default_nano = "nvidia/nemotron-3-nano" if prov == "brev" else "nvidia/nemotron-3-nano-30b-a3b"
    return os.environ.get("ARI_NEMOTRON_NANO", default_nano)


def _extra_body_disable_thinking() -> dict:
    """Provider-specific knob to suppress chain-of-thought in the output stream."""
    if _provider() == "brev":
        # Brev vLLM uses Nemotron chat template with this switch
        return {"chat_template_kwargs": {"enable_thinking": False}}
    # NIM / Build API / Friendli: omit — thinking off by default
    return {}


def _client(tier: Tier) -> OpenAI:
    kwargs = {"base_url": _base_url(tier), "api_key": _api_key()}
    headers = _default_headers()
    if headers:
        kwargs["default_headers"] = headers
    return OpenAI(**kwargs)


def call_nemotron(
    system: str,
    user: str,
    tier: Tier = "super",
    temperature: float = 0.2,
    max_tokens: int = 6000,
) -> str:
    """Blocking chat completion, returns assistant message text. Raises on API error."""
    client = _client(tier)
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
        "super_base_url": _base_url("super"),
        "nano_base_url": _base_url("nano"),
        "super_model": _model_for("super"),
        "nano_model": _model_for("nano"),
        "api_key_source": (
            "NVIDIA_API_KEY" if _provider() == "build"
            else "FRIENDLI_API_KEY" if _provider() == "friendli"
            else "n/a (empty)"
        ),
        "api_key_present": bool(
            os.environ.get("NVIDIA_API_KEY")
            if _provider() == "build"
            else os.environ.get("FRIENDLI_API_KEY")
            if _provider() == "friendli"
            else True
        ),
    }
