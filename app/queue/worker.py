"""Фоновий виконавець черги pgqueuer (консюмер, Ф4).

Модель черги — поверх PostgreSQL: LISTEN/NOTIFY + FOR UPDATE SKIP LOCKED
(підрозділ 2.6). Запускається фабрикою через CLI:

    python -m pgqueuer run app.queue.worker:create_pgqueuer

Кілька екземплярів воркера можуть працювати паралельно, не дублюючи
завдання завдяки SKIP LOCKED (НФ3 масштабованість).
"""
from __future__ import annotations

import psycopg
from pgqueuer import PgQueuer
from pgqueuer.db import PsycopgDriver
from pgqueuer.models import Job

from app.config import settings
from app.pipeline import process_request
from app.queue.producer import ENTRYPOINT


async def create_pgqueuer() -> PgQueuer:
    connection = await psycopg.AsyncConnection.connect(
        settings.database_url, autocommit=True
    )
    pgq = PgQueuer(PsycopgDriver(connection))

    @pgq.entrypoint(ENTRYPOINT)
    async def _handle(job: Job) -> None:
        if job.payload is None:
            return
        request_id = int(job.payload.decode())
        await process_request(request_id)

    return pgq
