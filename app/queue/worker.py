"""Фоновий виконавець черги (pgqueuer).

Каркас-заглушка: повна реалізація RAG-пайплайну в черзі — підрозділ 3.6
(задача «Асинхронна черга»). Наразі лише коректно стартує й чекає.
"""
from __future__ import annotations

import asyncio


async def main() -> None:
    print("[worker] стартував (заглушка). Реалізація pgqueuer — задача 6.")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
