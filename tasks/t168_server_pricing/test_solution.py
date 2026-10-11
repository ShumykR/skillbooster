import copy
import datetime

import pytest

from solution import OrderRejected, price_order

TODAY = datetime.date(2026, 6, 15)
CATALOG = {
    "book": {"price_cents": 1999, "max_qty": 5, "active": True},
    "pen": {"price_cents": 150, "max_qty": 100, "active": True},
    "old": {"price_cents": 500, "max_qty": 10, "active": False},
    "free": {"price_cents": 0, "max_qty": 1, "active": True},
}
PROMOS = {
    "SAVE10": {"percent": 10, "min_total_cents": 1000, "valid_until": "2026-06-30"},
    "OLD": {"percent": 50, "min_total_cents": 0, "valid_until": "2026-06-14"},
    "TODAY": {"percent": 5, "min_total_cents": 0, "valid_until": "2026-06-15"},
}


def order(items, **extra):
    p = {"items": items}
    p.update(extra)
    return p


def price(payload, today=TODAY):
    return price_order(CATALOG, PROMOS, payload, today)


def reject(payload, code, today=TODAY):
    with pytest.raises(OrderRejected) as e:
        price(payload, today)
    assert e.value.code == code


# ---------- ціни тільки з каталогу ----------

def test_basic_total():
    r = price(order([{"sku": "book", "qty": 2}, {"sku": "pen", "qty": 3}]))
    assert r["subtotal_cents"] == 2 * 1999 + 3 * 150
    assert r["discount_cents"] == 0
    assert r["total_cents"] == r["subtotal_cents"] == 4448
    assert r["price_changed"] is False


def test_lines_structure_and_order():
    r = price(order([{"sku": "pen", "qty": 3}, {"sku": "book", "qty": 2}]))
    assert r["lines"] == [
        {"sku": "book", "qty": 2, "unit_cents": 1999, "line_cents": 3998},
        {"sku": "pen", "qty": 3, "unit_cents": 150, "line_cents": 450},
    ]


def test_client_price_fields_ignored():
    r = price(order([{"sku": "book", "qty": 1, "price_cents": 1, "unit_cents": 1, "discount_pct": 99}],
                    total_cents=1, discount_cents=1999, is_admin=True))
    assert r["total_cents"] == 1999 and r["discount_cents"] == 0


def test_client_total_only_sets_price_changed():
    r = price(order([{"sku": "book", "qty": 1}], claimed_total_cents=1))
    assert r["total_cents"] == 1999 and r["price_changed"] is True


def test_claimed_total_equal_is_not_changed():
    assert price(order([{"sku": "book", "qty": 1}], claimed_total_cents=1999))["price_changed"] is False


def test_claimed_total_zero_still_compared():
    assert price(order([{"sku": "book", "qty": 1}], claimed_total_cents=0))["price_changed"] is True


def test_zero_price_item():
    assert price(order([{"sku": "free", "qty": 1}]))["total_cents"] == 0


# ---------- обʼєднання рядків і ліміти ----------

def test_duplicate_lines_merged():
    r = price(order([{"sku": "pen", "qty": 2}, {"sku": "pen", "qty": 3}]))
    assert r["lines"] == [{"sku": "pen", "qty": 5, "unit_cents": 150, "line_cents": 750}]


def test_qty_limit_exact_ok():
    assert price(order([{"sku": "book", "qty": 5}]))["total_cents"] == 5 * 1999


def test_qty_limit_exceeded():
    reject(order([{"sku": "book", "qty": 6}]), "qty_limit")


def test_qty_limit_bypass_by_two_lines():
    reject(order([{"sku": "book", "qty": 3}, {"sku": "book", "qty": 3}]), "qty_limit")


@pytest.mark.parametrize("qty", [0, -1, 1.5, "2", None, True, [1]])
def test_bad_qty(qty):
    reject(order([{"sku": "pen", "qty": qty}]), "bad_qty")


def test_missing_qty():
    reject(order([{"sku": "pen"}]), "bad_qty")


def test_negative_qty_cannot_offset_other_line():
    reject(order([{"sku": "book", "qty": 2}, {"sku": "pen", "qty": -5}]), "bad_qty")


# ---------- sku ----------

@pytest.mark.parametrize("sku", ["nope", "", None, 5, ["book"], "BOOK"])
def test_unknown_sku(sku):
    reject(order([{"sku": sku, "qty": 1}]), "unknown_sku")


def test_inactive_sku():
    reject(order([{"sku": "old", "qty": 1}]), "inactive_sku")


def test_item_not_a_dict():
    reject(order(["book"]), "unknown_sku")
    reject(order([None]), "unknown_sku")


