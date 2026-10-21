"""Завдання №169: BPE-токенізатор з нуля.

Токени це цілі числа. Базовий словник: байти UTF-8 (id 0..255), тож будь-який текст
(кирилиця, емодзі, керуючі символи) кодується без `unk`. Правило злиття `(a, b)` з номером
`i` у списку `merges` створює токен з id `256 + i`.

`train_bpe(corpus: str, num_merges: int) -> list[tuple[int, int]]`
    Навчання на ВЕСЬ корпус як на одній послідовності байтів (без попереднього поділу на слова):
    1. `ids = list(corpus.encode("utf-8"))`;
    2. повторюй до `num_merges` разів: порахуй усі сусідні пари в поточній послідовності
       (кожну позицію окремо, тобто у `aaaa` пара `(97, 97)` трапляється 3 рази);
       обери пару з НАЙБІЛЬШОЮ кількістю, а при нічиїй з НАЙМЕНШОЮ парою за порівнянням
       кортежів; якщо найбільша кількість менша за 2 (або пар немає), зупинись достроково;
    3. заміни всі входження обраної пари на новий токен зліва направо без накладання
       (`aaa` + пара `(a, a)` дає `[новий, a]`) і додай пару в результат.
    `num_merges` має бути `int` (не `bool`) >= 0, інакше `ValueError`. Повертає пари у порядку навчання.
`encode(text: str, merges) -> list[int]`
    Байти UTF-8 тексту; потім для кожного правила `merges` У ПОРЯДКУ НАВЧАННЯ замінюй усі його
    входження зліва направо без накладання на токен `256 + i`.
`decode(ids, merges) -> str`
    Розгорни токени в байти й декодуй UTF-8 з `errors="replace"` (неповна послідовність байтів
    не повинна давати виняток). Невідомий id (від'ємний або `>= 256 + len(merges)`) це `ValueError`.
    Для будь-якого `text`: `decode(encode(text, merges), merges) == text`.
`cost_ratio(merges, text_a, text_b) -> float`
    У скільки разів `text_a` «дорожчий» за `text_b` за кількістю токенів НА СИМВОЛ:
    `(len(encode(a)) / len(a)) / (len(encode(b)) / len(b))`. Порожній текст це `ValueError`.
"""


def train_bpe(corpus: str, num_merges: int) -> list[tuple[int, int]]:
    raise NotImplementedError


def encode(text: str, merges: list[tuple[int, int]]) -> list[int]:
    raise NotImplementedError


def decode(ids: list[int], merges: list[tuple[int, int]]) -> str:
    raise NotImplementedError


def cost_ratio(merges: list[tuple[int, int]], text_a: str, text_b: str) -> float:
    raise NotImplementedError
