import collections
import hashlib
import hmac
import importlib
import json
import os
import pickle
import struct

import pytest

import solution as sol
from solution import (DEFAULT_ALLOW, check_safetensors, choose_model_file, is_safe, scan_pickle, verify_hash)


# --- допоміжне: ми ЛИШЕ створюємо байти (pickle.dumps), pickle.loads у цих тестах не викликається ------------

class EvilSystem:
    def __reduce__(self):
        return (os.system, ("echo pwned",))


class EvilEval:
    def __reduce__(self):
        return (eval, ("1+1",))


SAFE_OBJECT = {"a": [1, 2.5, (3, None)], "s": {1, 2}, "f": frozenset({1, 2}), "b": b"xyz", "ok": True,
               "o": collections.OrderedDict(x=1), "text": "Привіт", "big": 2 ** 80, "ba": bytearray(b"ab")}


def rules(findings):
    return [f["rule"] for f in findings]


def raw(*parts):
    return b"".join(parts)


# --- scan_pickle: безпечні дані ----------------------------------------------------------------

@pytest.mark.parametrize("protocol", range(0, 6))
def test_plain_data_is_safe_for_every_protocol(protocol):
    data = pickle.dumps(SAFE_OBJECT, protocol=protocol)
    assert scan_pickle(data) == []
    assert is_safe(data) is True


def test_memo_is_not_tracked_so_second_global_of_same_module_is_unresolved_in_protocol_4():
    # у протоколі 4 другий `builtins` береться з memo (BINGET): за умовою це unresolved-global, fail closed
    data = pickle.dumps({"ba": bytearray(b"ab"), "c": 1 + 2j}, protocol=4)
    assert rules(scan_pickle(data)) == ["unresolved-global"]
    assert scan_pickle(pickle.dumps({"ba": bytearray(b"ab")}, protocol=4)) == []


# --- scan_pickle: небезпечні глобали -----------------------------------------------------------

@pytest.mark.parametrize("protocol", range(0, 6))
def test_os_system_is_dangerous_for_every_protocol(protocol):
    findings = scan_pickle(pickle.dumps(EvilSystem(), protocol=protocol))
    assert rules(findings) == ["dangerous-global"]
    assert findings[0]["module"] in ("posix", "nt") and findings[0]["name"] == "system"
    assert is_safe(pickle.dumps(EvilSystem(), protocol=protocol)) is False


@pytest.mark.parametrize("protocol", range(0, 6))
def test_builtin_eval_is_dangerous_and_builtin_alias_is_normalized(protocol):
    findings = scan_pickle(pickle.dumps(EvilEval(), protocol=protocol))
    assert [(f["rule"], f["module"], f["name"]) for f in findings] == [("dangerous-global", "builtins", "eval")]


def test_global_opcode_exact_findings_and_positions():
    data = raw(b"cos\nsystem\n", b"(S'echo'\ntR.")
    assert scan_pickle(data) == [{"rule": "dangerous-global", "module": "os", "name": "system", "pos": 0}]
    data2 = raw(b"\x80\x02", b"c__builtin__\neval\n", b"q\x00", b".")
    assert scan_pickle(data2) == [{"rule": "dangerous-global", "module": "builtins", "name": "eval", "pos": 2}]


def test_inst_opcode_is_scanned():
    data = raw(b"(", b"ios\nsystem\n", b".")
    assert scan_pickle(data) == [{"rule": "dangerous-global", "module": "os", "name": "system", "pos": 1}]


def test_submodule_of_denied_module_is_dangerous():
    findings = scan_pickle(b"cos.path\njoin\n.")
    assert [(f["rule"], f["module"], f["name"]) for f in findings] == [("dangerous-global", "os.path", "join")]
    assert rules(scan_pickle(b"csubprocess\nPopen\n.")) == ["dangerous-global"]
    assert rules(scan_pickle(b"cmultiprocessing.pool\nPool\n.")) == ["dangerous-global"]


def test_prefix_lookalike_module_is_not_dangerous_but_unlisted():
    assert rules(scan_pickle(b"cosmos\nthing\n.")) == ["unlisted-global"]
    assert rules(scan_pickle(b"csystem_tools\nrun\n.")) == ["unlisted-global"]


