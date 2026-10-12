import copy

import pytest

from solution import accepts, diff_schemas, is_breaking, verify_contract

PROVIDER = {
    "GET /users/{id}": {
        "query": {"verbose": {"type": "bool", "required": False}},
        "responses": {
            200: {"id": {"type": "int", "required": True}, "name": {"type": "str", "required": True},
                  "email": {"type": "str", "required": False}, "score": {"type": "float", "required": True}},
            404: {"detail": {"type": "str", "required": True}},
        },
    },
    "POST /users": {
        "request": {"name": {"type": "str", "required": True}, "age": {"type": "number", "required": False}},
        "responses": {201: {"id": {"type": "int", "required": True}}, 422: {}},
    },
    "GET /health": {"responses": {200: {}}},
}


def vc(*interactions):
    return verify_contract(PROVIDER, list(interactions))


# ---------- accepts ------------------------------------------------------------------


@pytest.mark.parametrize("expected, actual, ok", [
    ("int", "int", True), ("str", "int", False), ("number", "int", True), ("number", "float", True), ("number", "str", False),
    ("int", "number", False), ("float", "int", False)])
def test_accepts(expected, actual, ok):
    assert accepts(expected, actual) is ok


# ---------- verify_contract ----------------------------------------------------------


def test_satisfied_contract_has_no_violations():
    assert vc({"endpoint": "GET /users/{id}", "query": ["verbose"], "status": 200, "response": {"id": "int", "name": "str", "score": "number"}},
              {"endpoint": "POST /users", "request": {"name": "str", "age": "int"}, "status": 201, "response": {"id": "int"}},
              {"endpoint": "GET /users/{id}", "status": 404, "response": {"detail": "str"}},
              {"endpoint": "GET /health", "status": 200}) == []


def test_missing_endpoint_skips_other_checks():
    assert vc({"endpoint": "DELETE /users/{id}", "query": ["x"], "status": 204, "response": {"a": "int"}}) == ["missing_endpoint:DELETE /users/{id}"]


def test_response_field_problems():
    got = vc({"endpoint": "GET /users/{id}", "status": 200, "response": {"id": "str", "phone": "str", "email": "str", "name": "str"}})
    assert got == ["missing_field:GET /users/{id}:200:phone", "optional_field:GET /users/{id}:200:email",
                   "type_mismatch:GET /users/{id}:200:id:str!=int"]


def test_optional_field_with_wrong_type_reports_both():
    got = vc({"endpoint": "GET /users/{id}", "status": 200, "response": {"email": "int"}})
    assert got == ["optional_field:GET /users/{id}:200:email", "type_mismatch:GET /users/{id}:200:email:int!=str"]


def test_missing_status_skips_response_checks():
    assert vc({"endpoint": "GET /users/{id}", "status": 500, "response": {"x": "int"}}) == ["missing_status:GET /users/{id}:500"]


def test_query_parameters():
    assert vc({"endpoint": "GET /users/{id}", "query": ["verbose", "expand"]}) == ["unknown_param:GET /users/{id}:expand"]


def test_request_body_problems():
    got = vc({"endpoint": "POST /users", "request": {"nick": "str", "age": "str"}, "status": 201})
    assert got == ["missing_required_request:POST /users:name", "type_mismatch:POST /users:request.age:str!=number",
                   "unknown_request_field:POST /users:nick"]


def test_provider_number_accepts_int_and_float_requests():
    assert vc({"endpoint": "POST /users", "request": {"name": "str", "age": "float"}}) == []
    assert vc({"endpoint": "POST /users", "request": {"name": "str"}}) == [], "необовʼязкове поле можна не надсилати"


def test_consumer_number_accepts_int_response():
    assert vc({"endpoint": "GET /users/{id}", "status": 200, "response": {"id": "number"}}) == []
    assert vc({"endpoint": "GET /users/{id}", "status": 200, "response": {"id": "float"}}) == ["type_mismatch:GET /users/{id}:200:id:float!=int"]


def test_violations_are_unique_and_sorted_across_interactions():
    bad = {"endpoint": "GET /users/{id}", "status": 200, "response": {"phone": "str"}}
    got = vc(bad, bad, {"endpoint": "GET /nope"}, {"endpoint": "GET /users/{id}", "query": ["zzz"]})
    assert got == sorted(set(got)) and len(got) == 3


