"""
LLM-powered listing generation using Ollama (local, open-source).

Text model: qwen2.5:3b (fast structured JSON)
Vision model: moondream (tiny, photo captioning)
Both run via Ollama's OpenAI-compatible API at localhost:11434.
"""

from __future__ import annotations
import base64
import json
import os
from openai import AsyncOpenAI

_LLM_BASE_URL  = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
_LLM_API_KEY   = os.environ.get("LLM_API_KEY", "")
_TEXT_MODEL    = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
_VISION_MODEL  = os.environ.get("VISION_MODEL", "llama-3.2-11b-vision-preview")

_CATEGORIES = [
    "electronics", "electronics/phones", "electronics/laptops",
    "clothing", "furniture", "vehicles", "sports", "books",
    "tools", "garden", "toys", "other",
]

_GENERATE_SYSTEM = """You are an expert secondhand marketplace listing writer for a local buy-sell app.
Given a seller's description, write a compelling, honest listing that will attract buyers.
Include specific details like brand, model, size, color, what's included, and why the seller is selling.
Return ONLY a valid JSON object — no prose, no markdown fences, no explanation."""

_GENERATE_PROMPT = """Write a marketplace listing for this item:
"{description}"
{price_hint_line}
{location_line}
{photo_line}

Categories available: {categories}

Return this exact JSON structure:
{{
  "title": "Brand + Model + key detail, max 80 chars — NO price in title, e.g. 'Sony WH-1000XM5 Headphones — Black'",
  "description": "2-4 engaging sentences covering condition, specs, what's included, and why selling",
  "suggested_price": <fair market price as a number, e.g. 350>,
  "condition": <"new" | "like_new" | "good" | "fair" | "poor">,
  "category_id": <most specific matching category from the list>,
  "attributes": {{"brand": "...", "model": "...", "size": "...", "color": "..."}},
  "price_negotiable": <true if condition is good or below, false if new/like_new>,
  "reasoning": "One sentence explaining how you arrived at the price and condition"
}}"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=_LLM_BASE_URL, api_key=_LLM_API_KEY or "ollama")


async def generate_listing_draft(
    description: str,
    price_hint: float | None = None,
    location: str | None = None,
    photo_urls: list[str] | None = None,
) -> dict:
    """Generate a structured listing draft from a casual seller description."""
    photo_captions: list[str] = []
    if photo_urls:
        captions = await _describe_photos(photo_urls)
        photo_captions.extend(captions)

    prompt = _GENERATE_PROMPT.format(
        description=description,
        price_hint_line=f"Price in mind: ${price_hint}" if price_hint else "",
        location_line=f"Location: {location}" if location else "",
        photo_line=f"Photos show: {'; '.join(photo_captions)}" if photo_captions else "",
        categories=", ".join(_CATEGORIES),
    )

    response = await _client().chat.completions.create(
        model=_TEXT_MODEL,
        messages=[
            {"role": "system", "content": _GENERATE_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1024,
    )

    text = response.choices[0].message.content.strip()
    # Strip accidental markdown fences
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.split("```")[0].strip()

    draft = json.loads(text)
    draft["suggested_price"] = float(draft.get("suggested_price", 0))
    draft.setdefault("attributes", {})
    draft.setdefault("price_negotiable", True)
    draft.setdefault("reasoning", "")
    return draft


async def analyze_photos(base64_images: list[str]) -> str:
    """
    Describe marketplace item photos using a local vision model.
    Returns a plain-English summary for listing generation context.
    """
    if not base64_images:
        return ""

    content = []
    for b64 in base64_images[:4]:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    content.append({
        "type": "text",
        "text": "Describe the item(s) in these marketplace photos. "
                "Note condition, visible brand or model, color, any damage. One paragraph.",
    })

    response = await _client().chat.completions.create(
        model=_VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()


async def _describe_photos(urls: list[str]) -> list[str]:
    """Fetch photo URLs, encode to base64, and describe them."""
    import httpx
    captions = []
    async with httpx.AsyncClient(timeout=15) as client:
        for url in urls[:4]:
            try:
                r = await client.get(url)
                b64 = base64.b64encode(r.content).decode()
                caption = await analyze_photos([b64])
                captions.append(caption)
            except Exception:
                continue
    return captions
