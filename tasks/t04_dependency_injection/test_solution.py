import socket

import pytest
from fastapi.testclient import TestClient

import solution
from solution import RateUnavailable, app, get_history, get_rates


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Будь-яка спроба вийти в мережу провалює тест: це і є критерій завдання."""

    real_connect, real_getaddrinfo = socket.socket.connect, socket.getaddrinfo
    local = {"127.0.0.1", "::1", "localhost", None}

    def guarded_connect(self, address, *args, **kwargs):
        if isinstance(address, tuple) and address[0] not in local:  # локальні socketpair самого asyncio дозволені
            raise AssertionError(f"тест звернувся до мережі ({address[0]}): підміни залежність через dependency_overrides")
        return real_connect(self, address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in local:
            raise AssertionError(f"тест звернувся до мережі (DNS {host}): підміни залежність через dependency_overrides")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


@pytest.fixture(autouse=True)
def clean_overrides():
    yield
    app.dependency_overrides.clear()


class FakeRates:
    def __init__(self, table):
        self.table = table
        self.calls = []

    def get_rate(self, currency):
        self.calls.append(currency)
        if currency not in self.table:
            raise RateUnavailable(currency)
        return self.table[currency]


class FakeHistory:
    def __init__(self):
        self.records = []

    def add(self, record):
        self.records.append(record)

    def all(self):
        return list(self.records)


@pytest.fixture
def client():
    return TestClient(app)


def use(rates, history):
    app.dependency_overrides[get_rates] = lambda: rates
    app.dependency_overrides[get_history] = lambda: history


def test_convert_uses_injected_rate(client):
    rates, history = FakeRates({"EUR": 0.5}), FakeHistory()
    use(rates, history)
    r = client.get("/convert", params={"amount": 10, "currency": "EUR"})
    assert r.status_code == 200
    assert r.json() == {"amount": 10.0, "currency": "EUR", "rate": 0.5, "converted": 5.0}
    assert rates.calls == ["EUR"]


def test_convert_writes_to_injected_history_not_to_a_global(client):
    first, second = FakeHistory(), FakeHistory()
    use(FakeRates({"EUR": 2.0}), first)
    client.get("/convert", params={"amount": 1})
    assert len(first.records) == 1
    use(FakeRates({"EUR": 2.0}), second)
    assert client.get("/history").json() == []  # інша історія: стан не протікає між тестами
    assert second.records == []


def test_history_comes_from_injected_object_in_order(client):
    history = FakeHistory()
    use(FakeRates({"EUR": 1.0, "USD": 2.0}), history)
    client.get("/convert", params={"amount": 1, "currency": "EUR"})
    client.get("/convert", params={"amount": 3, "currency": "USD"})
    assert [h["currency"] for h in client.get("/history").json()] == ["EUR", "USD"]


def test_unknown_currency_is_503_and_not_recorded(client):
    history = FakeHistory()
    use(FakeRates({}), history)
    r = client.get("/convert", params={"amount": 5, "currency": "XXX"})
    assert r.status_code == 503
    assert history.records == []


@pytest.mark.parametrize("amount", ["0", "-3", "abc"])
def test_invalid_amount_is_422_without_calling_rates(client, amount):
    rates = FakeRates({"EUR": 1.0})
    use(rates, FakeHistory())
    assert client.get("/convert", params={"amount": amount}).status_code == 422
    assert rates.calls == []


def test_default_dependencies_are_real_objects_built_without_network():
    rates, history = get_rates(), get_history()
    assert callable(rates.get_rate)
    history.add({"x": 1})
    assert history.all()[-1] == {"x": 1}


def test_history_dependency_is_shared_between_requests_by_default():
    # без підміни одна й та сама історія живе між запитами одного застосунку (але не глобальний список модуля)
    assert get_history() is get_history()
    assert not hasattr(solution, "_HISTORY"), "глобальний список історії має зникнути"
