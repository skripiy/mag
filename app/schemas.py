"""Pydantic-схеми запитів/відповідей API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Текст звернення користувача")
    external_id: str | None = Field(None, description="Ідентифікатор у зовнішній системі")


class SourceOut(BaseModel):
    chunk_id: int
    document_title: str
    source: str | None
    rank: int
    score: float
    snippet: str


class AnswerOut(BaseModel):
    request_id: int
    status: str
    answer: str | None = None
    sources: list[SourceOut] = []
    latency_ms: int | None = None


class AcceptedOut(BaseModel):
    """Відповідь на асинхронний прийом запиту (Ф4)."""
    request_id: int
    status: str
    created_at: datetime
