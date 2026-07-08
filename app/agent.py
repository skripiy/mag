"""Агентний роутер: tool-calling (динамічні дані з API) vs RAG.

Легкий евристичний фільтр наміру визначає, чи схоже звернення на запит
статусу заявки:
  • ні  → одразу RAG над базою знань (один виклик LLM, НФ2);
  • так → агентна гілка: модель викликає інструмент get_application_status,
          результат передається моделі для фінальної відповіді (джерело —
          зовнішня CRM). Якщо номера заявки немає — просимо його (без LLM).
          Якщо модель не викликала інструмент, але номер у тексті є —
          спрацьовує regex-фолбек.

Інструмент шукає за номером заявки (не-PII), тож сумісний з анонімізацією.
"""
from __future__ import annotations

import json
import re

from app.config import settings
from app.generation import RagResult, answer_query
from app.llm import chat_raw
from app.tools import TOOLS, TOOL_FUNCS, get_application_status

# Номер заявки (не-PII референс), напр. APP-2024-000123.
CODE_RE = re.compile(r"APP-\d{4}-\d{4,}", re.IGNORECASE)

# Намір «дізнатися стан СВОЄЇ заявки» (а не загальне питання «як подати заяву»).
STATUS_INTENT_RE = re.compile(
    r"(статус|стан)\W+(мо\w+\W+)?заявк"
    r"|заявк\w*\W+.{0,20}?(статус|стан|готов|опрацьов|розглян)"
    r"|мо(єї|ю|я)\W+заявк",
    re.IGNORECASE,
)

AGENT_SYSTEM = (
    "Ти — асистент гарячої лінії гуманітарної організації. Якщо користувач "
    "питає про стан своєї заявки й вказує її номер — виклич інструмент "
    "get_application_status. Номер не вигадуй."
)

COMPOSE_SYSTEM = (
    "Ти — асистент гарячої лінії. На основі даних із системи (роль tool) дай "
    "користувачу коротку, ввічливу відповідь українською про стан його заявки. "
    "Якщо у даних error='not_found' — повідом, що заявку з таким номером не "
    "знайдено, і попроси перевірити номер. Не вигадуй даних поза наданими."
)

MISSING_CODE_MSG = (
    "Щоб перевірити статус заявки, вкажіть, будь ласка, її номер у форматі "
    "APP-РРРР-NNNNNN (наприклад, APP-2024-000123)."
)


def _looks_like_status_query(query: str) -> bool:
    return bool(CODE_RE.search(query) or STATUS_INTENT_RE.search(query))


def _extract_call(call: dict) -> tuple[str, dict]:
    fn = call.get("function", {}) or {}
    name = fn.get("name", "")
    args = fn.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return name, args


async def answer(query: str) -> RagResult:
    """Основний вхід обробки запиту (агентний роутер над RAG)."""
    if not (settings.enable_tools and _looks_like_status_query(query)):
        return await answer_query(query)
    return await _agentic_answer(query)


async def _agentic_answer(query: str) -> RagResult:
    messages: list[dict] = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "user", "content": query},
    ]
    # Маршрутизувальний виклик: потрібне лише рішення про інструмент — обмежуємо
    # довжину, щоб не марнувати генерацію (НФ2).
    assistant_msg = await chat_raw(messages, tools=TOOLS, num_predict=64)
    tool_calls = assistant_msg.get("tool_calls") or []

    tool_results: list[dict] = []
    if tool_calls:
        messages.append(assistant_msg)
        for call in tool_calls:
            name, args = _extract_call(call)
            func = TOOL_FUNCS.get(name)
            if func is None:
                result = {"error": "unknown_tool", "name": name}
            elif name == "get_application_status" and not args.get("application_code"):
                return RagResult(answer=MISSING_CODE_MSG, sources=[])
            else:
                try:
                    result = await func(**args)
                except TypeError:
                    result = {"error": "bad_arguments", "args": args}
            tool_results.append(result)
            messages.append(
                {"role": "tool", "content": json.dumps(result, ensure_ascii=False)}
            )
    else:
        # Модель не викликала інструмент. Regex-фолбек: якщо номер у тексті є —
        # звертаємось до CRM напряму; якщо немає — просимо номер.
        match = CODE_RE.search(query)
        if not match:
            return RagResult(answer=MISSING_CODE_MSG, sources=[])
        result = await get_application_status(match.group(0))
        tool_results.append(result)
        messages = [
            {"role": "system", "content": COMPOSE_SYSTEM},
            {"role": "user", "content": query},
            {"role": "tool", "content": json.dumps(result, ensure_ascii=False)},
        ]

    # Фінальна генерація: складаємо відповідь користувачу з даних інструмента.
    messages[0] = {"role": "system", "content": COMPOSE_SYSTEM}
    final_msg = await chat_raw(messages)
    final = (final_msg.get("content") or "").strip()
    if not final:
        final = "Не вдалося отримати статус заявки. Спробуйте пізніше."
    return RagResult(answer=final, sources=[])