@pytest.mark.parametrize("payload", [{}, {"items": []}, {"items": None}, {"items": "book"}, {"items": {"sku": "book"}}])
def test_empty_orders(payload):
    reject(payload, "empty")


def test_too_many_lines():
    reject(order([{"sku": "pen", "qty": 1}] * 51), "empty")
    assert price(order([{"sku": "pen", "qty": 1}] * 50))["lines"][0]["qty"] == 50


# ---------- порядок перевірок ----------

def test_error_order_by_lines():
    reject(order([{"sku": "nope", "qty": 0}]), "unknown_sku")
    reject(order([{"sku": "old", "qty": 0}]), "inactive_sku")
    reject(order([{"sku": "book", "qty": 99}, {"sku": "pen", "qty": 0}]), "bad_qty")


def test_first_bad_line_wins():
    reject(order([{"sku": "pen", "qty": 0}, {"sku": "nope", "qty": 1}]), "bad_qty")
    reject(order([{"sku": "nope", "qty": 1}, {"sku": "pen", "qty": 0}]), "unknown_sku")


def test_qty_limit_before_promo():
    reject(order([{"sku": "book", "qty": 9}], promo_code="NOPE"), "qty_limit")


# ---------- промокоди ----------

def test_promo_applied():
    r = price(order([{"sku": "book", "qty": 1}], promo_code="SAVE10"))
    assert (r["subtotal_cents"], r["discount_cents"], r["total_cents"]) == (1999, 199, 1800)


def test_promo_discount_rounds_down():
    r = price(order([{"sku": "pen", "qty": 7}], promo_code="SAVE10"))  # 1050 * 10 // 100 = 105
    assert r["discount_cents"] == 105
    r = price(order([{"sku": "book", "qty": 1}, {"sku": "pen", "qty": 1}], promo_code="save10"))  # 2149 -> 214
    assert (r["discount_cents"], r["total_cents"]) == (214, 1935)


def test_promo_code_normalized():
    for code in ("save10", "  SAVE10 ", "Save10"):
        assert price(order([{"sku": "book", "qty": 1}], promo_code=code))["discount_cents"] == 199


def test_promo_none_means_no_promo():
    assert price(order([{"sku": "book", "qty": 1}], promo_code=None))["discount_cents"] == 0


@pytest.mark.parametrize("code", ["NOPE", "", 5, ["SAVE10"]])
def test_bad_promo(code):
    reject(order([{"sku": "book", "qty": 1}], promo_code=code), "bad_promo")


def test_promo_expired():
    reject(order([{"sku": "book", "qty": 1}], promo_code="OLD"), "promo_expired")


def test_promo_valid_on_last_day():
    assert price(order([{"sku": "book", "qty": 1}], promo_code="TODAY"))["discount_cents"] == 99


def test_promo_depends_on_today_param():
    p = order([{"sku": "book", "qty": 1}], promo_code="SAVE10")
    assert price(p, datetime.date(2026, 6, 30))["discount_cents"] == 199
    reject(p, "promo_expired", today=datetime.date(2026, 7, 1))


def test_promo_min_total_uses_subtotal_before_discount():
    reject(order([{"sku": "pen", "qty": 6}], promo_code="SAVE10"), "promo_min_total")   # 900 < 1000
    assert price(order([{"sku": "pen", "qty": 7}], promo_code="SAVE10"))["total_cents"] == 945  # 1050 >= 1000


def test_promo_min_total_exact():
    p = {"book": {"price_cents": 1000, "max_qty": 1, "active": True}}
    r = price_order(p, PROMOS, order([{"sku": "book", "qty": 1}], promo_code="SAVE10"), TODAY)
    assert r["total_cents"] == 900


def test_client_discount_cannot_replace_promo():
    r = price(order([{"sku": "book", "qty": 1}], discount_pct=50, promo_discount_cents=1000))
    assert r["discount_cents"] == 0


# ---------- загальне ----------

def test_inputs_not_mutated():
    payload = order([{"sku": "pen", "qty": 8}, {"sku": "pen", "qty": 1}], promo_code=" save10 ", claimed_total_cents=5)
    snap = (copy.deepcopy(payload), copy.deepcopy(CATALOG), copy.deepcopy(PROMOS))
    price(payload)
    assert (payload, CATALOG, PROMOS) == snap


def test_result_types():
    r = price(order([{"sku": "book", "qty": 1}]))
    assert set(r) == {"lines", "subtotal_cents", "discount_cents", "total_cents", "price_changed"}
    assert all(type(r[k]) is int for k in ("subtotal_cents", "discount_cents", "total_cents"))


def test_rejection_is_exception_with_code():
    e = OrderRejected("x")
    assert isinstance(e, Exception) and e.code == "x"
