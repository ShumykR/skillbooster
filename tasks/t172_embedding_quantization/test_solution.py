import math
import random

import pytest

from solution import (BinaryRescoreIndex, binary_code, dequantize_int8, dot, hamming, memory_bytes, quantize_int8,
                      recall_at_k, search_binary, search_float, search_int8, tradeoff_table, truncate)


def norm(v):
    m = math.sqrt(sum(x * x for x in v))
    return [x / m for x in v]


def clustered(seed, d=128, clusters=40, per=10, noise=1.5, qnoise=0.5, decay=16):
    """40 кластерів по 10 векторів; перші виміри несуть більше сигналу (як у Matryoshka-embeddings)."""
    r = random.Random(seed)
    sc = [1 / (1 + i / decay) for i in range(d)]
    centers = [[r.gauss(0, 1) * sc[i] for i in range(d)] for _ in range(clusters)]
    db = [norm([c[i] + r.gauss(0, 1) * noise * sc[i] for i in range(d)]) for c in centers for _ in range(per)]
    queries = [norm([c[i] + r.gauss(0, 1) * qnoise * sc[i] for i in range(d)]) for c in centers[:20]]
    return db, queries


def mean_recall(search, queries, exact):
    return sum(recall_at_k(search(q), e) for q, e in zip(queries, exact)) / len(queries)


# --- dot ---------------------------------------------------------------------------------------

def test_dot():
    assert dot([1, 2, 3], [4, 5, 6]) == 32 and dot([0.5], [4]) == 2.0
    with pytest.raises(ValueError):
        dot([1, 2], [1])


# --- quantize_int8 -----------------------------------------------------------------------------

def test_int8_exact_codes_scales_and_half_away_from_zero_rounding():
    vectors = [[127.0, 254.0], [63.5, -127.0], [-63.5, 0.4], [0.49, -0.5]]
    codes, scales = quantize_int8(vectors)
    assert scales == [1.0, 2.0]
    assert codes == [[127, 127], [64, -64], [-64, 0], [0, 0]]            # 63.5 -> 64, -63.5 -> -64, -0.25 -> 0
    assert all(isinstance(c, int) for row in codes for c in row)


def test_int8_rounding_is_half_away_from_zero_not_banker_s():
    codes, scales = quantize_int8([[127.0], [62.5], [-62.5], [0.5], [1.5], [-0.5], [2.5]])
    assert scales == [1.0]
    assert [row[0] for row in codes] == [127, 63, -63, 1, 2, -1, 3]       # round() дав би 62, -62, 0, 2, -0, 2


def test_int8_zero_column_has_unit_scale_and_zero_codes():
    codes, scales = quantize_int8([[0.0, 2.0], [0.0, -1.0]])
    assert scales[0] == 1.0 and [row[0] for row in codes] == [0, 0]
    assert scales[1] == pytest.approx(2.0 / 127) and [row[1] for row in codes] == [127, -64]   # -0.5 * 127 = -63.5


def test_int8_extremes_map_to_plus_minus_127_and_never_exceed():
    r = random.Random(1)
    vectors = [[r.uniform(-5, 5) for _ in range(6)] for _ in range(50)]
    codes, scales = quantize_int8(vectors)
    for j in range(6):
        col = [row[j] for row in codes]
        assert max(abs(c) for c in col) == 127 and all(-127 <= c <= 127 for c in col)
        assert scales[j] == pytest.approx(max(abs(v[j]) for v in vectors) / 127)


def test_int8_roundtrip_error_is_at_most_half_a_step():
    r = random.Random(2)
    vectors = [[r.gauss(0, 1) for _ in range(8)] for _ in range(40)]
    codes, scales = quantize_int8(vectors)
    back = dequantize_int8(codes, scales)
    for v, b in zip(vectors, back):
        for j, (x, y) in enumerate(zip(v, b)):
            assert abs(x - y) <= scales[j] / 2 + 1e-12
    assert back[0] == [c * s for c, s in zip(codes[0], scales)]


def test_int8_scales_are_per_dimension_not_global():
    codes, scales = quantize_int8([[100.0, 1.0], [-100.0, -1.0]])
    assert scales[0] == pytest.approx(100 / 127) and scales[1] == pytest.approx(1 / 127)
    assert codes == [[127, 127], [-127, -127]]


