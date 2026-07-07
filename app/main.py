"""FastAPI-застосунок (точка входу).

Наразі — каркас: health-check і /metrics. Повні роути прийому запиту й
відповіді з джерелами додаються в підрозділі 3.2 (задача API).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.db import close_pool, open_pool


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
