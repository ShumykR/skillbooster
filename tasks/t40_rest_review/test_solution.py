import copy

import pytest

from solution import review_openapi

PROBLEM = {"application/problem+json": {"schema": {"type": "object"}}}


def err(*codes):
    return {c: {"description": "error", "content": PROBLEM} for c in codes}


def ok(code="200"):
    return {code: {"description": "ok"}}


PAGING = [{"name": "limit", "in": "query"}]


def good_spec():
    return {
        "openapi": "3.0.3",
        "security": [{"bearer": []}],
        "paths": {
            "/v1/users": {
                "get": {"parameters": PAGING, "responses": {**ok(), **err("400")}},
                "post": {"responses": {**ok("201"), **err("422")}},
            },
            "/v1/users/{id}": {
                "parameters": [{"name": "id", "in": "path", "required": True}],
                "get": {"responses": {**ok(), **err("404")}},
                "put": {"responses": {**ok(), **err("404")}},
                "delete": {"responses": {**ok("204"), **err("404")}},
            },
            "/v1/health": {"get": {"security": [], "responses": ok()}},
        },
    }


def test_clean_spec_has_no_findings():
    assert review_openapi(good_spec()) == []


def test_empty_spec():
    assert review_openapi({"openapi": "3.0.3", "paths": {}}) == []


def mutate(fn):
    spec = copy.deepcopy(good_spec())
    fn(spec)
    return review_openapi(spec)


def rename(spec, old, new):
    spec["paths"][new] = spec["paths"].pop(old)


@pytest.mark.parametrize("path", ["/v1/getUsers", "/v1/users/create", "/v1/create-user", "/v1/list", "/v1/delete_item"])
def test_r001_verbs_in_path(path):
    findings = mutate(lambda s: s["paths"].__setitem__(path, {"get": {"parameters": PAGING, "responses": {**ok(), **err("400")}}}))
    assert f"R001 {path}" in findings


@pytest.mark.parametrize("path", ["/v1/settings", "/v1/listings", "/v1/address", "/v1/users/{id}/setup"])
def test_r001_does_not_flag_words_that_merely_start_like_verbs(path):
    findings = mutate(lambda s: s["paths"].__setitem__(path, {"get": {"parameters": PAGING, "responses": {**ok(), **err("400")}}}))
    assert not [f for f in findings if f.startswith("R001")]


def test_r002_case_and_underscores():
    findings = mutate(lambda s: s["paths"].__setitem__("/v1/userProfiles/{id}", {"parameters": [{"name": "id", "in": "path"}], "get": {"responses": {**ok(), **err("404")}}}))
    assert findings == ["R002 /v1/userProfiles/{id}"]
    findings = mutate(lambda s: s["paths"].__setitem__("/v1/user_roles", {"post": {"responses": {**ok("201"), **err("422")}}}))
    assert findings == ["R002 /v1/user_roles"]


def test_r002_ignores_path_parameter_names():
    findings = mutate(lambda s: s["paths"].__setitem__("/v1/files/{fileId}", {"get": {"responses": {**ok(), **err("404")}}}))
    assert findings == []


def test_r003_post_on_collection_must_say_201_or_202():
    def f(s):
        s["paths"]["/v1/users"]["post"]["responses"] = {**ok("200"), **err("422")}

    assert mutate(f) == ["R003 POST /v1/users"]

    def g(s):
        s["paths"]["/v1/users"]["post"]["responses"] = {**ok("202"), **err("422")}

    assert mutate(g) == []


def test_r003_post_on_non_collection_actions_is_fine():
    def f(s):
        s["paths"]["/v1/users/{id}/activate"] = {"post": {"responses": {**ok("200"), **err("404")}}}

    assert mutate(f) == []


def test_r004_delete_needs_204():
    def f(s):
        s["paths"]["/v1/users/{id}"]["delete"]["responses"] = {**ok("200"), **err("404")}

    assert mutate(f) == ["R004 DELETE /v1/users/{id}"]


def test_r005_get_with_body():
    def f(s):
        s["paths"]["/v1/users"]["get"]["requestBody"] = {"content": {"application/json": {}}}

    assert mutate(f) == ["R005 GET /v1/users"]


