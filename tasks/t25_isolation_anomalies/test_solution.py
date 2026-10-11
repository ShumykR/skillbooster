import pytest

from solution import anomalies_allowed, find_anomalies, violations


def S(text):
    """Скорочений запис: 'b1 r1x w1x c1 a2' = begin T1, read T1 x, write T1 x, commit T1, abort T2 (ключі та транзакції однолітерні)."""
    names = {"b": "begin", "r": "read", "w": "write", "c": "commit", "a": "abort"}
    ops = []
    for tok in text.split():
        kind = names[tok[0]]
        tx = "T" + tok[1]
        ops.append((kind, tx) if len(tok) == 2 else (kind, tx, tok[2]))
    return ops


def anomalies(text):
    return find_anomalies(S(text))


# --- відсутність аномалій ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "",
        "b1 r1x w1x c1",
        "b1 r1x w1x c1 b2 r2x w2x c2",                       # послідовно
        "b1 b2 r1x r2y w1x w2y c1 c2",                       # різні ключі
        "b1 b2 r1x r2x c1 c2",                               # лише читання
        "b1 b2 w1x c1 r2x c2",                               # T2 читає вже після commit T1
        "b1 b2 r1x w1x c1 r2x w2x c2",                       # без перетину
    ],
)
def test_clean_schedules(text):
    assert anomalies(text) == []


# --- dirty read -------------------------------------------------------------------------------------------

def test_dirty_read_commit_later():
    assert anomalies("b1 b2 w1x r2x c1 c2") == [("dirty_read", "T1", "T2", "x")]


def test_dirty_read_even_if_writer_aborts():
    assert anomalies("b1 b2 w1x r2x a1 c2") == [("dirty_read", "T1", "T2", "x")]


def test_dirty_read_writer_never_finishes():
    assert anomalies("b1 b2 w1x r2x") == [("dirty_read", "T1", "T2", "x")]


def test_no_dirty_read_after_writer_finished():
    assert anomalies("b1 b2 w1x c1 r2x c2") == []
    assert anomalies("b1 b2 w1x a1 r2x c2") == []


def test_reading_own_write_is_not_dirty():
    assert anomalies("b1 w1x r1x c1") == []


def test_dirty_read_is_per_key():
    assert anomalies("b1 b2 w1x r2y c1 c2") == []


# --- non-repeatable read ---------------------------------------------------------------------------------------

def test_non_repeatable_read():
    assert anomalies("b1 b2 r1x w2x c2 r1x c1") == [("non_repeatable_read", "T1", "T2", "x")]


def test_non_repeatable_read_with_unfinished_reader():
    assert anomalies("b1 b2 r1x w2x c2 r1x") == [("non_repeatable_read", "T1", "T2", "x")]


def test_uncommitted_write_between_reads_is_a_dirty_read_not_a_non_repeatable_one():
    assert anomalies("b1 b2 r1x w2x r1x c1 c2") == [("dirty_read", "T2", "T1", "x")]
    assert anomalies("b1 b2 r1x w2x r1x a2 c1") == [("dirty_read", "T2", "T1", "x")]


def test_aborted_write_between_reads_is_not_an_anomaly():
    assert anomalies("b1 b2 r1x w2x a2 r1x c1") == []


def test_commit_after_second_read_is_not_non_repeatable():
    assert anomalies("b1 b2 r1x w2x r1x c2 c1") == [("dirty_read", "T2", "T1", "x")]


def test_single_read_is_never_non_repeatable():
    assert anomalies("b1 b2 r1x w2x c2 c1") == []


# --- lost update -----------------------------------------------------------------------------------------------

def test_classic_lost_update():
    # обидві прочитали баланс, обидві записали «баланс+внесок»: перший запис пропав
    assert anomalies("b1 b2 r1x r2x w1x w2x c1 c2") == [("lost_update", "T2", "T1", "x")]


def test_lost_update_other_order_of_commits():
    assert anomalies("b1 b2 r1x r2x w1x w2x c2 c1") == [("lost_update", "T2", "T1", "x")]


def test_lost_update_when_overwritten_between_read_and_write():
    assert anomalies("b1 b2 r1x w2x c2 w1x c1") == [("lost_update", "T1", "T2", "x")]


def test_no_lost_update_when_other_transaction_aborts():
    assert anomalies("b1 b2 r1x r2x w1x w2x c1 a2") == []
    assert anomalies("b1 b2 r1x w2x a2 w1x c1") == []


def test_no_lost_update_without_prior_read():
    assert anomalies("b1 b2 w2x w1x c1 c2") == []  # «сліпі» записи це інша проблема (dirty write)


def test_no_lost_update_when_write_happens_before_the_read():
    assert anomalies("b1 b2 w2x c2 r1x w1x c1") == []


def test_lost_update_on_different_keys_is_not_reported():
    assert anomalies("b1 b2 r1x r2y w1x w2y c1 c2") == []


# --- write skew ------------------------------------------------------------------------------------------------

def test_write_skew_on_call_roster():
    # двоє лікарів на зміні: кожен читає обох і знімає СЕБЕ; разом вийшла порожня зміна
    assert anomalies("b1 b2 r1a r1b r2a r2b w1a w2b c1 c2") == [("write_skew", "T1", "T2", "a,b")]


def test_write_skew_minimal_form():
    assert anomalies("b1 b2 r1a r2b w1b w2a c1 c2") == [("write_skew", "T1", "T2", "a,b")]


