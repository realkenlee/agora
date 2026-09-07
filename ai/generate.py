from __future__ import annotations
import asyncio
import base64
import json
import httpx
from openai import AsyncOpenAI

from ai.config import llm_settings, using_paid_llm


_settings = llm_settings()
_LLM_BASE_URL  = _settings["base_url"]
_LLM_API_KEY   = _settings["api_key"]
_TEXT_MODEL    = _settings["model"]
_VISION_MODEL  = _settings["vision_model"]

# Seed fallbacks — refreshed dynamically at startup via refresh_free_models()
_TEXT_FALLBACKS: list[str] = [
    "deepseek/deepseek-v4-flash:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen3-coder:free",
    "google/gemma-4-26b-a4b-it:free",
]
_VISION_FALLBACKS: list[str] = [
    "nvidia/nemotron-nano-12b-v2-vl:free",
]


async def refresh_free_models() -> None:
    """Query OpenRouter for currently available free models and update the lists.

    Skipped when paid LLM_* env is set — free :free models cap at 50/day
    and will sink drafts if the agent keeps using them.
    """
    global _TEXT_MODEL, _VISION_MODEL, _TEXT_FALLBACKS, _VISION_FALLBACKS
    if using_paid_llm():
        print(
            f"[models] paid LLM configured base={_LLM_BASE_URL} "
            f"text={_TEXT_MODEL or '(provider default)'} vision={_VISION_MODEL or '(none)'}"
        )
        return
    if not _LLM_API_KEY or "openrouter" not in _LLM_BASE_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{_LLM_BASE_URL.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {_LLM_API_KEY}"},
            )
            models = r.json().get("data", [])
        free_text = [
            m["id"] for m in models
            if ":free" in m["id"]
            and m.get("context_length", 0) >= 4096
            and "vl" not in m["id"] and "vision" not in m["id"]
        ]
        free_vision = [
            m["id"] for m in models
            if ":free" in m["id"]
            and ("vl" in m["id"] or "vision" in m["id"])
        ]
        if free_text:
            _TEXT_FALLBACKS = free_text[:8]
            if not _TEXT_MODEL:
                _TEXT_MODEL = free_text[0]
        if free_vision:
            _VISION_FALLBACKS = free_vision[:4]
            if not _VISION_MODEL:
                _VISION_MODEL = free_vision[0]
        print(f"[models] text={_TEXT_MODEL} vision={_VISION_MODEL} fallbacks={len(_TEXT_FALLBACKS)}")
    except Exception as e:
        print(f"[models] refresh failed: {e} — using seed list")

_CATEGORIES = [
    "electronics", "electronics/phones", "electronics/laptops",
    "clothing", "furniture", "vehicles", "sports", "books",
    "tools", "garden", "toys", "other",
]

_GENERATE_SYSTEM = """You are an expert secondhand marketplace listing writer.
Given a seller's item description and photo analysis, write a compelling, accurate listing.
Identify the brand from the photo description — read visible logos, text, and distinctive design cues.
Use web research to validate the model and find realistic used market prices.
Attributes should be the 3-5 most relevant facts for this specific item type — not a fixed template.
For shoes: size, brand, colorway. For furniture: dimensions, material. For electronics: storage, color, generation.
Return ONLY valid JSON — no prose, no markdown."""

