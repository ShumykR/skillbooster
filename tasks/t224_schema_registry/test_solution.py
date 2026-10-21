import pytest

from solution import IncompatibleSchemaError, SchemaRegistry, UpcastError


def F(type_, required=True, **kw):
    return {"type": type_, "required": required, **kw}


def S(**fields):
    return {"fields": fields}


BASE = S(id=F("string"), amount=F("int"), note=F("string", False))


def reg(mode="backward", base=BASE, subject="orders"):
    r = SchemaRegistry()
    r.set_mode(subject, mode)
    assert r.register(subject, base) == 1
    return r


def reasons(mode, new, base=BASE):
    return reg(mode, base).check("orders", new)


# --- реєстр: версії, копії, ідемпотентність ----------------------------------------------------

def test_versions_are_numbered_and_retrievable():
    r = SchemaRegistry()
    assert r.register("s", S(a=F("int"))) == 1
    assert r.register("s", S(a=F("int"), b=F("int", False))) == 2
    assert r.get("s", 1) == S(a=F("int"))
    assert r.latest("s") == (2, S(a=F("int"), b=F("int", False)))


def test_registering_the_latest_again_is_idempotent():
    r = SchemaRegistry()
    r.register("s", S(a=F("int")))
    assert r.register("s", S(a=F("int"))) == 1
    assert r.latest("s")[0] == 1


def test_older_schema_registered_again_is_a_new_version_if_compatible():
    r = SchemaRegistry()
    r.set_mode("s", "none")
    r.register("s", S(a=F("int")))
    r.register("s", S(a=F("string")))
    assert r.register("s", S(a=F("int"))) == 3


def test_subjects_are_independent():
    r = SchemaRegistry()
    r.register("a", S(x=F("int")))
    assert r.register("b", S(y=F("string"))) == 1
    with pytest.raises(KeyError):
        r.latest("c")


@pytest.mark.parametrize("subject, version", [("nope", 1), ("orders", 0), ("orders", 2), ("orders", -1)])
def test_get_unknown(subject, version):
    with pytest.raises(KeyError):
        reg().get(subject, version)


def test_stored_schema_is_isolated_from_callers():
    r = SchemaRegistry()
    schema = S(a=F("int"))
    r.register("s", schema)
    schema["fields"]["a"]["type"] = "string"
    schema["fields"]["extra"] = F("int")
    got = r.get("s", 1)
    assert got == S(a=F("int"))
    got["fields"]["a"]["type"] = "bool"
    assert r.get("s", 1) == S(a=F("int"))
    r.latest("s")[1]["fields"].clear()
    assert r.get("s", 1) == S(a=F("int"))


@pytest.mark.parametrize("bad", [
    None, {}, {"fields": []}, {"fields": {"a": {}}}, {"fields": {"a": {"type": "decimal"}}},
    {"fields": {"a": {"type": "int", "required": "yes"}}}, {"fields": {"a": {"type": "int", "default": "x"}}},
    {"fields": {"a": {"type": "int", "default": True}}}, {"fields": {"": {"type": "int"}}}, {"fields": {"a": "int"}},
])
def test_invalid_schemas(bad):
    r = SchemaRegistry()
    with pytest.raises(ValueError):
        r.register("s", bad)
    with pytest.raises(ValueError):
        r.check("s", bad)


def test_invalid_modes():
    with pytest.raises(ValueError):
        SchemaRegistry("strict")
    with pytest.raises(ValueError):
        SchemaRegistry().set_mode("s", "transitive")


def test_default_mode_is_backward_and_set_mode_overrides_per_subject():
    r = SchemaRegistry()
    r.register("a", S(x=F("int")))
    with pytest.raises(IncompatibleSchemaError):
        r.register("a", S(x=F("int"), y=F("int")))
    r.set_mode("b", "none")
    r.register("b", S(x=F("int")))
    assert r.register("b", S(y=F("int"))) == 2


