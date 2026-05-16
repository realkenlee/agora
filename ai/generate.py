from __future__ import annotations
import asyncio
import base64
import json
import os
from openai import AsyncOpenAI

_LLM_BASE_URL  = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
_LLM_API_KEY   = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("LLM_API_KEY", "")
_TEXT_MODEL    = os.environ.get("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
_VISION_MODEL  = os.environ.get("VISION_MODEL", "nvidia/nemotron-nano-12b-v2-vl:free")

_TEXT_FALLBACKS = [
    "meta-llama/llama-3.2-3b-instruct:free",
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-v4-flash:free",
    "google/gemma-4-26b-a4b-it:free",
]

_CATEGORIES = [
    "electronics", "electronics/phones", "electronics/laptops",
    "clothing", "furniture", "vehicles", "sports", "books",
    "tools", "garden", "toys", "other",
]

_GENERATE_SYSTEM = """You are an expert secondhand marketplace listing writer.
Given a seller's item description plus web research context, write a compelling, accurate listing.
Use the web research to identify the brand, model, and realistic used market price.
Attributes should be the 3-5 most relevant facts for this specific item type — not a fixed template.
For shoes: size, brand, colorway. For furniture: dimensions, material. For electronics: storage, color, generation.
Return ONLY valid JSON — no prose, no markdown."""

_GENERATE_PROMPT = """Item description: "{description}"
{price_hint_line}
{location_line}
{brand_line}
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
  "reasoning": "One sentence on how you priced this and identified the brand"
}}"""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=_LLM_BASE_URL, api_key=_LLM_API_KEY or "ollama")


async def _search_context(query: str) -> str:
    """DuckDuckGo search for brand/price context. Returns snippets or empty string."""
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


def _extract_brand_candidates(vision_caption: str, search_results: list) -> tuple[list[str], str]:
    """Score brand confidence from vision + search. Returns (candidates, confidence)."""
    import re
    from collections import Counter

    NOISE = {
        "the", "a", "an", "for", "sale", "used", "new", "best", "review", "reviews",
        "price", "buy", "shop", "store", "amazon", "ebay", "walmart", "target",
        "craigslist", "vs", "and", "or", "with", "in", "on", "at", "of", "my",
        "this", "that", "good", "great", "top", "free", "shipping", "item",
        "product", "model", "listing", "second", "hand", "cheap", "sell",
        "resale", "find", "get", "available", "also", "can", "use", "its",
        "has", "have", "not", "but", "from", "like", "just", "more", "very",
        "real", "how", "what", "when", "where", "condition", "quality",
        "original", "genuine", "official", "authentic", "vintage", "classic",
        "size", "color", "black", "white", "red", "blue", "green", "pink",
        "selling", "buying", "looking", "includes", "comes", "works",
        "perfect", "excellent", "mint", "fair", "poor", "image", "photo",
        "shows", "please", "contact", "message", "offer", "make", "local",
        "cash", "payment", "delivery", "pickup", "meet", "inch", "inches",
        "marketplace", "items", "your", "their", "these", "those", "here",
        "listing", "listings", "seller", "buyer", "deal", "deals", "lot",
        "set", "bundle", "used", "brand", "brands", "type", "style", "version",
    }

    # Per-result word spread (breadth beats frequency — one result mentioning Nike 10x ≠ 4 results)
    result_appearances: Counter = Counter()
    for r in search_results:
        text = f"{r.get('title', '')} {r.get('body', '')}"
        for w in set(re.findall(r'\b[A-Z][a-z]{2,19}\b', text)):
            if w.lower() not in NOISE:
                result_appearances[w] += 1

    vision_words = re.findall(r'\b[A-Z][a-z]{2,19}\b', vision_caption)
    vision_set = {w for w in vision_words if w.lower() not in NOISE}
    vision_counter: Counter = Counter(w for w in vision_words if w.lower() not in NOISE)

    n = max(len(search_results), 1)
    scored: dict[str, float] = {}
    for word, count in result_appearances.items():
        if count < 2 and word not in vision_set:
            continue
        score = (count / n) * 10
        if word in vision_set:
            score += vision_counter.get(word, 0) * 2 + 5
        scored[word] = score

    # Vision-only strong signals (appears 2+ times in caption but not in search)
    for word, count in vision_counter.items():
        if word.lower() not in NOISE and count >= 2 and word not in scored:
            scored[word] = count * 1.5

    candidates = sorted(scored, key=scored.get, reverse=True)[:5]
    if not candidates:
        return [], "NONE"

    top_spread = result_appearances.get(candidates[0], 0)
    second_spread = result_appearances.get(candidates[1], 0) if len(candidates) > 1 else 0

    if top_spread >= max(2, n * 0.6) and second_spread < top_spread * 0.5:
        confidence = "HIGH"
    elif len(candidates) <= 2 or top_spread >= 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return candidates, confidence


async def analyze_brand(description: str, vision_caption: str) -> tuple[list[str], str]:
    """Search for brand context and score confidence. Returns (candidates, confidence)."""
    query = f"{vision_caption[:120]} {description}"[:200] if vision_caption else description
    try:
        from ddgs import DDGS
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: list(DDGS().text(f"{query} brand", max_results=4))
        )
    except Exception as e:
        print(f"[brand_search] failed: {e}")
        return [], "NONE"
    if not results:
        return [], "NONE"
    return _extract_brand_candidates(vision_caption, results)


async def generate_listing_draft(
    description: str,
    price_hint: float | None = None,
    location: str | None = None,
    photo_urls: list[str] | None = None,
    confirmed_brand: str | None = None,
) -> dict:
    photo_captions: list[str] = []
    if photo_urls:
        captions = await _describe_photos(photo_urls)
        photo_captions.extend(captions)

    # Build search query — confirmed brand anchors the query for better price/model results
    search_query = description
    if photo_captions:
        search_query = f"{photo_captions[0][:120]} {description}"[:200]
    if confirmed_brand:
        search_query = f"{confirmed_brand} {search_query}"[:200]

    search_context = await _search_context(search_query)

    prompt = _GENERATE_PROMPT.format(
        description=description,
        price_hint_line=f"Seller's asking price: ${price_hint}" if price_hint else "",
        location_line=f"Location: {location}" if location else "",
        brand_line=f"Brand (confirmed by seller — use this exactly, do not guess otherwise): {confirmed_brand}" if confirmed_brand else "",
        photo_line=f"Photo shows: {'; '.join(photo_captions)}" if photo_captions else "",
        search_line=f"Web research:\n{search_context}" if search_context else "",
        categories=", ".join(_CATEGORIES),
    )

    from openai import APIStatusError, APITimeoutError
    last_err = None
    for model in [_TEXT_MODEL] + _TEXT_FALLBACKS:
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
