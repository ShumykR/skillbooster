"""Завдання №153: Adapter / Anti-corruption layer.

Два платіжні провайдери віддають різні формати. Решта коду має працювати лише з доменною моделлю
`PaymentResult`, ніколи не бачити «чужих» полів і не падати з `KeyError`.

Провайдер "alpha":
    {"id": "ch_1", "status": "succeeded" | "failed" | "processing", "amount": 1250, "currency": "usd"}
    `amount` це цілі копійки (int >= 0, не bool).
Провайдер "beta":
    {"txn": "B-77", "state": "APPROVED" | "DECLINED" | "WAITING", "total": "12.50", "cur": "UAH"}
    `total` це десятковий рядок: цифри 0-9, необов'язково `.` і 1-2 цифри після неї ("12", "12.5", "0.05");
    усе інше (мінус, пробіли, експонента, ".5", "12.", "12.505", не-ASCII цифри) це помилка контракту.

Доменні статуси: "paid", "failed", "pending" (succeeded/APPROVED -> paid, failed/DECLINED -> failed,
processing/WAITING -> pending). НЕВІДОМИЙ статус це ProviderContractError, і ніколи не "paid" (fail closed).

`adapt(provider, payload) -> PaymentResult`
    * невідомий провайдер: UnknownProvider (підклас KeyError);
    * payload не dict, бракує поля, поле не того типу, порожній id, невідомий статус, валюта не з 3 латинських
      літер: ProviderContractError (підклас ValueError). Ніяких KeyError/TypeError назовні;
    * валюта приводиться до верхнього регістру; зайві поля в payload ігноруються.

`Gateway(fetch)`, де `fetch(provider, ref) -> dict` ходить у мережу (у тестах підмінений).
    `status(provider, ref) -> PaymentResult`:
    * невідомий провайдер: UnknownProvider ДО звернення до fetch;
    * `OSError` (у тому числі TimeoutError, ConnectionError) з fetch стає `ProviderUnavailable`
      (оригінал у `__cause__`); інші винятки (наприклад, баги) летять далі без змін;
    * id у відповіді має збігатися з `ref`, інакше ProviderContractError (чужа відповідь).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentResult:
    provider_id: str
    status: str  # "paid" | "failed" | "pending"
    amount_cents: int
    currency: str


class UnknownProvider(KeyError):
    pass


class ProviderContractError(ValueError):
    pass


class ProviderUnavailable(Exception):
    pass


def adapt(provider: str, payload: dict) -> PaymentResult:
    raise NotImplementedError


class Gateway:
    def __init__(self, fetch):
        self._fetch = fetch

    def status(self, provider: str, ref: str) -> PaymentResult:
        raise NotImplementedError
