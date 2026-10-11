import datetime as dt

import pytest

from solution import ddl_create, ddl_drop, partition_bounds, partition_name, partitions_for_range, plan_partitions

D = dt.date


# --- імена -----------------------------------------------------------------------------------------------

def test_partition_name():
    assert partition_name("events", D(2026, 3, 15)) == "events_2026_03"
    assert partition_name("events", dt.datetime(2026, 12, 31, 23, 59, 59)) == "events_2026_12"
    assert partition_name("audit_log", D(2027, 1, 1)) == "audit_log_2027_01"


@pytest.mark.parametrize("table", ["", "Events", "events; DROP TABLE users", "events-1", "1events", "ev ents", "events\n", "a" * 42,
                                   "events'", "події", None, 5])
def test_unsafe_table_names_are_rejected_everywhere(table):
    with pytest.raises(ValueError):
        partition_name(table, D(2026, 1, 1))
    with pytest.raises(ValueError):
        ddl_create(table, D(2026, 1, 1))
    with pytest.raises(ValueError):
        plan_partitions(table, [], D(2026, 1, 1), 1, 1)
    with pytest.raises(ValueError):
        partitions_for_range(table, [], D(2026, 1, 1), D(2026, 2, 1))


def test_boundary_table_name_lengths():
    assert partition_name("a" * 41, D(2026, 1, 1)).endswith("_2026_01")
    assert partition_name("_t", D(2026, 1, 1)) == "_t_2026_01"


# --- межі ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, start, end",
    [
        ("events_2026_03", D(2026, 3, 1), D(2026, 4, 1)),
        ("events_2026_12", D(2026, 12, 1), D(2027, 1, 1)),
        ("events_2026_01", D(2026, 1, 1), D(2026, 2, 1)),
        ("events_2024_02", D(2024, 2, 1), D(2024, 3, 1)),   # високосний рік: межі все одно по 1-х числах
    ],
)
def test_bounds(name, start, end):
    assert partition_bounds("events", name) == (start, end)


@pytest.mark.parametrize(
    "name",
    ["events_2026_13", "events_2026_00", "events_2026_3", "events_26_03", "events_2026_03_x", "other_2026_03", "eventsx_2026_03",
     "events_default", "events", "", None, "events_1899_01", "events_3000_01", "events_2026-03", "Events_2026_03"],
)
def test_bounds_reject_non_partition_names(name):
    with pytest.raises(ValueError):
        partition_bounds("events", name)


def test_table_name_with_underscores_and_digits():
    assert partition_bounds("user_events_v2", "user_events_v2_2026_05") == (D(2026, 5, 1), D(2026, 6, 1))
    with pytest.raises(ValueError):
        partition_bounds("user_events", "user_events_v2_2026_05")


# --- DDL ----------------------------------------------------------------------------------------------------------

def test_ddl_create_exact_text():
    assert ddl_create("events", D(2026, 3, 17)) == (
        "CREATE TABLE events_2026_03 PARTITION OF events FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');")


def test_ddl_create_december_rolls_the_year():
    assert ddl_create("events", D(2026, 12, 5)) == (
        "CREATE TABLE events_2026_12 PARTITION OF events FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');")


def test_ddl_create_accepts_datetime():
    assert "FROM ('2026-02-01') TO ('2026-03-01')" in ddl_create("events", dt.datetime(2026, 2, 28, 12, 0))


def test_ddl_drop():
    assert ddl_drop("events", "events_2024_01") == "DROP TABLE events_2024_01;"


@pytest.mark.parametrize("name", ["events_default", "users", "events_2024_01; DROP TABLE users", "other_2024_01", "events_2024_13"])
def test_ddl_drop_refuses_anything_that_is_not_a_partition(name):
    with pytest.raises(ValueError):
        ddl_drop("events", name)


# --- plan_partitions -----------------------------------------------------------------------------------------------

def names(*months, table="events"):
    return [f"{table}_{y:04d}_{m:02d}" for y, m in months]


def test_plan_on_empty_schema_creates_the_whole_window():
    plan = plan_partitions("events", [], D(2026, 3, 15), retention_months=3, ahead_months=2)
    assert plan == {"create": names((2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)), "drop": []}


def test_plan_drops_old_and_creates_missing():
    existing = names((2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3))
    plan = plan_partitions("events", existing, D(2026, 3, 15), retention_months=3, ahead_months=1)
    assert plan == {"create": names((2026, 4)), "drop": names((2025, 10), (2025, 11), (2025, 12))}


def test_plan_is_idempotent_when_schema_matches():
    existing = names((2026, 1), (2026, 2), (2026, 3), (2026, 4))
    assert plan_partitions("events", existing, D(2026, 3, 1), 3, 1) == {"create": [], "drop": []}


def test_retention_one_keeps_only_the_current_month():
    plan = plan_partitions("events", names((2026, 2), (2026, 3)), D(2026, 3, 31), retention_months=1, ahead_months=0)
    assert plan == {"create": [], "drop": names((2026, 2))}


def test_window_crosses_year_boundary():
    plan = plan_partitions("events", names((2025, 10), (2025, 11)), D(2026, 1, 10), retention_months=3, ahead_months=2)
    assert plan["create"] == names((2025, 12), (2026, 1), (2026, 2), (2026, 3))
    assert plan["drop"] == names((2025, 10))


def test_window_with_long_retention_crosses_several_years():
    plan = plan_partitions("events", [], D(2026, 2, 1), retention_months=26, ahead_months=0)
    assert len(plan["create"]) == 26
    assert plan["create"][0] == "events_2024_01" and plan["create"][-1] == "events_2026_02"


