"""Доступ до журналу запитів (таблиці requests / request_sources).

Відокремлює SQL від роутів API та воркера черги.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.db import connection
from app.retrieval import RetrievedChunk


@dataclass(slots=True)
class RequestRecord:
    id: int
    status: str
    raw_text: str
    answer: str | None
    latency_ms: int | None
    created_at: datetime
    sources: list["SourceRecord"]


@dataclass(slots=True)
class SourceRecord:
    chunk_id: int
    document_title: str
    source: str | None
    rank: int
    score: float
    snippet: str


async def create_request(
    raw_text: str,
    external_id: str | None = None,
    anonymized_text: str | None = None,
) -> tuple[int, datetime]:
    """Створює запис запиту у статусі pending (Ф1). Повертає (id, created_at)."""
    async with connection() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO requests (raw_text, external_id, anonymized_text) "
                "VALUES (%s, %s, %s) RETURNING id, created_at",
                (raw_text, external_id, anonymized_text),
            )
        ).fetchone()
    return row[0], row[1]


async def mark_processing(request_id: int) -> None:
    async with connection() as conn:
        await conn.execute(
            "UPDATE requests SET status = 'processing' WHERE id = %s", (request_id,)
        )


async def save_result(
    request_id: int,
    answer: str,
    sources: list[RetrievedChunk],
    latency_ms: int,
) -> None:
    """Зберігає відповідь, час обробки і використані джерела (трасування Ф3)."""
    async with connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE requests SET status='done', answer=%s, latency_ms=%s WHERE id=%s",
                (answer, latency_ms, request_id),
            )
            await conn.execute(
                "DELETE FROM request_sources WHERE request_id = %s", (request_id,)
            )
            async with conn.cursor() as cur:
                for rank, ch in enumerate(sources, start=1):
                    await cur.execute(
                        "INSERT INTO request_sources (request_id, chunk_id, rank, score) "
                        "VALUES (%s, %s, %s, %s)",
                        (request_id, ch.chunk_id, rank, ch.score),
                    )


async def mark_failed(request_id: int, error: str) -> None:
    async with connection() as conn:
        await conn.execute(
            "UPDATE requests SET status='failed', error=%s WHERE id=%s",
            (error[:2000], request_id),
        )


async def get_request(request_id: int) -> RequestRecord | None:
    """Повертає запит із приєднаними джерелами (Ф3) або None."""
    async with connection() as conn:
        row = await (
            await conn.execute(
                "SELECT id, status, raw_text, answer, latency_ms, created_at "
                "FROM requests WHERE id = %s",
                (request_id,),
            )
        ).fetchone()
        if row is None:
            return None

        src_rows = await (
            await conn.execute(
                """
                SELECT rs.chunk_id, d.title, d.source, rs.rank, rs.score, c.content
                FROM request_sources rs
                JOIN kb_chunks c ON c.id = rs.chunk_id
                JOIN kb_documents d ON d.id = c.document_id
                WHERE rs.request_id = %s
                ORDER BY rs.rank
                """,
                (request_id,),
            )
        ).fetchall()

    sources = [
        SourceRecord(
            chunk_id=s[0],
            document_title=s[1],
            source=s[2],
            rank=s[3],
            score=float(s[4]),
            snippet=(s[5][:200] + "…") if len(s[5]) > 200 else s[5],
        )
        for s in src_rows
    ]
    return RequestRecord(
        id=row[0],
        status=row[1],
        raw_text=row[2],
        answer=row[3],
        latency_ms=row[4],
        created_at=row[5],
        sources=sources,
    )
