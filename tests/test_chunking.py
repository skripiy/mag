"""Тести чанкінгу бази знань."""
from app.chunking import chunk_text

SAMPLE = "\n\n".join(f"Абзац номер {i}. " + "текст " * 20 for i in range(10))


def test_chunks_respect_size_limit():
    size, overlap = 300, 60
    chunks = chunk_text(SAMPLE, size, overlap)
    assert chunks, "має бути хоча б один чанк"
    assert all(len(c) <= size for c in chunks), "жоден чанк не перевищує CHUNK_SIZE"


def test_overlap_between_adjacent_chunks():
    chunks = chunk_text(SAMPLE, 300, 60)
    # Сусідні чанки мають спільний хвіст (перекриття) хоча б у кілька символів.
    overlaps = [
        any(a[-k:] and a[-k:] == b[:k] for k in range(10, 61))
        for a, b in zip(chunks, chunks[1:])
    ]
    assert any(overlaps), "між чанками очікується перекриття"


def test_long_paragraph_is_hard_split():
    long_para = "слово " * 500  # один довгий абзац
    chunks = chunk_text(long_para, 200, 40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_empty_input():
    assert chunk_text("", 300, 60) == []
    assert chunk_text("   \n\n  ", 300, 60) == []
