"""Асинхронний пул з'єднань до PostgreSQL (psycopg3) + реєстрація pgvector."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector_async

from app.config import settings

_pool: AsyncConnectionPool | None = None


async def _configure(conn: AsyncConnection) -> None:
    """Реєструє тип vector для кожного нового з'єднання пулу."""
    await register_vector_async(conn)


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            open=False,
            configure=_configure,
        )
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    pool = await open_pool()
    async with pool.connection() as conn:
        yield conn
