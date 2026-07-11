# CRM-hotline-AI

Сервісна система обробки запитів та формування контенту на основі **RAG** з локально
розгорнутою **LLM** (Ollama) та векторним пошуком (**PostgreSQL + pgvector**).

Практична частина магістерської роботи (спец. 122 «Комп'ютерні науки»).
Архітектура — модульний моноліт + фонові виконавці.

## Стек

| Компонент | Рішення |
|---|---|
| API | Python 3.11 / FastAPI |
| LLM | Ollama, локальна модель `gemma4:e4b` (Gemma 4, E4B) |
| Ембединги | `bge-m3` (через Ollama), 1024-вимірні |
| Сховище + вектори + черга | PostgreSQL 16 + pgvector (HNSW, косинус) |
| Черга завдань | pgqueuer (LISTEN/NOTIFY + FOR UPDATE SKIP LOCKED) |
| Моніторинг | Prometheus + Grafana |
| Контейнеризація | Docker, docker-compose |

## Трасування вимог

Ф1 приймання запиту · Ф2 пошук у базі знань · Ф3 відповідь з джерелами ·
Ф4 асинхронна обробка · Ф5 індексація бази знань · Ф6 метрики.
НФ1 локальність · НФ2 обмежені ресурси · НФ3 масштабованість ·
НФ4 спостережуваність · НФ5 мінімізація компонентів.

## Швидкий старт

```bash
cp .env.example .env
docker compose up -d --build          # підніме db, ollama, app, worker, prometheus, grafana
docker compose exec ollama ollama pull gemma4:e4b
docker compose exec ollama ollama pull bge-m3
docker compose exec app python -m app.indexing data/kb   # проіндексувати базу знань
```

### Запуск з GPU (NVIDIA)

Потрібні NVIDIA-драйвер і NVIDIA Container Toolkit (Linux) або Docker Desktop із
WSL2 + GPU (Windows). Додається GPU-оверлей:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
docker compose exec ollama nvidia-smi        # перевірити, що GPU видно з контейнера
```

Модель обирається в `.env` (`LLM_MODEL`). За замовчуванням — `gemma4:e4b`
(Gemma 4, E4B, Q4_K_M): за порівнянням п'яти моделей (див. Розділ 4) вона дає
найкращу достовірність відповідей і при цьому **повністю вміщається в 6 ГБ
VRAM** (рантайм ≈3.3 ГБ, 100 % на GPU), тож латентність лишається низькою.
Альтернативи: `qwen2.5:3b-instruct` (найшвидша, слабша достовірність) або
`qwen2.5:7b-instruct` (близька якість, але ~4× повільніша — не вміщається
повністю й виносить частину шарів на CPU). Reasoning-моделі викликаються з
вимкненим ланцюгом роздумів (`think: false`).

- Веб-UI:     http://localhost:8000/
- API:        http://localhost:8000/docs
- Метрики:    http://localhost:8000/metrics
- Mock CRM:   http://localhost:9100/docs
- Prometheus: http://localhost:9090
- Grafana:    http://localhost:3000 (admin / admin)

## Джерела даних

Система працює з двома типами даних:

1. **Статична база знань (RAG)** — довідкові матеріали в `data/kb`, індексуються
   у pgvector; загальні питання відповідаються пошуком + генерацією з джерелами.
2. **Динамічні дані з API (tool-calling)** — персональні/транзакційні запити
   (статус заявки) обслуговуються викликом зовнішньої CRM під час обробки.
   Агентний роутер (`app/agent.py`) за наміром обирає шлях: RAG або інструмент.

Демо-запит статусу (номери заявок у мок-CRM: `APP-2024-000123`, `-000456`,
`-000789`, `-000999`, `-000111`):

```
POST /ask/sync {"text": "Який статус моєї заявки APP-2024-000456?"}
```

Інструмент шукає за **номером заявки** (не-PII), тож не конфліктує з
анонімізацією: номер переживає знеособлення, а РНОКПП/телефон маскуються.

## Структура

```
app/          застосунок (FastAPI, RAG, черга)
migrations/   SQL-схема БД
monitoring/   prometheus.yml, Grafana dashboards
ui/           мінімальний веб-інтерфейс
tests/        тести
```
