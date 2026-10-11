import pytest

from solution import scan_python


def scan(code):
    return scan_python(code)


def test_clean_code_has_no_findings():
    code = """
import subprocess, hashlib, yaml, sqlite3, requests

subprocess.run(["ls", "-l"], check=True)
hashlib.sha256(b"x")
yaml.safe_load("a: 1")
yaml.load("a: 1", Loader=yaml.SafeLoader)
conn = sqlite3.connect(":memory:")
conn.execute("SELECT * FROM t WHERE id = ?", (1,))
requests.get("https://example.com", timeout=3)
"""
    assert scan(code) == []


def test_empty_and_syntax_error():
    assert scan("") == []
    with pytest.raises(ValueError):
        scan("def broken(:\n")


def test_py001_eval_exec_with_lines():
    code = "x = 1\nresult = eval(user_input)\nexec(code)\n"
    assert scan(code) == [(2, "PY001"), (3, "PY001")]


def test_py001_method_named_eval_is_not_builtin():
    assert scan("model.eval()\nself.exec(x)\n") == []


def test_py002_os_system_and_shell_true():
    code = (
        "import os, subprocess\n"
        "os.system('ls')\n"
        "subprocess.run('ls', shell=True)\n"
        "subprocess.Popen(cmd, shell=True, stdout=-1)\n"
        "subprocess.check_output('x', shell=True)\n"
        "subprocess.call('x', shell=True)\n"
        "subprocess.check_call('x', shell=True)\n"
    )
    assert scan(code) == [(2, "PY002"), (3, "PY002"), (4, "PY002"), (5, "PY002"), (6, "PY002"), (7, "PY002")]


def test_py002_shell_false_or_dynamic_is_not_flagged():
    code = "import subprocess\nsubprocess.run(['a'], shell=False)\nsubprocess.run(['a'], shell=flag)\nsubprocess.run(['a'])\n"
    assert scan(code) == []


def test_py002_other_functions_with_shell_true_are_ignored():
    assert scan("import foo\nfoo.run('x', shell=True)\n") == []


def test_py003_pickle_and_yaml():
    code = (
        "import pickle, yaml\n"
        "pickle.loads(data)\n"
        "pickle.load(fh)\n"
        "yaml.load(text)\n"
        "yaml.load(text, Loader=yaml.Loader)\n"
        "yaml.load(text, yaml.FullLoader)\n"
    )
    assert scan(code) == [(2, "PY003"), (3, "PY003"), (4, "PY003"), (5, "PY003"), (6, "PY003")]


@pytest.mark.parametrize(
    "call",
    ["yaml.load(t, Loader=yaml.SafeLoader)", "yaml.load(t, yaml.SafeLoader)", "yaml.load(t, Loader=yaml.CSafeLoader)",
     "yaml.load(t, Loader=yaml.BaseLoader)", "yaml.safe_load(t)"],
)
def test_py003_safe_yaml_variants(call):
    assert scan(f"import yaml\n{call}\n") == []


def test_py004_verify_false():
    code = (
        "import requests, httpx\n"
        "requests.get(url, verify=False)\n"
        "requests.post(url, data=1, verify=False, timeout=3)\n"
        "httpx.get(url, verify=False)\n"
        "requests.get(url, verify=True)\n"
        "requests.get(url, verify='/etc/ca.pem')\n"
        "other.get(url, verify=False)\n"
    )
    assert scan(code) == [(2, "PY004"), (3, "PY004"), (4, "PY004")]


def test_py005_weak_hashes():
    code = (
        "import hashlib\n"
        "hashlib.md5(b'x')\n"
        "hashlib.sha1(b'x')\n"
        "hashlib.md5(b'x', usedforsecurity=False)\n"
        "hashlib.sha256(b'x')\n"
    )
    assert scan(code) == [(2, "PY005"), (3, "PY005")]


@pytest.mark.parametrize(
    "arg",
    ['f"SELECT * FROM t WHERE id = {uid}"', '"SELECT * FROM t WHERE id = " + uid',
     '"SELECT * FROM t WHERE id = %s" % uid', '"SELECT * FROM t WHERE id = {}".format(uid)'],
)
def test_py006_dynamic_sql(arg):
    assert scan(f"cur.execute({arg})\n") == [(1, "PY006")]


def test_py006_executemany_and_other_receivers():
    assert scan('db.session.executemany(f"INSERT INTO t VALUES ({x})", rows)\n') == [(1, "PY006")]


@pytest.mark.parametrize(
    "call",
    ['cur.execute("SELECT 1")', 'cur.execute("SELECT * FROM t WHERE id = ?", (uid,))',
     "cur.execute(QUERY, (uid,))", 'cur.execute("SELECT * FROM t WHERE id = %s", (uid,))',
     'cur.execute("SELECT " "1")'],
)
def test_py006_static_or_parameterized_is_fine(call):
    assert scan(call + "\n") == []


def test_py007_mktemp():
    code = "import tempfile\ntempfile.mktemp()\ntempfile.mkstemp()\ntempfile.NamedTemporaryFile()\n"
    assert scan(code) == [(2, "PY007")]


def test_aliases_are_resolved():
    code = (
        "import subprocess as sp\n"
        "from subprocess import run\n"
        "from os import system as sh\n"
        "import hashlib as h\n"
        "from pickle import loads as unpickle\n"
        "sp.run('x', shell=True)\n"
        "run('x', shell=True)\n"
        "sh('x')\n"
        "h.md5(b'1')\n"
        "unpickle(blob)\n"
    )
    assert scan(code) == [(6, "PY002"), (7, "PY002"), (8, "PY002"), (9, "PY005"), (10, "PY003")]


def test_dotted_import_aliases():
    code = "import os.path as p\nimport os\nos.system('x')\np.join('a', 'b')\n"
    assert scan(code) == [(3, "PY002")]


def test_strings_and_comments_are_not_calls():
    code = (
        '# eval(x) and os.system("rm -rf /")\n'
        'doc = "call eval(user) or exec(code) or os.system(cmd)"\n'
        'def explain():\n    """Never use eval() or pickle.loads()."""\n'
    )
    assert scan(code) == []


def test_nosec_comment_suppresses_only_that_line():
    code = "import os\nos.system('a')  # nosec\nos.system('b')\neval(x)  # nosec: reviewed\n"
    assert scan(code) == [(3, "PY002")]


def test_calls_inside_functions_classes_and_comprehensions_are_found():
    code = (
        "import os\n"
        "class A:\n"
        "    def m(self):\n"
        "        return [eval(x) for x in self.items]\n"
        "def f():\n"
        "    lambda: os.system('x')\n"
    )
    assert scan(code) == [(4, "PY001"), (6, "PY002")]


def test_two_rules_on_one_line_and_sorted_unique():
    code = "import os, pickle\nos.system(pickle.loads(b))\nz = eval('1')\n"
    assert scan(code) == [(2, "PY002"), (2, "PY003"), (3, "PY001")]


def test_multiline_call_reports_first_line():
    code = "import subprocess\nsubprocess.run(\n    ['x'],\n    shell=True,\n)\n"
    assert scan(code) == [(2, "PY002")]


def test_user_defined_function_named_eval_is_ignored_only_when_attribute():
    # просте ім'я `eval` вважаємо вбудованим; атрибут — ні
    assert scan("obj.eval(1)\n") == []
    assert scan("eval(1)\n") == [(1, "PY001")]
