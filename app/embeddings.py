"""Клієнт ембедингів через Ollama (BGE-m3, 1024-вимірні вектори).

BGE-m3 — багатомовна модель (вкл. українську), не потребує префіксів
query/passage (на відміну від E5), тож той самий виклик використовується
і для документів, і для запитів.
"""
from __future__ import annotations

import httpx

from app.config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Повертає ембединги для списку текстів (батч)."""
    if not texts:
        return []
    async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=120) as client:
        resp = await client.post(
            "/api/embed",
            json={"model": settings.embed_model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
    embeddings = data.get("embeddings")
    if embeddings is None or len(embeddings) != len(texts):
        raise RuntimeError(f"Ollama повернув некоректну відповідь ембедингів: {data!r}")
    return embeddings


async def embed_query(text: str) -> list[float]:
    """Ембединг одного запиту (Ф2)."""
    result = await embed_texts([text])
    return result[0]


def to_pgvector(vec: list[float]) -> str:
    """Літерал pgvector '[a,b,c]' для параметра з приведенням `::vector`.

    Не залежить від адаптерів типів у конкретній версії драйвера.
    """
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
