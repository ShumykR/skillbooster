"""Завдання №28: Idempotency key для платежів.

Зараз кожен POST /payments списує гроші знову, навіть якщо клієнт просто
повторив запит через таймаут. Виправ це.
"""
import itertools
import time

from fastapi import FastAPI, Header
from pydantic import BaseModel


class PaymentIn(BaseModel):
    amount: int
    currency: str


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.ledger = []  # кожен елемент = одне реальне списання
    ids = itertools.count(1)

    @app.post("/payments", status_code=201)
    def create_payment(body: PaymentIn, idempotency_key: str | None = Header(default=None)):
        time.sleep(0.05)  # виклик платіжного провайдера
        payment = {"id": next(ids), "amount": body.amount, "currency": body.currency}
        app.state.ledger.append(payment)
        return payment

    return app
