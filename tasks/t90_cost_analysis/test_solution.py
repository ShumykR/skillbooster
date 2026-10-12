import pytest

from solution import budget_alerts, cost_diff, daily_anomalies, untagged_report


def item(service, cost, account="prod", usage="Usage", **tags):
    row = {"service": service, "account": account, "usage_type": usage, "cost": cost}
    if tags:
        row["tags"] = tags
    return row


PREV = [item("EC2", 100.0, team="search"), item("EC2", 50.0, team="web"), item("S3", 40.0, team="web"), item("RDS", 200.0, team="search"), item("Lambda", 5.0)]
CUR = [item("EC2", 110.0, team="search"), item("EC2", 55.0, team="web"), item("S3", 90.0, team="web"), item("RDS", 200.0, team="search"),
       item("NATGateway", 120.0, usage="NatGateway-Bytes"), item("Lambda", 0.0)]


# ---------- cost_diff ---------------------------------------------------------


def test_diff_by_service_sorted_by_biggest_increase():
    result = cost_diff(PREV, CUR)
    assert [(r["key"], r["prev"], r["cur"], r["delta"], r["pct"]) for r in result] == [
        ("NATGateway", 0.0, 120.0, 120.0, None),
        ("S3", 40.0, 90.0, 50.0, 125.0),
        ("EC2", 150.0, 165.0, 15.0, 10.0),
        ("RDS", 200.0, 200.0, 0.0, 0.0),
        ("Lambda", 5.0, 0.0, -5.0, -100.0),
    ]


def test_diff_top_limits_result():
    assert [r["key"] for r in cost_diff(PREV, CUR, top=2)] == ["NATGateway", "S3"]


def test_diff_by_tag_with_untagged_group():
    result = cost_diff(PREV, CUR, by="tag:team")
    by_key = {r["key"]: r for r in result}
    assert by_key["search"]["delta"] == 10.0 and by_key["web"]["delta"] == 55.0
    assert by_key["(untagged)"]["cur"] == 120.0 and by_key["(untagged)"]["prev"] == 5.0
    assert [r["key"] for r in result][0] == "(untagged)", "найбільший приріст (+115)"


def test_empty_tag_value_counts_as_untagged():
    rows = [{"service": "EC2", "cost": 3.0, "tags": {"team": ""}}, {"service": "EC2", "cost": 2.0, "tags": {}}, {"service": "EC2", "cost": 1.0}]
    assert cost_diff([], rows, by="tag:team")[0]["cur"] == 6.0


@pytest.mark.parametrize("by, key", [("account", "prod"), ("usage_type", "Usage")])
def test_diff_by_other_dimensions(by, key):
    assert key in {r["key"] for r in cost_diff(PREV, CUR, by=by)}


def test_sums_are_rounded_to_two_places_and_delta_uses_rounded_sums():
    prev = [item("A", 0.004), item("A", 0.004)]
    cur = [item("A", 0.3333), item("A", 0.3333)]
    row = cost_diff(prev, cur)[0]
    assert (row["prev"], row["cur"], row["delta"]) == (0.01, 0.67, 0.66)


def test_ties_are_ordered_by_key():
    prev = [item("B", 1.0), item("A", 1.0)]
    cur = [item("B", 2.0), item("A", 2.0)]
    assert [r["key"] for r in cost_diff(prev, cur)] == ["A", "B"]


def test_unknown_dimension():
    with pytest.raises(ValueError):
        cost_diff(PREV, CUR, by="region")


def test_both_periods_empty():
    assert cost_diff([], []) == []


# ---------- budget_alerts -----------------------------------------------------


@pytest.mark.parametrize("spend, day, expected", [
    (10.0, 10, []),
    (50.0, 28, ["actual_50"]),
    (49.99, 28, []),
    (80.0, 28, ["actual_50", "actual_80"]),
    (100.0, 28, ["actual_50", "actual_80", "actual_100"]),
    (120.0, 28, ["actual_50", "actual_80", "actual_100"]),
])
def test_actual_thresholds(spend, day, expected):
    assert budget_alerts(spend, 100.0, day, 30) == expected


