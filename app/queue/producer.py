"""Постановка завдань у чергу pgqueuer (сторона продюсера).

Консюмер (воркер) — у app/queue/worker.py (задача 6). Обидві сторони
використовують спільне ім'я точки входу ENTRYPOINT.
"""
from __future__ import annotations

import psycopg
from pgqueuer.db import PsycopgDriver
from pgqueuer.queries import Queries

from app.config import settings

ENTRYPOINT = "process_request"


async def enqueue_request(request_id: int) -> None:
    """Ставить запит в чергу на асинхронну обробку (Ф4)."""
    conn = await psycopg.AsyncConnection.connect(settings.database_url, autocommit=True)
    try:
        queries = Queries(PsycopgDriver(conn))
        await queries.enqueue(ENTRYPOINT, str(request_id).encode(), priority=0)
    finally:
        await conn.close()
