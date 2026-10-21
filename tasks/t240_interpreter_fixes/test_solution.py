import base64
import hashlib
import hmac
import importlib
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

import solution as sol

HERE = Path(__file__).resolve().parent
SECRET = b"k" * 32
FLAG = "PWNED_T240"
EXEC_PAYLOAD = f"import os; os.environ['{FLAG}'] = '1'"


@pytest.fixture(autouse=True)
def clean_flag(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    yield
    leaked = FLAG in os.environ
    os.environ.pop(FLAG, None)
    assert not leaked, "зловмисний код виконався"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def signed(payload: str, secret=SECRET) -> str:
    return payload + "." + hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


class Evil:
    def __reduce__(self):
        return (exec, (EXEC_PAYLOAD,))


def run_isolated(kind, payloads, timeout=15):
    """Виконує solution.<kind>(payload) у дочірньому процесі: зависання не валить тести."""
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(HERE)!r})\n"
        "import solution\n"
        "fn = getattr(solution, sys.argv[1])\n"
        "out = []\n"
        "for p in json.loads(sys.stdin.read()):\n"
        "    try:\n"
        "        r = fn(p)\n"
        "        out.append(['returned', repr(r)[:40]])\n"
        "    except ValueError:\n"
        "        out.append(['ValueError', ''])\n"
        "    except BaseException as e:\n"
        "        out.append([type(e).__name__, ''])\n"
        "print(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", code, kind], input=json.dumps(payloads),
                              capture_output=True, text=True, timeout=timeout, cwd=str(HERE))
    except subprocess.TimeoutExpired:
        pytest.fail(f"{kind}: перевищено {timeout} с (DoS: вхід вішає процес)")
    assert proc.returncode == 0, proc.stderr[-500:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


# --- 1. cookie сесії ---------------------------------------------------------------------------

def test_session_roundtrip_and_exact_format():
    data = {"user_id": 7, "roles": ["a", "b"], "name": "Оля", "nested": {"x": None, "y": 1.5, "z": True}}
    cookie = sol.dump_session(data, SECRET)
    assert sol.load_session(cookie, SECRET) == data
    payload = b64url(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
    assert cookie == signed(payload)


def test_session_tampering_is_rejected():
    cookie = sol.dump_session({"role": "user"}, SECRET)
    payload, tag = cookie.split(".")
    forged = b64url(json.dumps({"role": "admin"}, separators=(",", ":"), sort_keys=True).encode())
    for bad in [forged + "." + tag, payload + "." + "0" * 64, payload + "." + tag[:-1],
                payload + "." + tag.upper(), payload, "." + tag, payload + "." + tag + ".x"]:
        with pytest.raises(ValueError):
            sol.load_session(bad, SECRET)


def test_session_wrong_secret():
    cookie = sol.dump_session({"a": 1}, SECRET)
    with pytest.raises(ValueError):
        sol.load_session(cookie, b"z" * 32)


@pytest.mark.parametrize("bad", ["", ".", "é.é", "abc", None, 5, b"a.b", ["a"]])
def test_session_garbage_is_value_error(bad):
    with pytest.raises(ValueError):
        sol.load_session(bad, SECRET)


def test_session_tag_compared_in_constant_time(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    importlib.reload(sol)
    try:
        cookie = sol.dump_session({"a": 1}, SECRET)
        assert sol.load_session(cookie, SECRET) == {"a": 1}
        assert calls
    finally:
        monkeypatch.undo()
        importlib.reload(sol)


def test_session_unsigned_pickle_is_rejected_and_not_executed():
    evil = base64.urlsafe_b64encode(pickle.dumps(Evil())).decode()
    with pytest.raises(ValueError):
        sol.load_session(evil, SECRET)
    with pytest.raises(ValueError):
        sol.load_session(evil + "." + "0" * 64, SECRET)


def test_session_correctly_signed_pickle_is_still_not_executed():
    cookie = signed(b64url(pickle.dumps(Evil())))
    with pytest.raises(ValueError):
        sol.load_session(cookie, SECRET)


def test_session_signed_non_object_json_rejected():
    for raw in (b"[1,2]", b"42", b'"str"', b"null", b"{broken"):
        with pytest.raises(ValueError):
            sol.load_session(signed(b64url(raw)), SECRET)


# --- 2. YAML -----------------------------------------------------------------------------------

def test_config_honest_documents():
    text = "name: app\nport: 8080\ntags: [a, b]\nnested:\n  debug: true\n  ratio: 0.5\n"
    assert sol.load_config(text) == {"name": "app", "port": 8080, "tags": ["a", "b"],
                                     "nested": {"debug": True, "ratio": 0.5}}
    assert sol.load_config("a: &x 1\nb: *x\n") == {"a": 1, "b": 1}


@pytest.mark.parametrize("text", [
    f"x: !!python/object/apply:builtins.exec [\"{EXEC_PAYLOAD}\"]",
    "x: !!python/object/apply:os.system [\"echo hacked\"]",
    f"!!python/object/apply:builtins.exec [\"{EXEC_PAYLOAD}\"]",
    "x: !!python/name:os.system",
    "x: !!python/object/new:subprocess.Popen [[\"echo\"]]",
])
def test_config_python_tags_rejected(text):
    with pytest.raises(ValueError):
        sol.load_config(text)


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just a string", "42", "a: [", "a: b: c", None, 123, b"a: 1"])
def test_config_invalid_inputs(text):
    with pytest.raises(ValueError):
        sol.load_config(text)


def test_config_size_limit():
    assert sol.load_config("a: " + "x" * (65536 - 3)) == {"a": "x" * (65536 - 3)}
    with pytest.raises(ValueError):
        sol.load_config("a: " + "x" * (65536 - 2))


# --- 3. калькулятор ----------------------------------------------------------------------------

@pytest.mark.parametrize("expr, expected", [
    ("1+2*3", 7), ("(1+2)*3", 9), ("2**3**2", 512), ("-2**2", -4), ("7//2", 3), ("-7//2", -4), ("-7%3", 2),
    ("7/2", 3.5), ("+5", 5), ("--5", 5), ("1_000+1", 1001), ("1.5e3", 1500.0), ("2**-1", 0.5), ("2**0.5", 2 ** 0.5),
    ("  1 + 1  ", 2), ("10%4*3", 6), ("2**1000", 2 ** 1000), ("2**1000*2**23", 2 ** 1023), ("0.1+0.2", 0.1 + 0.2), ("0x10", 16),
    ("+".join(["1"] * 90), 90),
])
def test_calc_honest(expr, expected):
    result = sol.calc(expr)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize("expr", [
    "__import__('os').environ.setdefault('PWNED_T240','1')", "().__class__.__bases__[0].__subclasses__()",
    "(lambda: 1)()", "[x for x in range(3)]", "'a'*3", "abs(-1)", "x", "1 if 1 else 2", "1 < 2", "not 1", "~1",
    "1 << 3", "1 & 1", "1 | 1", "1 ^ 1", "True", "False", "None", "1j", "...", "[1,2]", "{1:2}", "(1,2)", "1; 2",
    "a.b", "1 @ 2", "exec('x=1')", "f'{1}'", "1,", "", "   ", "1 2", "1 +", "(", "((1)", "1 and 2", "-True",
    "(-8)**0.5", "2 .real", "1 if",
])
def test_calc_rejects_everything_else(expr):
    with pytest.raises(ValueError):
        sol.calc(expr)


@pytest.mark.parametrize("expr", ["1/0", "1//0", "1%0", "0**-1", "0.0**-1", "1e308*10", "10.0**1000", "1e400",
                                  "2**1001", "2**1024", "(2**1000)*(2**1000)", "2**1000*2**24", "1" * 201])
def test_calc_limits(expr):
    with pytest.raises(ValueError):
        sol.calc(expr)


def test_calc_allows_two_hundred_chars():
    assert sol.calc("1" + "+1" * 99) == 100


def test_calc_dos_payloads_are_rejected_quickly():
    payloads = ["9**9**9", "10**10**10", "(9**9)**(9**9)", "1<<10000000", "2**2**2**2**2", "(9**1000)**1000",
                "9**9**9**9", "7**7**7**7", "'a'*10**8", "((2**1000)**1000)**1000"]
    outcomes = run_isolated("calc", payloads)
    assert [o[0] for o in outcomes] == ["ValueError"] * len(payloads), list(zip(payloads, outcomes))


# --- 4. шаблон листа ---------------------------------------------------------------------------

USER = {"name": "Ann", "email": "ann@example.com", "plan": "pro"}


def test_template_honest():
    assert sol.render_email("Hi {name}, plan {plan}, mail {email}.", USER) == "Hi Ann, plan pro, mail ann@example.com."
    assert sol.render_email("{{literal}} {name}", USER) == "{literal} Ann"
    assert sol.render_email("no placeholders", USER) == "no placeholders"
    assert sol.render_email("{name}{name}", USER) == "AnnAnn"
    assert sol.render_email("n={plan}", {**USER, "plan": 3, "extra": "ignored"}) == "n=3"
    assert sol.render_email("{name}", {"name": "only"}) == "only"


def test_template_substitution_is_single_pass():
    user = {**USER, "name": "{email} {{x}} {name}"}
    assert sol.render_email("Hi {name}!", user) == "Hi {email} {{x}} {name}!"


@pytest.mark.parametrize("tpl", [
    "{user.__init__.__globals__[SECRET_KEY]}", "{user.__class__}", "{name.__class__}", "{name.upper}", "{name[0]}",
    "{name!r}", "{name!s}", "{name:>10}", "{name:{plan}}", "{0}", "{}", "{unknown}", "{", "}", "{name", "name}",
    "{name}}", "{ name }", "{NAME}", "{email.__len__}", "{plan.real}", "{{name}", "{name}{",
])
def test_template_rejects_anything_but_plain_allowed_fields(tpl):
    with pytest.raises(ValueError):
        sol.render_email(tpl, USER)


def test_template_missing_field_is_value_error():
    with pytest.raises(ValueError):
        sol.render_email("{plan}", {"name": "x"})


def test_template_never_leaks_module_secret():
    for tpl in ["{user.__init__.__globals__[SECRET_KEY]}", "{user.__class__.__init__.__globals__}"]:
        try:
            out = sol.render_email(tpl, USER)
        except ValueError:
            continue
        assert sol.SECRET_KEY not in out


# --- 5. email ----------------------------------------------------------------------------------

LOCAL64 = "a" * 64
DOMAIN_189 = "b" * 63 + "." + "b" * 63 + "." + "b" * 58 + ".co"


@pytest.mark.parametrize("addr", [
    "a@b.co", "john.doe+tag@sub.example.com", "a_b-c@x-y.io", "A1@B2.COM", "a.b.c@d.ef", "1@2.ab",
    "x@" + "y" * 63 + ".com", LOCAL64 + "@b.co", LOCAL64 + "@" + DOMAIN_189,
])
def test_email_valid(addr):
    assert len(addr) <= 254
    assert sol.validate_email(addr) is True


@pytest.mark.parametrize("addr", [
    "", "a", "@b.co", "a@", "a@b", "a@b.c", "a@b.c0m", "a@b.12", ".a@b.co", "a.@b.co", "a..b@b.co", "-a@b.co",
    "a-@b.co", "a+-b@b.co", "a@-b.co", "a@b-.co", "a@b..co", "a@.co", "a@b.co.", "a@@b.co", "a@b@c.co", "a b@b.co",
    "a@b .co", "a@b.co\n", "\na@b.co", "a@b.co ", "a@b.co\x00", "é@b.co", "a@é.co", "٣@b.co", "a@b.٣o",
    "a" * 65 + "@b.co", "a@" + "x" * 64 + ".com", "a@b." + "c" * 64, LOCAL64 + "@" + DOMAIN_189 + "b",
    "a%b@b.co", "a!b@b.co", "a@b_c.co",
])
def test_email_invalid(addr):
    assert sol.validate_email(addr) is False


@pytest.mark.parametrize("bad", [None, 123, b"a@b.co", ["a@b.co"]])
def test_email_non_string(bad):
    assert sol.validate_email(bad) is False


def test_email_total_length_limit():
    assert len(LOCAL64 + "@" + DOMAIN_189) == 254
    assert sol.validate_email(LOCAL64 + "@" + DOMAIN_189) is True
    assert sol.validate_email(LOCAL64 + "@" + DOMAIN_189 + "x") is False


def test_email_redos_payloads_finish_fast():
    payloads = [
        "a" * 60 + "!", "a." * 30 + "!", "a" * 100_000 + "!", "a" * 30 + "@" + "b-" * 40 + "!", "a-" * 40000,
        "a" * 40 + "@" + "b." * 60 + "!", ("a" * 30 + ".") * 5 + "!", "a" * 25 + "@" + "b" * 100_000,
        "a@" + ("b." * 30000), "a" * 200 + "!" + "a" * 200, "a+" * 50 + "@", "-" * 100_000 + "@b.co",
    ]
    outcomes = run_isolated("validate_email", payloads, timeout=10)
    assert [o[0] for o in outcomes] == ["returned"] * len(payloads)
    assert all(o[1] == "False" for o in outcomes), list(zip(payloads, outcomes))