def test_forecast_alert():
    assert budget_alerts(40.0, 100.0, 10, 30) == ["forecast_100"], "40/10*30 = 120 > 100"
    assert budget_alerts(30.0, 100.0, 10, 30) == []  # прогноз рівно 90
    assert budget_alerts(30.0, 90.0, 10, 30) == []  # прогноз рівно 90 = бюджет: не строго більше


def test_forecast_with_actual_thresholds_ordering():
    assert budget_alerts(55.0, 100.0, 15, 30) == ["actual_50", "forecast_100"]


def test_forecast_waits_until_day_three():
    assert budget_alerts(500.0, 100.0, 1, 30) == ["actual_50", "actual_80", "actual_100"]
    assert "forecast_100" not in budget_alerts(70.0, 100.0, 2, 30)
    assert "forecast_100" in budget_alerts(30.0, 100.0, 3, 30)


def test_forecast_is_not_added_when_actual_100_already_fired():
    assert budget_alerts(130.0, 100.0, 20, 30) == ["actual_50", "actual_80", "actual_100"]


def test_custom_thresholds_sorted():
    assert budget_alerts(90.0, 100.0, 29, 30, thresholds=(100, 25, 75)) == ["actual_25", "actual_75"]


@pytest.mark.parametrize("args", [(1, 0, 5, 30), (1, -10, 5, 30), (1, 10, 0, 30), (1, 10, 31, 30)])
def test_budget_alerts_validation(args):
    with pytest.raises(ValueError):
        budget_alerts(*args)


# ---------- daily_anomalies ---------------------------------------------------


def test_spike_is_detected():
    costs = [20.0] * 10 + [95.0] + [20.0] * 3
    assert daily_anomalies(costs) == [10]


def test_small_amounts_do_not_trigger():
    costs = [1.0] * 10 + [5.0]
    assert daily_anomalies(costs) == []


def test_requires_both_factor_and_absolute_increase():
    assert daily_anomalies([100.0] * 8 + [150.0]) == [], "лише в 1.5 раза"
    assert daily_anomalies([100.0] * 8 + [201.0]) == [8]
    assert daily_anomalies([100.0] * 8 + [200.0]) == [], "рівно factor * mean: не більше"


def test_not_enough_history():
    assert daily_anomalies([1.0, 500.0]) == []
    assert daily_anomalies([20.0] * 7) == []
    assert daily_anomalies([20.0] * 7 + [100.0]) == [7]


def test_window_is_rolling():
    costs = [10.0] * 7 + [100.0] + [10.0] * 7 + [100.0]
    assert daily_anomalies(costs) == [7, 15]


def test_custom_parameters():
    costs = [10.0] * 3 + [25.0]
    assert daily_anomalies(costs, window=3, factor=2.0, min_increase=5.0) == [3]
    assert daily_anomalies(costs, window=3, factor=3.0, min_increase=5.0) == []


# ---------- untagged_report ---------------------------------------------------


def test_untagged_report():
    items = [item("EC2", 60.0, team="a"), item("EC2", 30.0), item("S3", 10.0, team=""), item("S3", 5.5), item("RDS", 20.0, owner="x"),
             item("Lambda", 1.0), item("Lambda", 2.0)]
    report = untagged_report(items, "team")
    assert report == {
        "untagged": 68.5, "total": 128.5, "share": 0.5331,
        "top_services": [("EC2", 30.0), ("RDS", 20.0), ("S3", 15.5)],
    }


def test_untagged_top_services_limited_to_three_with_name_tiebreak():
    items = [item("D", 4.0), item("C", 4.0), item("B", 4.0), item("A", 4.0)]
    assert untagged_report(items, "team")["top_services"] == [("A", 4.0), ("B", 4.0), ("C", 4.0)]


def test_untagged_report_empty_and_fully_tagged():
    assert untagged_report([], "team") == {"untagged": 0.0, "total": 0.0, "share": 0.0, "top_services": []}
    assert untagged_report([item("EC2", 5.0, team="x")], "team") == {"untagged": 0.0, "total": 5.0, "share": 0.0, "top_services": []}
