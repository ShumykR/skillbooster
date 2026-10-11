import pytest

from solution import crashloop_backoff, diagnose, recommend_memory_limit


# ---------- diagnose: образ і конфігурація ----------

@pytest.mark.parametrize("reason", ["ErrImagePull", "ImagePullBackOff", "InvalidImageName"])
def test_image_pull(reason):
    assert diagnose({"reason": reason}) == "IMAGE_PULL"


def test_image_pull_wins_over_exit_code():
    assert diagnose({"reason": "ImagePullBackOff", "exit_code": 137}) == "IMAGE_PULL"


def test_config_error():
    assert diagnose({"reason": "CreateContainerConfigError"}) == "MISSING_CONFIG"


def test_config_error_before_no_failure():
    assert diagnose({"reason": "CreateContainerConfigError", "exit_code": None}) == "MISSING_CONFIG"


@pytest.mark.parametrize("state", [
    {},
    {"reason": "Running"},
    {"reason": "ContainerCreating"},
    {"exit_code": None, "log": "address already in use"},
])
def test_no_failure_without_exit_code(state):
    assert diagnose(state) == "NO_FAILURE"


# ---------- diagnose: памʼять ----------

def test_oom_by_reason():
    assert diagnose({"reason": "OOMKilled", "exit_code": 137}) == "OOM_KILLED"


def test_oom_reason_without_limits():
    assert diagnose({"reason": "OOMKilled", "exit_code": 1}) == "OOM_KILLED"


def test_oom_by_peak_close_to_limit():
    assert diagnose({"exit_code": 137, "memory_limit_mb": 512, "peak_memory_mb": 500}) == "OOM_KILLED"


def test_oom_threshold_exactly_90_percent():
    assert diagnose({"exit_code": 137, "memory_limit_mb": 1000, "peak_memory_mb": 900}) == "OOM_KILLED"


def test_not_oom_just_below_90_percent():
    assert diagnose({"exit_code": 137, "memory_limit_mb": 1000, "peak_memory_mb": 899}) == "KILLED_SIGKILL"


def test_sigkill_with_low_memory_is_not_oom():
    assert diagnose({"exit_code": 137, "memory_limit_mb": 512, "peak_memory_mb": 100}) == "KILLED_SIGKILL"


@pytest.mark.parametrize("limit, peak", [(None, 500), (512, None), (None, None)])
def test_sigkill_with_partial_memory_data(limit, peak):
    assert diagnose({"exit_code": 137, "memory_limit_mb": limit, "peak_memory_mb": peak}) == "KILLED_SIGKILL"


def test_high_peak_but_other_exit_code_is_not_oom():
    assert diagnose({"exit_code": 1, "memory_limit_mb": 512, "peak_memory_mb": 510}) == "APP_ERROR"


# ---------- diagnose: liveness ----------

def test_liveness_kill_sigterm():
    st = {"exit_code": 143, "events": ["Warning  Unhealthy  Liveness probe failed: HTTP probe failed with statuscode: 500"]}
    assert diagnose(st) == "LIVENESS_KILLED"


def test_liveness_kill_sigkill():
    assert diagnose({"exit_code": 137, "events": ["liveness probe failed"]}) == "LIVENESS_KILLED"


def test_liveness_ignored_for_other_exit_codes():
    assert diagnose({"exit_code": 1, "events": ["Liveness probe failed"]}) == "APP_ERROR"


def test_readiness_probe_event_is_not_liveness():
    assert diagnose({"exit_code": 143, "events": ["Readiness probe failed"]}) == "SIGTERM"


def test_oom_beats_liveness():
    st = {"reason": "OOMKilled", "exit_code": 137, "events": ["Liveness probe failed"]}
    assert diagnose(st) == "OOM_KILLED"


# ---------- diagnose: коди виходу ----------

@pytest.mark.parametrize("code, verdict", [
    (137, "KILLED_SIGKILL"),
    (143, "SIGTERM"),
    (126, "NOT_EXECUTABLE"),
    (127, "COMMAND_NOT_FOUND"),
    (139, "SEGFAULT"),
])
def test_exit_code_table(code, verdict):
    assert diagnose({"exit_code": code}) == verdict


def test_exit_code_beats_log_patterns():
    assert diagnose({"exit_code": 127, "log": "ModuleNotFoundError: No module named 'x'"}) == "COMMAND_NOT_FOUND"


def test_exit_zero_with_always_restarts():
    assert diagnose({"exit_code": 0}) == "EXITED_CLEANLY"
    assert diagnose({"exit_code": 0, "restart_policy": "Always"}) == "EXITED_CLEANLY"


