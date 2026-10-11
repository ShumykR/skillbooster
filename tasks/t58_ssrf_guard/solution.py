"""Завдання №58: Захист від SSRF.

Сервіс завантажує зображення за URL від користувача. Зловмисник підставляє
внутрішні адреси (метадані хмари 169.254.169.254, localhost, приватні мережі)
і краде секрети. Реалізуй валідацію URL ДО запиту.
"""
import ipaddress
import socket
from typing import Callable
from urllib.parse import urlsplit


class UnsafeURL(ValueError):
    pass


def default_resolve(host: str) -> list[str]:
    """DNS-резолв у список IP-адрес (у тестах підміняється)."""
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def validate_url(url: str, resolve: Callable[[str], list[str]] = default_resolve) -> str:
    """Повертає url, якщо він безпечний; інакше піднімає UnsafeURL.

    Вимоги:
    - лише схеми http і https;
    - без userinfo (`http://good.com@127.0.0.1/` це пастка);
    - порт лише за замовчуванням, 80 або 443;
    - `localhost` та піддомени `.localhost`/`.internal` заборонені;
    - IP-літерали, включно з екзотичними (`2130706433`, `0x7f.1`, `127.1`, `[::1]`,
      `[::ffff:127.0.0.1]`), перевіряються як IP, а не як імʼя;
    - для імен виконується resolve(host); БУДЬ-ЯКА з адрес має бути публічною
      (`ipaddress.ip_address(x).is_global`), інакше UnsafeURL.
    """
    raise NotImplementedError
