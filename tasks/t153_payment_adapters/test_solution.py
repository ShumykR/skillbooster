import dataclasses

import pytest

from solution import (
    Gateway,
    PaymentResult,
    ProviderContractError,
    ProviderUnavailable,
    UnknownProvider,
    adapt,
)


def alpha(**over):
    p = {"id": "ch_1", "status": "succeeded", "amount": 1250, "currency": "usd"}
    p.update(over)
    return p


def beta(**over):
    p = {"txn": "B-77", "state": "APPROVED", "total": "12.50", "cur": "UAH"}
    p.update(over)
    return p


# --- чесні відповіді -----------------------------------------------------------------------------

def test_alpha_success():
    assert adapt("alpha", alpha()) == PaymentResult("ch_1", "paid", 1250, "USD")


def test_beta_success():
    assert adapt("beta", beta()) == PaymentResult("B-77", "paid", 1250, "UAH")


@pytest.mark.parametrize("raw, status", [("succeeded", "paid"), ("failed", "failed"), ("processing", "pending")])
def test_alpha_status_mapping(raw, status):
    assert adapt("alpha", alpha(status=raw)).status == status


@pytest.mark.parametrize("raw, status", [("APPROVED", "paid"), ("DECLINED", "failed"), ("WAITING", "pending")])
def test_beta_status_mapping(raw, status):
    assert adapt("beta", beta(state=raw)).status == status


@pytest.mark.parametrize(
    "total, cents",
    [("12", 1200), ("12.5", 1250), ("12.50", 1250), ("0", 0), ("0.05", 5), ("0.5", 50), ("007.50", 750),
     ("99999999999.99", 9_999_999_999_999)],
)
def test_beta_amounts_are_exact(total, cents):
    assert adapt("beta", beta(total=total)).amount_cents == cents


def test_amount_is_int_not_float():
    assert type(adapt("beta", beta(total="0.29")).amount_cents) is int
    assert adapt("beta", beta(total="0.29")).amount_cents == 29  # 0.29 * 100 у float дає 28.999...


def test_currency_is_normalised_to_upper_case():
    assert adapt("alpha", alpha(currency="eur")).currency == "EUR"
    assert adapt("beta", beta(cur="Pln")).currency == "PLN"


def test_extra_fields_are_ignored():
    assert adapt("alpha", alpha(card={"last4": "4242"}, new_field=1)).status == "paid"


def test_result_is_immutable():
    r = adapt("alpha", alpha())
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.status = "failed"


def test_zero_amount_is_allowed():
    assert adapt("alpha", alpha(amount=0)).amount_cents == 0


# --- fail closed ------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["SUCCEEDED", "paid", "success", "", None, 1, "succeeded ", "requires_action"])
def test_unknown_alpha_status_is_an_error_not_paid(status):
    with pytest.raises(ProviderContractError):
        adapt("alpha", alpha(status=status))


@pytest.mark.parametrize("state", ["approved", "OK", "", None, "PENDING", 1])
def test_unknown_beta_state_is_an_error_not_paid(state):
    with pytest.raises(ProviderContractError):
        adapt("beta", beta(state=state))


@pytest.mark.parametrize("field", ["id", "status", "amount", "currency"])
def test_missing_alpha_field(field):
    p = alpha()
    del p[field]
    with pytest.raises(ProviderContractError):
        adapt("alpha", p)


@pytest.mark.parametrize("field", ["txn", "state", "total", "cur"])
def test_missing_beta_field(field):
    p = beta()
    del p[field]
    with pytest.raises(ProviderContractError):
        adapt("beta", p)


@pytest.mark.parametrize("amount", [-1, 12.5, "1250", None, True, False, [1250]])
def test_bad_alpha_amount(amount):
    with pytest.raises(ProviderContractError):
        adapt("alpha", alpha(amount=amount))


@pytest.mark.parametrize(
    "total",
    ["-1", "-0.01", " 12", "12 ", "1e3", ".5", "12.", "12.505", "12.0000", "1,50", "", "abc", "NaN", "inf",
     "١٢.٥٠", "１２.５０", "12\n", 12.5, 12, None, True],
)
def test_bad_beta_total(total):
    with pytest.raises(ProviderContractError):
        adapt("beta", beta(total=total))


@pytest.mark.parametrize("cur", ["US", "USDD", "12$", "", None, 5, "ЮЕС", "u d"])
def test_bad_currency(cur):
    with pytest.raises(ProviderContractError):
        adapt("alpha", alpha(currency=cur))
    with pytest.raises(ProviderContractError):
        adapt("beta", beta(cur=cur))


@pytest.mark.parametrize("ident", ["", None, 5, ["x"]])
def test_bad_id(ident):
    with pytest.raises(ProviderContractError):
        adapt("alpha", alpha(id=ident))
    with pytest.raises(ProviderContractError):
        adapt("beta", beta(txn=ident))


@pytest.mark.parametrize("payload", [None, [], "text", 5, b"{}"])
def test_payload_must_be_a_dict(payload):
    for provider in ("alpha", "beta"):
        with pytest.raises(ProviderContractError):
            adapt(provider, payload)


def test_error_types():
    assert issubclass(ProviderContractError, ValueError)
    assert issubclass(UnknownProvider, KeyError)
    with pytest.raises(UnknownProvider):
        adapt("gamma", alpha())
    with pytest.raises(UnknownProvider):
        adapt(None, alpha())


def test_alpha_payload_is_not_accepted_by_beta_adapter():
    with pytest.raises(ProviderContractError):
        adapt("beta", alpha())


# --- Gateway ---------------------------------------------------------------------------------------

def test_gateway_returns_domain_object():
    calls = []

    def fetch(provider, ref):
        calls.append((provider, ref))
        return alpha(id=ref)

    assert Gateway(fetch).status("alpha", "ch_9") == PaymentResult("ch_9", "paid", 1250, "USD")
    assert calls == [("alpha", "ch_9")]


def test_unknown_provider_never_reaches_fetch():
    def fetch(provider, ref):
        raise AssertionError("must not be called")

    with pytest.raises(UnknownProvider):
        Gateway(fetch).status("gamma", "x")


@pytest.mark.parametrize("exc", [TimeoutError("slow"), ConnectionError("reset"), OSError("dns")])
def test_network_errors_become_provider_unavailable(exc):
    def fetch(provider, ref):
        raise exc

    with pytest.raises(ProviderUnavailable) as info:
        Gateway(fetch).status("beta", "B-77")
    assert info.value.__cause__ is exc


def test_other_exceptions_propagate_unchanged():
    bug = ZeroDivisionError("bug")

    def fetch(provider, ref):
        raise bug

    with pytest.raises(ZeroDivisionError) as info:
        Gateway(fetch).status("beta", "B-77")
    assert info.value is bug


def test_contract_violation_from_fetch_is_reported():
    with pytest.raises(ProviderContractError):
        Gateway(lambda p, r: {"txn": r}).status("beta", "B-77")


def test_response_for_another_payment_is_rejected():
    with pytest.raises(ProviderContractError):
        Gateway(lambda p, r: beta(txn="B-OTHER")).status("beta", "B-77")
    with pytest.raises(ProviderContractError):
        Gateway(lambda p, r: alpha(id="ch_other")).status("alpha", "ch_1")