_GENERATE_PROMPT = """Item description: "{description}"
{price_hint_line}
{location_line}
{photo_line}
{search_line}

Categories: {categories}

Return this JSON:
{{
  "title": "Concise title with brand + key detail, max 80 chars, no price",
  "description": "2-4 sentences: condition, key specs, what's included, why selling",
  "suggested_price": <used market price as number — use web research if available, else estimate conservatively>,
  "condition": <"new"|"like_new"|"good"|"fair"|"poor">,
  "category_id": <best matching category>,
  "attributes": {{"<relevant_key>": "<value>", ...}},
  "price_negotiable": <true if condition good or below>,
  "price_confidence": <"high" if web research confirms price, "medium" if estimated from similar items, "low" if guessing>,
  "reasoning": "One sentence on how you priced this and identified the brand"
}}"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=_LLM_BASE_URL, api_key=_LLM_API_KEY or "ollama")



async def _search_context(query: str) -> str:
    """DuckDuckGo search for used price context. Returns snippets or empty string."""
    try:
        from ddgs import DDGS
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: list(DDGS().text(f"{query} used price resale", max_results=4))
        )
        if not results:
            return ""
        snippets = [f"- {r['title']}: {r['body'][:200]}" for r in results if r.get('body')]
        return "\n".join(snippets[:3])
    except Exception as e:
        print(f"[search] failed: {e}")
        return ""


async def generate_listing_draft(
    description: str,
    price_hint: float | None = None,
    location: str | None = None,
    photo_urls: list[str] | None = None,
) -> dict:
    photo_captions: list[str] = []
    if photo_urls:
        captions = await _describe_photos(photo_urls)
        photo_captions.extend(captions)

    search_query = description
    if photo_captions:
        search_query = f"{photo_captions[0][:120]} {description}"[:200]

    search_context = await _search_context(search_query)

    prompt = _GENERATE_PROMPT.format(
        description=description,
        price_hint_line=f"Seller's asking price: ${price_hint}" if price_hint else "",
        location_line=f"Location: {location}" if location else "",
        photo_line=f"Photo shows: {'; '.join(photo_captions)}" if photo_captions else "",
        search_line=f"Web research:\n{search_context}" if search_context else "",
        categories=", ".join(_CATEGORIES),
    )

    from openai import APIStatusError, APITimeoutError
    last_err = None
    if using_paid_llm():
        models_to_try = [m for m in [_TEXT_MODEL] if m]
        if not models_to_try:
            raise ValueError(
                "Paid LLM_* is configured but LLM_MODEL is empty. "
                "Set LLM_MODEL (and VISION_MODEL) — do not fall back to OpenRouter :free."
            )
    else:
        models_to_try = [m for m in ([_TEXT_MODEL] + _TEXT_FALLBACKS) if m]
    for model in models_to_try:
        try:
            response = await _client().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _GENERATE_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
                timeout=25,
            )
            text = (response.choices[0].message.content or "").strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.split("```")[0].strip()
            if "{" in text and "}" in text:
                text = text[text.index("{"):text.rindex("}")+1]
            draft = json.loads(text)
            break
        except (APIStatusError, APITimeoutError, ValueError, json.JSONDecodeError) as e:
            last_err = e
            continue
    else:
        raise last_err or ValueError("All models failed")

    draft["suggested_price"] = float(draft.get("suggested_price", 0))
    draft.setdefault("price_negotiable", True)
    draft.setdefault("price_confidence", "medium")
    draft.setdefault("reasoning", "")
    cat = draft.get("category_id", "other")
    if not isinstance(cat, str) or cat not in _CATEGORIES:
        draft["category_id"] = "other"
    raw_attrs = draft.get("attributes") or {}
    draft["attributes"] = {
        k: str(v) for k, v in raw_attrs.items()
        if v and str(v).lower() not in ("unknown", "unspecified", "n/a", "")
    }
    return draft


async def analyze_photos(base64_images: list[str]) -> str:
    """Describe marketplace item photos using vision model."""
    if not base64_images:
        return ""
    if not _VISION_MODEL:
        raise ValueError(
            "VISION_MODEL is not set. Free OpenRouter vision models cap at 50/day; "
            "set VISION_MODEL on a paid LLM_* provider."
        )
    content = []
    for b64 in base64_images[:4]:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    content.append({
        "type": "text",
        "text": "Describe this item for a marketplace listing. "
                "Identify brand, model, color, condition, any visible damage or wear. "
                "Be specific — read any visible text, logos, labels. One paragraph.",
    })
    response = await _client().chat.completions.create(
        model=_VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=400,
        timeout=20,
    )
    return response.choices[0].message.content.strip()


async def _describe_photos(urls: list[str]) -> list[str]:
    import httpx
    captions = []
    async with httpx.AsyncClient(timeout=15) as client:
        for url in urls[:4]:
            try:
                if url.startswith("data:"):
                    b64 = url.split(",", 1)[1]
                else:
                    r = await client.get(url)
                    b64 = base64.b64encode(r.content).decode()
                caption = await analyze_photos([b64])
                captions.append(caption)
            except Exception:
                continue
    return captions
