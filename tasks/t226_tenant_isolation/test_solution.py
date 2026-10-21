import asyncio
import sqlite3
import textwrap

import pytest

from solution import (NoteRepository, TenantCache, TenantContextError, audit_migration, cache_key, current_tenant,
                      init_schema, object_belongs_to, object_key, parse_cache_key, tenant_context)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_schema(c)
    yield c
    c.close()


def raw(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


# --- контекст tenant'а -------------------------------------------------------------------------

def test_context_sets_and_clears_tenant():
    with pytest.raises(TenantContextError):
        current_tenant()
    with tenant_context("acme"):
        assert current_tenant() == "acme"
    with pytest.raises(TenantContextError):
        current_tenant()


def test_nested_contexts_restore_previous_even_after_error():
    with tenant_context("acme"):
        with tenant_context("globex"):
            assert current_tenant() == "globex"
        assert current_tenant() == "acme"
        with pytest.raises(RuntimeError):
            with tenant_context("initech"):
                raise RuntimeError("boom")
        assert current_tenant() == "acme"
    with pytest.raises(TenantContextError):
        current_tenant()


@pytest.mark.parametrize("bad", ["", None, 5, "ACME", "a:b", "a/b", " acme", "acme ", "-x", "_x", "a" * 64, "тенант", "a.b"])
def test_invalid_tenant_ids_are_rejected(bad):
    with pytest.raises(ValueError):
        with tenant_context(bad):
            pass
    with pytest.raises(TenantContextError):
        current_tenant()


def test_valid_tenant_id_boundaries():
    for ok in ("a", "0", "a" * 63, "a-b_c9"):
        with tenant_context(ok):
            assert current_tenant() == ok


def test_asyncio_tasks_do_not_see_each_others_tenant():
    seen = {}

    async def worker(name):
        with tenant_context(name):
            for step in range(3):
                await asyncio.sleep(0)
                assert current_tenant() == name
            seen[name] = current_tenant()

    async def main():
        await asyncio.gather(*(worker(n) for n in ("t1", "t2", "t3")))

    asyncio.run(main())
    assert seen == {"t1": "t1", "t2": "t2", "t3": "t3"}


def test_asyncio_repository_isolation_with_interleaving(conn):
    repo = NoteRepository(conn)

    async def worker(name, count):
        with tenant_context(name):
            for i in range(count):
                repo.add(f"{name}-{i}", "x")
                await asyncio.sleep(0)
            return [n["title"] for n in repo.list()]

    async def main():
        return await asyncio.gather(worker("aa", 3), worker("bb", 2))

    a, b = asyncio.run(main())
    assert a == ["aa-0", "aa-1", "aa-2"] and b == ["bb-0", "bb-1"]


# --- репозиторій -------------------------------------------------------------------------------

def test_every_method_fails_closed_without_context_and_runs_no_sql(conn):
    repo = NoteRepository(conn)
    with tenant_context("acme"):
        nid = repo.add("t", "b")
    statements = []
    conn.set_trace_callback(statements.append)
    calls = [lambda: repo.add("x", "y"), lambda: repo.get(nid), repo.list, lambda: repo.update_body(nid, "z"),
             lambda: repo.delete(nid), repo.count]
    for call in calls:
        with pytest.raises(TenantContextError):
            call()
    conn.set_trace_callback(None)
    assert statements == []
    assert raw(conn, "SELECT COUNT(*) FROM notes") == [(1,)]


def test_tenants_see_only_their_own_rows(conn):
    repo = NoteRepository(conn)
    with tenant_context("acme"):
        a1 = repo.add("a-one", "A1")
        a2 = repo.add("a-two", "A2")
    with tenant_context("globex"):
        g1 = repo.add("g-one", "G1")
        assert [n["title"] for n in repo.list()] == ["g-one"]
        assert repo.count() == 1
        assert repo.get(a1) is None
        assert repo.get(g1) == {"id": g1, "title": "g-one", "body": "G1"}
    with tenant_context("acme"):
        assert [n["id"] for n in repo.list()] == [a1, a2]
        assert repo.count() == 2
        assert repo.get(g1) is None
    with tenant_context("empty"):
        assert repo.list() == [] and repo.count() == 0


def test_rows_are_stamped_with_the_context_tenant(conn):
    repo = NoteRepository(conn)
    with tenant_context("acme"):
        repo.add("x", "y")
    with tenant_context("globex"):
        repo.add("x", "y")
    assert raw(conn, "SELECT tenant_id FROM notes ORDER BY id") == [("acme",), ("globex",)]


def test_cross_tenant_update_and_delete_do_nothing(conn):
    repo = NoteRepository(conn)
    with tenant_context("acme"):
        nid = repo.add("secret", "original")
    with tenant_context("globex"):
        assert repo.update_body(nid, "pwned") is False
        assert repo.delete(nid) is False
        assert repo.update_body(99999, "x") is False
        assert repo.delete(99999) is False
    assert raw(conn, "SELECT tenant_id, body FROM notes") == [("acme", "original")]
    with tenant_context("acme"):
        assert repo.update_body(nid, "changed") is True
        assert repo.get(nid)["body"] == "changed"
        assert repo.delete(nid) is True
        assert repo.delete(nid) is False
        assert repo.get(nid) is None


def test_list_is_ordered_by_id(conn):
    repo = NoteRepository(conn)
    with tenant_context("acme"):
        ids = [repo.add(f"n{i}", "b") for i in range(5)]
        assert [n["id"] for n in repo.list()] == ids


@pytest.mark.parametrize("bad", ["1", "1 OR 1=1", None, 1.0, True, [1]])
def test_note_id_must_be_int(conn, bad):
    repo = NoteRepository(conn)
    with tenant_context("acme"):
        repo.add("x", "y")
        for call in (repo.get, repo.delete, lambda i: repo.update_body(i, "z")):
            with pytest.raises(ValueError):
                call(bad)
    assert raw(conn, "SELECT COUNT(*) FROM notes") == [(1,)]


def test_titles_with_sql_metacharacters_are_stored_literally(conn):
    repo = NoteRepository(conn)
    with tenant_context("acme"):
        nid = repo.add("'; DROP TABLE notes; --", "O'Brien")
        assert repo.get(nid) == {"id": nid, "title": "'; DROP TABLE notes; --", "body": "O'Brien"}


# --- ключі кешу й сховища ----------------------------------------------------------------------

def test_cache_key_format_and_roundtrip():
    assert cache_key("acme", "user:42") == "t:acme:user:42"
    assert parse_cache_key("t:acme:user:42") == ("acme", "user:42")
    assert parse_cache_key(cache_key("a-1", "x")) == ("a-1", "x")


def test_cache_keys_of_different_tenants_never_collide():
    assert cache_key("a", "b:c") != cache_key("a-b", "c")
    keys = {cache_key(t, k) for t in ("a", "ab", "abc") for k in ("x", "bx", "c:x")}
    assert len(keys) == 9


@pytest.mark.parametrize("t, k", [("", "x"), ("ACME", "x"), ("a:b", "x"), ("acme", ""), ("acme", None), (None, "x"), ("acme", 5)])
def test_cache_key_rejects_bad_input(t, k):
    with pytest.raises(ValueError):
        cache_key(t, k)


@pytest.mark.parametrize("bad", ["", "acme:x", "t:acme", "t::x", "x:acme:y", "t:ACME:y", "t:acme:", None, 5, b"t:a:b"])
def test_parse_cache_key_rejects_foreign_formats(bad):
    with pytest.raises(ValueError):
        parse_cache_key(bad)


def test_object_key_format():
    assert object_key("acme", "reports/2026/q1.pdf") == "tenants/acme/reports/2026/q1.pdf"
    assert object_key("acme", "a.b-c_d") == "tenants/acme/a.b-c_d"


@pytest.mark.parametrize("name", ["", "/abs", "../other/x", "a/../../b", "a//b", "a/", "./x", "a/./b", "a\\b", "a%2e%2e/b",
                                  "a\x00b", "a b", "ім'я", ".."])
def test_object_key_rejects_escapes(name):
    with pytest.raises(ValueError):
        object_key("acme", name)


@pytest.mark.parametrize("t", ["", "A", "a/b", None])
def test_object_key_rejects_bad_tenant(t):
    with pytest.raises(ValueError):
        object_key(t, "x")


def test_object_belongs_to_exact_prefix():
    assert object_belongs_to("ab", "tenants/ab/file.txt") is True
    assert object_belongs_to("ab", "tenants/abc/file.txt") is False
    assert object_belongs_to("abc", "tenants/ab/file.txt") is False
    assert object_belongs_to("ab", "tenants/ab/") is False
    assert object_belongs_to("ab", "tenants/ab") is False
    assert object_belongs_to("ab", "tenants/ab/../abc/x") is False
    assert object_belongs_to("ab", "other/tenants/ab/x") is False
    assert object_belongs_to("ab", "/tenants/ab/x") is False
    assert object_belongs_to("ab", None) is False
    assert object_belongs_to("AB", "tenants/AB/x") is False
    assert object_belongs_to(None, "tenants/None/x") is False


def test_tenant_cache_isolation_and_shared_store():
    store = {"unrelated": 1}
    cache = TenantCache(store)
    with tenant_context("acme"):
        cache.set("k", "A")
        cache.set("only-acme", 1)
    with tenant_context("globex"):
        assert cache.get("k") is None
        assert cache.get("k", "dflt") == "dflt"
        cache.set("k", "G")
        assert cache.get("k") == "G"
    with tenant_context("acme"):
        assert cache.get("k") == "A"
    assert store["t:acme:k"] == "A" and store["t:globex:k"] == "G"
    assert set(store) - {"unrelated"} == {"t:acme:k", "t:acme:only-acme", "t:globex:k"}


def test_tenant_cache_fails_closed_without_context():
    store = {}
    cache = TenantCache(store)
    for call in (lambda: cache.get("k"), lambda: cache.set("k", 1), lambda: cache.delete("k"), cache.clear_tenant):
        with pytest.raises(TenantContextError):
            call()
    assert store == {}


def test_tenant_cache_delete_and_clear_only_touch_own_prefix():
    store = {}
    cache = TenantCache(store)
    for t in ("ab", "abc", "ab-c"):
        with tenant_context(t):
            cache.set("x", t)
            cache.set("y:z", t)
    with tenant_context("ab"):
        cache.delete("x")
        cache.delete("missing")
        assert cache.get("x") is None
        assert cache.clear_tenant() == 1
        assert cache.clear_tenant() == 0
    assert sorted(store) == ["t:ab-c:x", "t:ab-c:y:z", "t:abc:x", "t:abc:y:z"]


# --- аналіз міграцій ---------------------------------------------------------------------------

def audit(sql):
    return audit_migration(textwrap.dedent(sql).lstrip("\n"))


GOOD = """
CREATE TABLE notes (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    body text
);
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE notes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON notes
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
"""


def test_correct_migration_has_no_findings():
    assert audit(GOOD) == []


def test_empty_and_tables_without_tenant_id_are_ignored():
    assert audit("") == []
    assert audit("CREATE TABLE tenants (id uuid PRIMARY KEY, name text);\nCREATE INDEX i ON tenants(name);") == []
    assert audit("CREATE TABLE logs (id int, tenant_id_old int, my_tenant_id int);") == []


def test_missing_everything():
    sql = """
    CREATE TABLE notes (
        id bigserial PRIMARY KEY,
        tenant_id uuid NOT NULL
    );
    """
    assert audit(sql) == [("no-policy", 1), ("rls-not-enabled", 1), ("rls-not-forced", 1)]


def test_enable_without_force():
    sql = GOOD.replace("ALTER TABLE notes FORCE ROW LEVEL SECURITY;\n", "")
    assert audit(sql) == [("rls-not-forced", 1)]


def test_force_without_enable():
    sql = GOOD.replace("ALTER TABLE notes ENABLE ROW LEVEL SECURITY;\n", "")
    assert audit(sql) == [("rls-not-enabled", 1)]


def test_enabled_and_forced_but_no_policy():
    sql = GOOD[:GOOD.index("CREATE POLICY")]
    assert audit(sql) == [("no-policy", 1)]


@pytest.mark.parametrize("expr", [
    "USING (true)", "USING (TRUE)", "USING ( 1 = 1 )", "USING ((true))",
    "USING (tenant_id = current_setting('app.tenant_id')::uuid OR true)",
    "USING (current_setting('app.tenant_id') = 'tenant_id')",
    "USING (owner_id = current_user)",
    "USING (tenant_id IS NOT NULL OR 1=1)",
    "WITH CHECK (true)",
])
def test_policy_not_tenant_scoped(expr):
    sql = GOOD[:GOOD.index("CREATE POLICY")] + f"CREATE POLICY p ON notes {expr};\n"
    assert audit(sql) == [("policy-not-tenant-scoped", 8)]


@pytest.mark.parametrize("expr", [
    "FOR SELECT USING (tenant_id = current_setting('app.tenant_id', true)::uuid)",
    "FOR ALL TO app_user USING (notes.tenant_id = current_setting('app.tenant_id')::uuid)",
    "AS RESTRICTIVE FOR INSERT WITH CHECK (tenant_id = (SELECT current_setting('app.tenant_id'))::uuid)",
])
def test_scoped_policies_are_fine(expr):
    sql = GOOD[:GOOD.index("CREATE POLICY")] + f"CREATE POLICY p ON notes {expr};\n"
    assert audit(sql) == []


def test_one_bad_policy_among_good_ones():
    sql = GOOD + "CREATE POLICY open_read ON notes FOR SELECT USING (true);\n"
    assert audit(sql) == [("policy-not-tenant-scoped", 11)]


def test_disable_and_no_force_after_the_fact():
    sql = GOOD + "ALTER TABLE notes NO FORCE ROW LEVEL SECURITY;\n"
    assert audit(sql) == [("rls-not-forced", 1), ("rls-disabled", 11)]
    sql = GOOD + "ALTER TABLE notes DISABLE ROW LEVEL SECURITY;\n"
    assert audit(sql) == [("rls-not-enabled", 1), ("rls-disabled", 11)]


def test_disable_followed_by_enable_ends_enabled_but_is_still_reported():
    sql = GOOD + "ALTER TABLE notes DISABLE ROW LEVEL SECURITY;\nALTER TABLE notes ENABLE ROW LEVEL SECURITY;\n"
    assert audit(sql) == [("rls-disabled", 11)]


def test_disable_on_non_tenant_table_is_ignored():
    sql = GOOD + "CREATE TABLE tenants (id int);\nALTER TABLE tenants DISABLE ROW LEVEL SECURITY;\n"
    assert audit(sql) == []


def test_bypassrls_roles():
    assert audit("ALTER ROLE app BYPASSRLS;") == [("bypassrls-role", 1)]
    assert audit("CREATE ROLE etl LOGIN bypassrls;\n\nCREATE USER x BYPASSRLS PASSWORD 'p';") == [
        ("bypassrls-role", 1), ("bypassrls-role", 3)]
    assert audit("CREATE ROLE reader NOBYPASSRLS;\nALTER ROLE app NOSUPERUSER;") == []


def test_multiple_tables_each_checked_with_own_line():
    sql = """
    CREATE TABLE a (id int, tenant_id uuid);
    CREATE TABLE b (id int, tenant_id uuid);
    ALTER TABLE a ENABLE ROW LEVEL SECURITY;
    ALTER TABLE a FORCE ROW LEVEL SECURITY;
    CREATE POLICY pa ON a USING (tenant_id = current_setting('app.tenant_id')::uuid);
    ALTER TABLE b ENABLE ROW LEVEL SECURITY;
    """
    assert audit(sql) == [("no-policy", 2), ("rls-not-forced", 2)]


def test_names_with_schema_quotes_case_and_modifiers():
    sql = """
    CREATE UNLOGGED TABLE IF NOT EXISTS "public"."Orders" (
        "ID" int,
        "Tenant_ID" uuid
    );
    alter table only public.orders enable row level security;
    ALTER TABLE IF EXISTS ONLY "public"."ORDERS" FORCE ROW LEVEL SECURITY;
    create policy p on public."Orders" using (tenant_id = current_setting('app.tenant_id')::uuid);
    """
    assert audit(sql) == []


def test_alter_table_add_tenant_id_makes_a_tenant_table():
    sql = """
    CREATE TABLE legacy (id int);
    ALTER TABLE legacy ADD COLUMN IF NOT EXISTS tenant_id uuid;
    """
    assert audit(sql) == [("no-policy", 2), ("rls-not-enabled", 2), ("rls-not-forced", 2)]
    assert audit("ALTER TABLE legacy ADD tenant_id int, ADD note text;") == [
        ("no-policy", 1), ("rls-not-enabled", 1), ("rls-not-forced", 1)]
    assert audit("ALTER TABLE legacy ADD COLUMN tenant_id_old int;") == []


def test_constraints_mentioning_tenant_id_do_not_make_a_tenant_table():
    sql = """
    CREATE TABLE refs (
        id int,
        CONSTRAINT tenant_id_fk FOREIGN KEY (parent) REFERENCES t(id),
        UNIQUE (id)
    );
    """
    assert audit(sql) == []


def test_comments_strings_and_dollar_quotes_are_ignored():
    sql = """
    -- CREATE TABLE ghost (tenant_id int);
    /* CREATE TABLE ghost2 (
       tenant_id int); */
    CREATE TABLE notes (id int, tenant_id uuid); -- ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
    /* ALTER TABLE notes FORCE ROW LEVEL SECURITY; */
    CREATE FUNCTION f() RETURNS void AS $body$
        CREATE TABLE inner_t (tenant_id int);
        ALTER ROLE x BYPASSRLS;
    $body$ LANGUAGE sql;
    INSERT INTO log VALUES ('CREATE TABLE s (tenant_id int); ALTER ROLE y BYPASSRLS');
    """
    assert audit(sql) == [("no-policy", 4), ("rls-not-enabled", 4), ("rls-not-forced", 4)]


def test_line_numbers_follow_the_original_text_with_blank_lines_and_block_comments():
    sql = "\n\n/* one\n two */\n\nCREATE TABLE t (\n  tenant_id int\n);\n"
    assert audit_migration(sql) == [("no-policy", 6), ("rls-not-enabled", 6), ("rls-not-forced", 6)]


def test_several_statements_on_one_line():
    sql = "CREATE TABLE t (tenant_id int); ALTER TABLE t ENABLE ROW LEVEL SECURITY; ALTER TABLE t FORCE ROW LEVEL SECURITY;"
    assert audit_migration(sql) == [("no-policy", 1)]


def test_policy_on_unknown_or_non_tenant_table_is_ignored():
    sql = "CREATE POLICY p ON nowhere USING (true);\nCREATE TABLE x (id int);\nCREATE POLICY q ON x USING (true);\n"
    assert audit_migration(sql) == []


def test_leading_comments_do_not_hide_statements():
    sql = """
    -- notes table
    CREATE TABLE notes (id int, tenant_id uuid);
    -- enable it
    ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
    """
    assert audit(sql) == [("no-policy", 2), ("rls-not-forced", 2)]
