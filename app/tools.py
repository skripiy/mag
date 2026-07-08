"""Зовнішні інструменти для tool-calling (Тип 2 API-даних).

Інструмент get_application_status звертається до зовнішньої (мок-)CRM за
статусом заявки. Пошук за номером заявки — не-PII референсом, тож інструмент
сумісний з анонімізацією (номер переживає знеособлення, РНОКПП — ні).
"""
from __future__ import annotations

import httpx

from app.config import settings

# Схема інструментів у форматі, який приймає Ollama /api/chat (OpenAI-сумісний).
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_application_status",
            "description": (
                "Отримати поточний статус заявки користувача за її номером. "
                "Викликати, коли людина питає про стан своєї заявки, виплати, "
                "реєстрації чи компенсації й вказує номер заявки."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "application_code": {
                        "type": "string",
                        "description": "Номер заявки у форматі APP-РРРР-NNNNNN, напр. APP-2024-000123",
                    }
                },
                "required": ["application_code"],
            },
        },
    }
]


async def get_application_status(application_code: str) -> dict:
    """Викликає зовнішню CRM. Повертає статус або {'error': ...}."""
    code = (application_code or "").strip().upper()
    if not code:
        return {"error": "empty_code"}
    url = f"{settings.mock_crm_url}/applications/{code}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
        if resp.status_code == 404:
            return {"error": "not_found", "application_code": code}
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        return {"error": "unavailable", "detail": str(exc)}


# Диспетчер: ім'я інструмента -> корутина.
TOOL_FUNCS = {"get_application_status": get_application_status}