@pytest.mark.parametrize("bad", [[], None, [[1.0], [1.0, 2.0]], [[]], [["a"]], [[True]], "ab"])
def test_int8_validation(bad):
    with pytest.raises(ValueError):
        quantize_int8(bad)


# --- binary_code / hamming ---------------------------------------------------------------------

def test_binary_code_bit_order_padding_and_strict_positive():
    assert binary_code([0.5, -1, 0, 2, 0.1, 0.2, -0.3, 0.4, 1]) == b"\x9d\x80"
    assert binary_code([1, 1, 1, 1, 1, 1, 1, 1]) == b"\xff" and binary_code([1]) == b"\x80"
    assert binary_code([-1, -0.0, 0, 0.0, -5, -1, -1, -1]) == b"\x00"
    assert binary_code([0, 0, 0, 0, 0, 0, 0, 1]) == b"\x01"
    assert len(binary_code([1.0] * 16)) == 2 and len(binary_code([1.0] * 17)) == 3 and len(binary_code([1.0] * 100)) == 13
    assert isinstance(binary_code([1.0]), bytes)


@pytest.mark.parametrize("bad", [[], None, "abc", [None]])
def test_binary_code_validation(bad):
    with pytest.raises(ValueError):
        binary_code(bad)


def test_hamming():
    assert hamming(b"\xff\x00", b"\x0f\x01") == 5 and hamming(b"\xab", b"\xab") == 0 and hamming(b"", b"") == 0
    assert hamming(b"\x00\x00\x00", b"\xff\xff\xff") == 24
    with pytest.raises(ValueError):
        hamming(b"\x00", b"\x00\x00")


# --- truncate ----------------------------------------------------------------------------------

def test_truncate_takes_prefix_and_renormalizes():
    assert truncate([3.0, 4.0, 12.0], 2) == pytest.approx([0.6, 0.8])
    assert truncate([3.0, 4.0, 12.0], 3) == pytest.approx([3 / 13, 4 / 13, 12 / 13])
    assert truncate([5.0, 0.0, 9.0], 1) == [1.0]
    assert truncate([-2.0, 0.0], 2) == [-1.0, 0.0]
    t = truncate([1.0, 2.0, 3.0, 4.0, 5.0], 4)
    assert len(t) == 4 and math.sqrt(sum(x * x for x in t)) == pytest.approx(1.0)


def test_truncate_zero_prefix_stays_zeros_and_input_is_not_mutated():
    assert truncate([0.0, 0.0, 7.0], 2) == [0.0, 0.0]
    v = [3.0, 4.0]
    truncate(v, 1)
    assert v == [3.0, 4.0]


@pytest.mark.parametrize("dim", [0, -1, 4, 1.5, "2", None, True])
def test_truncate_validates_dim(dim):
    with pytest.raises(ValueError):
        truncate([1.0, 2.0, 3.0], dim)


# --- пошук: float / int8 / binary --------------------------------------------------------------

def test_search_float_uses_dot_product_with_index_tiebreak():
    vectors = [[10.0, 0.0], [0.0, 1.0], [5.0, 5.0], [5.0, 5.0]]
    assert search_float(vectors, [1.0, 1.0], 4) == [0, 2, 3, 1]          # 10, 10, 10, 1: рівність за індексом
    assert search_float(vectors, [1.0, 1.0], 2) == [0, 2]
    assert search_float(vectors, [1.0, 1.0], 10) == [0, 2, 3, 1]         # k більше за n
    assert search_float([[1.0, 0.0]], [0.0, 1.0], 1) == [0]


@pytest.mark.parametrize("k", [0, -1, 1.5, "2", None, True])
def test_search_k_validation(k):
    with pytest.raises(ValueError):
        search_float([[1.0]], [1.0], k)
    with pytest.raises(ValueError):
        search_binary([b"\x00"], b"\x00", k)
    codes, scales = quantize_int8([[1.0]])
    with pytest.raises(ValueError):
        search_int8(codes, scales, [1.0], k)


def test_search_float_rejects_empty_and_ragged_inputs():
    with pytest.raises(ValueError):
        search_float([], [1.0], 1)
    with pytest.raises(ValueError):
        search_float([[1.0], [1.0, 2.0]], [1.0], 1)


