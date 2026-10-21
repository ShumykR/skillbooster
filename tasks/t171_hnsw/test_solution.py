import random

import pytest

from solution import HNSW


def sq_euclid(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def manhattan(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


class CountingDist:
    def __init__(self, fn=sq_euclid):
        self.fn = fn
        self.calls = 0

    def __call__(self, a, b):
        self.calls += 1
        return self.fn(a, b)


def make_vectors(n, dim, seed):
    rng = random.Random(seed)
    return [[rng.random() for _ in range(dim)] for _ in range(n)]


def brute(vectors, query, k, dist=sq_euclid, alive=None):
    ids = range(len(vectors)) if alive is None else alive
    return sorted(ids, key=lambda i: (dist(vectors[i], query), i))[:k]


def recall(approx, exact):
    return len(set(approx) & set(exact)) / len(exact)


def build(vectors, dist=sq_euclid, **kw):
    kw.setdefault("M", 8)
    kw.setdefault("ef_construction", 48)
    kw.setdefault("seed", 1)
    index = HNSW(dist, **kw)
    ids = [index.add(v) for v in vectors]
    assert ids == list(range(len(vectors)))
    return index


@pytest.fixture(scope="module")
def big():
    """1500 векторів dim 16: будується один раз на модуль."""
    vectors = make_vectors(1500, 16, seed=5)
    dist = CountingDist()
    index = build(vectors, dist)
    queries = make_vectors(40, 16, seed=99)
    exact = [brute(vectors, q, 10) for q in queries]
    return index, dist, vectors, queries, exact


def mean_recall(index, queries, exact, ef):
    return sum(recall(index.search(q, 10, ef), e) for q, e in zip(queries, exact)) / len(queries)


# --- базова поведінка --------------------------------------------------------------------------

def test_parameter_validation():
    for bad in (0, 1, -3, 2.5, None):
        with pytest.raises(ValueError):
            HNSW(sq_euclid, M=bad)
    for bad in (0, -1, 1.5):
        with pytest.raises(ValueError):
            HNSW(sq_euclid, M=4, ef_construction=bad)
    index = build(make_vectors(5, 2, 1))
    for bad_k in (0, -1, 1.5):
        with pytest.raises(ValueError):
            index.search([0.5, 0.5], bad_k)


def test_empty_index_and_sequential_ids():
    index = HNSW(sq_euclid, M=4)
    assert len(index) == 0
    assert index.search([0.0, 0.0], 3) == []
    assert index.add([0.0, 0.0]) == 0
    assert index.add([1.0, 1.0]) == 1
    assert len(index) == 2
    assert index.search([0.9, 0.9], 5) == [1, 0]  # k більше за кількість: усі, від найближчого


def test_small_index_is_exact_when_graph_is_complete():
    vectors = make_vectors(30, 4, seed=3)
    index = build(vectors, M=16, ef_construction=64)  # 2*M = 32 > 29: жодного відсікання
    for q in make_vectors(20, 4, seed=4):
        assert index.search(q, 7, ef_search=100) == brute(vectors, q, 7)
    assert index.search(vectors[0], 1) == [0]


def test_uses_the_given_distance_function():
    vectors = make_vectors(30, 4, seed=3)
    dist = CountingDist(manhattan)
    index = build(vectors, dist, M=16, ef_construction=64)
    assert dist.calls > 0
    before = dist.calls
    for q in make_vectors(15, 4, seed=8):
        assert index.search(q, 5, ef_search=100) == brute(vectors, q, 5, manhattan)
    assert dist.calls > before


def test_ef_search_smaller_than_k_still_returns_k_results():
    vectors = make_vectors(200, 4, seed=2)
    index = build(vectors, M=8)
    assert len(index.search(vectors[3], 10, ef_search=1)) == 10


def test_same_seed_gives_same_structure_and_results():
    vectors = make_vectors(300, 6, seed=7)
    a, b = build(vectors, seed=3), build(vectors, seed=3)
    assert a.graph(0) == b.graph(0) and a.max_layer == b.max_layer
    q = [0.5] * 6
    assert a.search(q, 10) == b.search(q, 10)


# --- якість і вартість -------------------------------------------------------------------------

def test_recall_at_10_with_ef_64(big):
    index, _, _, queries, exact = big
    assert mean_recall(index, queries, exact, 64) >= 0.95


def test_recall_grows_with_ef_and_low_ef_is_worse(big):
    index, _, _, queries, exact = big
    values = [mean_recall(index, queries, exact, ef) for ef in (10, 16, 32, 64, 128, 256)]
    for lower, higher in zip(values, values[1:]):
        assert higher >= lower - 0.01, values
    assert values[0] < values[3] - 0.05, values


def test_distance_computations_grow_with_ef_and_stay_sublinear(big):
    index, dist, vectors, queries, _ = big
    costs = {}
    for ef in (10, 64, 256):
        dist.calls = 0
        for q in queries:
            index.search(q, 10, ef)
        costs[ef] = dist.calls / len(queries)
    assert costs[10] < costs[64] < costs[256], costs
    assert costs[64] < len(vectors) / 2, costs  # brute force це 1500 обчислень на запит
    assert costs[10] < len(vectors) / 5, costs


def test_search_results_are_sorted_by_distance_without_duplicates(big):
    index, _, vectors, queries, _ = big
    for q in queries[:10]:
        res = index.search(q, 10, 64)
        assert len(res) == 10 and len(set(res)) == 10
        d = [sq_euclid(vectors[i], q) for i in res]
        assert d == sorted(d)


# --- структура графа ---------------------------------------------------------------------------

def test_layers_are_nested_and_degrees_bounded(big):
    index, _, vectors, _, _ = big
    n = len(vectors)
    layers = [index.graph(l) for l in range(index.max_layer + 1)]
    assert index.max_layer >= 1
    assert set(layers[0]) == set(range(n))
    for lower, upper in zip(layers, layers[1:]):
        assert set(upper) <= set(lower)
    for l, g in enumerate(layers):
        cap = 16 if l == 0 else 8
        for node, nbrs in g.items():
            assert len(nbrs) <= cap, (l, node, len(nbrs))
            assert node not in nbrs and len(set(nbrs)) == len(nbrs)
            assert set(nbrs) <= set(g)
    assert max(len(v) for v in layers[0].values()) > 8  # M0 = 2*M справді використовується


def test_neighbours_are_close_not_random_and_pruning_keeps_the_nearest(big):
    _, _, vectors, _, _ = big
    index = big[0]
    g = index.graph(0)
    total = count = 0
    for node, nbrs in list(g.items())[:300]:
        for m in nbrs:
            total += sq_euclid(vectors[node], vectors[m])
            count += 1
    rng = random.Random(1)
    rand = sum(sq_euclid(vectors[rng.randrange(1500)], vectors[rng.randrange(1500)]) for _ in range(2000)) / 2000
    assert total / count < 0.47 * rand, total / count / rand  # еталон ~0.40, «лишити найдальших» ~0.54


def test_level_distribution_is_geometric_with_ratio_1_over_M(big):
    index, _, vectors, _, _ = big
    share = len(index.graph(1)) / len(vectors)
    assert 0.06 <= share <= 0.22, share  # очікувано 1/8
    sizes = [len(index.graph(l)) for l in range(index.max_layer + 1)]
    assert sizes == sorted(sizes, reverse=True) and sizes[-1] >= 1


def test_entry_point_lives_on_the_top_layer(big):
    index = big[0]
    assert index.entry_point in index.graph(index.max_layer)
    assert index.graph(index.max_layer + 1) == {}


def test_graph_returns_copies():
    index = build(make_vectors(50, 3, seed=1))
    g = index.graph(0)
    first = next(iter(g))
    g[first].append(999)
    g.clear()
    assert 999 not in index.graph(0)[first] and len(index.graph(0)) == 50


# --- видалення (tombstone) ---------------------------------------------------------------------

def test_deleted_ids_are_never_returned_and_graph_keeps_them():
    vectors = make_vectors(400, 8, seed=11)
    index = build(vectors)
    victim = brute(vectors, vectors[5], 1)[0]
    assert victim == 5
    index.delete(5)
    assert len(index) == 399
    assert 5 not in index.search(vectors[5], 10, 64)
    assert 5 in index.graph(0)  # tombstone: вузол лишається в графі для навігації


def test_delete_validation_and_id_not_reused():
    index = build(make_vectors(20, 3, seed=1), M=4)
    for bad in (-1, 20, 99, "a", None):
        with pytest.raises(KeyError):
            index.delete(bad)
    index.delete(3)
    with pytest.raises(KeyError):
        index.delete(3)
    assert index.add([0.1, 0.2, 0.3]) == 20
    assert len(index) == 20


def test_recall_after_deleting_half_of_the_points():
    vectors = make_vectors(500, 8, seed=13)
    index = build(vectors)
    rng = random.Random(4)
    removed = set(rng.sample(range(500), 250))
    for i in removed:
        index.delete(i)
    alive = [i for i in range(500) if i not in removed]
    queries = make_vectors(30, 8, seed=14)
    total = 0.0
    for q in queries:
        res = index.search(q, 10, 64)
        assert len(res) == 10 and not set(res) & removed
        total += recall(res, brute(vectors, q, 10, alive=alive))
    assert total / len(queries) >= 0.9


def test_search_survives_deleting_the_entry_point_and_everything():
    vectors = make_vectors(60, 4, seed=21)
    index = build(vectors, M=8)
    index.delete(index.entry_point)
    assert len(index.search(vectors[0], 5, 32)) == 5
    for i in range(60):
        if i != index.entry_point:
            try:
                index.delete(i)
            except KeyError:
                pass
    assert len(index) == 0
    assert index.search(vectors[0], 5, 32) == []


def test_new_points_after_deletions_are_findable():
    vectors = make_vectors(200, 6, seed=31)
    index = build(vectors)
    for i in range(0, 200, 2):
        index.delete(i)
    new_id = index.add([0.123] * 6)
    assert index.search([0.123] * 6, 1, 64) == [new_id]