def test_default_mode_argument():
    r = SchemaRegistry(default_mode="none")
    r.register("a", S(x=F("int")))
    assert r.register("a", S(y=F("string"))) == 2


# --- BACKWARD -----------------------------------------------------------------------------------

def test_backward_allows_optional_and_defaulted_additions_and_removals():
    new = S(id=F("string"), amount=F("int"), currency=F("string", True, default="EUR"), tag=F("string", False))
    assert reasons("backward", new) == []
    assert reasons("backward", S(id=F("string"))) == []  # видалення поля, у тому числі обовʼязкового


def test_backward_rejects_added_required_field():
    new = S(id=F("string"), amount=F("int"), currency=F("string"))
    assert reasons("backward", new) == [("added-required-field", "currency")]


def test_backward_type_change_and_widening():
    assert reasons("backward", S(id=F("int"), amount=F("int"))) == [("type-changed", "id")]
    assert reasons("backward", S(id=F("string"), amount=F("float"))) == []  # int -> float дозволено
    assert reasons("backward", S(id=F("string"), amount=F("string"))) == [("type-changed", "amount")]
    base = S(price=F("float"))
    assert reasons("backward", S(price=F("int")), base) == [("type-changed", "price")]  # float -> int ні


def test_backward_became_required():
    new = S(id=F("string"), amount=F("int"), note=F("string"))
    assert reasons("backward", new) == [("became-required", "note")]
    new = S(id=F("string"), amount=F("int"), note=F("string", True, default=""))
    assert reasons("backward", new) == []


def test_backward_default_makes_a_required_field_tolerant():
    base = S(a=F("int", True, default=0))
    assert reasons("backward", S(a=F("int", True, default=0), b=F("int", True, default=1)), base) == []


def test_register_raises_with_reasons_and_does_not_register():
    r = reg("backward")
    bad = S(id=F("int"), amount=F("int"), extra=F("string"))
    with pytest.raises(IncompatibleSchemaError) as e:
        r.register("orders", bad)
    assert e.value.reasons == [("added-required-field", "extra"), ("type-changed", "id")]
    assert r.latest("orders")[0] == 1


# --- FORWARD ------------------------------------------------------------------------------------

def test_forward_rejects_removing_a_required_field():
    assert reasons("forward", S(id=F("string"))) == [("removed-required-field", "amount")]
    assert reasons("forward", S(id=F("string"), amount=F("int"))) == []  # note був необовʼязковий


def test_forward_removing_a_defaulted_field_is_fine():
    base = S(a=F("int"), b=F("string", True, default="x"))
    assert reasons("forward", S(a=F("int")), base) == []


def test_forward_allows_new_fields_of_any_kind():
    new = S(id=F("string"), amount=F("int"), note=F("string", False), brand_new=F("string"))
    assert reasons("forward", new) == []


def test_forward_types():
    assert reasons("forward", S(id=F("string"), amount=F("string"))) == [("type-changed", "amount")]
    base = S(price=F("float"))
    assert reasons("forward", S(price=F("int")), base) == []  # старий читач (float) приймає ціле
    assert reasons("forward", S(price=F("float")), S(price=F("int"))) == [("type-changed", "price")]


def test_forward_became_optional():
    new = S(id=F("string"), amount=F("int", False), note=F("string", False))
    assert reasons("forward", new) == [("became-optional", "amount")]
    assert reasons("forward", S(id=F("string"), amount=F("int"), note=F("string"))) == []


# --- FULL, NONE --------------------------------------------------------------------------------

def test_full_is_the_union_without_duplicates():
    new = S(id=F("int"), extra=F("string"))
    assert reasons("full", new) == [
        ("removed-required-field", "amount"), ("added-required-field", "extra"), ("type-changed", "id"),
    ]


