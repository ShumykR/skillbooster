import random

import pytest

from solution import IVFIndex, brute_force, recall_at_k, sq_euclid

N_CLUSTERS, PER_CLUSTER, DIM, N_LISTS, K = 20, 60, 8, 20, 10


def make_data(seed=7):
    rng = random.Random(seed)
    centers = [[rng.uniform(-3, 3) for _ in range(DIM)] for _ in range(N_CLUSTERS)]
    vectors = [[c + rng.gauss(0, 1.4) for c in center] for center in centers for _ in range(PER_CLUSTER)]
    queries = [[x + rng.gauss(0, 0.8) for x in rng.choice(vectors)] for _ in range(40)]
    return vectors, queries


VECTORS, QUERIES = make_data()


class CountingDist:
    def __init__(self):
        self.calls = 0

    def __call__(self, a, b):
        self.calls += 1
        return sq_euclid(a, b)


def build(**kw):
    dist = CountingDist()
    index = IVFIndex(VECTORS, N_LISTS, dist=dist, **kw)
    return index, dist


def evaluate(index, dist, nprobe):
    """Середній recall@K та середня кількість викликів dist на один запит."""
    recalls, costs = [], []
    for q in QUERIES:
        dist.calls = 0
        found = index.search(q, K, nprobe)
        costs.append(dist.calls)
        recalls.append(recall_at_k(found, brute_force(VECTORS, q, K)))
    return sum(recalls) / len(recalls), sum(costs) / len(costs)


@pytest.fixture(scope="module")
def built():
    return build()


def test_probing_all_lists_is_exact(built):
    index, _ = built
    for q in QUERIES[:10]:
        assert index.search(q, K, nprobe=N_LISTS) == brute_force(VECTORS, q, K)
        assert index.search(q, K, nprobe=N_LISTS + 50) == brute_force(VECTORS, q, K)


def test_result_is_sorted_by_distance_and_has_no_duplicates(built):
    index, _ = built
    q = QUERIES[0]
    found = index.search(q, K, nprobe=3)
    assert len(found) == len(set(found)) == K
    distances = [sq_euclid(VECTORS[i], q) for i in found]
    assert distances == sorted(distances)


def test_recall_grows_with_nprobe_and_reaches_one(built):
    index, dist = built
    r1, _ = evaluate(index, dist, 1)
    r4, _ = evaluate(index, dist, 4)
    rall, _ = evaluate(index, dist, N_LISTS)
    assert r1 < r4 <= rall == 1.0, f"recall: nprobe=1 → {r1:.2f}, 4 → {r4:.2f}, всі → {rall:.2f}"


def test_small_nprobe_gives_good_recall_much_cheaper_than_brute_force(built):
    index, dist = built
    recall, cost = evaluate(index, dist, 4)
    assert recall >= 0.85, f"recall@{K} при nprobe=4: {recall:.2f}"
    assert cost <= len(VECTORS) * 0.35, f"{cost:.0f} відстаней на запит проти {len(VECTORS)} у повного перебору"


def test_every_distance_is_computed_once(built):
    index, dist = built
    _, cost = evaluate(index, dist, N_LISTS)
    assert cost == N_LISTS + len(VECTORS), "кожен центроїд і кожен кандидат мають рахуватись рівно один раз, лише через dist"


def test_cost_grows_with_nprobe(built):
    index, dist = built
    costs = [evaluate(index, dist, n)[1] for n in (1, 2, 4, 8)]
    assert costs == sorted(costs) and costs[0] < costs[-1]
    assert costs[0] >= N_LISTS, "порівняння із центроїдами теж коштують відстаней"


def test_build_is_deterministic_for_same_seed():
    a, _ = build(seed=3)
    b, _ = build(seed=3)
    for q in QUERIES[:10]:
        assert a.search(q, K, 2) == b.search(q, K, 2)


def test_k_larger_than_probed_candidates_returns_what_exists(built):
    index, _ = built
    found = index.search(QUERIES[0], 10_000, nprobe=1)
    assert 0 < len(found) < len(VECTORS)
    assert len(found) == len(set(found))


def test_degenerate_data_with_empty_clusters_does_not_crash():
    same = [[1.0, 1.0]] * 30
    index = IVFIndex(same, 5, dist=sq_euclid)
    assert sorted(index.search([1.0, 1.0], 5, nprobe=5)) == sorted(brute_force(same, [1.0, 1.0], 5))
    tiny = IVFIndex([[0.0], [1.0]], 5, dist=sq_euclid)  # n_lists більше за кількість векторів
    assert set(tiny.search([0.1], 2, nprobe=5)) == {0, 1}
