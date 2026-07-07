"""Простий раннер SQL-міграцій.

Застосовує файли migrations/*.sql у лексикографічному порядку один раз,
фіксуючи застосовані у таблиці schema_migrations. Викликається на старті
контейнера застосунку (див. entrypoint).
"""
from __future__ import annotations

import pathlib
import sys

import psycopg

from app.config import settings

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"


def run() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " filename TEXT PRIMARY KEY,"
            " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
        for path in files:
            if path.name in applied:
                print(f"[migrate] пропущено (вже застосовано): {path.name}")
                continue
            print(f"[migrate] застосовую: {path.name}")
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                conn.execute(sql)  # type: ignore[arg-type]
                conn.execute(
                    "INSERT INTO schema_migrations(filename) VALUES (%s)", (path.name,)
                )
        print("[migrate] готово.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"[migrate] ПОМИЛКА: {exc}", file=sys.stderr)
        sys.exit(1)
