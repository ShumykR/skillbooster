"""Завдання №180: GraphRAG з нуля.

Векторний пошук добре відповідає на питання про КОНКРЕТНИЙ факт («хто очолює Acme?»), але
слабкий на питання «про весь корпус» («які головні теми?»): top-k найсхожіших чанків покриває
лише одну тему. GraphRAG (Microsoft, 2024) будує з корпусу граф сутностей і звʼязків, ділить
його на спільноти, пише підсумок кожної спільноти й відповідає на глобальні питання через
map-reduce по підсумках. Локальні питання йдуть обходом сусідів сутності. Ти реалізуєш ядро
без бібліотек. Екстрактор сутностей і «LLM» це звичайні функції з тестів.

Чанк: `{"id": str, "text": str}`. `extract(text) -> {"entities": [str], "relations": [[a, label, b], ...]}`.

`normalize(name) -> str`: `" ".join(name.lower().split())`.

`build_graph(chunks, extract) -> dict`
    Граф `{"nodes": {ключ: {"name": str, "chunks": [id...]}}, "edges": {(a, b): {"weight": int,
    "relations": [...], "chunks": [...]}}}`.
    * `chunks` це список dict з унікальними непорожніми `id` та рядковим `text`, інакше `ValueError`;
    * ключ вузла це `normalize(імʼя)`; порожній ключ ігнорується; `name` це ПЕРШЕ зустрінуте
      написання (за порядком чанків і порядком у відповіді `extract`);
    * сутності чанка це `entities` та обидва кінці кожного відношення (відношення додає
      сутності, яких немає в `entities`); `nodes[k]["chunks"]` це відсортовані id чанків, у яких
      зустрілась сутність;
    * ребро це неорієнтована пара: ключ `(a, b)` де `a < b` (за ключами вузлів); петлі (`a == b`)
      ігноруються; `chunks` це відсортовані id чанків, де пару повʼязано відношенням (хоч раз у
      чанку, у будь-якому напрямку); `weight == len(chunks)`; `relations` це відсортовані унікальні
      мітки відношень (рядки, як є) з усіх таких чанків;
    * `extract` повернув не dict чи некоректні відношення (не список із трьох рядків): `ValueError`.
`neighbors(graph, node) -> dict`: `{сусід: вага}` для вузла (порожній dict, якщо немає ребер).

`communities(graph, max_iter=20) -> list[list[str]]`
    Label propagation, детермінована версія. Початкова мітка вузла це його ключ. За ітерацію вузли
    обходяться за зростанням ключа й оновлюються ОДРАЗУ (асинхронно): вузол з сусідами бере мітку з
    найбільшою сумарною вагою ребер до сусідів із цією міткою; при рівності та, що менша за
    алфавітом; вузол без сусідів лишає свою. Зупинка, коли за ітерацію нічого не змінилось або
    після `max_iter` ітерацій (`int >= 1`, інакше `ValueError`). Результат: спільноти (групи
    вузлів з однаковою міткою), кожна відсортована, список відсортований за першим елементом.
`local_search(graph, entities, hops=1) -> dict`
    `entities` це список імен (нормалізуються), `hops` це `int >= 0`. Обхід у ширину від сутностей,
    що є в графі, на `hops` кроків. Результат `{"entities": [досягнуті ключі, відсортовані],
    "chunks": [id чанків досягнутих сутностей: за спаданням кількості досягнутих сутностей, що
    згадані в чанку, далі за id], "missing": [нормалізовані імена, яких немає в графі,
    відсортовані, без дублікатів]}`.
`summarize_communities(graph, comms, summarize) -> list[dict]`
    Для кожної спільноти за порядком `comms` рівно один виклик `summarize(names, chunk_ids)`:
    `names` це відображувані імена вузлів (`name`) у порядку ключів, `chunk_ids` це відсортовані
    унікальні id чанків спільноти. Елемент результату: `{"id": "c<індекс>", "entities": [ключі],
    "chunks": [id], "summary": рядок з summarize}`.
`global_search(summaries, question, llm, min_score=1) -> dict`
    Map-reduce. Map: для КОЖНОЇ спільноти за порядком `llm("map", question, summary_text)` повертає
    `(score, text)` (`int` 0..100 це корисність підсумку для питання). Залишаються спільноти зі
    `score >= min_score`, впорядковані за спаданням score, далі за порядком у `summaries`. Reduce:
    якщо хоч одна лишилась, рівно один виклик `llm("reduce", question, [тексти лишених у цьому
    порядку])` повертає рядок. Результат `{"answer": рядок | "", "used": [id спільнот],
    "calls": кількість викликів llm}`. Якщо жодної не лишилось: `answer == ""`, `used == []`,
    reduce не викликається.
`chunks_for(summaries, used) -> list[str]`: відсортовані унікальні id чанків спільнот із `used`
    (невідомий id в `used`: `ValueError`).
`keyword_search(chunks, query, k) -> list[str]`
    Базовий «векторний» пошук для порівняння: токени це `set(re.findall(r"\\w+", text.lower()))`
    слів завдовжки >= 3; оцінка чанка це розмір перетину токенів запиту й чанка; повертаються id
    `k` чанків з оцінкою > 0 за спаданням оцінки, при рівності за id. `k` це `int >= 1`.
`theme_coverage(chunk_ids, themes) -> float`
    `themes` це `{id чанка: тема}`; частка тем (з усіх у `themes`), представлених серед
    `chunk_ids`; `round(.., 4)`; порожній `themes`: `ValueError`; id, яких немає в `themes`,
    ігноруються.
"""
import re  # noqa: F401  (знадобиться)


def normalize(name: str) -> str:
    raise NotImplementedError


def build_graph(chunks: list, extract) -> dict:
    raise NotImplementedError


def neighbors(graph: dict, node: str) -> dict:
    raise NotImplementedError


def communities(graph: dict, max_iter: int = 20) -> list:
    raise NotImplementedError


def local_search(graph: dict, entities: list, hops: int = 1) -> dict:
    raise NotImplementedError


def summarize_communities(graph: dict, comms: list, summarize) -> list:
    raise NotImplementedError


def global_search(summaries: list, question: str, llm, min_score: int = 1) -> dict:
    raise NotImplementedError


def chunks_for(summaries: list, used: list) -> list:
    raise NotImplementedError


def keyword_search(chunks: list, query: str, k: int) -> list:
    raise NotImplementedError


def theme_coverage(chunk_ids: list, themes: dict) -> float:
    raise NotImplementedError
