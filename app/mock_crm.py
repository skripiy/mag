"""Мок зовнішньої CRM-системи (імітація реального API організації).

Окремий сервіс, який віддає статус заявки за її номером. У реальній системі
тут була б інтеграція з обліковою системою організації; для роботи/демо —
синтетичні дані, без PII (ім'я заявника замасковане). Пошук за номером
заявки (не-PII референс), а не за РНОКПП — щоб не конфліктувати з
анонімізацією.

Запуск (окремий контейнер):
    uvicorn app.mock_crm:app --host 0.0.0.0 --port 9100
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Mock CRM API", description="Імітація облікової системи організації")

# Синтетичні заявки. Номер — не-PII референс, який видають заявнику.
_APPLICATIONS: dict[str, dict] = {
    "APP-2024-000123": {
        "application_code": "APP-2024-000123",
        "applicant": "О. К******",
        "program": "Грошова допомога",
        "status": "На розгляді",
        "submitted_at": "2024-11-05",
        "next_step": "Очікується перевірка документів; рішення до 30 робочих днів.",
        "amount_uah": None,
    },
    "APP-2024-000456": {
        "application_code": "APP-2024-000456",
        "applicant": "І. П******",
        "program": "Грошова допомога",
        "status": "Схвалено, виплату призначено",
        "submitted_at": "2024-10-12",
        "next_step": "Кошти буде зараховано на картку до 2024-12-01.",
        "amount_uah": 10800,
    },
    "APP-2024-000789": {
        "application_code": "APP-2024-000789",
        "applicant": "М. С******",
        "program": "Гуманітарний набір",
        "status": "Потрібні документи",
        "submitted_at": "2024-11-20",
        "next_step": "Додайте довідку ВПО через особистий кабінет або в офісі.",
        "amount_uah": None,
    },
    "APP-2024-000999": {
        "application_code": "APP-2024-000999",
        "applicant": "А. К******",
        "program": "Грошова допомога",
        "status": "Виплачено",
        "submitted_at": "2024-09-01",
        "next_step": "Виплату завершено 2024-10-15.",
        "amount_uah": 6600,
    },
    "APP-2024-000111": {
        "application_code": "APP-2024-000111",
        "applicant": "В. Т******",
        "program": "Компенсація за житло",
        "status": "Відхилено",
        "submitted_at": "2024-08-17",
        "next_step": "Причина: об'єкт поза межами програми. Можливе повторне звернення.",
        "amount_uah": None,
    },
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/applications/{application_code}")
def get_application(application_code: str) -> dict:
    """Повертає статус заявки за номером або 404."""
    record = _APPLICATIONS.get(application_code.strip().upper())
    if record is None:
        raise HTTPException(status_code=404, detail="Заявку з таким номером не знайдено")
    return record
