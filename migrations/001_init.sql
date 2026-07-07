-- Ініціалізація схеми БД.
-- Розділення «база знань» / «журнал запитів» (підрозділ 2.7).
-- Єдина СУБД закриває дані, векторний пошук і чергу (НФ5).

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- БАЗА ЗНАНЬ (RAG-корпус). PII зазвичай немає -> може містити реальний контент.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS kb_documents (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT        NOT NULL,
    source      TEXT,                      -- назва джерела/розділу
    uri         TEXT,                      -- шлях/URL оригіналу
    lang        TEXT        DEFAULT 'uk',
    checksum    TEXT,                      -- для ідемпотентної переіндексації
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id  BIGINT      NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    chunk_index  INT         NOT NULL,
    content      TEXT        NOT NULL,
    embedding    vector(1024),            -- BGE-m3, косинус
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

-- HNSW-індекс за косинусною відстанню (Ф2, векторний пошук).
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_hnsw
    ON kb_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- ЖУРНАЛ ЗАПИТІВ (потік звернень). Тут можлива PII -> анонімізація (3.7).
-- ---------------------------------------------------------------------------

CREATE TYPE request_status AS ENUM ('pending', 'processing', 'done', 'failed');

CREATE TABLE IF NOT EXISTS requests (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id      TEXT,                          -- ідентифікатор звернення у зовн. системі
    raw_text         TEXT        NOT NULL,          -- як прийшло (може містити PII)
    anonymized_text  TEXT,                          -- після модуля анонімізації
    status           request_status NOT NULL DEFAULT 'pending',
    answer           TEXT,                          -- згенерована відповідь (Ф3)
    error            TEXT,
    latency_ms       INT,                           -- час обробки (для Розділу 4)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS requests_status_idx ON requests(status);
CREATE INDEX IF NOT EXISTS requests_created_idx ON requests(created_at);

-- Джерела, використані у відповіді (трасування «відповідь -> чанки бази знань»).
CREATE TABLE IF NOT EXISTS request_sources (
    request_id  BIGINT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    chunk_id    BIGINT NOT NULL REFERENCES kb_chunks(id) ON DELETE CASCADE,
    rank        INT    NOT NULL,           -- позиція в топ-k
    score       REAL   NOT NULL,           -- косинусна схожість
    PRIMARY KEY (request_id, chunk_id)
);

-- Тригер оновлення updated_at.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER requests_set_updated_at
    BEFORE UPDATE ON requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
