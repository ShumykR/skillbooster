"""Завдання №127: Structured output з повторною спробою.

LLM повертає текст, а бекенду потрібен типізований обʼєкт. Модель інколи
додає пояснення, огортає JSON у ```json або помиляється в полях.
Тут `llm` це звичайна функція prompt -> відповідь (текст), тож завдання не
залежить від провайдера. У реальному проєкті її роль виконує твій проксі
(LLM_BASE_URL / LLM_API_KEY / LLM_MODEL).
"""
import json
from datetime import date
from typing import Callable, Literal

from pydantic import BaseModel, ValidationError


class Invoice(BaseModel):
    vendor: str
    total: float
    currency: Literal["USD", "EUR", "UAH"]
    due_date: date


class ExtractionError(Exception):
    """Не вдалося отримати валідний Invoice за max_attempts спроб."""


def extract_invoice(llm: Callable[[str], str], text: str, *, max_attempts: int = 3) -> Invoice:
    """Витягає Invoice з довільного тексту.

    Вимоги:
    - перший prompt містить `text` та JSON-схему Invoice (Invoice.model_json_schema());
    - відповідь може мати зайвий текст або ```json-огорожу: дістань JSON-обʼєкт;
    - якщо JSON невалідний або не проходить pydantic, зроби НОВУ спробу, у prompt якої
      є `text`, попередня відповідь моделі й текст помилки валідації;
    - не більше max_attempts викликів llm; після вичерпання піднімай ExtractionError;
    - після першої успішної відповіді більше llm не викликай;
    - винятки самого llm (мережа тощо) не ковтай.
    """
    raise NotImplementedError