def test_full_accepts_only_safe_changes():
    assert reasons("full", S(id=F("string"), amount=F("int"), note=F("string", False), tag=F("string", False))) == []
    assert reasons("full", S(id=F("string"), amount=F("int"), note=F("string", False), t=F("int", True, default=0))) == []


def test_none_accepts_everything_and_check_is_empty():
    r = reg("none")
    weird = S(totally=F("dict"))
    assert r.check("orders", weird) == []
    assert r.register("orders", weird) == 2


def test_check_does_not_register_and_first_version_is_always_fine():
    r = SchemaRegistry()
    assert r.check("s", S(a=F("int"))) == []
    with pytest.raises(KeyError):
        r.latest("s")
    r.register("s", S(a=F("int")))
    r.check("s", S(a=F("string")))
    assert r.latest("s")[0] == 1


def test_compatibility_is_checked_against_the_latest_version_only():
    r = SchemaRegistry()
    r.register("s", S(a=F("int")))
    r.register("s", S(a=F("float")))  # int -> float
    with pytest.raises(IncompatibleSchemaError):
        r.register("s", S(a=F("int")))  # float -> int


# --- upcasting ---------------------------------------------------------------------------------

def registry_with_history():
    r = SchemaRegistry()
    r.register("user", S(name=F("string")))
    r.register("user", S(name=F("string"), email=F("string", True, default="unknown@example.com")))
    r.register("user", S(name=F("string"), email=F("string", True, default="unknown@example.com"), tags=F("list", False)))
    return r


def test_auto_upcast_fills_defaults_through_several_versions():
    r = registry_with_history()
    assert r.upcast("user", 1, {"name": "Ann"}) == {"name": "Ann", "email": "unknown@example.com"}
    assert r.upcast("user", 2, {"name": "Bob", "email": "b@x"}) == {"name": "Bob", "email": "b@x"}
    assert r.upcast("user", 3, {"name": "C", "email": "c@x", "tags": ["x"]}) == {"name": "C", "email": "c@x", "tags": ["x"]}


def test_upcast_to_intermediate_version():
    r = registry_with_history()
    assert r.upcast("user", 1, {"name": "Ann"}, to_version=2) == {"name": "Ann", "email": "unknown@example.com"}
    assert r.upcast("user", 1, {"name": "Ann"}, to_version=1) == {"name": "Ann"}


def test_upcast_does_not_mutate_input_and_returns_a_copy():
    r = registry_with_history()
    data = {"name": "Ann", "tags": []}
    r2 = SchemaRegistry()
    r2.register("t", S(name=F("string"), tags=F("list", False)))
    out = r2.upcast("t", 1, data)
    out["tags"].append("x")
    assert data == {"name": "Ann", "tags": []}
    old = {"name": "Ann"}
    r.upcast("user", 1, old)
    assert old == {"name": "Ann"}


def test_default_values_are_copied_not_shared():
    r = SchemaRegistry()
    r.register("s", S(a=F("int")))
    r.register("s", S(a=F("int"), items=F("list", True, default=[])))
    one = r.upcast("s", 1, {"a": 1})
    one["items"].append("leak")
    assert r.upcast("s", 1, {"a": 2})["items"] == []
    assert r.get("s", 2)["fields"]["items"]["default"] == []


def test_auto_step_drops_fields_removed_from_the_schema():
    r = SchemaRegistry()
    r.register("s", S(a=F("int"), legacy=F("string", False)))
    r.register("s", S(a=F("int")))
    assert r.upcast("s", 1, {"a": 1, "legacy": "x"}) == {"a": 1}


def test_custom_upcaster_is_used_and_chained():
    r = SchemaRegistry()
    r.register("p", S(full_name=F("string")))
    r.set_mode("p", "none")
    r.register("p", S(first=F("string"), last=F("string")))
    r.register("p", S(first=F("string"), last=F("string"), initials=F("string", True, default="?")))

    calls = []

    def split(d):
        calls.append(dict(d))
        first, _, last = d["full_name"].partition(" ")
        return {"first": first, "last": last}

    r.register_upcaster("p", 1, split)
    out = r.upcast("p", 1, {"full_name": "Ada Lovelace"})
    assert out == {"first": "Ada", "last": "Lovelace", "initials": "?"}
    assert calls == [{"full_name": "Ada Lovelace"}]