def test_write_skew_key_order_and_tx_order_are_normalised():
    assert anomalies("b2 b1 r2z r1y w2y w1z c2 c1") == [("write_skew", "T1", "T2", "y,z")]


def test_no_write_skew_if_one_transaction_aborts():
    assert anomalies("b1 b2 r1a r2b w1b w2a c1 a2") == []


def test_no_write_skew_if_reads_happen_after_a_commit():
    assert anomalies("b1 b2 r1a w1b c1 r2b w2a c2") == []


def test_no_write_skew_if_the_other_transaction_read_after_the_first_commit():
    assert anomalies("b1 b2 r2b w2a c2 r1a w1b c1") == []


def test_no_write_skew_when_the_second_write_is_not_to_the_first_read_key():
    assert anomalies("b1 b2 r1a r2b w1b w2c c1 c2") == []
    assert anomalies("b1 b2 r1a r2b w1b w2b c1 c2") == [("lost_update", "T2", "T1", "b")]  # а це вже lost update


# --- комбінації та унікальність -----------------------------------------------------------------------------------

def test_result_is_sorted_and_unique():
    text = "b1 b2 r1x r2x w1x w2x r1y r1y w1y c1 c2"
    result = anomalies(text)
    assert result == sorted(set(result))


def test_several_anomalies_in_one_schedule():
    result = anomalies("b1 b2 b3 w3x r1x r1y w2y c2 r1y c1 a3")
    assert ("dirty_read", "T3", "T1", "x") in result
    assert ("non_repeatable_read", "T1", "T2", "y") in result


def test_same_anomaly_is_not_duplicated_for_repeated_operations():
    result = anomalies("b1 b2 w1x r2x r2x r2x c1 c2")
    assert result == [("dirty_read", "T1", "T2", "x")]


def test_accepts_lists_instead_of_tuples():
    schedule = [["begin", "T1"], ["begin", "T2"], ["write", "T1", "x"], ["read", "T2", "x"], ["commit", "T1"], ["commit", "T2"]]
    assert find_anomalies(schedule) == [("dirty_read", "T1", "T2", "x")]


def test_input_is_not_modified():
    schedule = S("b1 b2 w1x r2x c1 c2")
    copy = list(schedule)
    find_anomalies(schedule)
    assert schedule == copy


# --- некоректні розклади ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "schedule",
    [
        [("read", "T1", "x")],                                              # без begin
        [("begin", "T1"), ("begin", "T1")],                                 # повторний begin
        [("begin", "T1"), ("commit", "T1"), ("read", "T1", "x")],           # після commit
        [("begin", "T1"), ("abort", "T1"), ("write", "T1", "x")],           # після abort
        [("begin", "T1"), ("commit", "T1"), ("commit", "T1")],
        [("begin", "T1"), ("sleep", "T1")],                                 # невідома операція
        [("begin", "T1"), ("read", "T1")],                                  # бракує ключа
        [("begin", "T1", "x")],                                             # зайвий елемент
        [("begin", 1)],                                                     # tx не рядок
        [("begin", "T1"), ("read", "T1", 5)],                               # ключ не рядок
        [()],
        ["begin T1"],
        [None],
    ],
)
def test_invalid_schedules(schedule):
    with pytest.raises(ValueError):
        find_anomalies(schedule)


# --- рівні ізоляції ---------------------------------------------------------------------------------------------------

def test_allowed_anomalies_per_level():
    assert anomalies_allowed("read committed") == {"non_repeatable_read", "lost_update", "write_skew"}
    assert anomalies_allowed("read uncommitted") == anomalies_allowed("read committed")
    assert anomalies_allowed("repeatable read") == {"write_skew"}
    assert anomalies_allowed("serializable") == set()


@pytest.mark.parametrize("name", ["READ COMMITTED", " Read  Committed ", "Serializable", "REPEATABLE READ"])
def test_level_names_are_case_and_space_insensitive(name):
    assert isinstance(anomalies_allowed(name), set)


@pytest.mark.parametrize("name", ["snapshot", "", "read_committed", None, 3, "serialisable"])
def test_unknown_levels(name):
    with pytest.raises(ValueError):
        anomalies_allowed(name)


def test_returned_set_is_a_copy():
    anomalies_allowed("serializable").add("dirty_read")
    assert anomalies_allowed("serializable") == set()


def test_violations_show_what_the_level_must_not_allow():
    lost = S("b1 b2 r1x r2x w1x w2x c1 c2")
    assert violations(lost, "read committed") == []
    assert violations(lost, "repeatable read") == [("lost_update", "T2", "T1", "x")]
    assert violations(lost, "serializable") == [("lost_update", "T2", "T1", "x")]


def test_dirty_read_violates_every_level():
    dirty = S("b1 b2 w1x r2x c1 c2")
    for level in ("read uncommitted", "read committed", "repeatable read", "serializable"):
        assert violations(dirty, level) == [("dirty_read", "T1", "T2", "x")]


def test_write_skew_is_allowed_below_serializable():
    skew = S("b1 b2 r1a r2b w1b w2a c1 c2")
    assert violations(skew, "repeatable read") == []
    assert violations(skew, "serializable") == [("write_skew", "T1", "T2", "a,b")]


def test_clean_schedule_never_violates():
    assert violations(S("b1 r1x w1x c1"), "serializable") == []


def test_violations_validates_level_and_schedule():
    with pytest.raises(ValueError):
        violations(S("b1 c1"), "snapshot")
    with pytest.raises(ValueError):
        violations([("read", "T1", "x")], "serializable")
