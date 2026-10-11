import random
from decimal import Decimal as D

import pytest

from solution import add_vat, allocate, convert, parse_money


def cents(x):
    """Точна перевірка форми: Decimal із двома знаками після коми."""
    assert isinstance(x, D)
    assert x.as_tuple().exponent == -2, f"{x!r} має мати рівно 2 знаки"
    return x


# --- parse_money -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("12", "12.00"),
        ("12.5", "12.50"),
        ("12.50", "12.50"),
        ("0.07", "0.07"),
        ("0", "0.00"),
        ("1,234.50", "1234.50"),
        ("1,234,567", "1234567.00"),
        ("  7.00 ", "7.00"),
        ("-5.25", "-5.25"),
        ("+3", "3.00"),
        ("999", "999.00"),
        ("1,000", "1000.00"),
    ],
)
def test_parse_money_valid(text, expected):
    assert cents(parse_money(text)) == D(expected)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "abc", "1.234", "1,23", "1.2.3", "1e3", ".5", "5.", "1 000", "12,34,567", "1,2345", ",100",
     "--5", "$5", "5.00.", "1,000,00"],
)
def test_parse_money_invalid(text):
    with pytest.raises(ValueError):
        parse_money(text)


# --- convert ---------------------------------------------------------------------------------

def test_convert_rounds_half_up_not_float_style():
    assert cents(convert(D("2.675"), D("1"))) == D("2.68")
    assert cents(convert(D("0.005"), D("1"))) == D("0.01")
    assert cents(convert(D("1.005"), D("1"))) == D("1.01")


def test_convert_not_bankers_rounding():
    assert convert(D("0.125"), D("1")) == D("0.13")  # банківське дало б 0.12
    assert convert(D("0.135"), D("1")) == D("0.14")


@pytest.mark.parametrize(
    "amount, rate, expected",
    [
        ("100.00", "41.2345", "4123.45"),
        ("19.99", "0.9231", "18.45"),   # 18.451...
        ("10.00", "0.333333", "3.33"),
        ("0.01", "0.5", "0.01"),         # 0.005 -> 0.01
        ("0.00", "41.5", "0.00"),
        ("-2.675", "1", "-2.68"),        # симетрично від нуля
    ],
)
def test_convert_values(amount, rate, expected):
    assert cents(convert(D(amount), D(rate))) == D(expected)


# --- add_vat ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "net, rate, vat, gross",
    [
        ("100.00", "20", "20.00", "120.00"),
        ("19.99", "20", "4.00", "23.99"),    # 3.998
        ("0.99", "7", "0.07", "1.06"),       # 0.0693
        ("10.50", "5", "0.53", "11.03"),     # 0.525 -> 0.53
        ("33.33", "0", "0.00", "33.33"),
        ("1234.56", "19", "234.57", "1469.13"),  # 234.5664
    ],
)
def test_add_vat(net, rate, vat, gross):
    v, g = add_vat(D(net), D(rate))
    assert cents(v) == D(vat)
    assert cents(g) == D(gross)
    assert v + D(net) == g


def test_add_vat_gross_is_exact_sum_not_rounded_again():
    v, g = add_vat(D("10.00"), D("12.5"))
    assert (v, g) == (D("1.25"), D("11.25"))


# --- allocate --------------------------------------------------------------------------------

def test_allocate_three_equal_parts_gives_extra_cent_to_first():
    parts = allocate(D("100.00"), [1, 1, 1])
    assert [cents(p) for p in parts] == [D("33.34"), D("33.33"), D("33.33")]


def test_allocate_exact_division():
    assert allocate(D("90.00"), [1, 1, 1]) == [D("30.00")] * 3


def test_allocate_by_weights():
    parts = allocate(D("10.00"), [70, 20, 10])
    assert parts == [D("7.00"), D("2.00"), D("1.00")]
    assert all(p.as_tuple().exponent == -2 for p in parts)


def test_allocate_largest_remainder():
    # 0.10 по вагах 1:1:1 -> 3,3,3 + 1 копійка першій; 1.00 по 5:3:2 точно
    assert allocate(D("0.10"), [1, 1, 1]) == [D("0.04"), D("0.03"), D("0.03")]
    # 0.05 по 3:1:1 -> 3,1,1 точно; 0.07 по 3:1:1: 4.2, 1.4, 1.4 -> 4,1,1 + 1 копійка найбільшому залишку (0.4, 0.4 -> перший з рівних)
    assert allocate(D("0.07"), [3, 1, 1]) == [D("0.04"), D("0.02"), D("0.01")]


def test_allocate_remainder_goes_to_biggest_fraction_not_biggest_weight():
    # 1.00 за вагами 1,1,98: 1,1,98 точно. А 0.02 за вагами 49,49,2: 0.98,0.98,0.04 -> 0,0,0 + 2 копійки
    # найбільші залишки: 0.98, 0.98, 0.04 -> отримують перші дві
    assert allocate(D("0.02"), [49, 49, 2]) == [D("0.01"), D("0.01"), D("0.00")]


def test_allocate_zero_weights_get_zero():
    assert allocate(D("10.00"), [0, 1, 0, 1]) == [D("0.00"), D("5.00"), D("0.00"), D("5.00")]


def test_allocate_zero_total():
    assert allocate(D("0.00"), [1, 2]) == [D("0.00"), D("0.00")]


def test_allocate_single_part():
    assert allocate(D("12.34"), [5]) == [D("12.34")]


@pytest.mark.parametrize(
    "total, weights",
    [(D("-1.00"), [1]), (D("10.00"), []), (D("10.00"), [0, 0]), (D("10.00"), [1, -1, 2])],
)
def test_allocate_invalid(total, weights):
    with pytest.raises(ValueError):
        allocate(total, weights)


def test_allocate_property_sum_is_always_exact():
    rng = random.Random(2024)
    for _ in range(300):
        total = D(rng.randint(0, 10_000_000)).scaleb(-2)
        weights = [rng.randint(0, 50) for _ in range(rng.randint(1, 8))]
        if sum(weights) == 0:
            weights[0] = 1
        parts = allocate(total, weights)
        assert len(parts) == len(weights)
        assert sum(parts) == total
        assert all(p >= 0 and p.as_tuple().exponent == -2 for p in parts)
        whole = sum(weights)
        for p, w in zip(parts, weights):
            ideal = total * w / whole
            assert abs(p - ideal) < D("0.01")  # відхилення менше однієї копійки


def test_allocate_is_deterministic_and_does_not_mutate_weights():
    weights = [3, 1, 2]
    a = allocate(D("10.00"), weights)
    b = allocate(D("10.00"), weights)
    assert a == b and weights == [3, 1, 2]
