"""Тести regex-рівня анонімізації (без Presidio)."""
from app.anonymize import Anonymizer, anonymize


def _regex_only():
    # Вимикаємо Presidio, щоб тест не залежав від spaCy-моделі.
    return Anonymizer(use_presidio=False)


def test_email_and_phone_masked():
    text = "Телефон +380671234567, пошта ivan@example.com"
    out, ents = _regex_only().anonymize(text)
    assert "[ТЕЛЕФОН]" in out
    assert "[EMAIL]" in out
    assert "+380671234567" not in out
    assert "ivan@example.com" not in out
    kinds = {e.kind for e in ents}
    assert {"ТЕЛЕФОН", "EMAIL"} <= kinds


def test_card_ipn_iban():
    text = "Картка 4149 6090 1234 5678, ІПН 1234567890, IBAN UA903052992990004149123456789"
    out, _ = _regex_only().anonymize(text)
    assert "[КАРТКА]" in out
    assert "[ІПН]" in out
    assert "[IBAN]" in out
    assert "1234567890" not in out


def test_phone_keeps_preceding_space():
    out, _ = _regex_only().anonymize("номер 067 123 45 67 ok")
    assert "номер [ТЕЛЕФОН]" in out  # пробіл перед номером не з'їдається


def test_clean_text_unchanged():
    text = "Яка вартість доставки по Києву?"
    out, ents = _regex_only().anonymize(text)
    assert out == text
    assert ents == []


def test_convenience_wrapper_returns_str():
    assert isinstance(anonymize("тест 0501234567"), str)
