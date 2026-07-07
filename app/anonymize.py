"""Анонімізація персональних даних у потоці запитів (підрозділ 3.7, НФ1).

Два рівні:
  1. Regex-розпізнавачі української PII (телефон, РНОКПП/ІПН, платіжна
     картка, IBAN, e-mail, паспорт) — працюють завжди, без залежностей.
  2. Опційно Presidio + spaCy `uk_core_news_*` для іменованих сутностей
     (ПІБ, локації) — вмикається, якщо встановлено extra `pii` та модель.

База знань зазвичай PII не містить; анонімізується саме журнал звернень.
Демонстрація — на знеособлених/синтетичних даних; архітектура розрахована
на реальні дані в захищеному локальному контурі.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Порядок важливий: складніші/довші шаблони — раніше, щоб коротші (напр.
# 10-значний ІПН) не «з'їдали» частини телефонів чи карток.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.UNICODE)),
    ("IBAN", re.compile(r"\bUA\d{27}\b", re.IGNORECASE)),
    ("КАРТКА", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("ТЕЛЕФОН", re.compile(r"(?:\+?38[\s\-]?)?\(?0\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b")),
    ("ПАСПОРТ", re.compile(r"\b[А-ЯІЇЄҐ]{2}\s?\d{6}\b")),
    ("ІПН", re.compile(r"\b\d{10}\b")),
]

TAG = "[{}]"


@dataclass(slots=True)
class Entity:
    kind: str
    start: int
    end: int
    text: str


def _regex_anonymize(text: str) -> tuple[str, list[Entity]]:
    entities: list[Entity] = []
    result = text
    for kind, pattern in _PATTERNS:
        found: list[Entity] = []

        def _sub(m: re.Match[str], _kind=kind, _found=found) -> str:
            _found.append(Entity(_kind, m.start(), m.end(), m.group()))
            return TAG.format(_kind)

        result = pattern.sub(_sub, result)
        entities.extend(found)
    return result, entities


class Anonymizer:
    """Знеособлювач тексту. Presidio підключається ліниво й опційно."""

    def __init__(self, use_presidio: bool = True):
        self._analyzer = None
        self._anonymizer = None
        if use_presidio:
            self._try_init_presidio()

    def _try_init_presidio(self) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_anonymizer import AnonymizerEngine

            provider = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "uk", "model_name": "uk_core_news_sm"}],
                }
            )
            self._analyzer = AnalyzerEngine(
                nlp_engine=provider.create_engine(), supported_languages=["uk"]
            )
            self._anonymizer = AnonymizerEngine()
        except Exception:
            # spaCy-модель або Presidio недоступні — лишаємось на regex-рівні.
            self._analyzer = None
            self._anonymizer = None

    @property
    def presidio_enabled(self) -> bool:
        return self._analyzer is not None

    def anonymize(self, text: str) -> tuple[str, list[Entity]]:
        """Повертає (знеособлений_текст, перелік знайдених сутностей)."""
        masked, entities = _regex_anonymize(text)
        if self._analyzer is not None and self._anonymizer is not None:
            try:
                results = self._analyzer.analyze(
                    text=masked, language="uk",
                    entities=["PERSON", "LOCATION"],
                )
                if results:
                    anonymized = self._anonymizer.anonymize(text=masked, analyzer_results=results)
                    masked = anonymized.text
                    for r in results:
                        entities.append(Entity("ПІБ/ЛОКАЦІЯ", r.start, r.end, ""))
            except Exception:
                pass
        return masked, entities


_default: Anonymizer | None = None


def get_anonymizer() -> Anonymizer:
    global _default
    if _default is None:
        _default = Anonymizer()
    return _default


def anonymize(text: str) -> str:
    """Зручний вхід: повертає лише знеособлений текст."""
    return get_anonymizer().anonymize(text)[0]
