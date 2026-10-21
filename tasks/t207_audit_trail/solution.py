"""Завдання №207: Audit trail на хеш-ланцюжку.

Журнал дій агента й рішень моделі має бути append-only і захищеним від тихих змін: вставка, видалення, зміна чи
переставлення записів мають виявлятись. А ще GDPR: за запитом суб'єкта треба видалити його персональні дані, не зламавши
ланцюжок. Тому PII не входить у хеш запису, замість нього в хеш іде ключовий HMAC значення; видалення стирає значення й
лишає HMAC.

Канонічний JSON: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
GENESIS = "0" * 64 (prev першого запису).

AuditLog(hmac_key: bytes, clock)
    clock() повертає ts (число).

    .append(actor, action, data, pii=None, subject=None) -> int
        Додає запис і повертає його seq (0, 1, 2, ...). actor і action: непорожні рядки; data: dict лише з JSON-типів
        БЕЗ персональних даних; pii: dict {поле: значення} з персональними даними (значення JSON-типів); subject: ідентифікатор
        суб'єкта даних (рядок) або None. Порушення: ValueError.
        Запис це dict:
            {"seq", "ts", "actor", "action", "data",
             "pii_hashes": {поле: HMAC-SHA256(key, canonical({"seq": seq, "field": поле, "value": значення})).hexdigest()},
             "subject_hash": HMAC-SHA256(key, canonical({"subject": subject})).hexdigest() або None,
             "pii": {поле: значення} (копія pii або {}),
             "erased": False,
             "prev": hash попереднього запису (GENESIS для першого),
             "hash": sha256(canonical({"seq", "ts", "actor", "action", "data", "pii_hashes", "subject_hash", "prev"})).hexdigest()}
        Поля "pii" та "erased" НЕ входять у хеш запису (саме тому їх можна стерти).

    .export() -> list[dict]       глибока копія всіх записів (зміна копії не впливає на журнал).
    .anchor() -> {"count": n, "hash": хеш останнього запису (GENESIS, якщо журнал порожній)}
        Якір: його зберігають окремо (інша система, підпис), щоб виявити відсікання хвоста.
    .erase_subject(subject) -> int
        Для кожного запису з subject_hash цього суб'єкта: "pii" = {}, "erased" = True. Повертає кількість стертих записів
        (запис, що вже стертий, не рахується вдруге). pii_hashes і хеші не змінюються: verify() далі проходить.

verify(entries, anchor=None, hmac_key=None) -> dict    (вільна функція)
    Перевіряє список записів (наприклад, export()). Результат {"ok": bool, "broken_at": index | None, "reason": код | None}.
    Для кожного запису за порядком у списку (index = позиція) перевірки в такому порядку, перша невдала зупиняє:
        "bad-seq":      entry["seq"] != index
        "bad-link":     entry["prev"] != hash попереднього запису (GENESIS для index 0)
        "bad-hash":     entry["hash"] не дорівнює перерахованому sha256 (з полів, що входять у хеш)
        "pii-mismatch": лише якщо задано hmac_key і запис не стертий ("erased" False): pii_hashes не збігаються з HMAC від
                        значень у "pii" (поля чи значення підмінили, не чіпаючи хеш), або набір полів pii != набір ключів pii_hashes
    Після всіх записів, якщо задано anchor: len(entries) != anchor["count"] або (останній hash або GENESIS) != anchor["hash"]:
        reason "truncated", broken_at = len(entries).
    Усе гаразд: {"ok": True, "broken_at": None, "reason": None}. Порожній список без anchor це ok.
    Відсутні ключі в записі чи сміття замість запису: той самий результат "bad-seq" для цього index (verify не кидає винятків).
"""


class AuditLog:
    def __init__(self, hmac_key, clock):
        raise NotImplementedError

    def append(self, actor, action, data, pii=None, subject=None):
        raise NotImplementedError

    def export(self):
        raise NotImplementedError

    def anchor(self):
        raise NotImplementedError

    def erase_subject(self, subject):
        raise NotImplementedError


def verify(entries, anchor=None, hmac_key=None):
    raise NotImplementedError
