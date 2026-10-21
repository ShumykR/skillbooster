import math
import textwrap
from collections import Counter

import pytest

from solution import lint_diff


def new_file(path, code):
    """Дифф, у якому весь файл доданий."""
    lines = textwrap.dedent(code).strip("\n").split("\n")
    body = "\n".join("+" + ln for ln in lines)
    return (f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}\n")


def rules(diff):
    return [(f["file"], f["line"], f["rule"]) for f in lint_diff(diff)]


def entropy(s):
    c = Counter(s)
    return -sum(v / len(s) * math.log2(v / len(s)) for v in c.values())


# --- розбір диффу й номери рядків --------------------------------------------------------------

MODIFIED = """\
diff --git a/app/api.py b/app/api.py
index 111..222 100644
--- a/app/api.py
+++ b/app/api.py
@@ -10,6 +10,7 @@ def fetch(url):
     headers = {}
     data = load(url)
-    old = legacy()
+    resp = requests.get(url, verify=False)
+    obj = pickle.loads(resp.content)
     return data

 def other():
@@ -40,2 +41,3 @@ def other():
     x = 1
+    cfg = yaml.load(text)
     return x
"""


def test_line_numbers_follow_new_file_counters():
    assert rules(MODIFIED) == [
        ("app/api.py", 12, "tls-verify-disabled"),
        ("app/api.py", 13, "unsafe-deserialization"),
        ("app/api.py", 42, "unsafe-yaml-load"),
    ]


def test_findings_have_full_shape_and_comment_hint():
    f = lint_diff(MODIFIED)[0]
    assert set(f) == {"file", "line", "rule", "cwe", "comment"}
    assert f["cwe"] == 295 and isinstance(f["line"], int)
    assert isinstance(f["comment"], str) and f["comment"].strip()


def test_context_and_removed_lines_are_not_reported():
    diff = """\
--- a/x.py
+++ b/x.py
@@ -1,3 +1,3 @@
 resp = requests.get(url, verify=False)
-bad = yaml.load(text)
+good = yaml.safe_load(text)
 DEBUG = True
"""
    assert rules(diff) == []


def test_removed_line_that_looks_like_a_file_header_does_not_break_parsing():
    diff = """\
--- a/q.py
+++ b/q.py
@@ -1,3 +1,3 @@
 a = 1
--- sql comment
+resp = requests.get(url, verify=False)
 b = 2
"""
    assert "--- sql comment" in diff
    assert rules(diff) == [("q.py", 2, "tls-verify-disabled")]


def test_hunk_header_without_counts_and_no_newline_marker():
    diff = ("--- a/one.py\n+++ b/one.py\n@@ -1 +1 @@\n-x = 1\n"
            "\\ No newline at end of file\n+DEBUG = True\n\\ No newline at end of file\n")
    assert rules(diff) == [("one.py", 1, "debug-enabled")]


def test_multiple_files_hunks_sorted_deleted_and_non_py_skipped():
    diff = new_file("b.py", "resp = requests.get(u, verify=False)\n") \
        + new_file("a.py", "x = 1\nDEBUG = True\n") \
        + "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-resp = requests.get(u, verify=False)\n" \
        + new_file("notes.md", "resp = requests.get(u, verify=False)\n")
    assert rules(diff) == [("a.py", 2, "debug-enabled"), ("b.py", 1, "tls-verify-disabled")]


def test_second_hunk_of_same_file_uses_own_numbering():
    diff = """\
--- a/m.py
+++ b/m.py
@@ -1,2 +1,3 @@
 a = 1
+DEBUG = True
 b = 2
@@ -50,2 +51,3 @@
 c = 3
+resp = requests.get(u, verify=False)
 d = 4
"""
    assert rules(diff) == [("m.py", 2, "debug-enabled"), ("m.py", 52, "tls-verify-disabled")]


def test_tab_suffix_in_header_and_non_git_style_paths():
    diff = "--- old.py\t2024-01-01\n+++ new.py\t2024-01-02\n@@ -0,0 +1 @@\n+DEBUG = True\n"
    assert rules(diff) == [("new.py", 1, "debug-enabled")]


@pytest.mark.parametrize("text", ["", "\n", "hello world\nnot a diff\n", "diff --git a/x b/x\nBinary files differ\n"])
def test_empty_or_non_diff_input(text):
    assert lint_diff(text) == []


