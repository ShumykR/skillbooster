import dataclasses

import pytest

from solution import Email, Line, Order, Quantity, Sku, ValidationError, parse_order


# --- Email ----------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    ["ann@example.com", "a@b.co", "first.last@mail.example.org", "x+tag@ex-ample.com", "u_1%@a.bc",
     "a" * 64 + "@example.com", "ann@" + "-".join(["a" * 20] * 3) + ".com", "ann@a.b.c.dd"],
)
def test_valid_emails(raw):
    local, domain = raw.split("@")
    assert Email(raw).value == local + "@" + domain.lower()


def test_domain_is_lowercased_local_part_is_kept():
    assert Email("Ann.Smith@Example.COM").value == "Ann.Smith@example.com"


def test_equality_and_hash_by_normalised_value():
    assert Email("a@EXAMPLE.com") == Email("a@example.com")
    assert len({Email("a@EXAMPLE.com"), Email("a@example.com")}) == 1
    assert Email("A@example.com") != Email("a@example.com")


@pytest.mark.parametrize(
    "raw",
    ["", "a", "a@", "@b.com", "a@b", "a@@b.com", "a@b@c.com", "a b@example.com", " a@example.com", "a@example.com ",
     "a@example.com\n", "a@example.com\r\nBcc: evil@x.com", "a\x00@example.com", "\ta@example.com",
     ".a@example.com", "a.@example.com", "a..b@example.com", "a" * 65 + "@example.com",
     "a@-example.com", "a@example-.com", "a@exa_mple.com", "a@example..com", "a@.example.com", "a@example.c0m",
     "a@example.c", "a@" + "a" * 64 + ".com", "ünï@example.com", "a@exämple.com", "a(b)@example.com",
     "a,b@example.com", "a" * 60 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 63 + "." + "e" * 60 + ".com",
     "a@example.com>", "<a@example.com>", '"a"@example.com'],
)
def test_invalid_emails(raw):
    with pytest.raises(ValueError):
        Email(raw)


@pytest.mark.parametrize("raw", [None, 5, b"a@b.co", ["a@b.co"], True])
def test_email_requires_str(raw):
    with pytest.raises(TypeError):
        Email(raw)


def test_email_is_immutable():
    e = Email("a@example.com")
    with pytest.raises(AttributeError):
        e.value = "evil@example.com"


# --- Quantity ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 2, 999, 1000])
def test_valid_quantity(n):
    assert Quantity(n).value == n and int(Quantity(n)) == n


@pytest.mark.parametrize("n", [0, -1, 1001, 10**9])
def test_quantity_out_of_range(n):
    with pytest.raises(ValueError):
        Quantity(n)


@pytest.mark.parametrize("n", [True, False, 5.0, 1.5, "5", None, [1]])
def test_quantity_requires_a_real_int(n):
    with pytest.raises(TypeError):
        Quantity(n)


# --- Sku ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("s", ["ABC", "A1B", "ABC-123", "0-9", "A" * 20])
def test_valid_sku(s):
    assert Sku(s).value == s


@pytest.mark.parametrize(
    "s", ["", "AB", "A" * 21, "abc", "ABC_1", "-ABC", "ABC\n", "ABC ", " ABC", "AB C", "ABС", "ABC;", "A\x00B"]
)  # у «ABС» остання літера кирилична
def test_invalid_sku(s):
    with pytest.raises(ValueError):
        Sku(s)


@pytest.mark.parametrize("s", [None, 123, b"ABC"])
def test_sku_requires_str(s):
    with pytest.raises(TypeError):
        Sku(s)


# --- Line / Order -------------------------------------------------------------------------------------

def test_line_total_and_order_total():
    l1 = Line(Sku("AAA"), Quantity(3), 250)
    l2 = Line(Sku("BBB"), Quantity(1), 1000)
    assert l1.total_cents == 750
    assert Order(Email("a@example.com"), (l1, l2)).total_cents == 1750


@pytest.mark.parametrize("price", [0, -1, 10**9 + 1, 1.5, "10", None, True])
def test_line_validates_price(price):
    with pytest.raises((ValueError, TypeError)):
        Line(Sku("AAA"), Quantity(1), price)


def test_line_requires_value_objects_not_raw_values():
    with pytest.raises(TypeError):
        Line("AAA", Quantity(1), 100)
    with pytest.raises(TypeError):
        Line(Sku("AAA"), 1, 100)


def test_order_requires_email_object_and_non_empty_tuple_of_lines():
    line = Line(Sku("AAA"), Quantity(1), 100)
    with pytest.raises(TypeError):
        Order("a@example.com", (line,))
    with pytest.raises((TypeError, ValueError)):
        Order(Email("a@example.com"), ())
    with pytest.raises(TypeError):
        Order(Email("a@example.com"), [line])  # список змінний: потрібен tuple
    with pytest.raises(TypeError):
        Order(Email("a@example.com"), ("not a line",))


def test_everything_is_frozen():
    line = Line(Sku("AAA"), Quantity(1), 100)
    order = Order(Email("a@example.com"), (line,))
    for obj, attr in ((line, "unit_price_cents"), (order, "email"), (Sku("AAA"), "value"), (Quantity(1), "value")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, attr, 5)


# --- parse_order --------------------------------------------------------------------------------------

