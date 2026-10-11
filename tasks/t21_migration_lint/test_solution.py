import pytest

from solution import lint_migration, split_statements

LT = "SET lock_timeout = '5s';\n"


def rules(sql, with_lock=True):
    """Правила для ОДНОГО оператора, зазвичай із попереднім lock_timeout, щоб не заважав MIG010."""
    return [r for r, _ in lint_migration((LT if with_lock else "") + sql)]


# --- split_statements ----------------------------------------------------------------------------------

def test_split_basic():
    assert split_statements("SELECT 1; SELECT 2;\n\nSELECT 3") == ["SELECT 1", "SELECT 2", "SELECT 3"]


def test_split_empty_and_whitespace():
    assert split_statements("") == []
    assert split_statements("  ;; \n ; ") == []


def test_semicolon_inside_string_literals():
    sql = "INSERT INTO t VALUES ('a;b'); INSERT INTO t VALUES ('it''s;ok');"
    assert split_statements(sql) == ["INSERT INTO t VALUES ('a;b')", "INSERT INTO t VALUES ('it''s;ok')"]


def test_semicolon_inside_quoted_identifier():
    assert split_statements('ALTER TABLE "we;ird" ADD COLUMN a int; SELECT 1') == ['ALTER TABLE "we;ird" ADD COLUMN a int', "SELECT 1"]


def test_semicolon_inside_dollar_quotes():
    sql = "CREATE FUNCTION f() RETURNS int AS $$ BEGIN RETURN 1; END; $$ LANGUAGE plpgsql; SELECT 2;"
    parts = split_statements(sql)
    assert len(parts) == 2 and parts[0].endswith("LANGUAGE plpgsql") and parts[1] == "SELECT 2"
    tagged = "DO $body$ BEGIN PERFORM 1; END $body$; SELECT 3"
    assert len(split_statements(tagged)) == 2


def test_comments_are_removed():
    sql = "-- header; with semicolon\nSELECT 1; /* block; comment */ SELECT 2; -- tail"
    assert split_statements(sql) == ["SELECT 1", "SELECT 2"]


def test_comment_markers_inside_strings_are_kept():
    assert split_statements("SELECT '-- not a comment', '/* nor this */';") == ["SELECT '-- not a comment', '/* nor this */'"]


def test_unterminated_final_statement_is_kept():
    assert split_statements("SELECT 1; SELECT 2") == ["SELECT 1", "SELECT 2"]


# --- MIG001 / MIG002 ------------------------------------------------------------------------------------

def test_not_null_without_default_is_mig001():
    assert rules("ALTER TABLE users ADD COLUMN age int NOT NULL;") == ["MIG001"]


def test_not_null_with_constant_default_is_fine():
    assert rules("ALTER TABLE users ADD COLUMN age int NOT NULL DEFAULT 0;") == []
    assert rules("ALTER TABLE users ADD COLUMN tag text NOT NULL DEFAULT 'x';") == []
    assert rules("ALTER TABLE users ADD COLUMN at timestamptz NOT NULL DEFAULT now();") == []
    assert rules("ALTER TABLE users ADD COLUMN at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP;") == []


def test_nullable_column_is_fine():
    assert rules("ALTER TABLE users ADD COLUMN age int;") == []
    assert rules("ALTER TABLE IF EXISTS ONLY public.users ADD COLUMN IF NOT EXISTS age int NULL;") == []


@pytest.mark.parametrize(
    "ddl",
    [
        "ADD COLUMN id2 bigserial",
        "ADD COLUMN n serial",
        "ADD COLUMN u uuid DEFAULT gen_random_uuid()",
        "ADD COLUMN u uuid NOT NULL DEFAULT uuid_generate_v4()",
        "ADD COLUMN r double precision DEFAULT random()",
        "ADD COLUMN c timestamptz DEFAULT clock_timestamp()",
        "ADD COLUMN s int DEFAULT nextval('seq')",
        "ADD COLUMN g int GENERATED ALWAYS AS (a + b) STORED",
    ],
)
def test_table_rewriting_columns_are_mig002(ddl):
    assert "MIG002" in rules(f"ALTER TABLE t {ddl};")


def test_not_null_default_volatile_is_mig002_not_mig001():
    assert rules("ALTER TABLE t ADD COLUMN u uuid NOT NULL DEFAULT gen_random_uuid();") == ["MIG002"]


def test_keywords_in_literals_do_not_trigger():
    assert rules("ALTER TABLE t ADD COLUMN note text DEFAULT 'NOT NULL, DROP COLUMN x';") == []
    assert rules("COMMENT ON COLUMN t.a IS 'SET NOT NULL later; RENAME maybe';") == []


# --- MIG003 -----------------------------------------------------------------------------------------------------

