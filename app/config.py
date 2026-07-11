"""Налаштування застосунку (читаються з оточення / .env)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    database_url: str = "postgresql://hotline:hotline@db:5432/hotline"

    # Ollama
    ollama_url: str = "http://ollama:11434"
    llm_model: str = "gemma4:e4b"
    embed_model: str = "bge-m3"
    embed_dim: int = 1024

    # RAG
    top_k: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 120
    min_score: float = 0.30

    # LLM генерація
    llm_temperature: float = 0.2
    llm_num_ctx: int = 4096
    llm_max_tokens: int = 800

    # Зовнішні інструменти (tool-calling)
    enable_tools: bool = True
    mock_crm_url: str = "http://mock-crm:9100"

    log_level: str = "INFO"


settings = Settings()
