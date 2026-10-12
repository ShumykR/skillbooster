import pytest

from solution import (DEFAULT_POLICY, alert_expr, budget_consumed, budget_status, burn_rate, error_budget, error_ratio, evaluate_alerts,
                      highest_severity, hours_to_exhaustion, latency_sli, release_policy)


# ---------- budget and burn rate ------------------------------------------------


def test_error_budget():
    assert error_budget(0.999) == {"budget_ratio": 0.001, "allowed_downtime_min": 43.2}
    assert error_budget(0.995) == {"budget_ratio": 0.005, "allowed_downtime_min": 216.0}
    assert error_budget(0.9995, window_days=1)["allowed_downtime_min"] == 0.72
    assert error_budget(0.99, window_days=7) == {"budget_ratio": 0.01, "allowed_downtime_min": 100.8}


@pytest.mark.parametrize("slo", [0, 1, 1.5, -0.1])
def test_invalid_slo(slo):
    with pytest.raises(ValueError):
        error_budget(slo)
    with pytest.raises(ValueError):
        burn_rate(0.1, slo)
    with pytest.raises(ValueError):
        evaluate_alerts(slo, {})
    with pytest.raises(ValueError):
        budget_status(1, 1, slo)


def test_burn_rate():
    assert burn_rate(0.25, 0.75) == 1.0
    assert burn_rate(0.5, 0.75) == 2.0
    assert burn_rate(0, 0.99) == 0.0
    assert burn_rate(0.01, 0.99) == pytest.approx(1.0)
    assert burn_rate(0.0144, 0.999) == pytest.approx(14.4)
    with pytest.raises(ValueError):
        burn_rate(1.5, 0.99)
    with pytest.raises(ValueError):
        burn_rate(-0.1, 0.99)


def test_budget_consumed_by_a_sustained_burn():
    assert budget_consumed(14.4, 1) == 0.02, "2% місячного бюджету за годину"
    assert budget_consumed(6, 6) == 0.05
    assert budget_consumed(1, 720) == 1.0
    assert budget_consumed(3, 24) == 0.1
    assert budget_consumed(1, 7 * 24, window_days=7) == 1.0


def test_hours_to_exhaustion():
    assert hours_to_exhaustion(14.4) == 50.0
    assert hours_to_exhaustion(1) == 720.0
    assert hours_to_exhaustion(2, remaining=0.5) == 180.0
    assert hours_to_exhaustion(1, window_days=7) == 168.0
    assert hours_to_exhaustion(0) is None


# ---------- SLI ----------------------------------------------------------------


def test_error_ratio():
    assert error_ratio(995, 1000) == pytest.approx(0.005)
    assert error_ratio(10, 10) == 0.0
    assert error_ratio(0, 0) == 0.0
    assert error_ratio(0, 10) == 1.0
    with pytest.raises(ValueError):
        error_ratio(11, 10)
    with pytest.raises(ValueError):
        error_ratio(-1, 10)


def test_latency_sli():
    assert latency_sli([0.1, 0.2, 0.3, 0.4], 0.3) == 0.75, "поріг включно"
    assert latency_sli([], 0.3) == 1.0
    assert latency_sli([1, 2], 0.5) == 0.0


def test_budget_status():
    assert budget_status(995, 1000, 0.99) == {"sli": 0.995, "meets_slo": True, "consumed": 0.5, "remaining": 0.5}
    assert budget_status(980, 1000, 0.99) == {"sli": 0.98, "meets_slo": False, "consumed": 2.0, "remaining": -1.0}
    assert budget_status(990, 1000, 0.99)["meets_slo"] is True, "рівно SLO: виконано"
    assert budget_status(0, 0, 0.99) == {"sli": 1.0, "meets_slo": True, "consumed": 0.0, "remaining": 1.0}
    assert budget_status(1000, 1000, 0.999)["consumed"] == 0.0
    with pytest.raises(ValueError):
        budget_status(5, 3, 0.99)


@pytest.mark.parametrize("consumed, policy", [
    (0, "normal"), (0.49, "normal"), (0.5, "caution"), (0.99, "caution"), (1, "freeze"), (3, "freeze")])
def test_release_policy(consumed, policy):
    assert release_policy(consumed) == policy


# ---------- multi-window multi-burn-rate alerts -----------------------------------


