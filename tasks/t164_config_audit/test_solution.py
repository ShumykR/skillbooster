import copy

import pytest

from solution import WEAK_SECRETS, audit_settings

GOOD = {
    "debug": False,
    "docs_url": None,
    "redoc_url": None,
    "openapi_url": None,
    "cors_allow_origins": ["https://app.example.com"],
    "cors_allow_credentials": True,
    "allowed_hosts": ["api.example.com"],
    "secret_key": "k3Jx9-Qm2vL8pRtZ4nWb7YcHd1FsAe6UgXo0IqPzTy5",
    "session_cookie_secure": True,
    "session_cookie_httponly": True,
    "session_cookie_samesite": "lax",
    "database_url": "postgresql://app:Zr7!pQ2x@db.internal:5432/app?sslmode=require",
    "show_error_details": False,
    "log_level": "INFO",
    "public_url": "https://api.example.com",
}


def audit(env="prod", **over):
    s = copy.deepcopy(GOOD)
    for k, v in over.items():
        if v is KeyError:
            s.pop(k, None)
        else:
            s[k] = v
    return audit_settings(env, s)


# --- базові ------------------------------------------------------------------------------------------

def test_good_configuration_is_clean():
    assert audit_settings("prod", GOOD) == []
    assert audit_settings("staging", GOOD) == []


def test_good_configuration_is_not_modified():
    s = copy.deepcopy(GOOD)
    audit_settings("prod", s)
    assert s == GOOD


def test_empty_settings_violate_the_fail_closed_rules():
    # без явних налаштувань безпечності: hosts, ключ, cookie
    assert audit_settings("prod", {}) == ["CFG004", "CFG005", "CFG006"]


@pytest.mark.parametrize("env", ["prod", "PROD", " Production ", "staging", "Staging"])
def test_strict_envs_and_case_insensitivity(env):
    assert audit_settings(env, {**GOOD, "debug": True}) == ["CFG001"]


@pytest.mark.parametrize("env", ["dev", "development", "local", "test", "DEV", " Test "])
def test_lax_envs_allow_everything(env):
    assert audit_settings(env, {"debug": True, "secret_key": "changeme", "docs_url": "/docs", "cors_allow_origins": ["*"]}) == []
    assert audit_settings(env, {}) == []


@pytest.mark.parametrize("env", ["", "qa", "production2", None, 5, "pro", "prod-eu"])
def test_unknown_env_is_value_error(env):
    with pytest.raises(ValueError):
        audit_settings(env, GOOD)


@pytest.mark.parametrize("settings", [None, [], "debug", 5])
def test_settings_must_be_dict(settings):
    with pytest.raises(TypeError):
        audit_settings("prod", settings)


def test_unknown_keys_are_ignored():
    assert audit("prod", something_else=True, debug_toolbar=True) == []


def test_result_is_sorted_and_unique():
    result = audit("prod", debug=True, docs_url="/docs", redoc_url="/redoc", cors_allow_origins=["*", "null"],
                   log_level="debug", public_url="http://x")
    assert result == ["CFG001", "CFG002", "CFG003", "CFG009", "CFG010"]
    assert result == sorted(set(result))


# --- булеві значення з env-змінних ------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [True, "true", "True", "1", "yes", "on", " TRUE ", 1, "enabled", "anything"])
def test_truthy_debug_values(value):
    assert audit("prod", debug=value) == ["CFG001"]


@pytest.mark.parametrize("value", [False, "false", "False", "0", "no", "off", "", "  ", "none", "None", "null", 0, None])
def test_falsy_debug_values(value):
    assert audit("prod", debug=value) == []


def test_missing_debug_is_fine():
    assert audit("prod", debug=KeyError) == []


@pytest.mark.parametrize("key", ["session_cookie_secure", "session_cookie_httponly"])
@pytest.mark.parametrize("value", [False, "false", "0", "", None, KeyError])
def test_cookie_flags_must_be_explicitly_true(key, value):
    assert audit("prod", **{key: value}) == ["CFG006"]


@pytest.mark.parametrize("value", ["true", "1", "yes"])
def test_cookie_flags_from_strings(value):
    assert audit("prod", session_cookie_secure=value, session_cookie_httponly=value) == []


# --- CFG002 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["docs_url", "redoc_url", "openapi_url"])
def test_exposed_docs(key):
    assert audit("prod", **{key: "/anything"}) == ["CFG002"]


@pytest.mark.parametrize("value", [None, "", False, "none", "false", KeyError])
def test_hidden_docs(value):
    assert audit("prod", docs_url=value, redoc_url=value, openapi_url=value) == []


# --- CFG003 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("origins", [["*"], ["https://a.com", "*"], ["null"], ["NULL"], [" * "], ("*",)])
def test_dangerous_cors(origins):
    assert audit("prod", cors_allow_origins=origins) == ["CFG003"]


@pytest.mark.parametrize("origins", [[], ["https://a.com", "https://b.com"], ["https://*.example.com"], KeyError, None])
def test_non_wildcard_cors(origins):
    assert audit("prod", cors_allow_origins=origins) == []


# --- CFG004 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("hosts", [KeyError, None, [], (), ["*"], ["api.example.com", "*"], "api.example.com", "*"])
def test_bad_allowed_hosts(hosts):
    assert audit("prod", allowed_hosts=hosts) == ["CFG004"]


