"""Завдання №172: квантизація embeddings.

Вектор із 1024 вимірів у float32 це 4 КБ. Мільйон документів це 4 ГБ лише на вектори, і їх
треба тримати в памʼяті для швидкого пошуку. Квантизація міняє точність на памʼять:
int8 (4x менше), бінарна (32x менше, лише знак кожного виміру) і Matryoshka-обрізання (перші
виміри несуть більше сигналу, тож їх можна відрізати). Бінарний пошук грубий, тож його
доповнюють rescoring: беруть кандидатів за відстанню Хеммінга й переоцінюють повними векторами.
Ти реалізуєш усе на чистому Python без numpy. Тести генерують дані з фіксованим seed.

Вектор це список чисел (`list[float]`); набір векторів це список списків однакової довжини.
Скрізь, де обирають top-k, рівність оцінок розвʼязується за МЕНШИМ індексом. Порожній набір,
різна довжина векторів чи `k < 1` (`int`, не `bool`): `ValueError`.

`dot(a, b) -> float`: скалярний добуток (різна довжина: `ValueError`).

`quantize_int8(vectors) -> (codes, scales)`
    Масштаб на ВИМІР: `scales[j] = max(|v[j]| за всіма векторами) / 127`; якщо максимум 0, то
    `scales[j] = 1.0`. Код: `q = x / scales[j]`, округлення «половина від нуля» (`floor(|q| + 0.5)`
    зі знаком), обмеження діапазоном `-127..127`. `codes` це `list[list[int]]`.
`dequantize_int8(codes, scales) -> list[list[float]]`: `code * scales[j]`.
`binary_code(vector) -> bytes`
    Біт на вимір: `1`, якщо значення СТРОГО більше 0, інакше `0`. Біти пакуються по 8 у байт, перший
    вимір це старший біт байта; останній байт добивається нулями справа. Довжина `ceil(d / 8)`.
`hamming(a, b) -> int`: кількість різних бітів двох `bytes` (різна довжина: `ValueError`).
`truncate(vector, dim) -> list[float]`
    Matryoshka-обрізання: перші `dim` компонент (`1 <= dim <= len(vector)`, інакше `ValueError`),
    нормалізовані до одиничної L2-довжини; нульовий вектор лишається нулями.
`search_float(vectors, query, k) -> list[int]`: індекси `k` найбільших `dot(v, query)` від
    найкращого (менше `k` елементів, якщо їх менше).
`search_int8(codes, scales, query, k) -> list[int]`: те саме за `dot(dequantized, query)`.
`search_binary(codes, query_code, k) -> list[int]`: `codes` це список `bytes`; `k` найменших
    `hamming` (рівність: менший індекс).

`BinaryRescoreIndex(vectors)`
    Тримає бінарні коди для швидкого відбору й повні вектори для rescoring.
    `.search(query, k, oversample=4) -> list[int]`: `oversample` це `int >= 1`. Крок 1: взяти
    `min(n, k * oversample)` кандидатів за найменшим `hamming(binary_code(query), код)`. Крок 2:
    переоцінити кандидатів `dot(вектор, query)` і повернути `k` найкращих. `.codes` це список
    бінарних кодів.
`memory_bytes(n, d, scheme) -> int`
    `"float32"`: `4*n*d`; `"int8"`: `n*d + 4*d` (коди плюс масштаби float32); `"binary"`:
    `n * ceil(d / 8)`. Інша схема, `n < 1`, `d < 1`: `ValueError`.
`recall_at_k(approx, exact) -> float`: `|set(approx) & set(exact)| / len(exact)`; `exact` порожній:
    `ValueError`.
`tradeoff_table(vectors, queries, k, truncate_dim) -> list[dict]`
    Рівно 5 рядків у такому порядку: `"float32"`, `"int8"`, `"binary"`, `"binary+rescore"` (оверсемплінг
    4), `"matryoshka"` (вектори й запити обрізані `truncate`, пошук `search_float`). Кожен рядок:
    `{"scheme", "bytes", "ratio", "recall"}`; `bytes` за `memory_bytes` (для `"binary+rescore"`:
    `binary` плюс `float32`; для `"matryoshka"`: `float32` для `truncate_dim`), `ratio` це
    `round(bytes_float32 / bytes, 4)` для повних векторів, `recall` це середній `recall_at_k` за
    запитами відносно `search_float` на повних векторах, `round(.., 4)`. Для `float32` recall 1.0.
"""
import math  # noqa: F401  (знадобиться)


def dot(a, b):
    raise NotImplementedError


def quantize_int8(vectors):
    raise NotImplementedError


def dequantize_int8(codes, scales):
    raise NotImplementedError


def binary_code(vector) -> bytes:
    raise NotImplementedError


def hamming(a: bytes, b: bytes) -> int:
    raise NotImplementedError


def truncate(vector, dim):
    raise NotImplementedError


def search_float(vectors, query, k):
    raise NotImplementedError


def search_int8(codes, scales, query, k):
    raise NotImplementedError


def search_binary(codes, query_code, k):
    raise NotImplementedError


class BinaryRescoreIndex:
    def __init__(self, vectors):
        raise NotImplementedError

    @property
    def codes(self):
        raise NotImplementedError

    def search(self, query, k, oversample=4):
        raise NotImplementedError


def memory_bytes(n, d, scheme):
    raise NotImplementedError


def recall_at_k(approx, exact):
    raise NotImplementedError


def tradeoff_table(vectors, queries, k, truncate_dim):
    raise NotImplementedError