@pytest.mark.parametrize("name", ["exec", "compile", "__import__", "open", "getattr", "setattr", "globals", "breakpoint"])
def test_dangerous_builtins(name):
    assert rules(scan_pickle(f"cbuiltins\n{name}\n.".encode())) == ["dangerous-global"]


def test_other_builtins_are_only_unlisted_and_allowlisted_ones_are_fine():
    assert rules(scan_pickle(b"cbuiltins\nprint\n.")) == ["unlisted-global"]
    assert scan_pickle(b"cbuiltins\nset\n.") == []
    assert scan_pickle(b"c__builtin__\nfrozenset\n.") == []
    assert scan_pickle(b"ccollections\nOrderedDict\n.") == []
    assert scan_pickle(b"c_codecs\nencode\n.") == []


def test_copy_reg_alias_is_normalized():
    findings = scan_pickle(b"ccopy_reg\n_reconstructor\n.")
    assert [(f["rule"], f["module"], f["name"]) for f in findings] == [("unlisted-global", "copyreg", "_reconstructor")]


def test_allowlist_parameter_replaces_default_and_denied_wins():
    numpy_ref = b"cnumpy.core.multiarray\n_reconstruct\n."
    assert rules(scan_pickle(numpy_ref)) == ["unlisted-global"]
    assert scan_pickle(numpy_ref, allow={("numpy.core.multiarray", "_reconstruct")}) == []
    assert scan_pickle(numpy_ref, allow=set()) == scan_pickle(numpy_ref)
    # allow замінює DEFAULT_ALLOW, а не доповнює
    assert rules(scan_pickle(b"cbuiltins\nset\n.", allow={("x", "y")})) == ["unlisted-global"]
    assert rules(scan_pickle(b"cos\nsystem\n.", allow={("os", "system")})) == ["dangerous-global"]
    assert ("builtins", "set") in DEFAULT_ALLOW


# --- STACK_GLOBAL, memo, EXT -------------------------------------------------------------------

def stack_global(mod, name, memo=True, proto=True):
    m = b"\x94" if memo else b""
    head = b"\x80\x04" if proto else b""
    return raw(head, b"\x8c", bytes([len(mod)]), mod.encode(), m, b"\x8c", bytes([len(name)]), name.encode(), m,
               b"\x93", m, b".")


def test_stack_global_with_memoize_between_strings_is_resolved():
    findings = scan_pickle(stack_global("os", "system"))
    assert findings == [{"rule": "dangerous-global", "module": "os", "name": "system", "pos": 2 + 4 + 1 + 9 + 1}] or \
        [(f["rule"], f["module"], f["name"]) for f in findings] == [("dangerous-global", "os", "system")]
    assert [(f["rule"], f["module"], f["name"]) for f in scan_pickle(stack_global("os", "system", memo=False))] == [
        ("dangerous-global", "os", "system")]


def test_stack_global_position_is_the_opcode_position():
    data = stack_global("os", "system", memo=False)
    assert data.index(b"\x93") == scan_pickle(data)[0]["pos"]


def test_stack_global_with_binput_memo_variants():
    data = raw(b"\x80\x03", b"X\x02\x00\x00\x00os", b"q\x00", b"X\x06\x00\x00\x00system", b"r\x01\x00\x00\x00", b"\x93.")
    assert [(f["rule"], f["module"], f["name"]) for f in scan_pickle(data)] == [("dangerous-global", "os", "system")]


def test_stack_global_unresolved_when_operands_come_from_memo_get():
    data = raw(b"\x80\x04", b"\x8c\x02os", b"\x94", b"h\x00", b"\x93", b".")
    findings = scan_pickle(data)
    assert findings == [{"rule": "unresolved-global", "module": None, "name": None, "pos": data.index(b"\x93")}]


def test_stack_global_with_too_few_strings_is_unresolved():
    assert rules(scan_pickle(raw(b"\x80\x04", b"\x8c\x02os", b"\x93."))) == ["unresolved-global"]
    assert rules(scan_pickle(raw(b"\x80\x04", b"N", b"\x93."))) == ["unresolved-global"]


@pytest.mark.parametrize("data", [b"\x82\x01.", b"\x83\x01\x00.", b"\x84\x01\x00\x00\x00."])
def test_extension_registry_opcodes_are_unresolved(data):
    assert [(f["rule"], f["module"], f["name"]) for f in scan_pickle(data)] == [("unresolved-global", None, None)]


