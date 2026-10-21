"""Завдання №171: HNSW з нуля.

HNSW (Hierarchical Navigable Small World) це багатошаровий граф для наближеного пошуку найближчих
сусідів: на верхніх (рідких) шарах пошук «стрибає» далеко, на нижніх уточнюється, а шар 0 містить
усі точки. Це основа pgvector/HNSW, Qdrant, Weaviate. Ти пишеш індекс на чистому Python.
Дані тестів генеруються з `random.Random(seed)`, перевіряються якість (recall), кількість
обчислень відстані (не час) і структура графа.

`sq_euclid(a, b)`: квадрат евклідової відстані (готова функція). Відстань передається в індекс
параметром `dist(a, b) -> float` (менше означає ближче); тест рахує її виклики.

`HNSW(dist=sq_euclid, M=8, ef_construction=64, seed=0)`
    * `M` це `int` >= 2, `ef_construction` це `int` >= 1, інакше `ValueError`.
    * Максимум сусідів вузла: `2*M` на шарі 0 і `M` на вищих шарах. Усі звʼязки двосторонні на
      момент вставки; якщо в сусіда стало більше за максимум, лишаються найближчі до нього
      (рівність відстаней: менший id). Вузол не є сусідом самого себе, дублікатів немає.
    * Рівень нового вузла: `int(-ln(1 - u) * mL)`, де `u` з `random.Random(seed)`, `mL = 1/ln(M)`
      (геометричний розподіл: частка вузлів вище шару 0 приблизно `1/M`). Той самий `seed` і ті
      самі вставки дають ТОЙ САМИЙ граф.
    * Шари вкладені: вузол рівня L присутній на шарах 0..L; шар 0 має ВСІ вузли (і видалені).

`add(vec) -> int`
    Вставляє вектор, повертає його id: 0, 1, 2, ... підряд (id видалених не використовуються
    повторно). Алгоритм: жадібний спуск з точки входу до рівня вузла (ef=1), далі на кожному шарі
    від min(рівень, верхній) до 0 пошук `ef_construction` кандидатів, вибір `M` найближчих,
    двосторонні звʼязки. Якщо рівень вузла вищий за поточний верхній, він стає точкою входу.

`delete(idx) -> None`
    Tombstone: позначає вузол видаленим, але ЛИШАЄ його в графі для навігації. Невідомий id
    (не `int`, поза діапазоном) чи вже видалений: `KeyError`.

`search(query, k, ef_search=64) -> list[int]`
    `k` це `int` >= 1, інакше `ValueError`. Порожній індекс це `[]`. Спуск від точки входу
    (ef=1) до шару 1, потім пошук на шарі 0 з `ef = max(ef_search, k)`. Повертає до `k` id ЖИВИХ
    вузлів від найближчого до найдальшого, без дублікатів (рівність відстаней: менший id).
    Видалені вузли не повертаються, але пошук може через них проходити.

`len(index)`: кількість живих вузлів.
`index.max_layer`: номер верхнього шару (`-1`, якщо порожній).
`index.entry_point`: id точки входу (`None`, якщо порожній); вона лежить на верхньому шарі.
`index.graph(layer) -> dict[int, list[int]]`: КОПІЯ списків сусідів шару (`{}` для неіснуючого
    шару); зміна результату не псує індекс.
"""
import heapq  # noqa: F401  (підказка: черги з пріоритетом для пошуку на шарі)
import math  # noqa: F401
import random  # noqa: F401


def sq_euclid(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


class HNSW:
    def __init__(self, dist=sq_euclid, M: int = 8, ef_construction: int = 64, seed: int = 0):
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    @property
    def max_layer(self) -> int:
        raise NotImplementedError

    @property
    def entry_point(self):
        raise NotImplementedError

    def graph(self, layer: int) -> dict:
        raise NotImplementedError

    def add(self, vec) -> int:
        raise NotImplementedError

    def delete(self, idx: int) -> None:
        raise NotImplementedError

    def search(self, query, k: int, ef_search: int = 64) -> list:
        raise NotImplementedError
