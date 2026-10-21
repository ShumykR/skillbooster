"""Завдання №231: envelope encryption полів із PII.

Поля з персональними даними (email, телефон) шифруються ключем даних (DEK), а сам DEK
зберігається лише в ЗАГОРНУТОМУ вигляді: його загортає ключ шифрування ключів (KEK), який
живе в KMS і ніколи не залишає його. Це дає три речі: KEK можна ротувати, не
перешифровуючи дані (перепаковуються лише DEK), шифртекст привʼязаний до місця (таблиця,
поле, запис), а знищення DEK користувача робить його дані назавжди нечитабельними
(crypto-shredding, право на забуття, GDPR art. 17).

Потрібна бібліотека `cryptography` (`AESGCM`). Нічого не пишемо на диск, усе в памʼяті.

KMS (у тестах мок) має два методи; решту про нього знати не треба:
    kms.wrap(kek_id: str, dek: bytes, context: bytes) -> bytes
    kms.unwrap(kek_id: str, wrapped: bytes, context: bytes) -> bytes
`unwrap` піднімає `KeyError`, якщо KEK знищено/невідомий, і `ValueError`, якщо `context` чи
`wrapped` не збігаються (захист від перекладання загорнутого DEK між користувачами).
`context` для користувача: `f"user:{user_id}".encode()`.

Сховище ключів `keystore` це звичайний `dict`, який передає викликач (у production це таблиця
в БД). Клас змінює його НА МІСЦІ. Ключ: `user_id` (str). Значення:
    {"version": int, "kek_id": str, "wrapped_dek": bytes}      активний DEK
    {"version": int, "kek_id": None, "wrapped_dek": None}      надгробок після shred_user
`version` починається з 1 для нового DEK і лише зростає (після надгробка наступний DEK має
`version + 1`). У keystore ніколи не лежить DEK у відкритому вигляді.

`FieldEncryptor(kms, keystore: dict, kek_id: str, rng=os.urandom)`
    `rng(n) -> bytes` єдине джерело випадковості (DEK і nonce): тести підставляють
    детермінований генератор. `kek_id` це поточний KEK для НОВИХ DEK.
`encrypt(user_id, table, field, record_id, plaintext) -> dict`
    Усі аргументи крім `plaintext` це непорожні `str`, `plaintext` це `bytes` (порожні
    байти дозволені), інакше `ValueError`. Якщо в користувача немає активного DEK, створює
    його (32 байти з `rng`), загортає через `kms.wrap(kek_id, dek, context)` і кладе в
    keystore (для кожного користувача DEK один, а не по одному на поле). Шифрує AES-GCM
    з новим 12-байтовим nonce з `rng` і AAD
        json.dumps([table, field, record_id], separators=(",", ":")).encode()
    Повертає запис, який можна класти в БД:
        {"v": 1, "dek_version": <version DEK>, "nonce": bytes, "ciphertext": bytes}
    (`ciphertext` це вихід AESGCM.encrypt, тобто шифртекст + 16-байтовий тег.)
`decrypt(user_id, table, field, record_id, record) -> bytes`
    * структура запису некоректна (не dict, `v != 1`, чужі типи, nonce не 12 байтів,
      ciphertext коротший за 16 байтів) це `ValueError`;
    * користувача немає в keystore, у нього надгробок, `record["dek_version"]` не дорівнює
      поточній `version`, або KMS каже `KeyError` (KEK знищено) це `ShreddedError`:
      дані втрачено свідомо;
    * підробка шифртексту/nonce, інші table/field/record_id, чужий DEK, невідповідний
      context у KMS це `ValueError`. Сміття ніколи не повертається.
`rotate_kek(new_kek_id: str) -> int`
    Перепаковує КОЖЕН активний DEK: `unwrap` старим KEK, `wrap` новим, запис у keystore
    отримує новий `kek_id` і `wrapped_dek`; `version` DEK і самі записи даних НЕ чіпаються
    (їх клас і не бачить). Записи, що вже на `new_kek_id`, і надгробки пропускаються.
    Атомарно: якщо будь-який `unwrap`/`wrap` кидає виняток, keystore і поточний `kek_id`
    лишаються як були, виняток піднімається. Після успіху `kek_id` класу це `new_kek_id`.
    Повертає кількість перепакованих DEK.
`shred_user(user_id) -> bool`
    Замінює запис користувача надгробком (`version` лишається, `kek_id` і `wrapped_dek`
    це `None`). `True`, якщо був активний DEK; `False` для невідомого чи вже знищеного.
    Після цього усі записи користувача це `ShreddedError`, навіть якщо він потім отримає
    новий DEK (новий `encrypt` створює DEK з `version + 1`, а старі записи його не мають).
"""
import os


class ShreddedError(Exception):
    """Ключ даних знищено (crypto-shredding) або KEK недоступний: дані втрачено свідомо."""


class FieldEncryptor:
    def __init__(self, kms, keystore: dict, kek_id: str, rng=os.urandom):
        raise NotImplementedError

    def encrypt(self, user_id: str, table: str, field: str, record_id: str, plaintext: bytes) -> dict:
        raise NotImplementedError

    def decrypt(self, user_id: str, table: str, field: str, record_id: str, record: dict) -> bytes:
        raise NotImplementedError

    def rotate_kek(self, new_kek_id: str) -> int:
        raise NotImplementedError

    def shred_user(self, user_id: str) -> bool:
        raise NotImplementedError