def test_malformed_hunk_header_is_value_error():
    with pytest.raises(ValueError):
        lint_diff("--- a/x.py\n+++ b/x.py\n@@ garbage @@\n+x = 1\n")


def test_unparsable_added_code_is_skipped_without_error():
    diff = new_file("bad.py", "def broken(:\n    pass\n") + new_file("ok.py", "DEBUG = True\n")
    assert rules(diff) == [("ok.py", 1, "debug-enabled")]


def test_hunk_that_does_not_parse_falls_back_to_added_lines():
    diff = """\
--- a/z.py
+++ b/z.py
@@ -5,3 +5,4 @@
         return value
     else:
+    resp = requests.get(url, verify=False)
         pass
"""
    assert rules(diff) == [("z.py", 7, "tls-verify-disabled")]


def test_multiline_call_is_reported_on_first_added_line():
    code = """\
    resp = requests.post(
        url,
        data=payload,
        verify=False,
    )
    """
    assert rules(new_file("net.py", code)) == [("net.py", 1, "tls-verify-disabled")]


def test_call_started_in_context_with_added_keyword_is_reported_on_added_line():
    diff = """\
--- a/net.py
+++ b/net.py
@@ -1,3 +1,4 @@
 resp = requests.post(
     url,
+    verify=False,
 )
"""
    assert rules(diff) == [("net.py", 3, "tls-verify-disabled")]


def test_analyzed_code_is_never_executed():
    code = "raise SystemExit('executed')\nDEBUG = True\n"
    assert rules(new_file("boom.py", code)) == [("boom.py", 2, "debug-enabled")]


def test_two_rules_on_one_line_sorted_by_rule():
    code = "r = requests.get(yaml.load(t), verify=False)\n"
    assert rules(new_file("two.py", code)) == [("two.py", 1, "tls-verify-disabled"), ("two.py", 1, "unsafe-yaml-load")]


def test_no_duplicates_for_same_rule_and_line():
    code = "a, b = requests.get(u, verify=False), requests.get(v, verify=False)\n"
    assert rules(new_file("dup.py", code)) == [("dup.py", 1, "tls-verify-disabled")]


# --- правила: позитивні й негативні випадки ----------------------------------------------------

POSITIVE = [
    ("tls-verify-disabled", 295, "requests.get(url, verify=False)"),
    ("tls-verify-disabled", 295, "client = httpx.Client(verify=False)"),
    ("tls-verify-disabled", 295, "ctx = ssl._create_unverified_context()"),
    ("shell-injection", 78, 'subprocess.run(f"ls {path}", shell=True)'),
    ("shell-injection", 78, 'subprocess.call("ls " + path, shell=True)'),
    ("shell-injection", 78, 'subprocess.Popen("ls %s" % path, shell=True)'),
    ("shell-injection", 78, 'subprocess.check_output("ls {}".format(path), shell=True)'),
    ("shell-injection", 78, 'subprocess.run(args=f"ls {path}", shell=True)'),
    ("shell-injection", 78, 'os.system(f"rm -rf {path}")'),
    ("shell-injection", 78, 'os.popen("cat " + name)'),
    ("unsafe-yaml-load", 502, "cfg = yaml.load(text)"),
    ("unsafe-yaml-load", 502, "cfg = yaml.load(text, Loader=yaml.Loader)"),
    ("unsafe-yaml-load", 502, "cfg = yaml.load(text, yaml.FullLoader)"),
    ("unsafe-yaml-load", 502, "cfg = yaml.unsafe_load(text)"),
    ("unsafe-deserialization", 502, "obj = pickle.loads(request.data)"),
    ("unsafe-deserialization", 502, "obj = pickle.load(open(path, 'rb'))"),
    ("unsafe-deserialization", 502, "obj = dill.loads(blob)"),
    ("unsafe-deserialization", 502, "obj = marshal.loads(data)"),
    ("sql-injection", 89, 'cur.execute(f"SELECT * FROM users WHERE id = {uid}")'),
    ("sql-injection", 89, 'cur.execute("SELECT * FROM users WHERE name = \'" + name + "\'")'),
    ("sql-injection", 89, 'cur.execute("SELECT * FROM t WHERE a = \'%s\'" % a)'),
    ("sql-injection", 89, 'cur.executemany("INSERT INTO t VALUES ({})".format(x), rows)'),
    ("sql-injection", 89, 'rows = session.execute(text(f"SELECT {cols} FROM t"))'),
    ("insecure-random-token", 330, "token = ''.join(random.choice(ALPHABET) for _ in range(32))"),
    ("insecure-random-token", 330, "self.reset_code = random.randint(100000, 999999)"),
    ("insecure-random-token", 330, "api_key: str = str(random.getrandbits(64))"),
    ("insecure-random-token", 330, "SESSION_ID = random.random()"),
    ("cors-wildcard-credentials", 942, 'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)'),
    ("cors-wildcard-credentials", 942, 'app.add_middleware(CORSMiddleware, allow_origins="*", allow_credentials=True)'),
    ("cors-wildcard-credentials", 942, 'CORSMiddleware(app, allow_origins=("https://a.com", "*"), allow_credentials=True)'),
    ("debug-enabled", 489, "DEBUG = True"),
    ("debug-enabled", 489, "app.debug = True"),
    ("debug-enabled", 489, "app.run(host='0.0.0.0', debug=True)"),
    ("debug-enabled", 489, "app = FastAPI(debug=True)"),
]


