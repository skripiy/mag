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
