import pytest

from solution import AuthError, SecretNotFound, SecretsClient, TemporaryError


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


class Vault:
    """Мок Secrets Manager із ротацією: current/previous за іменем."""

    def __init__(self, **secrets):
        self.current = dict(secrets)
        self.previous = {}
        self.calls = []
        self.failure = None  # виняток, що кидається замість відповіді

    def rotate(self, name, new_value):
        self.previous[name] = self.current[name]
        self.current[name] = new_value

    def __call__(self, name, stage):
        self.calls.append((name, stage))
        if self.failure:
            raise self.failure
        table = self.current if stage == "AWSCURRENT" else self.previous
        if name not in table:
            raise SecretNotFound(name)
        return table[name]


def make(vault=None, **kw):
    vault = vault or Vault(db="pw-1")
    clock = Clock()
    return SecretsClient(vault, clock=clock, **kw), vault, clock


# ---------- кеш ---------------------------------------------------------------


def test_second_get_is_served_from_cache():
    client, vault, _ = make()
    assert client.get("db") == "pw-1" and client.get("db") == "pw-1"
    assert vault.calls == [("db", "AWSCURRENT")]
    assert client.fetch_count == 1


def test_cache_expires_after_ttl_and_picks_up_rotation():
    client, vault, clock = make(ttl=300)
    client.get("db")
    vault.rotate("db", "pw-2")
    clock.now += 299
    assert client.get("db") == "pw-1"
    clock.now += 1
    assert client.get("db") == "pw-2"
    assert client.fetch_count == 2


def test_separate_cache_entries_per_name():
    client, vault, _ = make(Vault(db="a", api="b"))
    assert (client.get("db"), client.get("api")) == ("a", "b")
    client.get("db")
    assert client.fetch_count == 2


def test_jitter_is_applied_once_per_fetch():
    calls = []

    def jitter(ttl):
        calls.append(ttl)
        return ttl * 0.5

    client, vault, clock = make(ttl=300, jitter=jitter)
    client.get("db")
    clock.now += 149
    client.get("db")
    assert client.fetch_count == 1 and calls == [300]
    clock.now += 1
    client.get("db")
    assert client.fetch_count == 2 and calls == [300, 300]


def test_invalidate_one_and_all():
    client, vault, _ = make(Vault(a="1", b="2"))
    client.get("a")
    client.get("b")
    client.invalidate("a")
    client.get("a")
    client.get("b")
    assert client.fetch_count == 3
    client.invalidate()
    client.get("a")
    client.get("b")
    assert client.fetch_count == 5


# ---------- збої ---------------------------------------------------------------


def test_temporary_error_serves_stale_value_within_max_stale():
    client, vault, clock = make(ttl=300, max_stale=3600)
    client.get("db")
    vault.failure = TemporaryError("throttled")
    clock.now += 301
    assert client.get("db") == "pw-1"
    clock.now += 3000
    assert client.get("db") == "pw-1", "ще молодший за max_stale (3301 < 3600)"
    clock.now += 300
    with pytest.raises(TemporaryError):
        client.get("db")


def test_temporary_error_without_cache_is_raised():
    client, vault, _ = make()
    vault.failure = TemporaryError("down")
    with pytest.raises(TemporaryError):
        client.get("db")


def test_stale_value_is_retried_on_next_call_not_cached_as_fresh():
    client, vault, clock = make(ttl=300)
    client.get("db")
    clock.now += 400
    vault.failure = TemporaryError("blip")
    client.get("db")
    vault.failure = None
    vault.rotate("db", "pw-2")
    assert client.get("db") == "pw-2", "після збою наступний виклик знову йде у fetch"


def test_missing_secret_is_raised_and_not_cached():
    client, vault, _ = make()
    with pytest.raises(SecretNotFound):
        client.get("nope")
    with pytest.raises(SecretNotFound):
        client.get("nope")
    assert client.fetch_count == 2


def test_secret_deleted_after_caching_is_not_served_stale():
    client, vault, clock = make(ttl=10)
    client.get("db")
    del vault.current["db"]
    clock.now += 11
    with pytest.raises(SecretNotFound):
        client.get("db")
    with pytest.raises(SecretNotFound):
        client.get("db")
    vault.failure = TemporaryError("blip")
    with pytest.raises(TemporaryError):
        client.get("db")  # видалений секрет не повинен «воскреснути» зі старого кешу


# ---------- ротація і call_with_secret ----------------------------------------


class Database:
    """Приймає лише пароль, що відповідає поточному стану бази."""

    def __init__(self, accepted):
        self.accepted, self.attempts = set(accepted), []

    def connect(self, password):
        self.attempts.append(password)
        if password not in self.accepted:
            raise AuthError("password rejected")
        return f"connected:{password}"


def test_call_with_secret_happy_path():
    client, vault, _ = make()
    db = Database({"pw-1"})
    assert client.call_with_secret("db", db.connect) == "connected:pw-1"
    assert db.attempts == ["pw-1"]


def test_rotation_cached_old_password_is_replaced_by_fresh_current():
    client, vault, _ = make()
    client.get("db")
    vault.rotate("db", "pw-2")
    db = Database({"pw-2"})
    assert client.call_with_secret("db", db.connect) == "connected:pw-2"
    assert db.attempts == ["pw-1", "pw-2"]
    assert client.get("db") == "pw-2"
    assert client.fetch_count == 2, "свіже значення закешовано"


def test_rotation_in_progress_falls_back_to_previous():
    client, vault, _ = make()
    vault.rotate("db", "pw-2")  # у Secrets Manager вже новий пароль, а база ще приймає старий
    db = Database({"pw-1"})
    assert client.call_with_secret("db", db.connect) == "connected:pw-1"
    assert db.attempts == ["pw-2", "pw-1"]
    assert vault.calls == [("db", "AWSCURRENT"), ("db", "AWSCURRENT"), ("db", "AWSPREVIOUS")]
    assert client.get("db") == "pw-2", "у кеші лишається свіже AWSCURRENT, не PREVIOUS"
    assert client.fetch_count == 3


def test_auth_error_when_nothing_works_is_raised_after_bounded_attempts():
    client, vault, _ = make()
    db = Database(set())
    with pytest.raises(AuthError):
        client.call_with_secret("db", db.connect)
    assert len(db.attempts) <= 2


def test_non_auth_errors_are_not_retried_and_do_not_refetch():
    client, vault, _ = make()

    def broken(password):
        raise ConnectionError("db unreachable")

    with pytest.raises(ConnectionError):
        client.call_with_secret("db", broken)
    assert client.fetch_count == 1


def test_retry_result_is_final_even_if_it_fails_again():
    client, vault, _ = make()
    client.get("db")
    vault.rotate("db", "pw-2")

    def always_denied(password):
        raise AuthError("denied")

    with pytest.raises(AuthError):
        client.call_with_secret("db", always_denied)
    assert ("db", "AWSPREVIOUS") not in vault.calls, "новий CURRENT відрізнявся: повтор один, до PREVIOUS не йдемо"


# ---------- безпека ------------------------------------------------------------


def test_secret_values_never_appear_in_repr_or_str():
    client, vault, _ = make(Vault(db="s3cr3t-value"))
    client.get("db")
    assert "s3cr3t-value" not in repr(client)
    assert "s3cr3t-value" not in str(client)