@pytest.mark.parametrize("rule, cwe, code", POSITIVE)
def test_rule_fires(rule, cwe, code):
    found = lint_diff(new_file("m.py", code + "\n"))
    assert [(f["rule"], f["line"]) for f in found] == [(rule, 1)], found
    assert found[0]["cwe"] == cwe


NEGATIVE = [
    "requests.get(url, verify=True)",
    "requests.get(url, verify='/etc/ssl/ca.pem')",
    "requests.get(url, verify=flag)",
    'subprocess.run(["ls", path], shell=False)',
    'subprocess.run("ls -la", shell=True)',
    'subprocess.run(f"ls {path}")',
    'subprocess.run(f"ls {path}", shell=False)',
    "configure_logging(debug=True)",
    'subprocess.run("ls " + "-la", shell=True)',
    'os.system("clear")',
    "cfg = yaml.safe_load(text)",
    "cfg = yaml.load(text, Loader=yaml.SafeLoader)",
    "cfg = yaml.load(text, yaml.CSafeLoader)",
    "cfg = yaml.load(text, Loader=SafeLoader)",
    "obj = pickle.loads(b'\\x80\\x04N.')",
    "obj = json.loads(request.data)",
    'cur.execute("SELECT * FROM users WHERE id = ?", (uid,))',
    'cur.execute("SELECT 1")',
    'cur.execute(f"SELECT 1")',
    'cur.execute(query, params)',
    'cur.execute("SELECT * FROM " + "users")',
    "token = secrets.token_urlsafe(32)",
    "color = random.choice(COLORS)",
    "delay = random.random()",
    "token = generate()",
    'app.add_middleware(CORSMiddleware, allow_origins=["*"])',
    'app.add_middleware(CORSMiddleware, allow_origins=["https://a.com"], allow_credentials=True)',
    'app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False)',
    "DEBUG = False",
    "DEBUG = os.environ.get('DEBUG') == '1'",
    "app.run(debug=False)",
    "logging.debug('x')",
]


@pytest.mark.parametrize("code", NEGATIVE)
def test_rule_does_not_fire(code):
    assert lint_diff(new_file("m.py", code + "\n")) == []


def test_random_in_function_named_like_token_return():
    code = """\
    def make_session_token():
        return ''.join(random.choices(ALPHABET, k=32))

    def pick_color():
        return random.choice(COLORS)
    """
    assert rules(new_file("tok.py", code)) == [("tok.py", 2, "insecure-random-token")]


def test_multiline_sql_fstring_is_found():
    code = '''\
    def get(cur, uid):
        cur.execute(
            f"SELECT * FROM users WHERE id = {uid}"
        )
    '''
    assert rules(new_file("db.py", code)) == [("db.py", 2, "sql-injection")]


# --- секрети -----------------------------------------------------------------------------------

AWS = "AKIA" + "IOSFODNN7EXAMPLQ"
GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
SK = "sk-" + "proj_9fK3mQ8vLx2TzW5nB7cD1eR4"
HIGH = "k8Jd93LsPq02XmNvB7TzQw41"


