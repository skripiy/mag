"""Клієнт локальної LLM через Ollama (Ф3).

Використовує /api/chat без стрімінгу. Параметри генерації (temperature,
num_ctx, num_predict) — з конфігурації, під обмежені ресурси (НФ2).
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.metrics import llm_latency


async def chat(user_prompt: str, system_prompt: str | None = None) -> str:
    """Повертає відповідь моделі на пару system/user повідомлень."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        # Для моделей із «мисленням» (reasoning) вимикаємо ланцюг роздумів:
        # система потребує прямої стислої відповіді, а не токенів на міркування
        # (НФ2). Для звичайних моделей параметр ігнорується.
        "think": False,
        "options": {
            "temperature": settings.llm_temperature,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": settings.llm_max_tokens,
        },
    }

    with llm_latency.time():
        async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=300) as client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

    message = data.get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError(f"Ollama повернув порожню відповідь: {data!r}")
    return content.strip()


async def chat_raw(
    messages: list[dict],
    tools: list[dict] | None = None,
    num_predict: int | None = None,
) -> dict:
    """Низькорівневий виклик /api/chat зі списком повідомлень та (опційно)
    інструментами. Повертає повне повідомлення асистента (може містити
    tool_calls). Використовується агентним роутером.

    num_predict дозволяє обмежити довжину відповіді (напр. для дешевого
    маршрутизувального виклику, якому потрібне лише рішення про інструмент)."""
    payload: dict = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "think": False,  # прямі відповіді без ланцюга роздумів (див. chat)
        "options": {
            "temperature": settings.llm_temperature,
            "num_ctx": settings.llm_num_ctx,
            "num_predict": num_predict or settings.llm_max_tokens,
        },
    }
    if tools:
        payload["tools"] = tools

    with llm_latency.time():
        async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=300) as client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
    return data.get("message") or {}