def test_index_without_concurrently():
    assert rules("CREATE INDEX idx_a ON users (a);") == ["MIG003"]
    assert rules("CREATE UNIQUE INDEX idx_a ON users (a);") == ["MIG003"]
    assert rules("CREATE INDEX IF NOT EXISTS idx_a ON ONLY users (a);") == ["MIG003"]


def test_index_concurrently_is_fine():
    assert rules("CREATE INDEX CONCURRENTLY idx_a ON users (a);") == []
    assert rules("create unique index concurrently if not exists idx_a on users (a);") == []


def test_index_on_a_table_created_in_the_same_script_is_fine():
    sql = "CREATE TABLE fresh (id int); CREATE INDEX idx ON fresh (id);"
    assert rules(sql) == []
    assert rules("CREATE TABLE IF NOT EXISTS fresh (id int); CREATE INDEX idx ON fresh (id);") == []
    assert rules("CREATE TABLE fresh (id int); CREATE INDEX idx ON other (id);") == ["MIG003"]


def test_index_before_table_creation_is_not_excused():
    assert rules("CREATE INDEX idx ON fresh (id); CREATE TABLE fresh (id int);") == ["MIG003"]


# --- MIG004 -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sql", ["ALTER TABLE t DROP COLUMN a;", "ALTER TABLE t DROP a;", "ALTER TABLE t DROP COLUMN IF EXISTS a;",
                                 "DROP TABLE t;", "DROP TABLE IF EXISTS t;"])
def test_destructive_statements(sql):
    assert "MIG004" in rules(sql)


@pytest.mark.parametrize("sql", ["ALTER TABLE t DROP CONSTRAINT c;", "ALTER TABLE t ALTER COLUMN a DROP DEFAULT;",
                                 "ALTER TABLE t ALTER COLUMN a DROP NOT NULL;", "DROP INDEX CONCURRENTLY idx;"])
def test_non_destructive_drops_are_not_mig004(sql):
    assert "MIG004" not in rules(sql)


# --- MIG005..MIG009 -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sql", ["ALTER TABLE t ALTER COLUMN a TYPE bigint;", "ALTER TABLE t ALTER a SET DATA TYPE text;"])
def test_type_change(sql):
    assert rules(sql) == ["MIG005"]


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("ALTER TABLE t ADD CONSTRAINT fk FOREIGN KEY (a) REFERENCES o (id);", ["MIG006"]),
        ("ALTER TABLE t ADD FOREIGN KEY (a) REFERENCES o (id);", ["MIG006"]),
        ("ALTER TABLE t ADD CONSTRAINT c CHECK (a > 0);", ["MIG006"]),
        ("ALTER TABLE t ADD CHECK (a > 0);", ["MIG006"]),
        ("ALTER TABLE t ADD CONSTRAINT fk FOREIGN KEY (a) REFERENCES o (id) NOT VALID;", []),
        ("ALTER TABLE t ADD CONSTRAINT c CHECK (a > 0) NOT VALID;", []),
        ("ALTER TABLE t VALIDATE CONSTRAINT fk;", []),
    ],
)
def test_constraints_without_not_valid(sql, expected):
    assert rules(sql) == expected


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("ALTER TABLE t ADD CONSTRAINT u UNIQUE (a);", ["MIG007"]),
        ("ALTER TABLE t ADD UNIQUE (a);", ["MIG007"]),
        ("ALTER TABLE t ADD CONSTRAINT pk PRIMARY KEY (id);", ["MIG007"]),
        ("ALTER TABLE t ADD PRIMARY KEY (id);", ["MIG007"]),
        ("ALTER TABLE t ADD CONSTRAINT u UNIQUE USING INDEX idx_u;", []),
        ("ALTER TABLE t ADD CONSTRAINT pk PRIMARY KEY USING INDEX idx_pk;", []),
    ],
)
def test_unique_and_pk(sql, expected):
    assert rules(sql) == expected


@pytest.mark.parametrize("sql", ["ALTER TABLE t RENAME COLUMN a TO b;", "ALTER TABLE t RENAME a TO b;", "ALTER TABLE t RENAME TO t2;",
                                 "ALTER TABLE IF EXISTS t RENAME COLUMN a TO b;"])
def test_rename(sql):
    assert rules(sql) == ["MIG008"]


def test_set_not_null():
    assert rules("ALTER TABLE t ALTER COLUMN a SET NOT NULL;") == ["MIG009"]
    assert rules("ALTER TABLE t ALTER a SET NOT NULL;") == ["MIG009"]
    assert rules("ALTER TABLE t ALTER COLUMN a SET DEFAULT 5;") == []


# --- кілька дій в одному ALTER ---------------------------------------------------------------------------------------

def test_multiple_actions_are_checked_separately():
    sql = "ALTER TABLE t ADD COLUMN a int NOT NULL, ADD COLUMN b int, DROP COLUMN c, ALTER COLUMN d TYPE text;"
    assert rules(sql) == ["MIG001", "MIG004", "MIG005"]


