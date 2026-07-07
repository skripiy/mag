"""FastAPI-застосунок: приймання запитів і відповіді з джерелами.

Підрозділ 3.2. Два шляхи обробки:
  • POST /ask       — асинхронно (Ф4): запит у чергу, миттєва відповідь 202;
  • POST /ask/sync  — синхронно: повний RAG одразу (демо/тестування).
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.db import close_pool, open_pool
from app.generation import answer_query
from app.metrics import rag_latency, requests_total
from app.queue.producer import enqueue_request
from app.repository import create_request, get_request, save_result
from app.schemas import AcceptedOut, AnswerOut, AskRequest, SourceOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    await open_pool()
    yield
    await close_pool()


app = FastAPI(
    title="CRM-hotline-AI",
    description="Сервісна система обробки запитів на основі RAG з локальною LLM",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ask", response_model=AcceptedOut, status_code=202, tags=["requests"])
async def ask(req: AskRequest) -> AcceptedOut:
    """Приймає запит і ставить його в чергу на обробку (Ф1 + Ф4)."""
    request_id, created_at = await create_request(req.text, external_id=req.external_id)
    await enqueue_request(request_id)
    requests_total.labels(status="accepted").inc()
    return AcceptedOut(request_id=request_id, status="pending", created_at=created_at)


@app.post("/ask/sync", response_model=AnswerOut, tags=["requests"])
async def ask_sync(req: AskRequest) -> AnswerOut:
    """Синхронний RAG: пошук + генерація одразу (демонстрація/тести)."""
    request_id, _ = await create_request(req.text, external_id=req.external_id)
    started = time.perf_counter()
    with rag_latency.time():
        result = await answer_query(req.text)
    latency_ms = int((time.perf_counter() - started) * 1000)
    await save_result(request_id, result.answer, result.sources, latency_ms)
    requests_total.labels(status="done").inc()

    return AnswerOut(
        request_id=request_id,
        status="done",
        answer=result.answer,
        latency_ms=latency_ms,
        sources=[
            SourceOut(
                chunk_id=c.chunk_id,
                document_title=c.document_title,
                source=c.source,
                rank=i,
                score=round(c.score, 4),
                snippet=(c.content[:200] + "…") if len(c.content) > 200 else c.content,
            )
            for i, c in enumerate(result.sources, start=1)
        ],
    )


@app.get("/requests/{request_id}", response_model=AnswerOut, tags=["requests"])
async def get_request_status(request_id: int) -> AnswerOut:
    """Статус і результат обробки запиту (Ф3)."""
    rec = await get_request(request_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Запит не знайдено")
    return AnswerOut(
        request_id=rec.id,
        status=rec.status,
        answer=rec.answer,
        latency_ms=rec.latency_ms,
        sources=[
            SourceOut(
                chunk_id=s.chunk_id,
                document_title=s.document_title,
                source=s.source,
                rank=s.rank,
                score=round(s.score, 4),
                snippet=s.snippet,
            )
            for s in rec.sources
        ],
    )
