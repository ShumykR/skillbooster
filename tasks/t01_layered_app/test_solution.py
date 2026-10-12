"""Автоперевірка №1: і поведінка, і архітектура (напрямок залежностей між шарами)."""

import ast
import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PKG = Path(__file__).parent / "notes_app"
LAYERS = {"routers": "notes_app.routers", "services": "notes_app.services", "repositories": "notes_app.repositories"}
HTTP_LIBS = {"fastapi", "starlette"}
DB_LIBS = {"sqlite3", "sqlalchemy"}


def imports_of(path: Path) -> set[str]:
    """Усі імпортовані модулі файлу (повні шляхи: `os`, `notes_app.services.notes`, ...)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def layer_files(layer: str) -> list[Path]:
    return [p for p in (PKG / layer).glob("*.py") if p.name != "__init__.py"]


def uses(found: set[str], libs: set[str] | None = None, prefixes: set[str] | None = None) -> set[str]:
    bad = set()
    for name in found:
        if libs and name.split(".")[0] in libs:
            bad.add(name)
        if prefixes and any(name == p or name.startswith(p + ".") for p in prefixes):
            bad.add(name)
    return bad


# ---------- архітектура -------------------------------------------------------


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_exists(layer):
    assert layer_files(layer), f"notes_app/{layer}/ має містити модуль notes.py (і __init__.py)"
    assert (PKG / layer / "__init__.py").exists()


def test_router_has_no_sql_or_repository_imports():
    assert layer_files("routers"), "немає notes_app/routers/notes.py"
    for path in layer_files("routers"):
        bad = uses(imports_of(path), libs=DB_LIBS, prefixes={LAYERS["repositories"]})
        assert not bad, f"{path.name}: роутер не знає про БД і репозиторії: {sorted(bad)}"


def test_service_is_independent_of_http_and_database():
    assert layer_files("services"), "немає notes_app/services/notes.py"
    for path in layer_files("services"):
        bad = uses(imports_of(path), libs=HTTP_LIBS | DB_LIBS, prefixes={LAYERS["routers"], LAYERS["repositories"]})
        assert not bad, f"{path.name}: сервіс не залежить від HTTP, SQL і конкретного репозиторію: {sorted(bad)}"


def test_repository_is_independent_of_http_and_upper_layers():
    assert layer_files("repositories"), "немає notes_app/repositories/notes.py"
    for path in layer_files("repositories"):
        bad = uses(imports_of(path), libs=HTTP_LIBS, prefixes={LAYERS["routers"], LAYERS["services"]})
        assert not bad, f"{path.name}: репозиторій не залежить від HTTP і верхніх шарів: {sorted(bad)}"


def test_env_is_read_only_in_config():
    for path in PKG.rglob("*.py"):
        if path.name == "config.py" and path.parent == PKG:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                assert node.attr not in {"getenv", "environ"}, f"{path.relative_to(PKG)}: змінні оточення читає лише config.py"
            if isinstance(node, ast.ImportFrom) and node.module == "os":
                assert not {a.name for a in node.names} & {"getenv", "environ"}, f"{path.relative_to(PKG)}: os.getenv поза config.py"


def test_main_does_not_touch_the_database():
    assert not uses(imports_of(PKG / "main.py"), libs=DB_LIBS), "main.py лише збирає застосунок, без SQL"


def test_settings_is_pydantic_settings():
    config = PKG / "config.py"
    assert config.exists(), "немає notes_app/config.py"
    tree = ast.parse(config.read_text(encoding="utf-8"))
    bases = {ast.unparse(b) for n in ast.walk(tree) if isinstance(n, ast.ClassDef) for b in n.bases}
    assert any(b.endswith("BaseSettings") for b in bases), "config.py: Settings має успадковувати BaseSettings"


# ---------- конфіг ------------------------------------------------------------


def test_settings_reads_database_path_from_env(monkeypatch):
    from notes_app.config import Settings

    monkeypatch.delenv("NOTES_DATABASE_PATH", raising=False)
    assert Settings().database_path == "notes.db"
    monkeypatch.setenv("NOTES_DATABASE_PATH", "/tmp/other.db")
    assert Settings().database_path == "/tmp/other.db"


# ---------- сервіс на фейковому репозиторії (без БД і без HTTP) ---------------


class FakeRepo:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, title, body):
        row = {"id": len(self.rows) + 1, "title": title, "body": body}
        self.rows.append(row)
        return row

    def get(self, note_id):
        return next((r for r in self.rows if r["id"] == note_id), None)

    def list(self):
        return list(self.rows)


def service():
    from notes_app.services.notes import NoteService

    repo = FakeRepo()
    return NoteService(repo), repo


def test_service_strips_title_and_stores_via_repository():
    svc, repo = service()
    note = svc.create("  Hello  ", "body")
    assert note == {"id": 1, "title": "Hello", "body": "body"}
    assert repo.rows == [note]


@pytest.mark.parametrize("title", ["", "   ", "\n\t"])
def test_service_rejects_blank_title(title):
    from notes_app.services.notes import InvalidNote

    svc, repo = service()
    with pytest.raises(InvalidNote):
        svc.create(title, "x")
    assert repo.rows == []


def test_service_get_and_list():
    from notes_app.services.notes import NoteNotFound

    svc, _ = service()
    first = svc.create("a", "")
    assert svc.get(first["id"]) == first
    assert svc.list() == [first]
    with pytest.raises(NoteNotFound):
        svc.get(999)


# ---------- репозиторій на справжньому SQLite ---------------------------------


def test_repository_persists_between_instances(tmp_path):
    from notes_app.repositories.notes import NoteRepository

    db = str(tmp_path / "r.db")
    note = NoteRepository(db).add("t", "b")
    again = NoteRepository(db)
    assert again.get(note["id"]) == {"id": note["id"], "title": "t", "body": "b"}
    assert again.get(404) is None
    assert [n["id"] for n in again.list()] == [note["id"]]


# ---------- HTTP-контракт (має не змінитися після рефакторингу) ---------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTES_DATABASE_PATH", str(tmp_path / "api.db"))
    main = importlib.import_module("notes_app.main")
    return TestClient(main.create_app())


def test_api_create_get_list(client):
    r = client.post("/notes", json={"title": " First ", "body": "hi"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "title": "First", "body": "hi"}
    assert client.get("/notes/1").json() == r.json()
    client.post("/notes", json={"title": "Second"})
    assert [n["title"] for n in client.get("/notes").json()] == ["First", "Second"]


def test_api_errors(client):
    assert client.get("/notes/42").status_code == 404
    assert client.post("/notes", json={"title": "   "}).status_code == 422
    assert client.post("/notes", json={"body": "no title"}).status_code == 422
    assert client.get("/notes").json() == []


def test_api_uses_database_from_env(tmp_path, monkeypatch):
    main = importlib.import_module("notes_app.main")
    paths = [tmp_path / "a.db", tmp_path / "b.db"]
    for p in paths:
        monkeypatch.setenv("NOTES_DATABASE_PATH", str(p))
        TestClient(main.create_app()).post("/notes", json={"title": p.name})
    for p in paths:
        titles = [r[0] for r in sqlite3.connect(p).execute("SELECT title FROM notes")]
        assert titles == [p.name]
