from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer

from solution import audit_app, audit_openapi

bearer = HTTPBearer()


def require_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    return {"token": creds.credentials}


def require_admin(user=Depends(require_user)):
    return user


def require_scope(user=Depends(require_admin)):
    return user


def log_request():
    return None


def header_only_auth(authorization: str | None = Header(default=None)):
    # перевіряє вручну, але OpenAPI про це не знає
    if not authorization:
        raise HTTPException(401)
    return authorization


# --- audit_openapi на ручних специфікаціях ---------------------------------------------------------------

def op(**kw):
    return {"responses": {}, **kw}


def test_empty_specs():
    assert audit_openapi({}) == []
    assert audit_openapi({"paths": {}}) == []
    assert audit_openapi({"paths": None}) == []


def test_operation_without_security_is_unprotected():
    spec = {"paths": {"/items": {"get": op()}}}
    assert audit_openapi(spec) == ["UNPROTECTED GET /items"]


def test_operation_with_security_is_protected():
    spec = {"paths": {"/items": {"get": op(security=[{"bearer": []}])}}}
    assert audit_openapi(spec) == []


def test_global_security_applies_to_operations_without_their_own():
    spec = {"security": [{"bearer": []}], "paths": {"/a": {"get": op()}, "/b": {"post": op()}}}
    assert audit_openapi(spec) == []


def test_operation_security_overrides_global():
    spec = {"security": [{"bearer": []}], "paths": {"/open": {"get": op(security=[])}, "/ok": {"get": op()}}}
    assert audit_openapi(spec) == ["UNPROTECTED GET /open"]


def test_optional_auth_is_not_protection():
    spec = {"paths": {
        "/a": {"get": op(security=[{}])},
        "/b": {"get": op(security=[{}, {"bearer": []}])},
        "/c": {"get": op(security=[{"bearer": []}, {}])},
        "/d": {"get": op(security=[{"bearer": []}, {"apikey": []}])},
    }}
    assert audit_openapi(spec) == ["UNPROTECTED GET /a", "UNPROTECTED GET /b", "UNPROTECTED GET /c"]


def test_global_optional_auth_is_not_protection():
    spec = {"security": [{}], "paths": {"/a": {"get": op()}}}
    assert audit_openapi(spec) == ["UNPROTECTED GET /a"]


def test_each_method_is_judged_separately_and_uppercased():
    spec = {"paths": {"/r": {"get": op(), "put": op(security=[{"b": []}]), "DELETE": op(), "Patch": op()}}}
    assert audit_openapi(spec) == ["UNPROTECTED DELETE /r", "UNPROTECTED GET /r", "UNPROTECTED PATCH /r"]


def test_non_method_keys_are_ignored():
    spec = {"paths": {"/r": {
        "parameters": [{"name": "id", "in": "query"}], "summary": "s", "description": "d", "servers": [], "x-internal": {},
        "$ref": "#/x", "get": op(security=[{"b": []}]),
    }}}
    assert audit_openapi(spec) == []


def test_all_http_methods_are_recognised():
    spec = {"paths": {"/m": {m: op() for m in ["get", "put", "post", "delete", "options", "head", "patch", "trace"]}}}
    assert len(audit_openapi(spec)) == 8


def test_public_allowlist_uses_template_paths_and_exact_methods():
    spec = {"paths": {"/files/{file_id}": {"get": op(), "delete": op()}, "/health": {"get": op()}}}
    assert audit_openapi(spec, public={"GET /health", "GET /files/{file_id}"}) == ["UNPROTECTED DELETE /files/{file_id}"]


def test_stale_entries_are_reported():
    spec = {"paths": {"/health": {"get": op()}}}
    assert audit_openapi(spec, public={"GET /health", "GET /removed", "POST /health", "GET /files/1"}) == [
        "STALE GET /files/1", "STALE GET /removed", "STALE POST /health"]


def test_public_entry_for_protected_operation_is_not_stale_or_error():
    spec = {"paths": {"/me": {"get": op(security=[{"b": []}])}}}
    assert audit_openapi(spec, public=["GET /me"]) == []


def test_result_is_sorted_and_public_may_be_any_iterable():
    spec = {"paths": {"/z": {"get": op()}, "/a": {"get": op()}, "/m": {"get": op()}}}
    assert audit_openapi(spec, public=(p for p in ["GET /gone"])) == [
        "STALE GET /gone", "UNPROTECTED GET /a", "UNPROTECTED GET /m", "UNPROTECTED GET /z"]


def test_spec_is_not_modified():
    spec = {"security": [{"b": []}], "paths": {"/a": {"get": op()}}}
    import copy
    before = copy.deepcopy(spec)
    audit_openapi(spec, public=["GET /x"])
    assert spec == before


# --- audit_app на справжніх застосунках FastAPI -------------------------------------------------------------------

def test_empty_app_has_no_findings():
    assert audit_app(FastAPI()) == []


def test_unprotected_route_is_reported():
    app = FastAPI()

    @app.get("/items")
    def items():
        return []

    assert audit_app(app) == ["UNPROTECTED GET /items"]


def test_protected_by_parameter_dependency():
    app = FastAPI()

    @app.get("/me")
    def me(user=Depends(require_user)):
        return user

    assert audit_app(app) == []


