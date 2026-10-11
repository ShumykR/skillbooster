import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from solution import AppError, install_error_handlers

SECRET = "postgres://admin:s3cr3t-p4ss@db.internal/prod"


class Item(BaseModel):
    name: str
    price: float = Field(gt=0)


def build_app():
    app = FastAPI()

    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        return {"id": item_id}

    @app.post("/items")
    def create_item(item: Item):
        return item

    @app.get("/forbidden")
    def forbidden():
        raise HTTPException(403, "no access to this resource", headers={"X-Reason": "role"})

    @app.get("/conflict")
    def conflict():
        raise AppError(409, "Conflict", "item already exists", type="https://errors.example.com/conflict")

    @app.get("/bare-app-error")
    def bare():
        raise AppError(400, "Bad Request")

    @app.get("/boom")
    def boom():
        raise RuntimeError(f"cannot connect to {SECRET}")

    @app.get("/teapot")
    def teapot():
        raise HTTPException(418)

    install_error_handlers(app)
    return app


@pytest.fixture
def client():
    return TestClient(build_app(), raise_server_exceptions=False)


def assert_problem(resp, status, title):
    assert resp.status_code == status
    assert resp.headers["content-type"].split(";")[0] == "application/problem+json"
    body = resp.json()
    assert body["status"] == status
    assert body["title"] == title
    assert body["type"] == "about:blank" or body["type"].startswith("http")
    assert isinstance(body["instance"], str) and body["instance"].startswith("/")
    return body


def test_success_responses_are_untouched(client):
    r = client.get("/items/5")
    assert r.status_code == 200 and r.json() == {"id": 5}
    assert r.headers["content-type"].startswith("application/json")


def test_unknown_route_is_problem_404(client):
    body = assert_problem(client.get("/nope"), 404, "Not Found")
    assert body["instance"] == "/nope"
    assert body["detail"] == "Not Found"


def test_method_not_allowed_is_problem_405(client):
    body = assert_problem(client.delete("/items/1"), 405, "Method Not Allowed")
    assert body["instance"] == "/items/1"


def test_http_exception_keeps_detail_and_headers(client):
    r = client.get("/forbidden")
    body = assert_problem(r, 403, "Forbidden")
    assert body["detail"] == "no access to this resource"
    assert r.headers["x-reason"] == "role"
    assert body["instance"] == "/forbidden"


def test_http_exception_without_detail_uses_status_phrase(client):
    body = assert_problem(client.get("/teapot"), 418, "I'm a Teapot")
    assert body["detail"] == "I'm a Teapot"


def test_validation_error_path_param(client):
    r = client.get("/items/abc")
    body = assert_problem(r, 422, "Validation Error")
    assert body["detail"] == "Request validation failed"
    assert len(body["errors"]) == 1
    assert body["errors"][0]["loc"] == ["path", "item_id"]
    assert isinstance(body["errors"][0]["msg"], str)


def test_validation_error_body_lists_every_field(client):
    r = client.post("/items", json={"price": -1})
    body = assert_problem(r, 422, "Validation Error")
    locs = sorted(tuple(e["loc"]) for e in body["errors"])
    assert locs == [("body", "name"), ("body", "price")]


def test_validation_errors_contain_only_loc_and_msg(client):
    r = client.post("/items", json={"name": "x", "price": "not-a-number-secret-token"})
    body = assert_problem(r, 422, "Validation Error")
    for err in body["errors"]:
        assert set(err) == {"loc", "msg"}
    assert "not-a-number-secret-token" not in r.text  # клієнтський ввід не відбивається


def test_validation_error_for_malformed_json(client):
    r = client.post("/items", content=b"{broken", headers={"content-type": "application/json"})
    body = assert_problem(r, 422, "Validation Error")
    assert all(set(e) == {"loc", "msg"} for e in body["errors"])


def test_app_error_full(client):
    body = assert_problem(client.get("/conflict"), 409, "Conflict")
    assert body["detail"] == "item already exists"
    assert body["type"] == "https://errors.example.com/conflict"
    assert body["instance"] == "/conflict"


def test_app_error_defaults(client):
    body = assert_problem(client.get("/bare-app-error"), 400, "Bad Request")
    assert body["type"] == "about:blank"
    assert body.get("detail") is None


def test_unhandled_exception_is_generic_500(client):
    r = client.get("/boom")
    body = assert_problem(r, 500, "Internal Server Error")
    assert body["detail"] == "An unexpected error occurred"
    assert "s3cr3t" not in r.text and "postgres" not in r.text
    assert "Traceback" not in r.text and "RuntimeError" not in r.text


def test_every_error_has_the_same_core_fields(client):
    responses = [
        client.get("/nope"), client.delete("/items/1"), client.get("/forbidden"), client.get("/items/x"),
        client.get("/conflict"), client.get("/boom"),
    ]
    for r in responses:
        body = r.json()
        assert {"type", "title", "status", "detail", "instance"} <= set(body)
        assert body["status"] == r.status_code


def test_app_keeps_working_after_an_error(client):
    client.get("/boom")
    assert client.get("/items/1").status_code == 200
