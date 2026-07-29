"""
LLM factory for MUPO Sales Team.

Primary: xAI Grok via OpenAI-compatible API (https://api.x.ai/v1)
Fallback: Anthropic or OpenAI when configured.

CrewAI uses litellm-style model strings; we also expose a raw OpenAI client
for tools that need direct completions outside CrewAI.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from openai import OpenAI

from mupo_sales.config import get_settings, load_yaml_config

logger = logging.getLogger(__name__)


def _crew_llm_kwargs() -> dict[str, Any]:
    """Build kwargs for crewai.LLM."""
    s = get_settings()
    yaml_llm = load_yaml_config().get("llm", {}).get("primary", {})
    model = yaml_llm.get("model") or s.xai_model
    temperature = float(yaml_llm.get("temperature", 0.4))
    max_tokens = int(yaml_llm.get("max_tokens", 4096))

    if not s.xai_api_key:
        logger.warning(
            "XAI_API_KEY is empty — CrewAI calls will fail until set. "
            "Use dry-run demo mode or add key to .env"
        )

    # CrewAI / litellm: use openai/ prefix with custom base for xAI
    return {
        "model": f"openai/{model}",
        "api_key": s.xai_api_key or "missing-key",
        "base_url": s.xai_base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


@lru_cache
def get_crew_llm():
    """
    Return a CrewAI LLM instance pointed at xAI Grok.

    Falls back to a simple mock-compatible object only if crewai is unavailable
    (import deferred so unit tests without crewai can still load modules).
    """
    try:
        from crewai import LLM
    except ImportError as e:
        raise ImportError(
            "crewai is required. Install with: pip install -r requirements.txt"
        ) from e

    kwargs = _crew_llm_kwargs()
    logger.info("Initializing CrewAI LLM model=%s base=%s", kwargs["model"], kwargs["base_url"])
    return LLM(**kwargs)


def get_openai_client() -> OpenAI:
    """Direct OpenAI-compatible client for xAI (tools, one-off completions)."""
    s = get_settings()
    return OpenAI(api_key=s.xai_api_key or "missing-key", base_url=s.xai_base_url)


def complete(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 2048,
) -> str:
    """
    Simple chat completion via xAI.
    Used by tools and non-CrewAI paths.
    """
    s = get_settings()
    client = get_openai_client()
    yaml_llm = load_yaml_config().get("llm", {}).get("primary", {})
    temp = temperature if temperature is not None else float(yaml_llm.get("temperature", 0.4))

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = client.chat.completions.create(
            model=s.xai_model,
            messages=messages,
            temperature=temp,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        # Optional fallback
        if s.fallback_provider == "openai" and s.openai_api_key:
            logger.warning("xAI failed (%s); trying OpenAI fallback", e)
            fb = OpenAI(api_key=s.openai_api_key)
            resp = fb.chat.completions.create(
                model=s.fallback_model if "gpt" in s.fallback_model else "gpt-4o",
                messages=messages,
                temperature=temp,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        if s.fallback_provider == "anthropic" and s.anthropic_api_key:
            logger.warning("xAI failed (%s); Anthropic fallback not wired in MVP — re-raise", e)
        raise