def test_search_int8_scores_with_dequantized_vectors():
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7], [-1.0, 0.2]]
    codes, scales = quantize_int8(vectors)
    assert search_int8(codes, scales, [0.6, 0.8], 4) == search_float(vectors, [0.6, 0.8], 4)
    assert search_int8(codes, scales, [1.0, 0.0], 1) == [0]


def test_search_binary_orders_by_hamming_then_index():
    codes = [b"\xff", b"\x0f", b"\xf0", b"\x00", b"\xfe"]
    assert search_binary(codes, b"\xff", 5) == [0, 4, 1, 2, 3]            # hamming: 0, 1, 4, 4, 8
    assert search_binary(codes, b"\xff", 2) == [0, 4]
    assert search_binary(codes, b"\xff", 99) == [0, 4, 1, 2, 3]
    with pytest.raises(ValueError):
        search_binary([], b"\x00", 1)


# --- BinaryRescoreIndex ------------------------------------------------------------------------

def test_rescoring_corrects_the_ranking_of_the_hamming_candidates():
    a = [0.01] * 8                                                      # hamming 0 до запиту, але dot = 0.08
    b = [5.0] * 7 + [-1.0]                                              # hamming 1, але dot = 34
    q = [1.0] * 8
    idx = BinaryRescoreIndex([a, b])
    assert search_binary(idx.codes, binary_code(q), 1) == [0]
    assert idx.search(q, 1, oversample=2) == [1]                        # обидва кандидати переоцінені повними векторами
    assert idx.search(q, 1, oversample=1) == [0]                        # без запасу кандидатів rescoring не рятує


def test_oversample_is_capped_by_n_and_results_are_sorted_by_dot():
    vectors = [[1.0, 0.1], [1.0, 0.5], [1.0, 0.9], [-1.0, 1.0]]
    idx = BinaryRescoreIndex(vectors)
    assert idx.search([1.0, 1.0], 3, oversample=100) == [2, 1, 0]
    assert idx.search([1.0, 1.0], 10, oversample=1) == [2, 1, 0, 3]      # k більше за n: кандидатів усі 4


def test_index_codes_are_copies_and_vectors_are_not_aliased():
    vectors = [[1.0, -1.0], [-1.0, 1.0]]
    idx = BinaryRescoreIndex(vectors)
    assert idx.codes == [b"\x80", b"\x40"]
    idx.codes.append(b"x")
    vectors[0][0] = -100.0
    assert idx.codes == [b"\x80", b"\x40"]
    assert idx.search([1.0, -1.0], 1) == [0]


@pytest.mark.parametrize("oversample", [0, -1, 1.5, "4", None, True])
def test_oversample_validation(oversample):
    idx = BinaryRescoreIndex([[1.0, 2.0], [2.0, 1.0]])
    with pytest.raises(ValueError):
        idx.search([1.0, 1.0], 1, oversample=oversample)


def test_index_rejects_empty_and_ragged_input():
    with pytest.raises(ValueError):
        BinaryRescoreIndex([])
    with pytest.raises(ValueError):
        BinaryRescoreIndex([[1.0], [1.0, 2.0]])


# --- memory_bytes / recall_at_k ----------------------------------------------------------------

def test_memory_bytes():
    assert memory_bytes(1000, 1024, "float32") == 4_096_000
    assert memory_bytes(1000, 1024, "int8") == 1_024_000 + 4096
    assert memory_bytes(1000, 1024, "binary") == 128_000
    assert memory_bytes(5, 10, "binary") == 10 and memory_bytes(3, 1, "binary") == 3 and memory_bytes(1, 9, "binary") == 2
    assert memory_bytes(10 ** 6, 1024, "float32") // memory_bytes(10 ** 6, 1024, "binary") == 32
    assert memory_bytes(10 ** 6, 1024, "float32") / memory_bytes(10 ** 6, 1024, "int8") == pytest.approx(4, rel=0.001)


@pytest.mark.parametrize("args", [(0, 8, "binary"), (1, 0, "binary"), (-1, 8, "int8"), (1, 8, "fp16"), (1.5, 8, "int8"),
                                  (1, 8, None), (True, 8, "int8"), (1, 8.0, "float32")])
def test_memory_bytes_validation(args):
    with pytest.raises(ValueError):
        memory_bytes(*args)


