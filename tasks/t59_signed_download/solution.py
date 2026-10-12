"""Завдання №59: Підписані URL та доступ до файлів (IDOR).

Ендпоінт `GET /download?file=123` віддає файл будь-кому, хто підставив чужий id (IDOR / CWE-639).
Побудуй безпечний потік: сервіс видає короткоживуче підписане посилання лише тим, хто має право,
а віддача файлу перевіряє підпис І право ще раз.

sign_download(file_id, user_id, expires_at, secret) -> dict[str, str]
    параметри посилання: {"file": file_id, "uid": str(user_id), "exp": str(expires_at), "sig": <hex>},
    sig = HMAC-SHA256(secret, f"{file_id}\\n{user_id}\\n{expires_at}") у hex (усі три поля під підписом).
verify_download(params, secret, *, now, current_user_id) -> str  (повертає file_id)
    перевірки в такому порядку: усі 4 параметри є і `exp` ціле число, інакше SignatureError; підпис збігається
    (порівняння сталого часу), інакше SignatureError; `now > exp` -> Expired (підклас SignatureError);
    `uid` збігається з `current_user_id` (посилання, що витекло, чужому не допоможе), інакше SignatureError.

FileService(files, secret, clock, ttl=300)
    `files`: {file_id: {"owner_id": int, "shared_with": set[int], "path": str}}; `user`: {"id": int, "is_admin": bool}.
    download_link(user, file_id) -> dict: параметри підписаного посилання з терміном `clock() + ttl` (цілі секунди).
    Право мають власник, ті, з ким поділились, і адмін. Інакше FileNotFound, і ТАКА Ж помилка (те саме повідомлення
    "file not found"), як для неіснуючого файлу, щоб не розкривати, що файл існує. file_id має відповідати
    `^[A-Za-z0-9_-]{1,64}$`, інакше FileNotFound.
    open(params, user) -> str: шлях файлу. Перевіряє підпис (verify_download з поточним користувачем), а потім ПРАВО
    ЩЕ РАЗ (доступ могли скасувати вже після видачі посилання); будь-яка відмова в праві це FileNotFound.
    Шлях на диску беремо тільки зі сховища `files`, ніколи з параметрів посилання.
"""
import hashlib  # noqa: F401
import hmac  # noqa: F401
import re  # noqa: F401
from typing import Callable


class SignatureError(Exception):
    pass


class Expired(SignatureError):
    pass


class FileNotFound(Exception):
    pass


def sign_download(file_id: str, user_id: int, expires_at: int, secret: str) -> dict[str, str]:
    raise NotImplementedError


def verify_download(params: dict[str, str], secret: str, *, now: float, current_user_id: int) -> str:
    raise NotImplementedError


class FileService:
    def __init__(self, files: dict[str, dict], secret: str, clock: Callable[[], float], ttl: int = 300) -> None:
        raise NotImplementedError

    def download_link(self, user: dict, file_id: str) -> dict[str, str]:
        raise NotImplementedError

    def open(self, params: dict[str, str], user: dict) -> str:
        raise NotImplementedError