@pytest.mark.parametrize("policy", ["OnFailure", "Never"])
def test_exit_zero_is_fine_for_jobs(policy):
    assert diagnose({"exit_code": 0, "restart_policy": policy}) == "NO_FAILURE"


# ---------- diagnose: логи ----------

@pytest.mark.parametrize("log, verdict", [
    ("OSError: [Errno 98] Address already in use", "PORT_IN_USE"),
    ("Error: listen EADDRINUSE: address", "PORT_IN_USE"),
    ("standard_init_linux.go: exec user process caused: exec format error", "EXEC_FORMAT"),
    ("ModuleNotFoundError: No module named 'fastapi'", "MISSING_DEPENDENCY"),
    ("Error: Cannot find module 'express'", "MISSING_DEPENDENCY"),
    ("PermissionError: [Errno 13] Permission denied: '/data'", "PERMISSION_DENIED"),
    ("psycopg.OperationalError: connection refused", "DEPENDENCY_UNAVAILABLE"),
    ("socket.gaierror: Name or service not known", "DEPENDENCY_UNAVAILABLE"),
    ("RuntimeError: DATABASE_URL is not set", "MISSING_CONFIG"),
    ("ValueError: missing required setting SECRET_KEY", "MISSING_CONFIG"),
    ("Traceback ... ZeroDivisionError", "APP_ERROR"),
    ("", "APP_ERROR"),
])
def test_log_patterns(log, verdict):
    assert diagnose({"exit_code": 1, "log": log}) == verdict


def test_log_patterns_ignore_case():
    assert diagnose({"exit_code": 2, "log": "ADDRESS ALREADY IN USE"}) == "PORT_IN_USE"


def test_log_priority_first_rule_wins():
    log = "connection refused\nPermission denied\nNo module named x"
    assert diagnose({"exit_code": 1, "log": log}) == "MISSING_DEPENDENCY"
    assert diagnose({"exit_code": 1, "log": "connection refused; DB_URL is not set"}) == "DEPENDENCY_UNAVAILABLE"
    assert diagnose({"exit_code": 1, "log": "permission denied and exec format error"}) == "EXEC_FORMAT"
    assert diagnose({"exit_code": 1, "log": "exec format error, address already in use"}) == "PORT_IN_USE"


def test_missing_log_key():
    assert diagnose({"exit_code": 1}) == "APP_ERROR"
    assert diagnose({"exit_code": 1, "log": None, "events": None}) == "APP_ERROR"


def test_does_not_mutate_state():
    st = {"exit_code": 1, "log": "x", "events": ["a"]}
    before = repr(st)
    diagnose(st)
    assert repr(st) == before


# ---------- crashloop_backoff ----------

@pytest.mark.parametrize("n, sec", [
    (-3, 0), (0, 0), (1, 10), (2, 20), (3, 40), (4, 80), (5, 160), (6, 300), (7, 300), (50, 300), (1000, 300),
])
def test_backoff(n, sec):
    assert crashloop_backoff(n) == sec


# ---------- recommend_memory_limit ----------

def test_recommend_basic():
    # 400 * 1.25 = 500 -> 512
    assert recommend_memory_limit([200, 400, 350]) == 512


def test_recommend_exact_multiple_not_rounded_up():
    # 256 * 1.25 = 320 = 5 * 64
    assert recommend_memory_limit([256]) == 320


def test_recommend_rounds_up_just_above():
    # 257 * 1.25 = 321.25 -> 384
    assert recommend_memory_limit([257]) == 384


def test_recommend_uses_maximum():
    assert recommend_memory_limit([100, 100, 100, 800]) == recommend_memory_limit([800])


def test_recommend_custom_headroom_and_step():
    assert recommend_memory_limit([100], headroom_pct=0, step_mb=64) == 128
    assert recommend_memory_limit([128], headroom_pct=0, step_mb=64) == 128
    assert recommend_memory_limit([100], headroom_pct=50, step_mb=10) == 150
    assert recommend_memory_limit([100], headroom_pct=51, step_mb=10) == 160


def test_recommend_at_least_the_peak():
    for peak in (1, 63, 64, 65, 999):
        assert recommend_memory_limit([peak]) >= peak


def test_recommend_returns_int():
    assert type(recommend_memory_limit([300])) is int


def test_recommend_accepts_any_iterable():
    assert recommend_memory_limit(x for x in (200, 400)) == 512


@pytest.mark.parametrize("args, kwargs", [
    (([],), {}),
    (([0],), {}),
    (([100, -5],), {}),
    (([100],), {"headroom_pct": -1}),
    (([100],), {"step_mb": 0}),
    (([100],), {"step_mb": -64}),
])
def test_recommend_invalid(args, kwargs):
    with pytest.raises(ValueError):
        recommend_memory_limit(*args, **kwargs)