def test_protected_by_decorator_dependencies():
    app = FastAPI()

    @app.get("/me", dependencies=[Depends(require_user)])
    def me():
        return {}

    assert audit_app(app) == []


def test_protected_transitively():
    app = FastAPI()

    @app.get("/admin")
    def admin(user=Depends(require_admin)):
        return user

    @app.get("/deep")
    def deep(user=Depends(require_scope)):
        return user

    assert audit_app(app) == []


def test_security_helper_with_scopes():
    app = FastAPI()

    @app.get("/s")
    def s(user=Security(require_user, scopes=["read"])):
        return user

    assert audit_app(app) == []


def test_unrelated_dependencies_do_not_protect():
    app = FastAPI()

    @app.get("/a", dependencies=[Depends(log_request)])
    def a():
        return 1

    assert audit_app(app) == ["UNPROTECTED GET /a"]


def test_manual_header_check_is_invisible_to_openapi_and_gets_reported():
    app = FastAPI()

    @app.get("/manual")
    def manual(token=Depends(header_only_auth)):
        return token

    assert audit_app(app) == ["UNPROTECTED GET /manual"]
    assert audit_app(app, public={"GET /manual"}) == []  # свідомий виняток, поки перейдете на схему безпеки


def test_router_level_dependencies_cover_all_its_routes():
    app = FastAPI()
    router = APIRouter(prefix="/v1", dependencies=[Depends(require_user)])

    @router.get("/a")
    def a():
        return 1

    @router.post("/b")
    def b():
        return 2

    app.include_router(router)
    assert audit_app(app) == []


def test_include_router_dependencies_cover_routes():
    app = FastAPI()
    router = APIRouter()

    @router.get("/a")
    def a():
        return 1

    app.include_router(router, prefix="/api", dependencies=[Depends(require_user)])
    assert audit_app(app) == []


def test_app_level_dependencies_cover_everything():
    app = FastAPI(dependencies=[Depends(require_user)])

    @app.get("/a")
    def a():
        return 1

    @app.delete("/b")
    def b():
        return 2

    assert audit_app(app) == []


def test_only_the_forgotten_route_of_a_mixed_router_is_reported():
    app = FastAPI()
    router = APIRouter(prefix="/orders")

    @router.get("")
    def list_orders(user=Depends(require_user)):
        return []

    @router.get("/{order_id}")
    def get_order(order_id: int):  # забули Depends
        return {}

    app.include_router(router)
    assert audit_app(app) == ["UNPROTECTED GET /orders/{order_id}"]


def test_prefix_is_part_of_reported_path_and_methods_are_separate():
    app = FastAPI()
    router = APIRouter()

    @router.api_route("/x", methods=["GET", "POST"])
    def x():
        return 1

    app.include_router(router, prefix="/api/v2")
    assert audit_app(app) == ["UNPROTECTED GET /api/v2/x", "UNPROTECTED POST /api/v2/x"]


def test_other_security_scheme_classes():
    oauth2 = OAuth2PasswordBearer(tokenUrl="token")
    key = APIKeyHeader(name="X-API-Key")
    app = FastAPI()

    @app.get("/o")
    def o(token: str = Depends(oauth2)):
        return token

    @app.get("/k", dependencies=[Depends(key)])
    def k():
        return 1

    @app.get("/open")
    def open_():
        return 1

    assert audit_app(app) == ["UNPROTECTED GET /open"]


def test_public_allowlist_and_stale_on_real_app():
    app = FastAPI()

    @app.get("/health")
    def health():
        return "ok"

    @app.get("/me")
    def me(user=Depends(require_user)):
        return user

    assert audit_app(app, public={"GET /health"}) == []
    assert audit_app(app, public={"GET /health", "GET /gone"}) == ["STALE GET /gone"]


def test_mounted_subapp_is_checked_with_prefix():
    app = FastAPI()
    sub = FastAPI()

    @sub.get("/ping")
    def ping():
        return 1

    @sub.get("/me")
    def me(user=Depends(require_user)):
        return user

    app.mount("/internal", sub)
    assert audit_app(app) == ["UNPROTECTED GET /internal/ping"]
    assert audit_app(app, public={"GET /internal/ping"}) == []


def test_global_security_of_subapp_applies_only_to_it():
    app = FastAPI()
    sub = FastAPI(dependencies=[Depends(require_user)])

    @sub.get("/a")
    def a():
        return 1

    @app.get("/open")
    def open_():
        return 1

    app.mount("/secure", sub)
    assert audit_app(app) == ["UNPROTECTED GET /open"]


def test_nested_mounts():
    app, mid, leaf = FastAPI(), FastAPI(), FastAPI()

    @leaf.get("/deep")
    def deep():
        return 1

    mid.mount("/leaf", leaf)
    app.mount("/mid", mid)
    assert audit_app(app) == ["UNPROTECTED GET /mid/leaf/deep"]


def test_docs_routes_are_not_reported_and_non_fastapi_mounts_are_skipped():
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    app = FastAPI()
    app.mount("/plain", Starlette(routes=[Route("/x", lambda r: PlainTextResponse("x"))]))
    assert audit_app(app) == []


def test_routes_excluded_from_schema_are_invisible():
    app = FastAPI()

    @app.get("/secret-admin", include_in_schema=False)
    def secret():
        return 1

    assert audit_app(app) == []  # обмеження підходу: те, чого немає в OpenAPI, цим тестом не видно
