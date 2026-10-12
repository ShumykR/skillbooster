"""Завдання №39: Векторний пошук, IVF-індекс і компроміс швидкість/точність.

IVFFlat у pgvector працює так: вектори розбиваються k-means на `n_lists` кластерів;
пошук порівнює запит лише з центроїдами, обирає `nprobe` найближчих кластерів і
перебирає тільки їхні вектори. Менший `nprobe` швидший, але може пропустити справжніх сусідів.

Реалізуй `IVFIndex` без сторонніх бібліотек:
- `__init__(vectors, n_lists, dist, seed=0, iters=8)`: k-means з `iters` ітераціями.
  Початкові центроїди вибирай детерміновано (`random.Random(seed).sample`). Порожній кластер
  не повинен ламати індекс. Усі відстані, і під час побудови, і під час пошуку, рахуй ТІЛЬКИ
  через `dist(a, b)`: тести рахують її виклики як вартість запиту;
- `search(query, k, nprobe) -> list[int]`: індекси векторів у `vectors`, від найближчого, не більше `k`.
  `nprobe` більший за `n_lists` обрізається; `nprobe >= n_lists` має давати точний результат.
  Кожну відстань (до кожного центроїда й до кожного кандидата) рахуй рівно один раз.

`brute_force` (точний пошук) та `recall_at_k` дано.
"""
import random  # noqa: F401  (знадобиться для вибору початкових центроїдів)
from typing import Callable, Sequence

Vector = Sequence[float]
Dist = Callable[[Vector, Vector], float]


def sq_euclid(a: Vector, b: Vector) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def brute_force(vectors: Sequence[Vector], query: Vector, k: int, dist: Dist = sq_euclid) -> list[int]:
    return sorted(range(len(vectors)), key=lambda i: dist(vectors[i], query))[:k]


def recall_at_k(approx: Sequence[int], exact: Sequence[int]) -> float:
    return len(set(approx) & set(exact)) / len(exact) if exact else 1.0


class IVFIndex:
    def __init__(self, vectors: Sequence[Vector], n_lists: int, dist: Dist = sq_euclid, seed: int = 0, iters: int = 8) -> None:
        raise NotImplementedError

    def search(self, query: Vector, k: int, nprobe: int) -> list[int]:
        raise NotImplementedError
