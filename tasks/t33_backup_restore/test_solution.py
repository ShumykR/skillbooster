import copy
import datetime as dt

import pytest

from solution import RestoreImpossible, plan_restore, prune_backups, removable_wal

T0 = dt.datetime(2026, 3, 1, 0, 0)


def H(hours):
    return T0 + dt.timedelta(hours=hours)


def seg(n):
    """WAL-сегмент n закінчується через n годин після T0."""
    return {"seq": n, "ends_at": H(n)}


def wal_range(a, b, skip=()):
    return [seg(n) for n in range(a, b + 1) if n not in skip]


def backup(bid, taken_h, start, end):
    return {"id": bid, "taken_at": H(taken_h), "start_seq": start, "end_seq": end}


B1 = backup("B1", 10, 8, 10)
B2 = backup("B2", 30, 28, 30)
WAL = wal_range(0, 60)


# --- plan_restore: вибір копії ------------------------------------------------------------------------------------

def test_picks_the_newest_backup_not_after_target():
    assert plan_restore([B1, B2], WAL, H(40)) == {"backup_id": "B2", "wal_from": 28, "wal_to": 40}


def test_target_between_backups_uses_the_older_one():
    assert plan_restore([B1, B2], WAL, H(20)) == {"backup_id": "B1", "wal_from": 8, "wal_to": 20}


def test_wal_to_is_the_segment_that_contains_the_target():
    assert plan_restore([B1, B2], WAL, H(40) + dt.timedelta(minutes=30))["wal_to"] == 41
    assert plan_restore([B1, B2], WAL, H(40) - dt.timedelta(minutes=30))["wal_to"] == 40
    assert plan_restore([B1, B2], WAL, H(40))["wal_to"] == 40  # ends_at == target теж підходить


def test_target_equal_to_backup_time():
    assert plan_restore([B1, B2], WAL, H(30)) == {"backup_id": "B2", "wal_from": 28, "wal_to": 30}


def test_wal_to_is_never_below_the_backup_end_seq():
    late = backup("L", 30, 28, 33)  # копія стала узгодженою лише на сегменті 33
    assert plan_restore([late], WAL, H(30))["wal_to"] == 33


def test_input_order_and_duplicates_do_not_matter():
    shuffled = list(reversed(WAL)) + [seg(40), seg(41)]
    assert plan_restore([B2, B1], shuffled, H(40)) == {"backup_id": "B2", "wal_from": 28, "wal_to": 40}


def test_inputs_are_not_modified():
    backups, wal = [B2, B1], list(reversed(WAL))
    before = copy.deepcopy((backups, wal))
    plan_restore(backups, wal, H(40))
    assert (backups, wal) == before


# --- plan_restore: пропуски й відмови -----------------------------------------------------------------------------------

def test_gap_inside_the_needed_range_falls_back_to_an_older_backup():
    wal = wal_range(0, 60, skip={35})
    # для B2 і target 40 потрібні 28..40, а 35 немає; B1 потребує 8..40, теж зачіпає 35
    with pytest.raises(RestoreImpossible, match="wal gap"):
        plan_restore([B1, B2], wal, H(40))


def test_gap_before_the_newer_backup_does_not_matter_for_it():
    wal = wal_range(0, 60, skip={15})
    assert plan_restore([B1, B2], wal, H(40))["backup_id"] == "B2"
    with pytest.raises(RestoreImpossible, match="wal gap"):
        plan_restore([B1, B2], wal, H(20))  # тут B1 потребує 8..20, а 15 немає


def test_fallback_to_an_older_backup_when_the_newest_needs_a_missing_segment():
    old = backup("OLD", 5, 2, 5)
    new = backup("NEW", 30, 28, 33)  # стає узгодженою лише на сегменті 33, а сегмента 32 в архіві немає
    wal = wal_range(0, 60, skip={32})
    assert plan_restore([old, new], wal, H(31)) == {"backup_id": "OLD", "wal_from": 2, "wal_to": 31}
    assert plan_restore([old, new], wal_range(0, 60), H(31))["backup_id"] == "NEW"


def test_no_backup_before_target():
    with pytest.raises(RestoreImpossible, match="no backup"):
        plan_restore([B1, B2], WAL, H(9))
    with pytest.raises(RestoreImpossible, match="no backup"):
        plan_restore([], WAL, H(40))