def test_recall_at_k():
    assert recall_at_k([1, 2, 3], [1, 2, 4]) == pytest.approx(2 / 3)
    assert recall_at_k([3, 2, 1], [1, 2, 3]) == 1.0
    assert recall_at_k([], [1, 2]) == 0.0
    assert recall_at_k([1, 1, 1, 2], [1, 2]) == 1.0                      # дублікати не збільшують значення
    assert recall_at_k([9], [1]) == 0.0
    with pytest.raises(ValueError):
        recall_at_k([1], [])


# --- tradeoff_table і якість на кластерних даних -----------------------------------------------

@pytest.fixture(scope="module")
def table_data():
    vectors, queries = clustered(3)
    return vectors, queries, tradeoff_table(vectors, queries, 10, 32)


def test_tradeoff_table_structure_bytes_and_ratios(table_data):
    _, _, table = table_data
    assert [r["scheme"] for r in table] == ["float32", "int8", "binary", "binary+rescore", "matryoshka"]
    assert all(set(r) == {"scheme", "bytes", "ratio", "recall"} for r in table)
    assert [r["bytes"] for r in table] == [204_800, 51_712, 6_400, 211_200, 51_200]
    assert [r["ratio"] for r in table] == [1.0, round(204_800 / 51_712, 4), 32.0, round(204_800 / 211_200, 4), 4.0]
    assert table[0]["recall"] == 1.0
    assert all(round(r["recall"], 4) == r["recall"] for r in table)


def test_tradeoff_table_recall_levels(table_data):
    _, _, table = table_data
    recall = {r["scheme"]: r["recall"] for r in table}
    assert recall["int8"] >= 0.97                                        # int8 майже не втрачає
    assert 0.55 <= recall["binary"] <= 0.9
    assert recall["binary+rescore"] >= recall["binary"] + 0.05           # rescoring повертає частину втраченого
    assert 0.6 <= recall["matryoshka"] <= 0.9


def test_tradeoff_table_binary_rescore_equals_recomputation(table_data):
    vectors, queries, table = table_data
    idx = BinaryRescoreIndex(vectors)
    exact = [search_float(vectors, q, 10) for q in queries]
    expected = round(mean_recall(lambda q: idx.search(q, 10, 4), queries, exact), 4)
    assert next(r for r in table if r["scheme"] == "binary+rescore")["recall"] == expected


def test_oversample_improves_recall_monotonically_up_to_exact():
    for seed in (1, 2, 3):
        vectors, queries = clustered(seed)
        exact = [search_float(vectors, q, 10) for q in queries]
        idx = BinaryRescoreIndex(vectors)
        values = [mean_recall(lambda q, o=o: idx.search(q, 10, o), queries, exact) for o in (1, 4, 10, 40)]
        assert values == sorted(values), values
        assert values[0] == mean_recall(lambda q: search_binary(idx.codes, binary_code(q), 10), queries, exact)
        assert values[2] >= 0.85 and values[3] == 1.0                    # 40 * 10 = n: усі кандидати переоцінені


def test_matryoshka_recall_grows_with_dimension():
    vectors, queries = clustered(2)
    exact = [search_float(vectors, q, 10) for q in queries]
    recalls = []
    for dim in (8, 32, 64):
        tv = [truncate(v, dim) for v in vectors]
        recalls.append(mean_recall(lambda q, tv=tv, dim=dim: search_float(tv, truncate(q, dim), 10), queries, exact))
    assert recalls[0] < recalls[1] < recalls[2]
    assert recalls[0] < 0.5 and recalls[1] >= 0.6 and recalls[2] >= 0.8


def test_int8_search_recall_is_high_on_several_datasets():
    for seed in (1, 4, 5):
        vectors, queries = clustered(seed)
        codes, scales = quantize_int8(vectors)
        exact = [search_float(vectors, q, 10) for q in queries]
        assert mean_recall(lambda q: search_int8(codes, scales, q, 10), queries, exact) >= 0.97


def test_tradeoff_table_validation():
    vectors, queries = clustered(1, clusters=3, per=4)
    with pytest.raises(ValueError):
        tradeoff_table(vectors, queries, 0, 8)
    with pytest.raises(ValueError):
        tradeoff_table([], queries, 3, 8)
    with pytest.raises(ValueError):
        tradeoff_table(vectors, queries, 3, 0)
    with pytest.raises(ValueError):
        tradeoff_table(vectors, queries, 3, 129)