def test_custom_upcaster_receives_a_copy_and_can_mutate_it():
    r = SchemaRegistry()
    r.set_mode("p", "none")
    r.register("p", S(a=F("int")))
    r.register("p", S(b=F("int")))

    def convert(d):
        d["b"] = d.pop("a") * 2
        return d

    r.register_upcaster("p", 1, convert)
    data = {"a": 21}
    assert r.upcast("p", 1, data) == {"b": 42}
    assert data == {"a": 21}


def test_custom_upcaster_result_is_validated():
    r = SchemaRegistry()
    r.set_mode("p", "none")
    r.register("p", S(a=F("int")))
    r.register("p", S(b=F("int")))
    r.register_upcaster("p", 1, lambda d: {"b": "not-an-int"})
    with pytest.raises(UpcastError):
        r.upcast("p", 1, {"a": 1})
    r.register_upcaster("p", 1, lambda d: {"b": 1, "stray": 2})
    with pytest.raises(UpcastError):
        r.upcast("p", 1, {"a": 1})
    r.register_upcaster("p", 1, lambda d: {})
    with pytest.raises(UpcastError):
        r.upcast("p", 1, {"a": 1})


def test_missing_required_without_default_cannot_be_auto_upcast():
    r = SchemaRegistry()
    r.set_mode("p", "none")
    r.register("p", S(a=F("int")))
    r.register("p", S(a=F("int"), b=F("string")))
    with pytest.raises(UpcastError):
        r.upcast("p", 1, {"a": 1})


@pytest.mark.parametrize("data", [
    {}, {"name": 5}, {"name": None}, {"name": "x", "extra": 1}, {"name": True},
])
def test_input_is_validated_against_its_own_version(data):
    with pytest.raises(UpcastError):
        registry_with_history().upcast("user", 1, data)


def test_type_checks_in_upcast():
    r = SchemaRegistry()
    r.register("t", S(i=F("int", False), f=F("float", False), b=F("bool", False), s=F("string", False),
                      l=F("list", False), d=F("dict", False)))
    ok = {"i": 1, "f": 2, "b": True, "s": "x", "l": [], "d": {}}
    assert r.upcast("t", 1, ok) == ok
    assert r.upcast("t", 1, {"f": 2.5, "i": None}) == {"f": 2.5, "i": None}
    for bad in ({"i": True}, {"i": 1.5}, {"f": True}, {"b": 1}, {"s": 1}, {"l": ()}, {"d": []}):
        with pytest.raises(UpcastError):
            r.upcast("t", 1, bad)


def test_upcast_argument_errors():
    r = registry_with_history()
    with pytest.raises(KeyError):
        r.upcast("nope", 1, {})
    with pytest.raises(KeyError):
        r.upcast("user", 9, {})
    with pytest.raises(ValueError):
        r.upcast("user", 3, {"name": "x", "email": "e"}, to_version=1)
    with pytest.raises(KeyError):
        r.upcast("user", 1, {"name": "x"}, to_version=9)


def test_register_upcaster_requires_existing_versions():
    r = registry_with_history()
    for v in (0, 3, 4, -1):
        with pytest.raises(ValueError):
            r.register_upcaster("user", v, lambda d: d)
    with pytest.raises(ValueError):
        r.register_upcaster("nope", 1, lambda d: d)
    r.register_upcaster("user", 1, lambda d: {**d, "email": "custom"})
    assert r.upcast("user", 1, {"name": "A"})["email"] == "custom"
    r.register_upcaster("user", 1, lambda d: {**d, "email": "second"})
    assert r.upcast("user", 1, {"name": "A"})["email"] == "second"