def test_multiple_findings_sorted_by_position():
    data = raw(b"(cbuiltins\nprint\n", b"cos\nsystem\n", b"\x82\x01", b".")
    found = scan_pickle(data)
    assert [f["pos"] for f in found] == sorted(f["pos"] for f in found)
    assert rules(found) == ["unlisted-global", "dangerous-global", "unresolved-global"]


# --- trailing-data / malformed -----------------------------------------------------------------

def test_trailing_data_after_stop():
    good = pickle.dumps({"a": 1})
    findings = scan_pickle(good + b"cos\nsystem\n.")
    assert findings == [{"rule": "trailing-data", "module": None, "name": None, "pos": len(good)}]
    assert is_safe(good + b"x") is False


@pytest.mark.parametrize("data", [b"", b"garbage", b"\x80\x04", pickle.dumps([1, 2, 3])[:-1], b"\xff\xff\xff", b"N",
                                  pickle.dumps({"k": "v"})[:10]])
def test_malformed_pickles_give_exactly_one_malformed_finding(data):
    assert scan_pickle(data) == [{"rule": "malformed", "module": None, "name": None, "pos": -1}]
    assert is_safe(data) is False


def test_malformed_after_findings_still_gives_exactly_one_record():
    data = b"cos\nsystem\n" + b"\xff"
    assert scan_pickle(data) == [{"rule": "malformed", "module": None, "name": None, "pos": -1}]


def test_scan_never_executes_the_payload(monkeypatch):
    called = []
    monkeypatch.setattr(pickle, "loads", lambda *a, **k: called.append("loads"))
    monkeypatch.setattr(pickle, "load", lambda *a, **k: called.append("load"))
    scan_pickle(pickle.dumps(EvilSystem()))
    is_safe(pickle.dumps(SAFE_OBJECT))
    assert called == []


# --- verify_hash -------------------------------------------------------------------------------

def test_verify_hash_accepts_case_and_whitespace():
    data = b"model-bytes"
    h = hashlib.sha256(data).hexdigest()
    assert verify_hash(data, h) is True
    assert verify_hash(data, h.upper()) is True
    assert verify_hash(data, f"  {h}\n") is True
    assert verify_hash(b"", hashlib.sha256(b"").hexdigest()) is True


@pytest.mark.parametrize("bad", [None, 5, b"abc", "", "abc", "g" * 64, "0" * 63, "0" * 65, ["x"], "é" * 64])
def test_verify_hash_garbage_is_false_without_exceptions(bad):
    assert verify_hash(b"data", bad) is False


def test_verify_hash_wrong_hash_is_false():
    assert verify_hash(b"data", hashlib.sha256(b"other").hexdigest()) is False


def test_verify_hash_uses_constant_time_compare(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    importlib.reload(sol)
    try:
        assert sol.verify_hash(b"x", hashlib.sha256(b"x").hexdigest()) is True
        assert calls
    finally:
        monkeypatch.undo()
        importlib.reload(sol)


# --- check_safetensors -------------------------------------------------------------------------

def build_st(tensors, metadata=None, extra=None):
    """tensors: {name: (dtype, shape, payload bytes)}; розкладає тензори суцільно за порядком вставки."""
    header = {}
    buf = b""
    for name, (dtype, shape, payload) in tensors.items():
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [len(buf), len(buf) + len(payload)]}
        buf += payload
    if metadata is not None:
        header["__metadata__"] = metadata
    if extra:
        header.update(extra)
    h = json.dumps(header).encode()
    return struct.pack("<Q", len(h)) + h + buf


def st_raw(header_obj, buf=b"", header_bytes=None):
    h = header_bytes if header_bytes is not None else json.dumps(header_obj).encode()
    return struct.pack("<Q", len(h)) + h + buf


GOOD = build_st({"w": ("F32", [2, 2], b"\x00" * 16), "b": ("F16", [3], b"\x00" * 6)}, {"format": "pt"})