def test_commas_inside_parentheses_do_not_split_actions():
    sql = "ALTER TABLE t ADD CONSTRAINT c CHECK (a IN (1, 2, 3)) NOT VALID, ADD COLUMN b numeric(10, 2) DEFAULT 0 NOT NULL;"
    assert rules(sql) == []


def test_same_rule_twice_in_one_statement_is_reported_once():
    assert lint_migration(LT + "ALTER TABLE t ADD COLUMN a int NOT NULL, ADD COLUMN b int NOT NULL;") == [("MIG001", 2)]


# --- MIG010 ------------------------------------------------------------------------------------------------------------

def test_missing_lock_timeout_is_reported_once_on_first_locking_statement():
    sql = "SELECT 1;\nALTER TABLE t ADD COLUMN a int;\nALTER TABLE t ADD COLUMN b int;"
    assert lint_migration(sql) == [("MIG010", 2)]


@pytest.mark.parametrize("setter", ["SET lock_timeout = '3s'", "SET LOCAL lock_timeout TO 3000", "set session lock_timeout='1s'"])
def test_lock_timeout_variants_silence_mig010(setter):
    assert lint_migration(f"{setter}; ALTER TABLE t ADD COLUMN a int;") == []


def test_lock_timeout_set_after_the_first_ddl_is_too_late():
    assert lint_migration("ALTER TABLE t ADD COLUMN a int; SET lock_timeout = '5s'; ALTER TABLE t ADD COLUMN b int;") == [("MIG010", 1)]


def test_other_set_statements_are_not_lock_timeout():
    assert lint_migration("SET statement_timeout = '5s'; ALTER TABLE t ADD COLUMN a int;") == [("MIG010", 2)]
    assert lint_migration("SET lock_timeout_x = 1; ALTER TABLE t ADD COLUMN a int;") == [("MIG010", 2)]


def test_non_locking_scripts_do_not_need_lock_timeout():
    assert lint_migration("CREATE TABLE a (id int); INSERT INTO a VALUES (1); UPDATE a SET id = 2;") == []
    assert lint_migration("CREATE TABLE a (id int); CREATE INDEX i ON a (id);") == []  # нова таблиця ще нікому не заважає


@pytest.mark.parametrize("sql", ["DROP TABLE t;", "TRUNCATE t;", "DROP INDEX i;", "CREATE INDEX CONCURRENTLY i ON t (a);"])
def test_locking_statements_need_lock_timeout(sql):
    assert ("MIG010", 1) in lint_migration(sql)


# --- форма результату ----------------------------------------------------------------------------------------------------

def test_result_is_sorted_by_statement_then_rule_and_uses_statement_numbers():
    sql = (LT + "CREATE INDEX i ON t (a);\n-- comment; with semicolon\nALTER TABLE t ADD COLUMN a int NOT NULL, DROP COLUMN b;")
    assert lint_migration(sql) == [("MIG003", 2), ("MIG001", 3), ("MIG004", 3)]


def test_empty_script_and_comments_only():
    assert lint_migration("") == []
    assert lint_migration("-- nothing here\n/* at all */") == []


def test_case_and_whitespace_insensitive():
    sql = "set LOCK_TIMEOUT='1s';\nalter   table\n  users\n add column   age\n int   not\n null ;"
    assert lint_migration(sql) == [("MIG001", 2)]


def test_quoted_identifiers_are_supported():
    assert rules('ALTER TABLE "Order Items" ADD COLUMN "drop column" int NOT NULL;') == ["MIG001"]
    sql = 'CREATE TABLE "My Table" (id int); CREATE INDEX i ON "My Table" (id);'
    assert rules(sql) == []


def test_a_realistic_safe_expand_backfill_contract_sequence():
    sql = """
    SET lock_timeout = '5s';
    ALTER TABLE users ADD COLUMN full_name text;
    CREATE INDEX CONCURRENTLY idx_users_full_name ON users (full_name);
    ALTER TABLE users ADD CONSTRAINT users_full_name_nn CHECK (full_name IS NOT NULL) NOT VALID;
    ALTER TABLE users VALIDATE CONSTRAINT users_full_name_nn;
    """
    assert lint_migration(sql) == []


def test_a_realistic_dangerous_migration():
    sql = """
    ALTER TABLE orders ADD COLUMN status text NOT NULL;
    CREATE INDEX idx_orders_status ON orders (status);
    ALTER TABLE orders ADD CONSTRAINT fk_u FOREIGN KEY (user_id) REFERENCES users (id);
    ALTER TABLE orders RENAME COLUMN total TO amount;
    """
    assert lint_migration(sql) == [("MIG001", 1), ("MIG010", 1), ("MIG003", 2), ("MIG006", 3), ("MIG008", 4)]
