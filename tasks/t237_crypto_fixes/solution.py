"""Завдання №237: виправ криптографічні помилки.

Модуль `vault.py` одного стартапу «працює», але містить типові помилки. Перепиши функції так,
щоб публічний API (імена, аргументи, типи результатів) лишився, а помилки зникли.
Потрібна бібліотека `cryptography` (є в requirements.txt).

Ключі це `bytes`. Для шифрування ключ рівно 32 байти, інакше `ValueError`.

`sign(key, data) -> str`
    HMAC-SHA256 від `data` з ключем `key`, у вигляді малого hex (64 символи).
    Зараз: `sha256(key + data)` (власна схема, вразлива до length extension, CWE-328/327).
`verify(key, data, tag) -> bool`
    Чи збігається `tag` (str або bytes) із `sign(key, data)`. Порівняння за постійний час
    (CWE-208). Регістр має значення (тільки малі hex). Будь-який інший тип `tag`, не-ASCII
    рядок чи порожнє значення це `False`, а не виняток.
`new_token(nbytes=32) -> str`
    Непередбачуваний URL-safe токен (скидання пароля, API-ключ): `nbytes` випадкових байтів
    з криптографічного генератора ОС. `nbytes < 16` це `ValueError`. Зараз: модуль
    `random` (CWE-330: стан відновлюється зі спостережених значень).
`hash_password(password) -> str`, `verify_password(password, stored) -> bool`
    Зберігання пароля: сіль на кожен виклик, повільна KDF зі stdlib: `hashlib.scrypt`
    (n >= 2**14) або `hashlib.pbkdf2_hmac` ('sha256'/'sha512', iterations >= 100_000).
    Формат рядка довільний, але має містити все потрібне для перевірки. Два виклики для
    одного пароля дають різні рядки. `verify_password` повертає `False` (без винятків) для
    невірного пароля й для будь-якого сміття на місці `stored` (порожній рядок, чужий формат,
    старий md5-hex). Зараз: голий MD5 (CWE-327/328).
`encrypt_blob(key, plaintext) -> bytes`, `decrypt_blob(key, blob) -> bytes`
    Зараз AES-ECB: однакові блоки відкритого тексту дають однакові блоки шифртексту, а
    змінити шифртекст можна непомітно. Потрібно автентифіковане шифрування (AEAD, наприклад
    AES-GCM, або шифрування + MAC). Однаковий plaintext двічі дає різні blob (CWE-329).
    `decrypt_blob` піднімає `ValueError` для підробленого, обрізаного, порожнього blob і для
    чужого ключа: ніколи не повертає сміття.
`seal(key, plaintext, aad=b"") -> bytes`, `open_sealed(key, blob, aad=b"") -> bytes`
    AES-GCM з ФІКСОВАНИМ форматом: `nonce (12 байтів) + шифртекст + тег (16 байтів)`.
    Зараз nonce завжди нульовий: повтор nonce з тим самим ключем у GCM розкриває XOR
    відкритих текстів і дозволяє підробляти теги (CWE-323). Кожен виклик `seal` має мати
    свій nonce. `open_sealed` піднімає `ValueError` при підробці, іншому `aad`, чужому ключі
    або надто короткому blob.
"""
import hashlib
import random

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ZERO_NONCE = b"\x00" * 12


def sign(key: bytes, data: bytes) -> str:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return hashlib.sha256(key + data).hexdigest()


def verify(key: bytes, data: bytes, tag) -> bool:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return sign(key, data) == tag


def new_token(nbytes: int = 32) -> str:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return "".join(random.choice("0123456789abcdef") for _ in range(nbytes * 2))


def hash_password(password: str) -> str:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return hashlib.md5(password.encode()).hexdigest()


def verify_password(password: str, stored: str) -> bool:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return hash_password(password) == stored


def _check_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("key must be 32 bytes")


def encrypt_blob(key: bytes, plaintext: bytes) -> bytes:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    _check_key(key)
    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(data) + enc.finalize()


def decrypt_blob(key: bytes, blob: bytes) -> bytes:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    _check_key(key)
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    data = dec.update(blob) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(data) + unpadder.finalize()


def seal(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    _check_key(key)
    return _ZERO_NONCE + AESGCM(key).encrypt(_ZERO_NONCE, plaintext, aad)


def open_sealed(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    _check_key(key)
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)