def test_valid_safetensors_variants_are_ok():
    assert check_safetensors(GOOD) is None
    assert check_safetensors(st_raw({})) is None                                               # без тензорів
    assert check_safetensors(build_st({"s": ("I8", [], b"\x01")})) is None                      # скаляр: 1 елемент
    assert check_safetensors(build_st({"z": ("F32", [0, 5], b"")})) is None                     # порожній тензор
    assert check_safetensors(build_st({"a": ("F32", [], b"\x00" * 4), "z1": ("U8", [0], b""),
                                       "z2": ("U8", [0], b"")})) is None
    assert check_safetensors(build_st({"t": ("BOOL", [4], b"\x00" * 4), "u": ("BF16", [2], b"\x00" * 4)}, {})) is None
    assert check_safetensors(st_raw({}, header_bytes=b" {} ")) is None


@pytest.mark.parametrize("data", [b"", b"\x00" * 7])
def test_too_short(data):
    assert check_safetensors(data) == "too-short"


def test_header_size():
    assert check_safetensors(struct.pack("<Q", 10_000_001) + b"x" * 100) == "header-size"
    assert check_safetensors(struct.pack("<Q", 50) + b"{}") == "header-size"
    assert check_safetensors(struct.pack("<Q", 2 ** 63) + b"{}") == "header-size"
    assert check_safetensors(struct.pack("<Q", 2) + b"{}") is None                              # рівно до кінця


def test_header_size_limit_is_ten_million_even_when_the_file_is_long_enough():
    limit = 10_000_000
    assert check_safetensors(st_raw(None, header_bytes=b"{}" + b" " * (limit - 2))) is None
    assert check_safetensors(st_raw(None, header_bytes=b"{}" + b" " * (limit - 1))) == "header-size"


@pytest.mark.parametrize("header_bytes", [b"\xff\xfe\xfa", b"not json", b"[1, 2]", b'"str"', b"null", b"42", b"{",
                                          b""])
def test_header_json(header_bytes):
    assert check_safetensors(st_raw(None, header_bytes=header_bytes)) == "header-json"


@pytest.mark.parametrize("meta", [[1], "x", 5, {"k": 1}, {"k": None}, {"k": ["a"]}, None])
def test_metadata_must_be_object_of_strings(meta):
    assert check_safetensors(st_raw({"__metadata__": meta})) == "metadata"


@pytest.mark.parametrize("spec", [
    "text", [1], None,
    {"dtype": "F8", "shape": [1], "data_offsets": [0, 1]},
    {"shape": [1], "data_offsets": [0, 1]},
    {"dtype": "U8", "data_offsets": [0, 1]},
    {"dtype": "U8", "shape": [-1], "data_offsets": [0, 1]},
    {"dtype": "U8", "shape": [True], "data_offsets": [0, 1]},
    {"dtype": "U8", "shape": [1.0], "data_offsets": [0, 1]},
    {"dtype": "U8", "shape": "1", "data_offsets": [0, 1]},
    {"dtype": "U8", "shape": [1]},
    {"dtype": "U8", "shape": [1], "data_offsets": [0]},
    {"dtype": "U8", "shape": [1], "data_offsets": [0, 1, 2]},
    {"dtype": "U8", "shape": [1], "data_offsets": [-1, 0]},
    {"dtype": "U8", "shape": [1], "data_offsets": [0.0, 1]},
    {"dtype": "U8", "shape": [1], "data_offsets": [False, 1]},
    {"dtype": "U8", "shape": [1], "data_offsets": "ab"},
])
def test_tensor_spec(spec):
    assert check_safetensors(st_raw({"t": spec}, b"\x00")) == "tensor-spec"


def test_offsets_errors():
    assert check_safetensors(st_raw({"t": {"dtype": "U8", "shape": [1], "data_offsets": [1, 0]}}, b"\x00\x00")) == "offsets"
    assert check_safetensors(st_raw({"t": {"dtype": "U8", "shape": [4], "data_offsets": [0, 4]}}, b"\x00\x00")) == "offsets"
    assert check_safetensors(st_raw({"t": {"dtype": "U8", "shape": [1], "data_offsets": [0, 1]}}, b"")) == "offsets"


def test_size_mismatch():
    assert check_safetensors(st_raw({"t": {"dtype": "F32", "shape": [2, 2], "data_offsets": [0, 12]}}, b"\x00" * 12)) == "size-mismatch"
    assert check_safetensors(st_raw({"t": {"dtype": "F32", "shape": [], "data_offsets": [0, 8]}}, b"\x00" * 8)) == "size-mismatch"
    assert check_safetensors(st_raw({"t": {"dtype": "U8", "shape": [0], "data_offsets": [0, 1]}}, b"\x00")) == "size-mismatch"
    assert check_safetensors(st_raw({"t": {"dtype": "I64", "shape": [3], "data_offsets": [0, 16]}}, b"\x00" * 16)) == "size-mismatch"


