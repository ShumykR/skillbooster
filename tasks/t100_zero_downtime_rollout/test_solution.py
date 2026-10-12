import pytest

from solution import audit_rollout, pdb_disruptions_allowed, recommend_shutdown, resolve_count, rollout_plan, shutdown_report


# ---------- resolve_count -----------------------------------------------------


@pytest.mark.parametrize("value, total, up, expected", [
    (3, 10, True, 3), (0, 10, False, 0),
    ("25%", 10, True, 3), ("25%", 10, False, 2),
    ("50%", 4, True, 2), ("50%", 4, False, 2),
    ("1%", 3, True, 1), ("1%", 3, False, 0),
    ("100%", 7, False, 7), ("0%", 7, True, 0),
])
def test_resolve_count(value, total, up, expected):
    assert resolve_count(value, total, round_up=up) == expected


@pytest.mark.parametrize("bad", [-1, "-5%", "abc", "25", "%", "2.5%", None, True])
def test_resolve_count_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        resolve_count(bad, 10, round_up=True)


# ---------- rollout_plan ------------------------------------------------------


def test_surge_only_never_loses_capacity():
    assert rollout_plan(4, 1, 0, 10) == {"waves": 4, "duration": 40, "min_available": 4, "max_pods": 5}


def test_unavailable_only_never_exceeds_replicas():
    assert rollout_plan(3, 0, 1, 10) == {"waves": 3, "duration": 30, "min_available": 2, "max_pods": 3}


def test_default_percentages_round_surge_up_and_unavailable_down():
    # 10 реплік: surge 3, unavailable 2
    assert rollout_plan(10) == {"waves": 2, "duration": 20, "min_available": 8, "max_pods": 13}


def test_single_replica_defaults_keep_the_service_up():
    assert rollout_plan(1) == {"waves": 1, "duration": 10, "min_available": 1, "max_pods": 2}


def test_single_replica_with_unavailable_means_downtime():
    assert rollout_plan(1, 0, 1, 10) == {"waves": 1, "duration": 10, "min_available": 0, "max_pods": 1}


def test_full_surge_replaces_everything_in_one_wave():
    assert rollout_plan(3, "100%", 0, 10) == {"waves": 1, "duration": 10, "min_available": 3, "max_pods": 6}


def test_unavailable_larger_than_replicas():
    assert rollout_plan(2, 0, 5, 10) == {"waves": 1, "duration": 10, "min_available": 0, "max_pods": 2}


def test_duration_scales_with_ready_seconds():
    assert rollout_plan(4, 1, 0, 0)["duration"] == 0
    assert rollout_plan(4, 1, 0, 30)["duration"] == 120


def test_zero_zero_is_invalid_for_integers_but_not_for_percentages():
    with pytest.raises(ValueError):
        rollout_plan(4, 0, 0)
    assert rollout_plan(4, "0%", "0%", 10)["min_available"] == 3, "Kubernetes ставить maxUnavailable=1"
    assert rollout_plan(4, 0, "10%", 10)["min_available"] == 3, "10% від 4 -> 0 -> 1"


@pytest.mark.parametrize("args", [(0,), (-1,), (3, 1, 0, -1), (3, -1, 0), (3, "x", 0)])
def test_rollout_plan_validation(args):
    with pytest.raises(ValueError):
        rollout_plan(*args)


# ---------- pdb_disruptions_allowed -------------------------------------------


@pytest.mark.parametrize("expected, healthy, kwargs, allowed", [
    (5, 5, {"min_available": 4}, 1),
    (5, 4, {"min_available": 4}, 0),
    (5, 3, {"min_available": 4}, 0),
    (5, 5, {"min_available": "50%"}, 2),       # 50% від 5 = 2.5 -> 3, тож 5 - 3
    (5, 5, {"max_unavailable": 1}, 1),
    (5, 4, {"max_unavailable": 1}, 0),
    (5, 5, {"max_unavailable": "50%"}, 3),     # 2.5 -> 3 вгору: desired = 5 - 3 = 2
    (3, 3, {"min_available": 3}, 0),
    (3, 3, {"max_unavailable": 0}, 0),
    (3, 3, {"min_available": "100%"}, 0),
    (3, 3, {"min_available": 0}, 3),
])
def test_pdb_disruptions(expected, healthy, kwargs, allowed):
    assert pdb_disruptions_allowed(expected, healthy, **kwargs) == allowed


def test_pdb_needs_exactly_one_of_the_options():
    with pytest.raises(ValueError):
        pdb_disruptions_allowed(3, 3)
    with pytest.raises(ValueError):
        pdb_disruptions_allowed(3, 3, min_available=1, max_unavailable=1)


# ---------- shutdown_report ---------------------------------------------------


def report(**kw):
    base = dict(pre_stop=0, endpoint_lag=5, request_duration=2, grace=30, app_drain=10)
    base.update(kw)
    return shutdown_report(**base)