def test_target_after_archive_end():
    with pytest.raises(RestoreImpossible, match="target after archive end"):
        plan_restore([B1, B2], wal_range(0, 50), H(55))


def test_allow_latest_restores_to_the_end_of_the_archive():
    assert plan_restore([B1, B2], wal_range(0, 50), H(55), allow_latest=True) == {"backup_id": "B2", "wal_from": 28, "wal_to": 50}


def test_allow_latest_still_requires_a_continuous_chain():
    with pytest.raises(RestoreImpossible, match="wal gap"):
        plan_restore([B1, B2], wal_range(0, 50, skip={45}), H(55), allow_latest=True)


def test_allow_latest_skips_backups_that_became_consistent_after_the_archive_end():
    fresh = backup("FRESH", 49, 48, 55)  # потребує сегмента 55, якого ще немає
    assert plan_restore([B2, fresh], wal_range(0, 50), H(60), allow_latest=True)["backup_id"] == "B2"


def test_empty_archive():
    with pytest.raises(RestoreImpossible):
        plan_restore([B1], [], H(20))


def test_restore_impossible_is_a_value_error():
    assert issubclass(RestoreImpossible, ValueError)


def test_corrupt_backup_metadata_is_a_plain_value_error():
    bad = backup("BAD", 10, 12, 8)
    with pytest.raises(ValueError) as info:
        plan_restore([bad, B2], WAL, H(40))
    assert not isinstance(info.value, RestoreImpossible)


@pytest.mark.parametrize("target", ["2026-03-02", dt.date(2026, 3, 2), None, 1700000000])
def test_target_must_be_datetime(target):
    with pytest.raises(TypeError):
        plan_restore([B1], WAL, target)


# --- prune_backups ------------------------------------------------------------------------------------------------------

NOW = dt.datetime(2026, 3, 15, 12, 0)  # неділя, ISO-тиждень 11


def daily_backups(start=dt.date(2025, 12, 1), end=dt.date(2026, 3, 15)):
    out, d = [], start
    while d <= end:
        out.append({"id": f"b-{d.isoformat()}", "taken_at": dt.datetime(d.year, d.month, d.day, 2, 0), "start_seq": 0, "end_seq": 0})
        d += dt.timedelta(days=1)
    return out


def kept(backups, deleted):
    return sorted(b["id"] for b in backups if b["id"] not in set(deleted))


def test_grandfather_father_son_policy():
    backups = daily_backups()
    deleted = prune_backups(backups, NOW, keep_daily=7, keep_weekly=4, keep_monthly=3)
    assert kept(backups, deleted) == [
        "b-2026-01-31",                                                                 # кінець січня (місячна)
        "b-2026-02-22", "b-2026-02-28",                                                  # тиждень 8 та кінець лютого
        "b-2026-03-01", "b-2026-03-08",                                                  # тижні 9 і 10
        "b-2026-03-09", "b-2026-03-10", "b-2026-03-11", "b-2026-03-12", "b-2026-03-13", "b-2026-03-14", "b-2026-03-15",  # 7 днів
    ]
    assert deleted == sorted(deleted)


def test_only_the_newest_backup_of_a_day_is_kept_for_daily():
    backups = [
        {"id": "morning", "taken_at": dt.datetime(2026, 3, 15, 2, 0), "start_seq": 0, "end_seq": 0},
        {"id": "noon", "taken_at": dt.datetime(2026, 3, 15, 11, 0), "start_seq": 0, "end_seq": 0},
        {"id": "yesterday", "taken_at": dt.datetime(2026, 3, 14, 23, 0), "start_seq": 0, "end_seq": 0},
    ]
    assert prune_backups(backups, NOW, 2, 0, 0) == ["morning"]


def test_zero_counts_keep_only_the_newest_backup():
    backups = daily_backups(dt.date(2026, 3, 1), dt.date(2026, 3, 15))
    deleted = prune_backups(backups, NOW, 0, 0, 0)
    assert kept(backups, deleted) == ["b-2026-03-15"]


def test_newest_backup_is_kept_even_if_outside_every_window():
    old = [{"id": "ancient", "taken_at": dt.datetime(2020, 1, 1), "start_seq": 0, "end_seq": 0}]
    assert prune_backups(old, NOW, 7, 4, 3) == []