def test_default_policy_matches_the_sre_workbook():
    assert [(r["severity"], r["long"], r["short"], r["factor"]) for r in DEFAULT_POLICY] == [
        ("page", "1h", "5m", 14.4), ("page", "6h", "30m", 6), ("ticket", "1d", "2h", 3), ("ticket", "3d", "6h", 1)]


def test_fast_burn_pages():
    alerts = evaluate_alerts(0.999, {"1h": 0.02, "5m": 0.02})
    assert [(a["severity"], a["long"]) for a in alerts] == [("page", "1h")]
    assert highest_severity(alerts) == "page"


def test_recovered_incident_does_not_page():
    ratios = {"1h": 0.02, "5m": 0.0001, "6h": 0.004, "30m": 0.0001}
    assert evaluate_alerts(0.999, ratios) == [], "довге вікно ще червоне, але зараз уже все гаразд"


def test_both_windows_must_exceed_the_factor():
    assert evaluate_alerts(0.999, {"1h": 0.0001, "5m": 0.05}) == [], "коротка хвиля, довге вікно спокійне"
    assert evaluate_alerts(0.999, {"1h": 0.05, "5m": 0.0001}) == []


def test_slow_burn_creates_a_ticket_not_a_page():
    ratios = {"1h": 0.002, "5m": 0.002, "6h": 0.0035, "30m": 0.0035, "1d": 0.004, "2h": 0.004, "3d": 0.0012}
    alerts = evaluate_alerts(0.999, ratios)
    assert [(a["severity"], a["long"], a["short"]) for a in alerts] == [("ticket", "1d", "2h"), ("ticket", "3d", "6h")]
    assert highest_severity(alerts) == "ticket"


def test_page_wins_over_ticket():
    ratios = {"1h": 0.05, "5m": 0.05, "6h": 0.05, "30m": 0.05, "1d": 0.05, "2h": 0.05, "3d": 0.05}
    alerts = evaluate_alerts(0.999, ratios)
    assert [a["long"] for a in alerts] == ["1h", "6h", "1d", "3d"], "порядок політики"
    assert highest_severity(alerts) == "page"


def test_threshold_is_strict():
    policy = [{"severity": "page", "long": "a", "short": "b", "factor": 2}]
    assert evaluate_alerts(0.75, {"a": 0.5, "b": 0.5}, policy) == [], "burn рівно 2.0: ще не перевищено"
    assert len(evaluate_alerts(0.75, {"a": 0.51, "b": 0.51}, policy)) == 1
    assert evaluate_alerts(0.75, {"a": 0.9, "b": 0.5}, policy) == [], "коротке вікно рівно на межі"
    assert evaluate_alerts(0.75, {"a": 0.5, "b": 0.9}, policy) == [], "довге вікно рівно на межі"


def test_missing_windows_skip_the_rule():
    policy = [{"severity": "page", "long": "a", "short": "b", "factor": 1}]
    assert evaluate_alerts(0.9, {"a": 1.0}, policy) == []
    assert evaluate_alerts(0.9, {"b": 1.0}, policy) == []
    assert evaluate_alerts(0.9, {}) == []


def test_invalid_ratio_is_rejected():
    with pytest.raises(ValueError):
        evaluate_alerts(0.99, {"1h": 1.5})


def test_highest_severity_edge_cases():
    assert highest_severity([]) is None
    assert highest_severity([{"severity": "ticket"}]) == "ticket"
    assert highest_severity([{"severity": "ticket"}, {"severity": "page"}]) == "page"


# ---------- PromQL ------------------------------------------------------------


def test_alert_expr():
    assert alert_expr(0.999, "1h", "5m", 14.4) == (
        "job:slo_errors_per_request:ratio_rate1h > (14.4 * 0.001) and job:slo_errors_per_request:ratio_rate5m > (14.4 * 0.001)")
    assert alert_expr(0.99, "6h", "30m", 6) == (
        "job:slo_errors_per_request:ratio_rate6h > (6 * 0.01) and job:slo_errors_per_request:ratio_rate30m > (6 * 0.01)")
    assert alert_expr(0.9999, "1d", "2h", 3, metric="api:err:rate") == "api:err:rate1d > (3 * 0.0001) and api:err:rate2h > (3 * 0.0001)"
