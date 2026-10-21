import asyncio
import inspect
import textwrap

import pytest

from solution import audit_source, fail_closed


def audit(src):
    return audit_source(textwrap.dedent(src).lstrip("\n"))


# --- чистий код: жодних знахідок -----------------------------------------------------------------

def test_clean_code_has_no_findings():
    src = """
    import logging
    log = logging.getLogger(__name__)

    def load(path):
        try:
            return open(path).read()
        except FileNotFoundError:
            return None
        except (KeyError, ValueError):
            pass
        except Exception as e:
            log.exception("load failed")
            raise RuntimeError("load failed") from e
        finally:
            log.info("done")
    """
    assert audit(src) == []


def test_empty_and_trivial_sources():
    assert audit("") == []
    assert audit("x = 1\n") == []


def test_syntax_error_is_value_error():
    with pytest.raises(ValueError):
        audit_source("def broken(:\n    pass\n")


# --- bare-except / swallowed / broad-except ----------------------------------------------------

def test_bare_except_pass():
    src = """
    def f():
        try:
            risky()
        except:
            pass
    """
    assert audit(src) == [("bare-except", 4), ("swallowed", 4)]


def test_bare_except_that_reraises_is_still_bare():
    src = """
    try:
        risky()
    except:
        log()
        raise
    """
    assert audit(src) == [("bare-except", 3)]


def test_except_exception_pass():
    src = """
    try:
        risky()
    except Exception:
        pass
    """
    assert audit(src) == [("broad-except", 3), ("swallowed", 3)]


@pytest.mark.parametrize("handler", [
    "except BaseException:", "except builtins.Exception:", "except (ValueError, Exception):",
    "except (KeyError, builtins.BaseException) as e:",
])
def test_broad_variants_are_detected(handler):
    src = f"import builtins\ntry:\n    x()\n{handler}\n    pass\n"
    assert audit_source(src) == [("broad-except", 4), ("swallowed", 4)]


@pytest.mark.parametrize("body", ["...", "continue", "'ignored'", "pass; continue"])
def test_trivial_bodies(body):
    src = f"for i in x:\n    try:\n        work(i)\n    except Exception:\n        {body}\n"
    assert audit_source(src) == [("broad-except", 4), ("swallowed", 4)]


def test_broad_except_with_logging_only_is_broad_but_not_swallowed():
    src = """
    try:
        risky()
    except Exception as e:
        log.error("failed %s", e)
    """
    assert audit(src) == [("broad-except", 3)]


def test_reraise_variants_are_clean():
    src = """
    try:
        a()
    except Exception as e:
        log.exception("x")
        raise
    try:
        b()
    except Exception as e:
        raise HTTPException(500) from e
    try:
        c()
    except BaseException:
        cleanup()
        raise
    """
    assert audit(src) == []


def test_raise_inside_nested_def_does_not_count_as_reraise():
    src = """
    try:
        a()
    except Exception:
        def later():
            raise RuntimeError()
        schedule(later)
    """
    assert audit(src) == [("broad-except", 3)]


@pytest.mark.parametrize("handler", ["except KeyError:", "except (KeyError, ValueError):", "except OSError as e:"])
def test_specific_exceptions_with_pass_are_not_findings(handler):
    assert audit_source(f"try:\n    x()\n{handler}\n    pass\n") == []


# --- fail-open ---------------------------------------------------------------------------------

def test_fail_open_in_broad_and_bare_handlers():
    src = """
    def is_allowed(user, doc):
        try:
            return check(user, doc)
        except Exception:
            return True

    def is_admin(user):
        try:
            return lookup(user)
        except:
            return True
    """
    assert audit(src) == [
        ("broad-except", 4), ("fail-open", 4),
        ("bare-except", 10), ("fail-open", 10),
    ]


@pytest.mark.parametrize("value, flagged", [
    ("True", True), ("1", True), ("'ok'", True), ("b'x'", True), ("2.5", True),
    ("False", False), ("None", False), ("0", False), ("''", False), ("{}", False), ("x", False),
])
def test_fail_open_only_for_truthy_constants(value, flagged):
    src = f"def f():\n    try:\n        g()\n    except Exception:\n        return {value}\n"
    expected = [("broad-except", 4)] + ([("fail-open", 4)] if flagged else [])
    assert audit_source(src) == expected


