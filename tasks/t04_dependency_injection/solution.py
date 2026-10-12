"""Завдання №4: Dependency injection та тестування.

Конвертер валют: бере курс із зовнішнього API і веде історію конвертацій.
Зараз курс береться прямим HTTP-викликом, а історія лежить у глобальному списку,
тому ендпоінти не перевірити без мережі, а тести впливають один на одного.

Перепиши на залежності FastAPI (`Depends`):
- `get_rates()` повертає об'єкт з методом `get_rate(currency) -> float`
  (кидає `RateUnavailable`, якщо курсу немає);
- `get_history()` повертає об'єкт з методами `add(record: dict)` і `all() -> list[dict]`;
- обидва ендпоінти отримують їх через `Depends`, а не з глобальних змінних чи прямих викликів.

Контракт API не змінюється:
- GET /convert?amount=10&currency=EUR -> {"amount": 10.0, "currency": "EUR", "rate": r, "converted": amount * r}
  і запис у історію; amount <= 0 -> 422; курсу немає -> 503;
- GET /history -> список записів у порядку додавання.
"""
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query  # noqa: F401  (Depends знадобиться)

RATES_URL = "https://rates.example.invalid/v1/latest"
_HISTORY: list[dict] = []  # глобальний стан: спільний для всіх запитів і тестів

app = FastAPI()


class RateUnavailable(Exception):
    pass


class HttpRates:
    """Справжній клієнт курсів: ходить у мережу."""

    def get_rate(self, currency: str) -> float:
        raise NotImplementedError  # TODO: винеси сюди HTTP-виклик з /convert


class InMemoryHistory:
    def __init__(self) -> None:
        self._records: list[dict] = []

    def add(self, record: dict) -> None:
        self._records.append(record)

    def all(self) -> list[dict]:
        return list(self._records)


def get_rates():
    raise NotImplementedError  # TODO


def get_history():
    raise NotImplementedError  # TODO


@app.get("/convert")
def convert(amount: float = Query(gt=0), currency: str = "EUR"):
    resp = httpx.get(RATES_URL, params={"to": currency}, timeout=3)  # реальна мережа
    if resp.status_code != 200:
        raise HTTPException(status_code=503, detail="rate unavailable")
    rate = float(resp.json()["rate"])
    record = {"amount": amount, "currency": currency, "rate": rate, "converted": amount * rate}
    _HISTORY.append(record)
    return record


@app.get("/history")
def history():
    return list(_HISTORY)