def test_secret_values_have_expected_entropy():
    assert entropy(HIGH) > 4.0 and len(HIGH) >= 20
    assert entropy("a" * 30) < 0.1
    assert entropy("Passw0rdPassw0rdPassw0rd") < 3.5


@pytest.mark.parametrize("line", [
    f'AWS_ID = "{AWS}"',
    f"aws_access_key_id={AWS}",
    f'headers = {{"Authorization": "token {GH}"}}',
    f'client = OpenAI(api_key="{SK}")',
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
    "SLACK = 'xoxb-1234567890-abcdefghij'",
    f'API_KEY = "{HIGH}"',
    f'password = "{HIGH}"',
    f"db_password: '{HIGH}'",
    f'"client_secret": "{HIGH}"',
    f'access_token = "{HIGH}"',
    f'PRIVATE_KEY = "{HIGH}"',
])
def test_hardcoded_secret_detected(line):
    found = lint_diff(new_file("conf.py", line + "\n"))
    assert [(f["rule"], f["line"], f["cwe"]) for f in found] == [("hardcoded-secret", 1, 798)]


@pytest.mark.parametrize("line", [
    'API_KEY = os.environ["API_KEY"]',
    'API_KEY = os.getenv("API_KEY")',
    'password = "short"',
    f'color = "{HIGH}"',
    'token = "a" * 30',
    f'token = "{"a" * 30}"',
    'password = "Passw0rdPassw0rdPassw0rd"',
    'api_key = "your-api-key-goes-here-please"',
    'api_key = "EXAMPLE_KEY_FOR_DOCS_ONLY_1234"',
    'token = "changeme-changeme-changeme-1"',
    'secret = "${SECRET_FROM_VAULT_LONG_NAME}"',
    'secret = "<paste-secret-here-xyz-123>"',
    'secret = "{{ vault_secret_value_long }}"',
    'secret = "%(secret_from_config_value)s"',
    'token = "with spaces inside the value long"',
])
def test_not_a_secret(line):
    assert lint_diff(new_file("conf.py", line + "\n")) == []


def test_secret_comment_does_not_echo_the_secret():
    for line in (f'AWS_ID = "{AWS}"', f'API_KEY = "{HIGH}"', f'k = "{GH}"'):
        for f in lint_diff(new_file("conf.py", line + "\n")):
            assert f["comment"].strip()
            for secret in (AWS, HIGH, GH):
                assert secret not in f["comment"]
                assert secret[8:] not in f["comment"]


def test_secret_rule_applies_to_non_python_files_but_ast_rules_do_not():
    diff = new_file(".env", f"API_KEY={AWS}\nDEBUG = True\n") + new_file("deploy.yaml", f'password: "{HIGH}"\n')
    assert rules(diff) == [(".env", 1, "hardcoded-secret"), ("deploy.yaml", 1, "hardcoded-secret")]


def test_existing_secret_in_context_is_not_reported_but_added_one_is():
    diff = f"""\
--- a/conf.py
+++ b/conf.py
@@ -1,2 +1,3 @@
 OLD = "{AWS}"
+NEW = "{GH}"
 x = 1
"""
    assert rules(diff) == [("conf.py", 2, "hardcoded-secret")]


def test_one_secret_finding_per_line():
    line = f'pair = ("{AWS}", "{GH}")'
    assert rules(new_file("c.py", line + "\n")) == [("c.py", 1, "hardcoded-secret")]


# --- підказка виправлення в коментарі ----------------------------------------------------------

HINTS = {
    "tls-verify-disabled": "verify=true",
    "shell-injection": "shell=false",
    "unsafe-yaml-load": "safe_load",
    "unsafe-deserialization": "json",
    "hardcoded-secret": "environment",
    "sql-injection": "parameter",
    "insecure-random-token": "secrets",
    "cors-wildcard-credentials": "origins",
    "debug-enabled": "debug",
}


def test_every_rule_comment_contains_its_fix_hint():
    seen = set()
    for rule, _cwe, code in POSITIVE:
        for f in lint_diff(new_file("m.py", code + "\n")):
            assert HINTS[f["rule"]] in f["comment"].lower(), f
            seen.add(f["rule"])
    for f in lint_diff(new_file("m.py", f'K = "{AWS}"\n')):
        assert HINTS[f["rule"]] in f["comment"].lower()
        seen.add(f["rule"])
    assert seen == set(HINTS)
