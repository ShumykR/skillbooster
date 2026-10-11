import pytest

from solution import Registered, UnknownKey


def make_family():
    class Exporter(Registered):
        def __init__(self, sep=","):
            self.sep = sep

    class Csv(Exporter, key="csv"):
        pass

    class Json(Exporter, key="json"):
        pass

    return Exporter, Csv, Json


def test_registration_and_create():
    Exporter, Csv, Json = make_family()
    obj = Exporter.create("csv", sep=";")
    assert type(obj) is Csv and obj.sep == ";"
    assert type(Exporter.create("json")) is Json


def test_get_and_keys():
    Exporter, Csv, Json = make_family()
    assert Exporter.get("csv") is Csv
    assert Exporter.keys() == ["csv", "json"]


def test_keys_are_sorted_regardless_of_definition_order():
    class Root(Registered):
        pass

    for k in ["zeta", "alpha", "mid"]:
        type(k, (Root,), {}, key=k)
    assert Root.keys() == ["alpha", "mid", "zeta"]


def test_registry_belongs_to_the_root_only():
    class Root(Registered):
        pass

    class A(Root, key="a"):
        pass

    assert Root.keys() == ["a"]


def test_unknown_key_message_lists_available_keys():
    Exporter, *_ = make_family()
    with pytest.raises(UnknownKey) as info:
        Exporter.create("xml")
    assert issubclass(UnknownKey, KeyError)
    text = str(info.value)
    assert "csv" in text and "json" in text and "xml" in text
    with pytest.raises(UnknownKey):
        Exporter.get("nope")


def test_unknown_key_in_empty_registry():
    class Root(Registered):
        pass

    with pytest.raises(UnknownKey):
        Root.create("x")
    assert Root.keys() == []


def test_class_without_key_is_not_registered_but_children_can_be():
    class Root(Registered):
        pass

    class Base(Root):  # абстрактна ланка
        pass

    class Leaf(Base, key="leaf"):
        pass

    assert Root.keys() == ["leaf"]
    assert Root.get("leaf") is Leaf


def test_deep_descendants_register_in_the_root_registry():
    Exporter, Csv, Json = make_family()

    class FancyCsv(Csv, key="fancy"):
        pass

    assert Exporter.get("fancy") is FancyCsv
    assert Exporter.keys() == ["csv", "fancy", "json"]


def test_create_and_get_work_from_any_subclass():
    Exporter, Csv, Json = make_family()
    assert Csv.get("json") is Json
    assert type(Csv.create("json")) is Json
    assert Json.keys() == ["csv", "json"]


def test_different_roots_have_independent_registries():
    class Exporter(Registered):
        pass

    class Importer(Registered):
        pass

    class CsvOut(Exporter, key="csv"):
        pass

    class CsvIn(Importer, key="csv"):  # той самий ключ в іншому корені: це дозволено
        pass

    assert Exporter.get("csv") is CsvOut
    assert Importer.get("csv") is CsvIn
    assert Exporter.keys() == ["csv"] and Importer.keys() == ["csv"]


def test_registries_do_not_leak_between_calls_of_the_same_factory():
    a = make_family()[0]
    b = make_family()[0]
    assert a is not b
    assert a.get("csv") is not b.get("csv")


def test_duplicate_key_is_rejected_and_registry_unchanged():
    Exporter, Csv, Json = make_family()
    with pytest.raises(ValueError):
        class Other(Exporter, key="csv"):
            pass
    assert Exporter.get("csv") is Csv
    assert Exporter.keys() == ["csv", "json"]


def test_duplicate_key_in_a_branch_is_also_rejected():
    Exporter, Csv, Json = make_family()
    with pytest.raises(ValueError):
        class Again(Csv, key="json"):
            pass


@pytest.mark.parametrize("bad", ["", 5, b"csv", ("csv",), True])
def test_bad_keys_are_type_errors(bad):
    class Root(Registered):
        pass

    with pytest.raises(TypeError):
        class X(Root, key=bad):
            pass

    assert Root.keys() == []


def test_extra_class_keywords_reach_super():
    seen = {}

    class Mixin:
        def __init_subclass__(cls, *, color=None, **kwargs):
            super().__init_subclass__(**kwargs)
            seen[cls.__name__] = color

    class Root(Registered, Mixin):
        pass

    class A(Root, key="a", color="red"):
        pass

    assert seen["A"] == "red"
    assert Root.get("a") is A


def test_unexpected_class_keywords_still_fail_like_normal_python():
    class Root(Registered):
        pass

    with pytest.raises(TypeError):
        class A(Root, key="a", nonsense=1):
            pass


def test_create_passes_positional_and_keyword_arguments():
    class Root(Registered):
        def __init__(self, a, b=2, *, c=3):
            self.args = (a, b, c)

    class A(Root, key="a"):
        pass

    assert A.create("a", 1).args == (1, 2, 3)
    assert Root.create("a", 1, 5, c=9).args == (1, 5, 9)


def test_constructor_errors_are_not_swallowed():
    class Root(Registered):
        def __init__(self):
            raise RuntimeError("init failed")

    class A(Root, key="a"):
        pass

    with pytest.raises(RuntimeError):
        Root.create("a")


def test_keys_returns_a_copy():
    Exporter, *_ = make_family()
    Exporter.keys().append("hack")
    assert Exporter.keys() == ["csv", "json"]


def test_non_string_lookup_is_unknown_key():
    Exporter, *_ = make_family()
    for bad in (None, 5, ["csv"]):
        with pytest.raises(UnknownKey):
            Exporter.get(bad)
