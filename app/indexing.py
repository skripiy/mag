"""Індексація бази знань у pgvector (Ф5).

Ідемпотентно: за контрольною сумою вмісту документ переіндексовується лише
при зміні. Джерело — тека з файлами .txt/.md (RAG-корпус).

CLI:
    python -m app.indexing data/kb        # проіндексувати теку
"""
from __future__ import annotations

import asyncio
import hashlib
import pathlib
import sys

from app.chunking import chunk_text
from app.db import connection
from app.embeddings import embed_texts, to_pgvector

SUPPORTED_SUFFIXES = {".txt", ".md"}


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def index_document(
    title: str,
    content: str,
    *,
    source: str | None = None,
    uri: str | None = None,
    lang: str = "uk",
) -> tuple[int, int]:
    """Індексує один документ. Повертає (document_id, к-сть чанків).

    Якщо документ із таким uri вже є і контрольна сума не змінилась —
    переіндексація пропускається (0 чанків).
    """
    checksum = _checksum(content)

    async with connection() as conn:
        if uri is not None:
            row = await (
                await conn.execute(
                    "SELECT id, checksum FROM kb_documents WHERE uri = %s", (uri,)
                )
            ).fetchone()
        else:
            row = None

        if row is not None:
            doc_id, old_checksum = row
            if old_checksum == checksum:
                return doc_id, 0
            # Вміст змінився — прибираємо старі чанки й оновлюємо метадані.
            await conn.execute("DELETE FROM kb_chunks WHERE document_id = %s", (doc_id,))
            await conn.execute(
                "UPDATE kb_documents SET title=%s, source=%s, lang=%s, checksum=%s "
                "WHERE id=%s",
                (title, source, lang, checksum, doc_id),
            )
        else:
            doc_id = (
                await (
                    await conn.execute(
                        "INSERT INTO kb_documents (title, source, uri, lang, checksum) "
                        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (title, source, uri, lang, checksum),
                    )
                ).fetchone()
            )[0]

        chunks = chunk_text(content)
        if not chunks:
            return doc_id, 0

        embeddings = await embed_texts(chunks)
        async with conn.cursor() as cur:
            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                await cur.execute(
                    "INSERT INTO kb_chunks (document_id, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (doc_id, idx, chunk, to_pgvector(emb)),
                )
        return doc_id, len(chunks)


async def index_directory(path: str | pathlib.Path) -> None:
    root = pathlib.Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Тека не знайдена: {root}")

    files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files:
        print(f"[index] у теці {root} немає файлів {SUPPORTED_SUFFIXES}")
        return

    total_docs = total_chunks = 0
    for file in files:
        content = file.read_text(encoding="utf-8")
        doc_id, n = await index_document(
            title=file.stem,
            content=content,
            source=file.parent.name,
            uri=str(file.relative_to(root)),
        )
        status = "проіндексовано" if n else "без змін"
        print(f"[index] {file.name}: {status} (doc={doc_id}, чанків={n})")
        total_docs += 1
        total_chunks += n

    print(f"[index] готово: документів={total_docs}, нових чанків={total_chunks}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/kb"
    asyncio.run(index_directory(target))
