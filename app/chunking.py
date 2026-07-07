"""Чанкінг документів бази знань.

Абзацо-орієнтоване вікно: текст ділиться на абзаци, які накопичуються до
CHUNK_SIZE символів; між сусідніми чанками зберігається перекриття
CHUNK_OVERLAP символів (щоб не розривати думку на межі). Ф5.
"""
from __future__ import annotations

import re

from app.config import settings


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    size = chunk_size or settings.chunk_size
    over = overlap if overlap is not None else settings.chunk_overlap

    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    buf = ""

    for para in paragraphs:
        # Абзац, що не влазить у розмір чанка, ріжемо жорстко по символах.
        if len(para) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(para), size - over):
                chunks.append(para[i : i + size])
            continue

        if len(buf) + len(para) + 2 <= size:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            chunks.append(buf)
            # Хвіст-перекриття беремо лише в межах, які не виведуть новий
            # чанк за CHUNK_SIZE (з урахуванням абзацу та роздільника).
            room = size - len(para) - 2
            tail_len = max(0, min(over, room))
            tail = buf[-tail_len:] if tail_len else ""
            buf = f"{tail}\n\n{para}" if tail else para

    if buf:
        chunks.append(buf)
    return chunks
