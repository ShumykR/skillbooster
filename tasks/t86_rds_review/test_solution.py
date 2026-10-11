import copy

import pytest

from solution import connection_budget, default_max_connections, review_rds

GOOD_PG = {
    "Engine": "postgres",
    "MultiAZ": True,
    "BackupRetentionPeriod": 7,
    "StorageEncrypted": True,
    "PubliclyAccessible": False,
    "DeletionProtection": True,
    "PerformanceInsightsEnabled": True,
    "VpcSecurityGroups": [{"VpcSecurityGroupId": "sg-db"}],
}
GOOD_SGS = {"sg-db": [{"sg": "sg-app"}, {"cidr": "10.0.0.0/16"}]}
GOOD_PARAMS = {"rds.force_ssl": "1", "log_min_duration_statement": "500"}


def review(db=None, sgs=None, params=None, env="prod", **changes):
    base = copy.deepcopy(GOOD_PG if db is None else db)
    base.update(changes)
    return review_rds(base, GOOD_SGS if sgs is None else sgs, GOOD_PARAMS if params is None else params, env)


# ---------- базові ----------

def test_good_instance_has_no_findings():
    assert review() == []


def test_invalid_env():
    with pytest.raises(ValueError):
        review(env="staging")


def test_result_sorted_unique():
    got = review(MultiAZ=False, StorageEncrypted=False, PubliclyAccessible=True, BackupRetentionPeriod=0)
    assert got == sorted(set(got)) == ["RDS001", "RDS002", "RDS003", "RDS004"]


def test_inputs_not_mutated():
    db, sgs, params = copy.deepcopy(GOOD_PG), copy.deepcopy(GOOD_SGS), dict(GOOD_PARAMS)
    snapshot = (repr(db), repr(sgs), repr(params))
    review_rds(db, sgs, params, "prod")
    assert (repr(db), repr(sgs), repr(params)) == snapshot


# ---------- прості поля ----------

@pytest.mark.parametrize("value", [False, None])
def test_rds001_multi_az(value):
    assert review(MultiAZ=value) == ["RDS001"]


def test_rds001_missing_key():
    db = {k: v for k, v in GOOD_PG.items() if k != "MultiAZ"}
    assert review(db=db) == ["RDS001"]


@pytest.mark.parametrize("days, bad", [(0, True), (1, True), (6, True), (7, False), (35, False)])
def test_rds002_backups(days, bad):
    assert review(BackupRetentionPeriod=days) == (["RDS002"] if bad else [])


def test_rds002_missing_key():
    db = {k: v for k, v in GOOD_PG.items() if k != "BackupRetentionPeriod"}
    assert review(db=db) == ["RDS002"]


@pytest.mark.parametrize("value", [False, None])
def test_rds003_encryption(value):
    assert review(StorageEncrypted=value) == ["RDS003"]


def test_rds004_public():
    assert review(PubliclyAccessible=True) == ["RDS004"]
    assert review(PubliclyAccessible=False) == []


def test_rds004_missing_key_is_not_public():
    db = {k: v for k, v in GOOD_PG.items() if k != "PubliclyAccessible"}
    assert review(db=db) == []


@pytest.mark.parametrize("value", [False, None])
def test_rds005_deletion_protection(value):
    assert review(DeletionProtection=value) == ["RDS005"]


@pytest.mark.parametrize("value", [False, None])
def test_rds009_performance_insights(value):
    assert review(PerformanceInsightsEnabled=value) == ["RDS009"]


# ---------- dev ----------

def test_dev_relaxes_prod_only_rules():
    got = review(env="dev", MultiAZ=False, BackupRetentionPeriod=0, DeletionProtection=False,
                 PerformanceInsightsEnabled=False)
    assert got == []


def test_dev_still_checks_security_rules():
    got = review(env="dev", StorageEncrypted=False, PubliclyAccessible=True)
    assert got == ["RDS003", "RDS004"]
    assert review(env="dev", params={}) == ["RDS007", "RDS008"]


# ---------- security groups ----------

@pytest.mark.parametrize("cidr", ["0.0.0.0/0", "::/0"])
def test_rds006_world_open(cidr):
    assert review(sgs={"sg-db": [{"cidr": cidr}]}) == ["RDS006"]


@pytest.mark.parametrize("cidr", ["10.0.0.0/8", "0.0.0.0/8", "192.168.0.0/16", "0.0.0.0/1"])
def test_rds006_not_world_open(cidr):
    assert review(sgs={"sg-db": [{"cidr": cidr}]}) == []


def test_rds006_only_attached_groups_count():
    sgs = {"sg-db": [{"sg": "sg-app"}], "sg-other": [{"cidr": "0.0.0.0/0"}]}
    assert review(sgs=sgs) == []


def test_rds006_any_of_several_groups():
    db = copy.deepcopy(GOOD_PG)
    db["VpcSecurityGroups"] = [{"VpcSecurityGroupId": "sg-a"}, {"VpcSecurityGroupId": "sg-b"}]
    sgs = {"sg-a": [{"sg": "sg-app"}], "sg-b": [{"cidr": "10.0.0.0/16"}, {"cidr": "0.0.0.0/0"}]}
    assert review(db=db, sgs=sgs) == ["RDS006"]


def test_rds006_unknown_group_ignored():
    assert review(sgs={}) == []


def test_rds006_no_groups_key():
    db = {k: v for k, v in GOOD_PG.items() if k != "VpcSecurityGroups"}
    assert review(db=db) == []


def test_rds006_rule_without_cidr():
    assert review(sgs={"sg-db": [{"sg": "sg-app"}, {}]}) == []


# ---------- TLS і логи ----------