def test_return_true_in_specific_handler_is_not_fail_open():
    src = "def f():\n    try:\n        g()\n    except KeyError:\n        return True\n"
    assert audit_source(src) == []


def test_fail_open_nested_in_if_inside_handler():
    src = """
    def f():
        try:
            g()
        except Exception:
            if debug:
                return True
            return False
    """
    assert audit(src) == [("broad-except", 4), ("fail-open", 4)]


# --- return-in-finally -------------------------------------------------------------------------

def test_return_in_finally():
    src = """
    def f():
        try:
            return compute()
        finally:
            return 2
    """
    assert audit(src) == [("return-in-finally", 5)]


def test_return_in_finally_nested_in_if():
    src = """
    def f():
        try:
            work()
        finally:
            cleanup()
            if flag:
                return None
    """
    assert audit(src) == [("return-in-finally", 7)]


def test_finally_without_return_or_with_nested_def_is_clean():
    src = """
    def f():
        try:
            work()
        finally:
            cleanup()
            def helper():
                return 1
            run = lambda: 2
    """
    assert audit(src) == []


def test_try_finally_without_except_and_return_in_try_body_is_clean():
    src = """
    def f():
        try:
            return 1
        finally:
            cleanup()
    """
    assert audit(src) == []


# --- error-detail-leak -------------------------------------------------------------------------

@pytest.mark.parametrize("stmt", [
    'return {"error": str(e)}',
    'return {"error": repr(e)}',
    'return f"bad request: {e}"',
    'return {"args": e.args}',
    'return traceback.format_exc()',
    'return {"trace": traceback.format_exception(e)}',
    'return {"trace": format_tb(e.__traceback__)}',
    'raise HTTPException(500, detail=str(e))',
    'raise HTTPException(status_code=500, detail=f"{e!r}")',
    'return JSONResponse(content={"error": str(e)})',
    'send(body=traceback.format_exc())',
    'send(message=repr(e))',
])
def test_error_detail_leak(stmt):
    src = f"def view():\n    try:\n        work()\n    except ValueError as e:\n        {stmt}\n"
    assert audit_source(src) == [("error-detail-leak", 4)]


@pytest.mark.parametrize("stmt", [
    'logger.error("failed: %s", e)\n        return {"error": "internal"}',
    'logger.exception("failed")\n        raise HTTPException(500, detail="internal error")',
    'print(str(e))\n        return None',
    'return {"error": "bad input"}',
    'return {"code": e.code}',
])
def test_logging_the_error_is_not_a_leak(stmt):
    src = f"def view():\n    try:\n        work()\n    except ValueError as e:\n        {stmt}\n"
    assert audit_source(src) == []


def test_leak_checks_only_the_handler_variable():
    src = """
    def view(other):
        try:
            work()
        except ValueError as e:
            return {"error": str(other)}
    """
    assert audit(src) == []


def test_leak_in_broad_handler_gives_both_findings():
    src = """
    def view():
        try:
            work()
        except Exception as e:
            return {"error": str(e)}
    """
    assert audit(src) == [("broad-except", 4), ("error-detail-leak", 4)]


# --- ignored-verification ----------------------------------------------------------------------

def test_ignored_verification_with_logging_only():
    src = """
    def handle(req):
        try:
            verify_signature(req)
        except InvalidSignature:
            log("bad signature")
        process(req)
    """
    assert audit(src) == [("ignored-verification", 4)]


def test_ignored_verification_pass_in_specific_handler():
    src = """
    def handle(req):
        try:
            self.validator.validate_token(req.token)
        except TokenError:
            pass
        process(req)
    """
    assert audit(src) == [("ignored-verification", 4)]


def test_check_sig_name_and_case_insensitive():
    src = "try:\n    Crypto.CHECK_SIGNATURE(x)\nexcept ValueError:\n    pass\n"
    assert audit_source(src) == [("ignored-verification", 3)]


@pytest.mark.parametrize("tail", [
    "return False", "raise", "raise PermissionError() from None", "continue", "break",
])
def test_verification_failure_that_stops_is_clean(tail):
    src = f"for r in reqs:\n    try:\n        verify(r)\n    except ValueError:\n        {tail}\n"
    assert audit_source(src) == []


def test_non_verification_calls_are_not_flagged():
    src = "try:\n    value = raw.decode()\nexcept UnicodeDecodeError:\n    pass\n"
    assert audit_source(src) == []