def good(**over):
    p = {"email": "Ann@Example.com", "lines": [{"sku": "AAA", "qty": 2, "price_cents": 500},
                                               {"sku": "BBB-1", "qty": 1, "price_cents": 1500}]}
    p.update(over)
    return p


def errors_of(payload):
    with pytest.raises(ValidationError) as info:
        parse_order(payload)
    assert isinstance(info.value, ValueError)
    assert all(isinstance(k, str) and isinstance(v, str) and v for k, v in info.value.errors.items())
    return info.value.errors


def test_parse_valid_order():
    order = parse_order(good())
    assert isinstance(order, Order)
    assert order.email == Email("Ann@example.com")
    assert order.lines[0] == Line(Sku("AAA"), Quantity(2), 500)
    assert isinstance(order.lines, tuple)
    assert order.total_cents == 2500


def test_parse_does_not_mutate_the_input():
    payload = good()
    import copy
    before = copy.deepcopy(payload)
    parse_order(payload)
    assert payload == before


def test_all_errors_are_collected_with_paths():
    errs = errors_of({
        "email": "nope",
        "lines": [
            {"sku": "AAA", "qty": 0, "price_cents": 100},
            {"sku": "bad sku", "qty": 1, "price_cents": 100},
            {"sku": "CCC", "qty": 1, "price_cents": -5},
        ],
    })
    assert set(errs) == {"email", "lines[0].qty", "lines[1].sku", "lines[2].price_cents"}


def test_bool_and_float_quantity_are_errors_not_crashes():
    errs = errors_of(good(lines=[{"sku": "AAA", "qty": True, "price_cents": 100},
                                 {"sku": "BBB", "qty": 2.0, "price_cents": 100}]))
    assert set(errs) == {"lines[0].qty", "lines[1].qty"}


def test_wrong_types_everywhere_give_errors_not_exceptions():
    errs = errors_of({"email": 5, "lines": [{"sku": 7, "qty": "2", "price_cents": "100"}]})
    assert set(errs) == {"email", "lines[0].sku", "lines[0].qty", "lines[0].price_cents"}


def test_missing_fields_are_required():
    errs = errors_of({"lines": [{"sku": "AAA"}]})
    assert set(errs) == {"email", "lines[0].qty", "lines[0].price_cents"}
    assert set(errors_of({"email": "a@example.com"})) == {"lines"}


def test_unexpected_fields_are_rejected_mass_assignment():
    errs = errors_of(good(is_admin=True))
    assert set(errs) == {"is_admin"}
    p = good()
    p["lines"][1]["discount"] = 99
    p["lines"][0]["price"] = 1
    assert set(errors_of(p)) == {"lines[1].discount", "lines[0].price"}


def test_payload_must_be_an_object():
    for bad in (None, [], "x", 5, [good()]):
        assert set(errors_of(bad)) == {""}


def test_lines_must_be_a_non_empty_list_of_at_most_50():
    assert set(errors_of(good(lines=[]))) == {"lines"}
    assert set(errors_of(good(lines="AAA"))) == {"lines"}
    assert set(errors_of(good(lines=None))) == {"lines"}
    assert set(errors_of(good(lines={"sku": "AAA"}))) == {"lines"}
    many = [{"sku": f"S{i:03}", "qty": 1, "price_cents": 1} for i in range(51)]
    assert set(errors_of(good(lines=many))) == {"lines"}
    ok = [{"sku": f"S{i:03}", "qty": 1, "price_cents": 1} for i in range(50)]
    assert parse_order(good(lines=ok)).total_cents == 50


def test_line_that_is_not_an_object():
    errs = errors_of(good(lines=[{"sku": "AAA", "qty": 1, "price_cents": 1}, "AAA", None]))
    assert set(errs) == {"lines[1]", "lines[2]"}


def test_duplicate_skus():
    errs = errors_of(good(lines=[{"sku": "AAA", "qty": 1, "price_cents": 1},
                                 {"sku": "BBB", "qty": 1, "price_cents": 1},
                                 {"sku": "AAA", "qty": 1, "price_cents": 1},
                                 {"sku": "AAA", "qty": 1, "price_cents": 1}]))
    assert set(errs) == {"lines[2].sku", "lines[3].sku"}


def test_total_overflow_is_checked_only_when_lines_are_valid():
    big = {"sku": "AAA", "qty": 1000, "price_cents": 10**9}
    lines = [dict(big, sku=f"S{i:03}") for i in range(2)]  # 2 * 10**12 > 10**12
    assert set(errors_of(good(lines=lines))) == {"lines"}
    lines_ok = [dict(big)]  # ровно 10**12
    assert parse_order(good(lines=lines_ok)).total_cents == 10**12


def test_invalid_line_hides_total_check():
    lines = [dict(sku="AAA", qty=1000, price_cents=10**9), dict(sku="BBB", qty=1000, price_cents=10**9),
             dict(sku="bad", qty=1, price_cents=1)]
    assert set(errors_of(good(lines=lines))) == {"lines[2].sku"}


def test_hostile_email_in_payload_does_not_reach_the_order():
    errs = errors_of(good(email="a@example.com\r\nBcc: evil@example.com"))
    assert set(errs) == {"email"}


def test_validation_error_exposes_errors_dict():
    try:
        parse_order({})
    except ValidationError as exc:
        assert exc.errors["email"] and exc.errors["lines"]
    else:
        raise AssertionError("expected ValidationError")