def test_layout_problems():
    spec = lambda b, e: {"dtype": "U8", "shape": [e - b], "data_offsets": [b, e]}
    assert check_safetensors(st_raw({"a": spec(0, 2), "b": spec(3, 5)}, b"\x00" * 5)) == "layout"            # проміжок
    assert check_safetensors(st_raw({"a": spec(0, 3), "b": spec(2, 5)}, b"\x00" * 5)) == "layout"            # перекриття
    assert check_safetensors(st_raw({"a": spec(1, 4)}, b"\x00" * 4)) == "layout"                              # не з нуля
    assert check_safetensors(st_raw({"a": spec(0, 3)}, b"\x00" * 5)) == "layout"                              # хвіст
    assert check_safetensors(st_raw({}, b"\x00")) == "layout"                                                 # буфер без тензорів
    assert check_safetensors(st_raw({"a": spec(2, 4), "b": spec(0, 2)}, b"\x00" * 4)) is None                 # порядок імен не важить


def test_overlapping_tensors_hiding_data_is_layout_not_ok():
    spec = lambda b, e: {"dtype": "U8", "shape": [e - b], "data_offsets": [b, e]}
    assert check_safetensors(st_raw({"a": spec(0, 4), "b": spec(0, 4)}, b"\x00" * 4)) == "layout"


def test_error_precedence_header_before_tensors_and_tensors_in_name_order():
    bad_spec = {"dtype": "ZZ", "shape": [1], "data_offsets": [0, 1]}
    bad_offsets = {"dtype": "U8", "shape": [1], "data_offsets": [5, 0]}
    assert check_safetensors(st_raw({"__metadata__": [], "t": bad_spec}, b"\x00")) == "metadata"
    assert check_safetensors(st_raw({"a": bad_offsets, "b": bad_spec}, b"\x00")) == "offsets"
    assert check_safetensors(st_raw({"a": bad_spec, "b": bad_offsets}, b"\x00")) == "tensor-spec"
    size_bad = {"dtype": "U8", "shape": [2], "data_offsets": [0, 1]}
    assert check_safetensors(st_raw({"a": size_bad, "b": bad_spec}, b"\x00")) == "size-mismatch"
    assert check_safetensors(st_raw({"a": size_bad, "b": bad_offsets}, b"\x00")) == "size-mismatch"
    # layout перевіряється лише після всіх тензорів
    gap = {"dtype": "U8", "shape": [1], "data_offsets": [2, 3]}
    assert check_safetensors(st_raw({"a": gap, "b": bad_spec}, b"\x00" * 3)) == "tensor-spec"


# --- choose_model_file -------------------------------------------------------------------------

SAFE_PICKLE = pickle.dumps({"w": [1, 2, 3]})
EVIL_PICKLE = pickle.dumps(EvilSystem())
ST_OK = GOOD
ST_BAD = st_raw({"t": {"dtype": "U8", "shape": [9], "data_offsets": [0, 1]}}, b"\x00")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def manifest_for(files, skip=()):
    return {n: sha(b) for n, b in files.items() if n not in skip}


def test_prefers_valid_safetensors():
    files = {"model.safetensors": ST_OK, "pytorch_model.bin": SAFE_PICKLE, "config.json": b"{}"}
    result = choose_model_file(files, manifest_for(files))
    assert result == {"file": "model.safetensors", "format": "safetensors",
                      "rejected": []}


def test_safe_pickle_is_accepted_when_there_is_no_safetensors():
    files = {"model.pt": SAFE_PICKLE, "README.md": b"hi", "model.onnx": b"x"}
    assert choose_model_file(files, manifest_for(files)) == {"file": "model.pt", "format": "pickle", "rejected": []}


@pytest.mark.parametrize("name", ["w.pkl", "w.pickle", "w.pt", "w.pth", "w.bin", "w.ckpt", "W.PT", "Model.BIN"])
def test_pickle_extensions_are_candidates_case_insensitive(name):
    files = {name: SAFE_PICKLE}
    assert choose_model_file(files, manifest_for(files))["file"] == name