def test_without_prestop_new_requests_hit_a_closed_pod():
    assert report() == {"sigterm_delivered": True, "refused_window": 5, "inflight_ok": True}
    assert report(pre_stop=3)["refused_window"] == 2


def test_prestop_at_least_the_endpoint_lag_removes_refusals():
    assert report(pre_stop=5)["refused_window"] == 0
    assert report(pre_stop=20)["refused_window"] == 0


def test_app_that_keeps_listening_has_no_refused_window():
    assert report(stops_listening=False)["refused_window"] == 0


def test_inflight_requests_need_drain_time():
    assert report(request_duration=10)["inflight_ok"] is True, "рівно app_drain: встигає"
    assert report(request_duration=11)["inflight_ok"] is False


def test_inflight_requests_need_grace_period():
    assert report(pre_stop=25, request_duration=5)["inflight_ok"] is True, "25 + 5 = 30"
    assert report(pre_stop=25, request_duration=6)["inflight_ok"] is False


def test_sigkill_before_sigterm():
    r = report(pre_stop=30)
    assert r["sigterm_delivered"] is False and r["inflight_ok"] is False
    assert report(pre_stop=29)["sigterm_delivered"] is True


@pytest.mark.parametrize("field", ["pre_stop", "endpoint_lag", "request_duration", "grace", "app_drain"])
def test_shutdown_report_rejects_negative_numbers(field):
    with pytest.raises(ValueError):
        report(**{field: -1})


# ---------- recommend_shutdown ------------------------------------------------


def test_recommend_shutdown():
    assert recommend_shutdown(5, 3) == {"pre_stop": 7, "app_drain": 5, "grace": 14}
    assert recommend_shutdown(5, 3, margin=0) == {"pre_stop": 5, "app_drain": 3, "grace": 8}


def test_recommended_values_satisfy_the_report():
    rec = recommend_shutdown(8, 12)
    r = shutdown_report(pre_stop=rec["pre_stop"], endpoint_lag=8, request_duration=12, grace=rec["grace"], app_drain=rec["app_drain"])
    assert r == {"sigterm_delivered": True, "refused_window": 0, "inflight_ok": True}


# ---------- audit_rollout -----------------------------------------------------


def spec(**kw):
    base = dict(replicas=3, max_surge=1, max_unavailable=0, pre_stop=7, endpoint_lag=5, request_duration=3, app_drain=5, grace=20,
                readiness_probe=True, pdb={"min_available": 2})
    base.update(kw)
    return base


def test_a_healthy_setup_has_no_findings():
    assert audit_rollout(spec()) == []


@pytest.mark.parametrize("kw, codes", [
    (dict(replicas=1, max_surge=0, max_unavailable=1, pdb=None), ["DOWNTIME"]),
    (dict(replicas=4, max_surge=0, max_unavailable=1, pdb={"min_available": 3}), ["CAPACITY_DIP"]),
    (dict(readiness_probe=False), ["NO_READINESS_PROBE"]),
    (dict(pdb=None), ["NO_PDB"]),
    (dict(replicas=1, pdb=None), []),
    (dict(pdb={"min_available": 3}), ["PDB_BLOCKS_DRAIN"]),
    (dict(pdb={"max_unavailable": 0}), ["PDB_BLOCKS_DRAIN"]),
    (dict(pdb={"min_available": "100%"}), ["PDB_BLOCKS_DRAIN"]),
    (dict(pdb={"max_unavailable": 1}), []),
    (dict(pre_stop=0), ["PRESTOP_TOO_SHORT"]),
    (dict(pre_stop=4), ["PRESTOP_TOO_SHORT"]),
    (dict(app_drain=1), ["INFLIGHT_DROPPED"]),
    (dict(grace=8), ["INFLIGHT_DROPPED"]),
    (dict(pre_stop=20, grace=20), ["INFLIGHT_DROPPED"]),
])
def test_single_findings(kw, codes):
    assert audit_rollout(spec(**kw)) == codes


def test_findings_are_sorted_and_unique():
    bad = spec(replicas=1, max_surge=0, max_unavailable=1, pdb=None, readiness_probe=False, pre_stop=0, app_drain=0)
    assert audit_rollout(bad) == ["DOWNTIME", "INFLIGHT_DROPPED", "NO_READINESS_PROBE", "PRESTOP_TOO_SHORT"]


def test_defaults_for_missing_keys():
    assert audit_rollout({"replicas": 1, "readiness_probe": True}) == []
    assert audit_rollout({"replicas": 3, "readiness_probe": True, "pdb": {"max_unavailable": 1}}) == []
    assert audit_rollout({"replicas": 4}) == ["CAPACITY_DIP", "NO_PDB", "NO_READINESS_PROBE"], "типові 25%/25%: 3 з 4 доступні"


def test_invalid_strategy_propagates():
    with pytest.raises(ValueError):
        audit_rollout(spec(max_surge=0, max_unavailable=0))
