"""Оркестрація обробки одного запиту (спільна для черги й тестів).

Крок: позначити processing → RAG (пошук+генерація) → зберегти результат
або позначити failed. Ф2/Ф3/Ф4.
"""
from __future__ import annotations

import time

from app.generation import answer_query
from app.metrics import rag_latency, requests_total
from app.repository import get_request, mark_failed, mark_processing, save_result


async def process_request(request_id: int) -> None:
    rec = await get_request(request_id)
    if rec is None:
        return
    # Для обробки беремо знеособлений текст, якщо він є (задача PII, 3.7).
    query = rec.anonymized_text or rec.raw_text

    await mark_processing(request_id)
    started = time.perf_counter()
    try:
        with rag_latency.time():
            result = await answer_query(query)
        latency_ms = int((time.perf_counter() - started) * 1000)
        await save_result(request_id, result.answer, result.sources, latency_ms)
        requests_total.labels(status="done").inc()
    except Exception as exc:  # noqa: BLE001
        await mark_failed(request_id, repr(exc))
        requests_total.labels(status="failed").inc()
        raise
