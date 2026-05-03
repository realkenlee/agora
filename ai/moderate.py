"""
Content moderation using a local LLM via Ollama.

Fast keyword pre-check first, then LLM for ambiguous cases.
"""

from __future__ import annotations
import json
import os
from openai import AsyncOpenAI

_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
_LLM_API_KEY  = os.environ.get("LLM_API_KEY", "")
_TEXT_MODEL   = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")

_SYSTEM = """You are a marketplace content moderator. Evaluate listings quickly and accurately.
Return ONLY valid JSON — no prose, no markdown fences."""

_PROHIBITED = """
- Weapons, firearms, ammunition
- Illegal drugs or drug paraphernalia
- Stolen goods (suspiciously vague provenance + very low price)
- Adult content
- Live animals
- Hazardous materials
- Counterfeit items (fake brand claims)
"""

_PROMPT = """Evaluate this marketplace listing:

Title: {title}
Description: {description}
Category: {category}

Prohibited:{prohibited}

Return JSON:
{{
  "allowed": <true|false>,
  "reason": "brief reason if rejected, empty string if allowed",
  "flags": ["list", "of", "concern", "tags"],
  "confidence": <0.0-1.0>
}}"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=_LLM_BASE_URL, api_key=_LLM_API_KEY or "ollama")


async def moderate_listing(title: str, description: str, category: str | None) -> dict:
    quick = _quick_check(title, description)
    if quick:
        return quick

    response = await _client().chat.completions.create(
        model=_TEXT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _PROMPT.format(
                title=title, description=description,
                category=category or "unspecified", prohibited=_PROHIBITED,
            )},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=256,
    )

    text = response.choices[0].message.content.strip()
    try:
        return json.loads(text)
    except Exception:
        return {"allowed": True, "reason": "", "flags": ["parse_error"], "confidence": 0.5}


def _quick_check(title: str, description: str) -> dict | None:
    combined = (title + " " + description).lower()
    blocked = ["gun", "firearm", "pistol", "rifle", "ammo", "cocaine",
               "heroin", "meth", "fentanyl", "ssn ", "social security"]
    for kw in blocked:
        if kw in combined:
            return {
                "allowed": False,
                "reason": f"Listing contains prohibited content ({kw})",
                "flags": ["prohibited_keyword"],
                "confidence": 0.99,
            }
    return None
