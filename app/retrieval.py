"""Векторний пошук у базі знань (Ф2).

Косинусна схожість через оператор pgvector `<=>` (косинусна відстань) на
HNSW-індексі. score = 1 - distance ∈ [0, 1]. Результати нижче MIN_SCORE
відкидаються, щоб у контекст LLM не потрапляли нерелевантні чанки
(зменшення галюцинацій, підрозділ 1.6).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.db import connection
from app.embeddings import embed_query, to_pgvector
from app.metrics import retrieval_latency


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: int
    document_title: str
    source: str | None
    content: str
    score: float


async def search(
    query_embedding: list[float],
    top_k: int | None = None,
    min_score: float | None = None,
    ef_search: int = 40,
) -> list[RetrievedChunk]:
    """Повертає top-k чанків, відсортованих за спаданням косинусної схожості."""
    k = top_k or settings.top_k
    threshold = settings.min_score if min_score is None else min_score
    vec = to_pgvector(query_embedding)

    with retrieval_latency.time():
        async with connection() as conn:
            # ef_search керує точністю/швидкістю обходу HNSW на етапі запиту.
            # SET LOCAL не приймає bind-параметрів, тож через set_config(is_local=true).
            await conn.execute(
                "SELECT set_config('hnsw.ef_search', %s, true)", (str(int(ef_search)),)
            )
            rows = await (
                await conn.execute(
                    """
                    SELECT c.id,
                           d.title,
                           d.source,
                           c.content,
                           1 - (c.embedding <=> %s::vector) AS score
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.id = c.document_id
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vec, vec, k),
                )
            ).fetchall()

    result = [
        RetrievedChunk(chunk_id=r[0], document_title=r[1], source=r[2], content=r[3], score=float(r[4]))
        for r in rows
    ]
    return [c for c in result if c.score >= threshold]


async def search_text(
    query: str,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Зручний вхід: ембедить текст запиту й виконує пошук."""
    embedding = await embed_query(query)
    return await search(embedding, top_k=top_k, min_score=min_score)