def test_verification_inside_nested_function_does_not_count():
    src = """
    try:
        def inner():
            verify(x)
        register(inner)
    except ValueError:
        pass
    """
    assert audit(src) == []


# --- порядок, дублікати, форми синтаксису ------------------------------------------------------

def test_findings_sorted_by_line_then_rule_without_duplicates():
    src = """
    def a():
        try:
            verify(x)
        except Exception as e:
            log(e)
        finally:
            return 0

    def b():
        try:
            work()
        except:
            pass
    """
    assert audit(src) == [
        ("broad-except", 4), ("ignored-verification", 4),
        ("return-in-finally", 7),
        ("bare-except", 12), ("swallowed", 12),
    ]


def test_async_functions_and_nested_try():
    src = """
    async def a():
        try:
            try:
                await work()
            except Exception:
                pass
        except KeyError:
            pass
    """
    assert audit(src) == [("broad-except", 5), ("swallowed", 5)]


def test_try_star():
    src = """
    try:
        work()
    except* Exception:
        pass
    """
    assert audit(src) == [("broad-except", 3), ("swallowed", 3)]


def test_source_is_never_executed():
    src = "raise SystemExit('executed!')\ntry:\n    x()\nexcept:\n    pass\n"
    assert audit_source(src) == [("bare-except", 4), ("swallowed", 4)]


# --- fail_closed -------------------------------------------------------------------------------

class FakeLogger:
    def __init__(self, broken=False):
        self.records = []
        self.broken = broken

    def exception(self, msg, *args, **kwargs):
        if self.broken:
            raise RuntimeError("logging backend down")
        self.records.append(msg % args if args else msg)

    def error(self, msg, *args):  # на випадок, якщо студент викличе error: тест це не прийме
        self.records.append(("error", msg))


def test_returns_only_true_is_true():
    lg = FakeLogger()

    @fail_closed(lg)
    def check(value):
        return value

    assert check(True) is True
    for v in (False, None, 1, 0, "yes", "", {"ok": True}, [1], object()):
        assert check(v) is False
    assert lg.records == []


def test_exception_becomes_false_and_is_logged_once_without_arguments():
    lg = FakeLogger()

    @fail_closed(lg)
    def can_read(user, doc, token=None):
        raise KeyError(f"no grant for {user} on {doc} with {token}")

    assert can_read("alice", "doc-42", token="tok-SECRET-123") is False
    assert len(lg.records) == 1
    msg = lg.records[0]
    assert isinstance(msg, str)
    assert "can_read" in msg and "KeyError" in msg
    for secret in ("tok-SECRET-123", "alice", "doc-42"):
        assert secret not in msg


def test_each_failure_is_logged_separately():
    lg = FakeLogger()

    @fail_closed(lg)
    def f():
        1 / 0

    assert f() is False and f() is False
    assert len(lg.records) == 2
    assert all("ZeroDivisionError" in m for m in lg.records)


def test_passes_args_and_kwargs_and_keeps_metadata():
    lg = FakeLogger()

    @fail_closed(lg)
    def is_owner(user, resource, *, strict=False):
        """Docstring."""
        return user == resource.owner and (strict or True)

    class R:
        owner = "bob"

    assert is_owner("bob", R(), strict=True) is True
    assert is_owner("eve", R()) is False
    assert is_owner.__name__ == "is_owner"
    assert is_owner.__doc__ == "Docstring."


def test_logger_failure_still_fails_closed():
    lg = FakeLogger(broken=True)

    @fail_closed(lg)
    def f():
        raise ValueError("boom")

    assert f() is False


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_base_exceptions_propagate(exc):
    lg = FakeLogger()

    @fail_closed(lg)
    def f():
        raise exc()

    with pytest.raises(exc):
        f()
    assert lg.records == []


def test_async_function_is_supported():
    lg = FakeLogger()

    @fail_closed(lg)
    async def allowed(flag):
        await asyncio.sleep(0)
        if flag == "boom":
            raise ConnectionError("db down")
        return flag

    assert inspect.iscoroutinefunction(allowed)
    assert asyncio.run(allowed(True)) is True
    assert asyncio.run(allowed("yes")) is False
    assert asyncio.run(allowed("boom")) is False
    assert len(lg.records) == 1 and "ConnectionError" in lg.records[0] and "allowed" in lg.records[0]


def test_async_cancellation_propagates():
    lg = FakeLogger()

    @fail_closed(lg)
    async def f():
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(f())
    assert lg.records == []