def test_first_and_last_day_of_month_give_the_same_plan():
    a = plan_partitions("events", [], D(2026, 3, 1), 2, 1)
    b = plan_partitions("events", [], D(2026, 3, 31), 2, 1)
    c = plan_partitions("events", [], dt.datetime(2026, 3, 31, 23, 59), 2, 1)
    assert a == b == c


def test_future_partitions_beyond_ahead_are_not_dropped():
    existing = names((2026, 3), (2026, 9), (2027, 1))
    assert plan_partitions("events", existing, D(2026, 3, 1), 1, 1)["drop"] == []


def test_foreign_tables_and_special_partitions_are_never_dropped():
    existing = ["events_default", "events_archive", "eventsx_2020_01", "other_2020_01", "events_2020_13", "events_2020_1",
                "events_2020_01_old", "users", "events", "Events_2020_01", "events_2020_01"]
    plan = plan_partitions("events", existing, D(2026, 3, 1), 2, 0)
    assert plan["drop"] == ["events_2020_01"]


def test_prefix_tables_do_not_interfere():
    existing = names((2020, 1), table="events") + names((2020, 1), table="events_v2")
    assert plan_partitions("events", existing, D(2026, 3, 1), 1, 0)["drop"] == ["events_2020_01"]
    assert plan_partitions("events_v2", existing, D(2026, 3, 1), 1, 0)["drop"] == ["events_v2_2020_01"]


def test_duplicates_in_existing_do_not_duplicate_results():
    existing = ["events_2020_01", "events_2020_01", "events_2026_03", "events_2026_03"]
    plan = plan_partitions("events", existing, D(2026, 3, 1), 1, 1)
    assert plan == {"create": ["events_2026_04"], "drop": ["events_2020_01"]}


def test_existing_may_be_any_iterable_and_is_not_consumed_wrongly():
    gen = (n for n in names((2026, 3)))
    assert plan_partitions("events", gen, D(2026, 3, 1), 1, 0) == {"create": [], "drop": []}
    assert plan_partitions("events", set(names((2020, 1))), D(2026, 3, 1), 1, 0)["drop"] == ["events_2020_01"]


def test_results_are_sorted():
    plan = plan_partitions("events", names((2020, 5), (2019, 12), (2020, 1)), D(2026, 3, 1), 3, 3)
    assert plan["drop"] == sorted(plan["drop"]) and plan["create"] == sorted(plan["create"])


@pytest.mark.parametrize("retention, ahead", [(0, 1), (-1, 1), (1, -1), (1.5, 1), (1, 0.5), (True, 1), (1, True), ("3", 1), (None, 1)])
def test_window_validation(retention, ahead):
    with pytest.raises(ValueError):
        plan_partitions("events", [], D(2026, 1, 1), retention, ahead)


def test_generated_ddl_matches_the_plan():
    plan = plan_partitions("events", [], D(2026, 12, 1), 1, 1)
    assert [ddl_create("events", partition_bounds("events", n)[0]) for n in plan["create"]] == [
        "CREATE TABLE events_2026_12 PARTITION OF events FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');",
        "CREATE TABLE events_2027_01 PARTITION OF events FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');",
    ]


# --- partition pruning ------------------------------------------------------------------------------------------------

ALL = names((2026, 1), (2026, 2), (2026, 3), (2026, 4)) + ["events_default", "other_2026_02"]


def test_one_day_touches_one_partition():
    assert partitions_for_range("events", ALL, D(2026, 2, 10), D(2026, 2, 11)) == ["events_2026_02"]


def test_range_spanning_months():
    assert partitions_for_range("events", ALL, D(2026, 1, 31), D(2026, 3, 2)) == names((2026, 1), (2026, 2), (2026, 3))


def test_end_is_exclusive():
    assert partitions_for_range("events", ALL, D(2026, 2, 1), D(2026, 3, 1)) == ["events_2026_02"]
    assert partitions_for_range("events", ALL, D(2026, 2, 1), D(2026, 3, 2)) == names((2026, 2), (2026, 3))


def test_start_is_inclusive_and_partition_end_is_exclusive():
    assert partitions_for_range("events", ALL, D(2026, 3, 1), D(2026, 3, 2)) == ["events_2026_03"]
    assert partitions_for_range("events", ALL, D(2026, 2, 28), D(2026, 3, 1)) == ["events_2026_02"]


def test_empty_and_reversed_ranges():
    assert partitions_for_range("events", ALL, D(2026, 2, 1), D(2026, 2, 1)) == []
    assert partitions_for_range("events", ALL, D(2026, 3, 1), D(2026, 2, 1)) == []


def test_range_outside_existing_partitions():
    assert partitions_for_range("events", ALL, D(2020, 1, 1), D(2020, 2, 1)) == []
    assert partitions_for_range("events", ALL, D(2030, 1, 1), D(2031, 1, 1)) == []


def test_huge_range_returns_everything_of_this_table_only():
    assert partitions_for_range("events", ALL, D(2000, 1, 1), D(2100, 1, 1)) == names((2026, 1), (2026, 2), (2026, 3), (2026, 4))


def test_datetime_start_is_truncated_and_end_is_rounded_up():
    start = dt.datetime(2026, 2, 28, 23, 0)
    end = dt.datetime(2026, 3, 1, 0, 30)  # 00:30 першого березня вже належить березневій партиції
    assert partitions_for_range("events", ALL, start, end) == names((2026, 2), (2026, 3))
    assert partitions_for_range("events", ALL, start, dt.datetime(2026, 3, 1, 0, 0)) == names((2026, 2))


def test_year_boundary():
    existing = names((2025, 11), (2025, 12), (2026, 1))
    assert partitions_for_range("events", existing, D(2025, 12, 31), D(2026, 1, 1)) == ["events_2025_12"]
