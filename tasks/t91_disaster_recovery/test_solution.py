import pytest

from solution import component_recovery_min, component_rpo, dr_report, recommend_strategy, restore_tests_due

DAY = 86400
NOW = 1_800_000_000.0


def backup(**kw):
    base = {"strategy": "backup_restore", "data_gb": 600.0, "backup_interval_min": 60, "copy_delay_min": 15,
            "restore_gb_per_min": 10.0, "provision_min": 20, "failover_min": 5}
    base.update(kw)
    return base


# ---------- component_rpo -----------------------------------------------------


def test_backup_rpo_is_interval_plus_copy_delay():
    assert component_rpo(backup()) == 75.0
    assert component_rpo(backup(copy_delay_min=0)) == 60.0
    assert component_rpo({"strategy": "backup_restore", "backup_interval_min": 1440}) == 1440.0


@pytest.mark.parametrize("strategy", ["pilot_light", "warm_standby", "active_active"])
def test_replicated_strategies_use_lag(strategy):
    assert component_rpo(backup(strategy=strategy, replication_lag_s=90)) == 1.5


@pytest.mark.parametrize("strategy", ["pilot_light", "warm_standby", "active_active"])
def test_without_replication_falls_back_to_backups(strategy):
    assert component_rpo(backup(strategy=strategy, replication_lag_s=None)) == 75.0
    assert component_rpo(backup(strategy=strategy)) == 75.0


def test_backup_restore_ignores_replication_lag():
    assert component_rpo(backup(replication_lag_s=2)) == 75.0


# ---------- component_recovery_min --------------------------------------------


def test_recovery_time_by_strategy():
    assert component_recovery_min(backup()) == 20 + 600 / 10 + 5 == 85.0
    assert component_recovery_min({"strategy": "pilot_light", "provision_min": 20, "failover_min": 5}) == 25.0
    assert component_recovery_min({"strategy": "warm_standby", "scale_min": 8, "failover_min": 2}) == 10.0
    assert component_recovery_min({"strategy": "active_active", "failover_min": 1.5}) == 1.5


def test_missing_numbers_are_zero():
    assert component_recovery_min({"strategy": "active_active"}) == 0.0
    assert component_recovery_min({"strategy": "warm_standby"}) == 0.0


# ---------- dr_report ---------------------------------------------------------


def system():
    return {
        "db": backup(),
        "app": {"strategy": "warm_standby", "scale_min": 10, "failover_min": 5, "depends_on": ["db"], "replication_lag_s": 30},
        "cache": {"strategy": "pilot_light", "provision_min": 6, "failover_min": 2},
        "web": {"strategy": "active_active", "failover_min": 1, "depends_on": ["app", "cache"], "replication_lag_s": 0},
    }


def test_report_uses_critical_path_through_dependencies():
    report = dr_report(system(), {"rto_min": 240, "rpo_min": 120})
    # db: 85; app: 85 + 15 = 100; cache: 8; web: max(100, 8) + 1 = 101; + виявлення 5
    assert report["rto_min"] == 106.0
    assert report["rpo_min"] == 75.0
    assert report["meets_rto"] is True and report["meets_rpo"] is True and report["violations"] == []


def test_report_violations_name_the_components_that_break_the_goals():
    report = dr_report(system(), {"rto_min": 60, "rpo_min": 30})
    assert report["meets_rto"] is False and report["meets_rpo"] is False
    assert report["violations"] == ["app", "db", "web"], "cache (13 хв, rpo 0) вкладається в обидві цілі"


def test_boundaries_are_inclusive():
    plan = {"db": backup(copy_delay_min=0, data_gb=100, restore_gb_per_min=10, provision_min=5, failover_min=0)}  # rto: 5 + 10 + 0 = 15 + detection
    report = dr_report(plan, {"rto_min": 17, "rpo_min": 60}, detection_min=2)
    assert report["rto_min"] == 17.0 and report["meets_rto"] is True and report["meets_rpo"] is True
    tighter = dr_report(plan, {"rto_min": 16.99, "rpo_min": 59.99}, detection_min=2)
    assert tighter["meets_rto"] is False and tighter["meets_rpo"] is False


def test_detection_time_is_added_once():
    plan = {"a": {"strategy": "active_active", "failover_min": 1}, "b": {"strategy": "active_active", "failover_min": 1, "depends_on": ["a"]}}
    assert dr_report(plan, {"rto_min": 100, "rpo_min": 100}, detection_min=7)["rto_min"] == 9.0


def test_independent_components_run_in_parallel():
    plan = {"a": {"strategy": "pilot_light", "provision_min": 30}, "b": {"strategy": "pilot_light", "provision_min": 20}}
    assert dr_report(plan, {"rto_min": 100, "rpo_min": 100})["rto_min"] == 35.0


def test_empty_plan():
    assert dr_report({}, {"rto_min": 10, "rpo_min": 10}) == {
        "rto_min": 5.0, "rpo_min": 0.0, "meets_rto": True, "meets_rpo": True, "violations": []}


def test_numbers_are_rounded():
    plan = {"db": backup(data_gb=100, restore_gb_per_min=3, copy_delay_min=0, backup_interval_min=10)}
    assert dr_report(plan, {"rto_min": 100, "rpo_min": 100})["rto_min"] == 63.33  # 5 + (20 + 33.333 + 5)


def test_unknown_dependency_and_cycle():
    with pytest.raises(ValueError):
        dr_report({"a": {"strategy": "active_active", "depends_on": ["ghost"]}}, {"rto_min": 1, "rpo_min": 1})
    cyc = {"a": {"strategy": "active_active", "depends_on": ["b"]}, "b": {"strategy": "active_active", "depends_on": ["a"]}}
    with pytest.raises(ValueError):
        dr_report(cyc, {"rto_min": 1, "rpo_min": 1})


# ---------- recommend_strategy ------------------------------------------------


@pytest.mark.parametrize("rto, rpo, expected", [
    (1440, 1440, "backup_restore"),
    (240, 60, "backup_restore"),
    (239, 60, "pilot_light"),
    (240, 59, "pilot_light"),
    (60, 15, "pilot_light"),
    (30, 5, "pilot_light"),
    (29, 5, "warm_standby"),
    (30, 4, "warm_standby"),
    (10, 2, "warm_standby"),
    (5, 1, "warm_standby"),
    (4, 1, "active_active"),
    (5, 0.5, "active_active"),
    (0, 0, "active_active"),
])
def test_recommend_strategy(rto, rpo, expected):
    assert recommend_strategy(rto, rpo) == expected


# ---------- restore_tests_due -------------------------------------------------


def test_restore_tests_due():
    plan = {
        "fresh": {"last_restore_test": NOW - 10 * DAY},
        "edge": {"last_restore_test": NOW - 90 * DAY},
        "stale": {"last_restore_test": NOW - 91 * DAY},
        "never": {"last_restore_test": None},
        "unspecified": {},
    }
    assert restore_tests_due(plan, NOW) == ["never", "stale", "unspecified"]
    assert restore_tests_due(plan, NOW, max_age_days=5) == ["edge", "fresh", "never", "stale", "unspecified"]
    assert restore_tests_due({}, NOW) == []