def test_empty_contract_and_endpoint_without_optional_sections():
    assert vc() == []
    assert verify_contract({"GET /x": {"responses": {200: {}}}}, [{"endpoint": "GET /x", "status": 200}]) == []
    assert verify_contract({"GET /x": {}}, [{"endpoint": "GET /x", "status": 200}]) == ["missing_status:GET /x:200"]


# ---------- diff_schemas ---------------------------------------------------------------


def changed(mutate):
    new = copy.deepcopy(PROVIDER)
    mutate(new)
    return diff_schemas(PROVIDER, new)


def test_identical_schema_is_not_breaking():
    assert diff_schemas(PROVIDER, copy.deepcopy(PROVIDER)) == [] and is_breaking(PROVIDER, PROVIDER) is False


def test_removed_endpoint_and_status():
    assert changed(lambda s: s.pop("GET /health")) == ["removed_endpoint:GET /health"]
    assert changed(lambda s: s["GET /users/{id}"]["responses"].pop(404)) == ["removed_status:GET /users/{id}:404"]


def test_removed_field_type_change_and_optionality():
    assert changed(lambda s: s["GET /users/{id}"]["responses"][200].pop("name")) == ["removed_field:GET /users/{id}:200:name"]
    assert changed(lambda s: s["GET /users/{id}"]["responses"][200]["id"].update(type="str")) == ["type_changed:GET /users/{id}:200:id:int->str"]
    assert changed(lambda s: s["GET /users/{id}"]["responses"][200]["name"].update(required=False)) == ["became_optional:GET /users/{id}:200:name"]


def test_removed_field_is_not_reported_twice():
    def mutate(s):
        s["GET /users/{id}"]["responses"][200].pop("email")
    assert changed(mutate) == ["removed_field:GET /users/{id}:200:email"]


def test_request_changes():
    assert changed(lambda s: s["POST /users"]["request"].update(phone={"type": "str", "required": True})) == ["new_required_request:POST /users:phone"]
    assert changed(lambda s: s["POST /users"]["request"]["age"].update(required=True)) == ["new_required_request:POST /users:age"]
    assert changed(lambda s: s["POST /users"]["request"]["name"].update(type="int")) == ["request_type_changed:POST /users:name:str->int"]
    assert changed(lambda s: s["GET /users/{id}"]["query"].update(tenant={"type": "str", "required": True})) == ["new_required_param:GET /users/{id}:tenant"]


def test_compatible_changes_are_not_breaking():
    def mutate(s):
        s["GET /new"] = {"responses": {200: {}}}
        s["GET /users/{id}"]["responses"][200]["avatar"] = {"type": "str", "required": True}
        s["GET /users/{id}"]["responses"][200]["email"]["required"] = True
        s["GET /users/{id}"]["responses"][500] = {}
        s["POST /users"]["request"]["nick"] = {"type": "str", "required": False}
        s["POST /users"]["request"].pop("age")
        s["GET /users/{id}"]["query"]["page"] = {"type": "int", "required": False}
        s["GET /users/{id}"]["query"].pop("verbose")
    assert changed(mutate) == []


def test_already_required_request_field_is_not_new():
    assert changed(lambda s: s["POST /users"]["request"]["name"].update(type="str")) == []


def test_several_changes_are_sorted_and_the_removed_endpoint_hides_details():
    def mutate(s):
        s.pop("POST /users")
        s["GET /users/{id}"]["responses"][200].pop("score")
        s["GET /users/{id}"]["responses"][200]["id"]["type"] = "str"
    got = changed(mutate)
    assert got == ["removed_endpoint:POST /users", "removed_field:GET /users/{id}:200:score", "type_changed:GET /users/{id}:200:id:int->str"]
    assert is_breaking(PROVIDER, {}) is True


def test_a_contract_can_be_checked_against_a_new_version():
    contract = [{"endpoint": "GET /users/{id}", "status": 200, "response": {"id": "int", "name": "str"}}]
    new = copy.deepcopy(PROVIDER)
    new["GET /users/{id}"]["responses"][200]["name"]["type"] = "int"
    assert verify_contract(PROVIDER, contract) == []
    assert verify_contract(new, contract) == ["type_mismatch:GET /users/{id}:200:name:str!=int"]