def test_backups_from_the_future_are_never_deleted():
    backups = daily_backups(dt.date(2026, 3, 10), dt.date(2026, 3, 15))
    future = {"id": "future", "taken_at": dt.datetime(2026, 3, 15, 23, 59), "start_seq": 0, "end_seq": 0}
    deleted = prune_backups(backups + [future], NOW, 1, 0, 0)
    assert "future" not in deleted
    later = {"id": "later", "taken_at": dt.datetime(2026, 3, 16, 2, 0), "start_seq": 0, "end_seq": 0}
    assert not {"future", "later"} & set(prune_backups(backups + [future, later], NOW, 1, 0, 0))  # обидві з майбутнього лишаються
    assert "b-2026-03-15" in kept(backups, deleted)  # найновіша з минулого за сьогодні (02:00) теж лишилась


def test_monthly_window_crosses_year_boundary():
    backups = [
        {"id": "nov", "taken_at": dt.datetime(2025, 11, 20), "start_seq": 0, "end_seq": 0},
        {"id": "dec", "taken_at": dt.datetime(2025, 12, 20), "start_seq": 0, "end_seq": 0},
        {"id": "dec-late", "taken_at": dt.datetime(2025, 12, 28), "start_seq": 0, "end_seq": 0},
        {"id": "oct", "taken_at": dt.datetime(2025, 10, 20), "start_seq": 0, "end_seq": 0},
        {"id": "jan", "taken_at": dt.datetime(2026, 1, 9), "start_seq": 0, "end_seq": 0},
    ]
    assert prune_backups(backups, dt.datetime(2026, 1, 10), 0, 0, 3) == ["dec", "oct"]


def test_iso_week_year_boundary():
    mk = lambda i, y, m, d: {"id": i, "taken_at": dt.datetime(y, m, d, 3), "start_seq": 0, "end_seq": 0}
    backups = [mk("dec28", 2025, 12, 28), mk("dec29", 2025, 12, 29), mk("jan1", 2026, 1, 1)]
    # 29 грудня 2025 це понеділок ISO-тижня 2026-W01, разом із 1 січня; 28 грудня це неділя 2025-W52
    assert prune_backups(backups, dt.datetime(2026, 1, 1, 12), 0, 2, 0) == ["dec29"]


def test_policies_are_a_union():
    backups = daily_backups(dt.date(2026, 3, 1), dt.date(2026, 3, 15))
    daily_only = set(prune_backups(backups, NOW, 3, 0, 0))
    weekly_only = set(prune_backups(backups, NOW, 0, 2, 0))
    both = set(prune_backups(backups, NOW, 3, 2, 0))
    assert both == daily_only & weekly_only


def test_empty_list():
    assert prune_backups([], NOW, 7, 4, 3) == []


@pytest.mark.parametrize("counts", [(-1, 0, 0), (0, -1, 0), (0, 0, -1), (1.5, 0, 0), (0, True, 0), (0, 0, "3"), (None, 0, 0)])
def test_counts_validation(counts):
    with pytest.raises(ValueError):
        prune_backups(daily_backups(dt.date(2026, 3, 1), dt.date(2026, 3, 2)), NOW, *counts)


def test_duplicate_ids_are_rejected():
    dup = daily_backups(dt.date(2026, 3, 1), dt.date(2026, 3, 2)) * 2
    with pytest.raises(ValueError):
        prune_backups(dup, NOW, 1, 1, 1)


def test_prune_does_not_modify_input():
    backups = daily_backups()
    before = copy.deepcopy(backups)
    prune_backups(backups, NOW, 7, 4, 3)
    assert backups == before


# --- removable_wal ----------------------------------------------------------------------------------------------------------

def test_wal_older_than_every_kept_backup_can_go():
    kept_backups = [backup("A", 30, 28, 30), backup("B", 50, 48, 50)]
    assert removable_wal(WAL, kept_backups) == list(range(0, 28))


def test_oldest_kept_backup_defines_the_floor():
    assert removable_wal(WAL, [B1, B2]) == list(range(0, 8))


def test_removable_wal_has_no_duplicates_and_is_sorted():
    wal = [seg(5), seg(3), seg(5), seg(40)]
    assert removable_wal(wal, [B2]) == [3, 5]


def test_no_kept_backups_means_no_wal_deleted():
    assert removable_wal(WAL, []) == []


def test_nothing_to_remove_when_floor_is_below_the_archive():
    assert removable_wal(wal_range(10, 20), [backup("X", 1, 5, 6)]) == []
