"""
Semantic embeddings for listing search.

Uses sentence-transformers (local, no API cost).
Model: all-MiniLM-L6-v2 → 384-dim vectors, matches schema.sql.
"""

from __future__ import annotations
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


async def embed_text(text: str) -> list[float]:
    """Return a 384-dim embedding for a text string."""
    vec = _model().encode(text, normalize_embeddings=True)
    return vec.tolist()


async def embed_listing(title: str, description: str, category: str, attributes: dict) -> list[float]:
    """
    Compose a rich embedding for a listing.
    Includes structured attributes so agents can find items by attribute values.
    """
    attr_text = " ".join(f"{k} {v}" for k, v in attributes.items())
    text = f"{title} {category} {description} {attr_text}".strip()
    return await embed_text(text)
