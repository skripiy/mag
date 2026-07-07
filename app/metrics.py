"""Prometheus-метрики (НФ4, Ф6). Розширюється в підрозділі 3.8."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

requests_total = Counter(
    "hotline_requests_total", "Кількість прийнятих запитів", ["status"]
)
rag_latency = Histogram(
    "hotline_rag_latency_seconds", "Час повного RAG-циклу обробки запиту",
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34),
)
retrieval_latency = Histogram(
    "hotline_retrieval_latency_seconds", "Час векторного пошуку",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
llm_latency = Histogram(
    "hotline_llm_latency_seconds", "Час генерації відповіді LLM",
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34),
)