def test_rds007_postgres():
    assert review(params={"rds.force_ssl": "0", "log_min_duration_statement": "1"}) == ["RDS007"]
    assert review(params={"log_min_duration_statement": "1"}) == ["RDS007"]
    assert review(params={"rds.force_ssl": "1", "log_min_duration_statement": "1"}) == []


def test_rds007_postgres_engine_variants():
    assert review(Engine="postgresql", params={"log_min_duration_statement": "1"}) == ["RDS007"]
    assert review(Engine="aurora-postgresql", params={"log_min_duration_statement": "1"}) == []


@pytest.mark.parametrize("engine", ["mysql", "mariadb"])
@pytest.mark.parametrize("value, bad", [("1", False), ("ON", False), ("on", False), ("0", True), ("OFF", True), (None, True)])
def test_rds007_mysql_family(engine, value, bad):
    params = {} if value is None else {"require_secure_transport": value}
    assert review(Engine=engine, params=params) == (["RDS007"] if bad else [])


def test_rds007_mysql_ignores_postgres_param():
    assert review(Engine="mysql", params={"rds.force_ssl": "1"}) == ["RDS007"]


def test_rds007_other_engines_skipped():
    assert review(Engine="oracle-ee", params={}) == []
    assert review(Engine="sqlserver-se", params={}) == []


def test_rds008_slow_query_log():
    assert review(params={"rds.force_ssl": "1"}) == ["RDS008"]
    assert review(params={"rds.force_ssl": "1", "log_min_duration_statement": "-1"}) == ["RDS008"]
    assert review(params={"rds.force_ssl": "1", "log_min_duration_statement": "0"}) == []


def test_rds008_not_for_mysql():
    assert review(Engine="mysql", params={"require_secure_transport": "ON"}) == []


def test_engine_missing():
    db = {k: v for k, v in GOOD_PG.items() if k != "Engine"}
    assert review(db=db, params={}) == []


def test_engine_case_insensitive():
    assert review(Engine="Postgres", params={}) == ["RDS007", "RDS008"]


# ---------- connection_budget ----------

SVC = [{"name": "api", "replicas": 4, "pool_size": 10, "max_overflow": 5}]


def test_budget_basic():
    # 4 реплік * 1.25 = 5; 5 * 15 = 75
    got = connection_budget(100, SVC)
    assert got == {"available": 90, "needed": 75, "fits": True, "headroom": 15}


def test_budget_exact_fit():
    assert connection_budget(85, SVC)["fits"] is True
    assert connection_budget(85, SVC)["headroom"] == 0


def test_budget_one_over():
    got = connection_budget(84, SVC)
    assert got["fits"] is False and got["headroom"] == -1


def test_budget_surge_rounds_up_per_service():
    svc = [{"name": "a", "replicas": 3, "pool_size": 1}, {"name": "b", "replicas": 3, "pool_size": 1}]
    # ceil(3.75) = 4 для кожного: 4 + 4
    assert connection_budget(100, svc, reserved=0)["needed"] == 8


def test_budget_surge_zero():
    assert connection_budget(100, SVC, surge_pct=0)["needed"] == 60


def test_budget_surge_exact_no_extra_round():
    svc = [{"name": "a", "replicas": 4, "pool_size": 1}]
    assert connection_budget(100, svc, reserved=0, surge_pct=25)["needed"] == 5
    assert connection_budget(100, svc, reserved=0, surge_pct=100)["needed"] == 8


def test_budget_overflow_default_zero():
    svc = [{"name": "a", "replicas": 2, "pool_size": 10}]
    assert connection_budget(100, svc, reserved=0, surge_pct=0)["needed"] == 20


def test_budget_multiple_services_sum():
    svc = [
        {"name": "api", "replicas": 2, "pool_size": 10, "max_overflow": 10},
        {"name": "worker", "replicas": 4, "pool_size": 5},
    ]
    # api: ceil(2.5)=3 * 20 = 60; worker: 5 * 5 = 25
    assert connection_budget(200, svc)["needed"] == 85


def test_budget_empty_services():
    assert connection_budget(100, []) == {"available": 90, "needed": 0, "fits": True, "headroom": 90}


def test_budget_reserved_custom():
    assert connection_budget(100, [], reserved=0)["available"] == 100
    assert connection_budget(100, [], reserved=100)["available"] == 0


def test_budget_return_ints():
    got = connection_budget(100, SVC)
    assert all(type(got[k]) is int for k in ("available", "needed", "headroom"))


@pytest.mark.parametrize("args, kwargs", [
    ((-1, []), {}),
    ((100, []), {"reserved": -1}),
    ((100, []), {"reserved": 101}),
    ((100, []), {"surge_pct": -5}),
    ((100, [{"name": "a", "replicas": -1, "pool_size": 1}]), {}),
    ((100, [{"name": "a", "replicas": 1, "pool_size": -1}]), {}),
    ((100, [{"name": "a", "replicas": 1, "pool_size": 1, "max_overflow": -1}]), {}),
])
def test_budget_invalid(args, kwargs):
    with pytest.raises(ValueError):
        connection_budget(*args, **kwargs)


# ---------- default_max_connections ----------

@pytest.mark.parametrize("gib, expected", [(1, 112), (2, 225), (4, 450), (8, 901), (16, 1802), (32, 3604)])
def test_default_max_connections(gib, expected):
    assert default_max_connections(gib) == expected


@pytest.mark.parametrize("gib", [64, 128, 1024])
def test_default_max_connections_capped(gib):
    assert default_max_connections(gib) == 5000


def test_default_max_connections_fractional_memory():
    assert default_max_connections(0.5) == 56


@pytest.mark.parametrize("gib", [0, -1])
def test_default_max_connections_invalid(gib):
    with pytest.raises(ValueError):
        default_max_connections(gib)
