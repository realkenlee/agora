"""
LLM provider settings.

Paid `LLM_*` env wins. Free OpenRouter `:free` models cap at 50 req/day and
will sink listing drafts — do not assume that tier is enough to run the agent.
"""

from __future__ import annotations
import os


DEFAULT_OPENROUTER = "https://openrouter.ai/api/v1"


def llm_settings() -> dict:
    base_url = (os.environ.get("LLM_BASE_URL") or DEFAULT_OPENROUTER).rstrip("/")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""
    model = os.environ.get("LLM_MODEL") or ""
    vision_model = os.environ.get("VISION_MODEL") or ""
    using_openrouter = "openrouter.ai" in base_url.lower()
    explicit_paid_model = bool(model) and ":free" not in model
    paid = explicit_paid_model or (bool(api_key) and not using_openrouter)
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "vision_model": vision_model,
        "using_openrouter": using_openrouter,
        "paid": paid,
        "free_tier_note": (
            "OpenRouter :free models cap at 50 requests/day and will sink drafts. "
            "Set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, and VISION_MODEL to a paid provider."
        ),
    }


def using_paid_llm() -> bool:
    return bool(llm_settings()["paid"])
