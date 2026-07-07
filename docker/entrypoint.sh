#!/usr/bin/env bash
set -euo pipefail

# Роль контейнера визначає перший аргумент: api | worker.
ROLE="${1:-api}"

echo "[entrypoint] очікую PostgreSQL..."
python - <<'PY'
import time, psycopg
from app.config import settings
for _ in range(60):
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2):
            break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("PostgreSQL недоступний")
print("[entrypoint] PostgreSQL готовий")
PY

if [ "$ROLE" = "api" ]; then
    echo "[entrypoint] застосовую міграції..."
    python -m app.migrate
    echo "[entrypoint] встановлюю схему черги pgqueuer (якщо ще нема)..."
    python -m pgqueuer install 2>/dev/null && echo "[entrypoint] pgqueuer встановлено" \
        || echo "[entrypoint] pgqueuer вже встановлено"
    echo "[entrypoint] запускаю API..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
elif [ "$ROLE" = "worker" ]; then
    echo "[entrypoint] очікую схему черги pgqueuer (її ставить контейнер api)..."
    python - <<'PY'
import time, psycopg
from app.config import settings
for _ in range(120):
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as c:
            ok = c.execute("SELECT to_regclass('public.pgqueuer')").fetchone()[0]
            if ok:
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit("Схема pgqueuer не з'явилась вчасно")
print("[entrypoint] схема черги готова")
PY
    echo "[entrypoint] запускаю фоновий виконавець черги..."
    exec python -m pgqueuer run app.queue.worker:create_pgqueuer
else
    echo "[entrypoint] невідома роль: $ROLE" >&2
    exit 1
fi
