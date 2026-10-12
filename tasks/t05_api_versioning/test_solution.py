import pytest
from fastapi.testclient import TestClient

from solution import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


V1 = {"name": "Ann", "phone": "+380501234567"}
V2 = {"name": "Ann", "phone": {"country_code": "+380", "number": "501234567"}}


def test_v1_old_client_contract(client):
    r = client.post("/v1/users", json={**V1, "nickname": "legacy-extra-field"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "name": "Ann", "phone": "+380501234567"}
    assert "nickname" not in r.json()


def test_v1_responses_are_marked_deprecated(client):
    r = client.post("/v1/users", json=V1)
    assert r.headers.get("Deprecation") == "true"
    assert r.headers.get("Sunset")
    assert client.get("/v1/users/1").headers.get("Deprecation") == "true"
    assert "Deprecation" not in client.post("/v2/users", json=V2).headers


def test_v2_contract(client):
    r = client.post("/v2/users", json=V2)
    assert r.status_code == 201
    assert r.json() == {"id": 1, "name": "Ann", "phone": {"country_code": "+380", "number": "501234567"}}


def test_same_user_is_visible_through_both_versions(client):
    client.post("/v1/users", json=V1)
    client.post("/v2/users", json={"name": "Bob", "phone": {"country_code": "+1", "number": "2025550123"}})
    assert client.get("/v2/users/1").json()["phone"] == {"country_code": "+380", "number": "501234567"}
    assert client.get("/v1/users/2").json()["phone"] == "+12025550123"


def test_v2_is_strict_about_extra_fields_and_types(client):
    assert client.post("/v2/users", json={**V2, "nickname": "x"}).status_code == 422
    assert client.post("/v2/users", json={"name": "Ann", "phone": "+380501234567"}).status_code == 422
    assert client.post("/v2/users", json={"name": "Ann", "phone": {**V2["phone"], "extra": 1}}).status_code == 422
    assert client.post("/v2/users", json={"name": 123, "phone": V2["phone"]}).status_code == 422


@pytest.mark.parametrize("phone", [
    {"country_code": "380", "number": "501234567"},
    {"country_code": "+3800", "number": "501234567"},
    {"country_code": "+380", "number": "50-123"},
    {"country_code": "+380", "number": "123"},
    {"country_code": "+380", "number": "1" * 13},
])
def test_v2_validates_phone(client, phone):
    assert client.post("/v2/users", json={"name": "Ann", "phone": phone}).status_code == 422


@pytest.mark.parametrize("phone", ["0501234567", "+38abc", "+", "", "+380 50 123", "+99912345678", "+380123"])
def test_v1_still_validates_phone(client, phone):
    assert client.post("/v1/users", json={"name": "Ann", "phone": phone}).status_code == 422


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_name_rules_in_both_versions(client, version):
    phone = V1["phone"] if version == "v1" else V2["phone"]
    assert client.post(f"/{version}/users", json={"name": "   ", "phone": phone}).status_code == 422
    assert client.post(f"/{version}/users", json={"name": "x" * 51, "phone": phone}).status_code == 422
    r = client.post(f"/{version}/users", json={"name": "  Ann  ", "phone": phone})
    assert r.status_code == 201 and r.json()["name"] == "Ann"


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_unknown_user_is_404(client, version):
    assert client.get(f"/{version}/users/99").status_code == 404