def test_r006_item_operations_need_404():
    def f(s):
        del s["paths"]["/v1/users/{id}"]["get"]["responses"]["404"]
        del s["paths"]["/v1/users/{id}"]["delete"]["responses"]["404"]

    assert mutate(f) == ["R006 DELETE /v1/users/{id}", "R006 GET /v1/users/{id}"]


def test_r006_not_required_for_post_on_collection():
    def f(s):
        s["paths"]["/v1/users"]["post"]["responses"].pop("404", None)

    assert mutate(f) == []


def test_r007_collection_get_needs_pagination():
    def f(s):
        s["paths"]["/v1/users"]["get"]["parameters"] = [{"name": "q", "in": "query"}]

    assert mutate(f) == ["R007 GET /v1/users"]


def test_r007_accepts_path_level_and_ref_parameters():
    def f(s):
        s["components"] = {"parameters": {"PageCursor": {"name": "cursor", "in": "query"}}}
        s["paths"]["/v1/users"]["get"]["parameters"] = [{"$ref": "#/components/parameters/PageCursor"}]

    assert mutate(f) == []

    def g(s):
        s["paths"]["/v1/users"]["parameters"] = [{"name": "page", "in": "query"}]
        s["paths"]["/v1/users"]["get"]["parameters"] = []

    assert mutate(g) == []


def test_r007_not_required_outside_collections():
    def f(s):
        s["paths"]["/v1/reports"] = {"get": {"responses": {**ok(), **err("400")}}}  # немає /v1/reports/{id}: це не колекція

    assert mutate(f) == []


def test_r008_errors_must_be_problem_json():
    def f(s):
        s["paths"]["/v1/users"]["get"]["responses"]["400"] = {"description": "bad", "content": {"application/json": {}}}
        s["paths"]["/v1/users"]["post"]["responses"]["422"] = {"description": "no content"}
        s["paths"]["/v1/users"]["post"]["responses"]["default"] = {"description": "x", "content": {"text/plain": {}}}

    assert mutate(f) == [
        "R008 GET /v1/users 400",
        "R008 POST /v1/users 422",
        "R008 POST /v1/users default",
    ]


def test_r009_mutations_need_security():
    def f(s):
        del s["security"]

    assert mutate(f) == [
        "R009 DELETE /v1/users/{id}",
        "R009 POST /v1/users",
        "R009 PUT /v1/users/{id}",
    ]


def test_r009_operation_security_overrides_global():
    def f(s):
        s["paths"]["/v1/users"]["post"]["security"] = []  # явне «без автентифікації»

    assert mutate(f) == ["R009 POST /v1/users"]

    def g(s):
        del s["security"]
        for item in ("/v1/users", "/v1/users/{id}"):
            for m in ("post", "put", "delete"):
                if m in s["paths"][item]:
                    s["paths"][item][m]["security"] = [{"bearer": []}]

    assert mutate(g) == []


def test_r010_trailing_slash():
    findings = mutate(lambda s: s["paths"].__setitem__("/v1/tags/", {"get": {"responses": {**ok(), **err("400")}}}))
    assert findings == ["R010 /v1/tags/"]


def test_r011_version_prefix():
    def f(s):
        rename(s, "/v1/health", "/health")
        s["paths"]["/v2beta/things"] = {"get": {"responses": ok()}}

    assert mutate(f) == ["R011 /health", "R011 /v2beta/things"]


def test_findings_are_sorted_and_unique():
    spec = {
        "openapi": "3.0.3",
        "paths": {
            "/getUsers/": {"get": {"requestBody": {}, "responses": {"200": {"description": "ok"}, "500": {"description": "boom"}}}},
        },
    }
    findings = review_openapi(spec)
    assert findings == sorted(set(findings))
    assert findings == [
        "R001 /getUsers/",
        "R002 /getUsers/",
        "R005 GET /getUsers/",
        "R008 GET /getUsers/ 500",
        "R010 /getUsers/",
        "R011 /getUsers/",
    ]


def test_does_not_mutate_input():
    spec = good_spec()
    snapshot = copy.deepcopy(spec)
    review_openapi(spec)
    assert spec == snapshot
