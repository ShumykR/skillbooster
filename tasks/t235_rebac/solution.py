"""Завдання №235: ReBAC у стилі Zanzibar.

Доступ визначається не ролями, а ВІДНОСИНАМИ між обʼєктами. Сховище це набір кортежів
`(object, relation, subject)`, усі значення рядки:

    ("doc:1",    "parent", "folder:a")           документ лежить у теці
    ("folder:a", "owner",  "user:alice")         alice власник теки
    ("folder:a", "viewer", "group:eng#member")   усі члени групи eng бачать теку
    ("group:eng","member", "user:bob")           bob член групи

Типи й відносини (схема зафіксована):
    group:   `member`
    folder:  `owner`, `editor`, `viewer`, `parent`
    doc:     `owner`, `editor`, `viewer`, `parent`
`parent` має субʼєкт `folder:<id>`. Інші відносини мають субʼєкт `user:<id>` або userset
`group:<id>#member` (усі, хто є `member` цієї групи). Ідентифікатор не порожній і не містить
`:`, `#`, пробілів. Кортеж іншого вигляду це `ValueError`.

Правила виведення (`X` це folder або doc, `P` його `parent`):
    editor(X) ⊇ owner(X)            viewer(X) ⊇ editor(X)
    editor(X) ⊇ editor(P)           viewer(X) ⊇ viewer(P)
`owner` НЕ успадковується від теки (власник теки не стає власником кожного документа).
Групи вкладаються: `("group:a","member","group:b#member")` робить членів b членами a.

`ReBAC(max_depth=10)`
`write(add=(), remove=()) -> int`
    Атомарна нова версія. Спершу застосовуються `remove`, потім `add`. Якщо хоч один
    кортеж некоректний, змін немає й версія та сама (`ValueError`). Дублікати й видалення
    неіснуючих кортежів безпечні. Якщо множина кортежів не змінилась, версія НЕ зростає.
    Повертає поточну версію. Початкова версія 0 (порожньо). Кожна зміна: версія +1.
`version -> int`
`tuples(at_version=None) -> list[tuple]`
    Усі кортежі знімка, відсортовані.
`check(user, relation, obj, at_version=None) -> Decision`
    `user` це `user:<id>`, `relation` це `owner`/`editor`/`viewer` (для group тільки
    `member`), інакше `ValueError`. `at_version` це знімок (аналог zookie): `None` це
    остання версія, версія з майбутнього це `ValueError`. Повертає `Decision`:
    * `allowed`: чи має `user` відношення `relation` до `obj` (прямо чи виведено);
    * `path`: кортежі сховища (у порядку від `obj` до користувача), через які знайдено доступ,
      НАЙКОРОТШИЙ шлях за кількістю кортежів; правила виведення кортежів не додають;
      порожній кортеж, якщо відмова;
    * `reason`: `"allowed"`, `"no_path"` або `"depth_limit"` (шлях довший за `max_depth`
      кортежів існував би, але відсікся).
    Шлях з рівно `max_depth` кортежів дозволений, з `max_depth + 1` ні (відмова,
    fail closed). Цикли (група в групі, тека у власному піддереві) не зациклюють перевірку.
`list_objects(user, relation, obj_type, at_version=None) -> list[str]`
    Відсортований список обʼєктів типу `obj_type` (`"doc"`/`"folder"`/`"group"`), до яких
    `check(user, relation, obj)` дозволяє доступ. Розглядаються лише обʼєкти, що згадані в
    кортежах (як обʼєкт або як батьківська тека).

`Decision` це незмінний датаклас (див. нижче).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    path: tuple = ()
    reason: str = "no_path"


class ReBAC:
    def __init__(self, max_depth: int = 10):
        raise NotImplementedError

    @property
    def version(self) -> int:
        raise NotImplementedError

    def write(self, add=(), remove=()) -> int:
        raise NotImplementedError

    def tuples(self, at_version=None) -> list:
        raise NotImplementedError

    def check(self, user: str, relation: str, obj: str, at_version=None) -> Decision:
        raise NotImplementedError

    def list_objects(self, user: str, relation: str, obj_type: str, at_version=None) -> list:
        raise NotImplementedError
