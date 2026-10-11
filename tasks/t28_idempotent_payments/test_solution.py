import threading

from fastapi.testclient import TestClient

from solution import create_app

BODY = {"amount": 1000, "currency": "USD"}


def client():
    app = create_app()
    return app, TestClient(app)


def test_missing_key_is_400():
    app, c = client()
    r = c.post("/payments", json=BODY)
    assert r.status_code == 400
    assert app.state.ledger == []


def test_first_call_creates_payment():
    app, c = client()
    r = c.post("/payments", json=BODY, headers={"Idempotency-Key": "k1"})
    assert r.status_code == 201
    assert r.json()["amount"] == 1000
    assert len(app.state.ledger) == 1


def test_retry_returns_same_payment_without_new_charge():
    app, c = client()
    h = {"Idempotency-Key": "k1"}
    first = c.post("/payments", json=BODY, headers=h)
    second = c.post("/payments", json=BODY, headers=h)
    assert second.status_code == 201
    assert second.json() == first.json()
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert "Idempotent-Replayed" not in first.headers
    assert len(app.state.ledger) == 1


def test_same_key_different_body_is_422():
    app, c = client()
    h = {"Idempotency-Key": "k1"}
    c.post("/payments", json=BODY, headers=h)
    r = c.post("/payments", json={"amount": 2000, "currency": "USD"}, headers=h)
    assert r.status_code == 422
    assert len(app.state.ledger) == 1


def test_different_keys_create_different_payments():
    app, c = client()
    a = c.post("/payments", json=BODY, headers={"Idempotency-Key": "a"}).json()
    b = c.post("/payments", json=BODY, headers={"Idempotency-Key": "b"}).json()
    assert a["id"] != b["id"]
    assert len(app.state.ledger) == 2


def test_concurrent_retries_charge_once():
    app, c = client()
    results = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        r = c.post("/payments", json=BODY, headers={"Idempotency-Key": "race"})
        results.append((r.status_code, r.json()["id"]))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(app.state.ledger) == 1, "гонка: платіж створено кілька разів"
    assert {code for code, _ in results} == {201}
    assert len({pid for _, pid in results}) == 1