@pytest.mark.parametrize("hosts", [["api.example.com"], ("a.com", "b.com"), ["*.example.com"], ["localhost"]])
def test_good_allowed_hosts(hosts):
    assert audit("prod", allowed_hosts=hosts) == []


# --- CFG005 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "key",
    [KeyError, None, "", 123, b"x" * 40, "short-key", "x" * 31, "a" * 40, "abab" * 20, "ab12" * 10, "changeme", " CHANGEME ",
     "Secret", "your-secret-key", "Please-Change-Me", ["k" * 40]],
)
def test_weak_secret_keys(key):
    assert audit("prod", secret_key=key) == ["CFG005"]


def test_secret_exactly_32_chars_with_variety_is_ok():
    assert audit("prod", secret_key="aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bD2fG") == []


def test_weak_secrets_constant_contains_the_usual_suspects():
    assert {"changeme", "secret", "password"} <= set(WEAK_SECRETS)


# --- CFG006 samesite -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [KeyError, None, "", "none", "None", "NONE", " none "])
def test_bad_samesite(value):
    assert audit("prod", session_cookie_samesite=value) == ["CFG006"]


@pytest.mark.parametrize("value", ["lax", "Lax", "STRICT", "strict"])
def test_good_samesite(value):
    assert audit("prod", session_cookie_samesite=value) == []


# --- CFG007 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "postgresql://app:Zr7pQ2x@db/app?sslmode=disable",
        "postgresql://app:Zr7pQ2x@db/app?application_name=x&sslmode=disable",
        "postgresql://app:Zr7pQ2x@db/app?sslmode=DISABLE",
        "postgresql://postgres:postgres@db/app",
        "postgresql://app:app@db/app",
        "postgresql://root:root@db:5432/app",
        "postgresql://admin:Admin@db/app",
        "mysql://svc:password@db/app",
        "postgresql://app:p%61ssword@db/app",  # %61 = 'a': пароль «password»
        "postgresql://alice:alice@db/app",
        "postgresql+asyncpg://postgres:changeme@db.internal/app",
    ],
)
def test_bad_database_urls(url):
    assert audit("prod", database_url=url) == ["CFG007"]


@pytest.mark.parametrize(
    "url",
    [
        KeyError,
        None,
        "postgresql://app:Zr7pQ2x@db/app",
        "postgresql://app:Zr7pQ2x@db/app?sslmode=require",
        "postgresql://app:Zr7pQ2x@db/app?sslmode=verify-full",
        "postgresql://app@db/app",
        "postgresql://db/app",
        "sqlite:///./app.db",
        "not a url at all",
    ],
)
def test_ok_or_ignored_database_urls(url):
    assert audit("prod", database_url=url) == []


def test_malformed_database_url_does_not_crash():
    assert isinstance(audit("prod", database_url="postgresql://app:secret@[::1/app"), list)
    assert isinstance(audit("prod", database_url=12345), list)


def test_sslmode_in_the_password_or_path_is_not_a_query():
    assert audit("prod", database_url="postgresql://app:sslmode=disableX9@db/app") == []


# --- CFG008 – CFG010 --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [True, "true", "1", "yes"])
def test_error_details(value):
    assert audit("prod", show_error_details=value) == ["CFG008"]


@pytest.mark.parametrize("level", ["debug", "DEBUG", "Trace", " debug "])
def test_verbose_logging(level):
    assert audit("prod", log_level=level) == ["CFG009"]


@pytest.mark.parametrize("level", ["info", "INFO", "warning", "error", KeyError, None, 10])
def test_normal_logging(level):
    assert audit("prod", log_level=level) == []


@pytest.mark.parametrize("url", ["http://api.example.com", "HTTP://api.example.com", " http://x"])
def test_insecure_public_url(url):
    assert audit("prod", public_url=url) == ["CFG010"]


@pytest.mark.parametrize("url", ["https://api.example.com", "HTTPS://x", KeyError, None, "", "api.example.com"])
def test_secure_or_missing_public_url(url):
    assert audit("prod", public_url=url) == []


# --- комбінації --------------------------------------------------------------------------------------------------------

def test_a_typical_copied_dev_config_hits_most_rules():
    dev_like = {
        "debug": "true", "docs_url": "/docs", "openapi_url": "/openapi.json", "cors_allow_origins": ["*"],
        "allowed_hosts": ["*"], "secret_key": "changeme", "database_url": "postgresql://postgres:postgres@localhost/app",
        "show_error_details": "1", "log_level": "DEBUG", "public_url": "http://localhost:8000",
    }
    assert audit_settings("production", dev_like) == [f"CFG{i:03}" for i in range(1, 11)]
    assert audit_settings("dev", dev_like) == []


def test_rules_are_independent():
    for rule, over in {
        "CFG001": {"debug": True}, "CFG002": {"docs_url": "/d"}, "CFG003": {"cors_allow_origins": ["*"]},
        "CFG004": {"allowed_hosts": ["*"]}, "CFG005": {"secret_key": "x"}, "CFG006": {"session_cookie_secure": False},
        "CFG007": {"database_url": "postgresql://u:u@h/d"}, "CFG008": {"show_error_details": True},
        "CFG009": {"log_level": "debug"}, "CFG010": {"public_url": "http://x"},
    }.items():
        assert audit("prod", **over) == [rule], rule