def test_non_candidates_are_ignored_even_when_unhashed():
    files = {"config.json": b"{}", "model.onnx": b"x", "notes.txt": b"x", "weights.safetensors.bak": b"x"}
    assert choose_model_file(files, {}) == {"file": None, "format": None, "rejected": []}


def test_missing_hash_and_hash_mismatch_for_safetensors():
    files = {"a.safetensors": ST_OK, "b.safetensors": ST_OK}
    manifest = {"b.safetensors": sha(b"something else")}
    assert choose_model_file(files, manifest) == {
        "file": None, "format": None,
        "rejected": [{"file": "a.safetensors", "reason": "no-hash"}, {"file": "b.safetensors", "reason": "hash-mismatch"}]}


def test_bad_safetensors_with_correct_hash_is_rejected_and_next_one_is_used():
    files = {"a.safetensors": ST_BAD, "b.safetensors": ST_OK}
    result = choose_model_file(files, manifest_for(files))
    assert result == {"file": "b.safetensors", "format": "safetensors",
                      "rejected": [{"file": "a.safetensors", "reason": "bad-safetensors"}]}


def test_candidates_are_checked_in_name_order_and_first_accepted_wins():
    files = {"z.safetensors": ST_OK, "a.safetensors": ST_OK}
    assert choose_model_file(files, manifest_for(files))["file"] == "a.safetensors"
    files = {"m2.bin": SAFE_PICKLE, "m1.bin": SAFE_PICKLE}
    assert choose_model_file(files, manifest_for(files))["file"] == "m1.bin"


def test_hash_is_checked_before_scanning_pickle():
    files = {"model.bin": EVIL_PICKLE}
    assert choose_model_file(files, {})["rejected"] == [{"file": "model.bin", "reason": "no-hash"}]
    assert choose_model_file(files, {"model.bin": sha(b"x")})["rejected"] == [{"file": "model.bin", "reason": "hash-mismatch"}]
    assert choose_model_file(files, manifest_for(files)) == {
        "file": None, "format": None, "rejected": [{"file": "model.bin", "reason": "unsafe-pickle"}]}


def test_unsafe_pickle_is_skipped_and_next_safe_pickle_is_accepted():
    files = {"a.bin": EVIL_PICKLE, "b.bin": SAFE_PICKLE}
    assert choose_model_file(files, manifest_for(files)) == {
        "file": "b.bin", "format": "pickle", "rejected": [{"file": "a.bin", "reason": "unsafe-pickle"}]}


def test_pickle_is_never_used_when_a_safetensors_candidate_exists_even_if_it_was_rejected():
    files = {"model.safetensors": ST_BAD, "model.bin": SAFE_PICKLE}
    result = choose_model_file(files, manifest_for(files))
    assert result == {"file": None, "format": None, "rejected": [
        {"file": "model.safetensors", "reason": "bad-safetensors"},
        {"file": "model.bin", "reason": "safetensors-preferred"}]}


def test_safetensors_preferred_needs_no_hash_and_no_scan():
    files = {"model.safetensors": ST_BAD, "model.bin": EVIL_PICKLE, "model.pt": b"garbage"}
    result = choose_model_file(files, {})
    assert [r["reason"] for r in result["rejected"]] == ["no-hash", "safetensors-preferred", "safetensors-preferred"]


def test_accepted_safetensors_stops_the_search_so_pickles_are_not_even_listed():
    files = {"a.safetensors": ST_OK, "b.bin": EVIL_PICKLE}
    result = choose_model_file(files, manifest_for(files))
    assert result["file"] == "a.safetensors" and result["rejected"] == []


def test_uppercase_extension_counts_as_safetensors_for_preference():
    files = {"MODEL.SAFETENSORS": ST_BAD, "m.bin": SAFE_PICKLE}
    result = choose_model_file(files, manifest_for(files))
    assert result["file"] is None and result["rejected"][1]["reason"] == "safetensors-preferred"


def test_inputs_are_not_mutated():
    files = {"a.bin": SAFE_PICKLE}
    manifest = manifest_for(files)
    snapshot = (dict(files), dict(manifest))
    choose_model_file(files, manifest)
    assert (files, manifest) == snapshot
