"""Формування контенту (відповіді) на основі знайдених джерел.

Підрозділ 2.5 / 3.5. Промпт обмежує модель наданим контекстом і вимагає
посилань на джерела [n] — це підвищує достовірність і дає трасування
«відповідь → джерело» (боротьба з галюцинаціями, 1.6; НФ1).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.llm import chat
from app.retrieval import RetrievedChunk, search_text

SYSTEM_PROMPT = (
    "Ти — асистент служби підтримки. Відповідай українською мовою, стисло, "
    "ввічливо й по суті. Використовуй ВИКЛЮЧНО інформацію з наведених джерел. "
    "Якщо у джерелах немає відповіді — прямо скажи, що інформації недостатньо, "
    "і не вигадуй. Після тверджень став посилання на джерело у форматі [n], "
    "де n — номер джерела."
)

NO_CONTEXT_ANSWER = (
    "На жаль, у базі знань немає інформації для відповіді на це запитання. "
    "Рекомендую уточнити запит або звернутися до оператора."
)


@dataclass(slots=True)
class RagResult:
    answer: str
    sources: list[RetrievedChunk]


def _build_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, ch in enumerate(chunks, start=1):
        title = ch.document_title
        blocks.append(f"[{i}] Джерело «{title}»:\n{ch.content}")
    return "\n\n".join(blocks)


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    context = _build_context(chunks)
    return (
        f"Контекст (джерела):\n{context}\n\n"
        f"Запитання користувача: {query}\n\n"
        "Дай відповідь, спираючись лише на контекст, із посиланнями [n]."
    )


async def generate_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    """Генерує відповідь за вже знайденими чанками."""
    if not chunks:
        return NO_CONTEXT_ANSWER
    prompt = build_prompt(query, chunks)
    return await chat(prompt, system_prompt=SYSTEM_PROMPT)


async def answer_query(query: str) -> RagResult:
    """Повний RAG-крок: пошук → генерація. Використовується воркером і API."""
    chunks = await search_text(query)
    answer = await generate_answer(query, chunks)
    return RagResult(answer=answer, sources=chunks)
