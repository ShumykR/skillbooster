"""Завдання №66: Мережа: де саме ламається `curl -v`.

`diagnose_curl(output)` отримує ПОВНИЙ вивід `curl -v` (stderr разом із stdout) і каже, на якому етапі запит
зламався і чому. Етапи йдуть по порядку: DNS -> TCP -> TLS -> HTTP.

Результат: {"stage": ..., "cause": ..., "detail": {...}}.

Основний сигнал це останній рядок виду `curl: (N) повідомлення`. Якщо його немає, запит дійшов до відповіді,
і діагноз ставиться за останнім рядком статусу `< HTTP/1.1 502 Bad Gateway` чи `< HTTP/2 200`.

| код curl | stage | cause                                                                              |
|----------|-------|------------------------------------------------------------------------------------|
| 6        | dns   | resolve_failed; detail {"host": імʼя з "Could not resolve host: X"}                 |
| 7        | tcp   | refused                                                                            |
| 28       | залежить від того, що вже було у виводі:                                           |
|          | http  | read_timeout, якщо є рядок запиту `> GET ...` (запит надіслано, відповіді нема)      |
|          | tls   | handshake_timeout, якщо є рядок `TLS handshake, Client hello` (але нема `> GET`)     |
|          | tcp   | connect_timeout в інших випадках                                                   |
| 35       | tls   | not_tls, якщо повідомлення містить "wrong version number" (HTTP на TLS-порту);     |
|          |       | protocol_version, якщо "protocol version"; інакше handshake_failed                 |
| 52       | http  | empty_reply                                                                        |
| 56       | http  | connection_reset                                                                   |
| 60       | tls   | cert_expired ("has expired"), hostname_mismatch ("no alternative certificate       |
|          |       | subject name matches target host name" або "does not match"), untrusted_issuer     |
|          |       | ("self-signed" або "unable to get local issuer"), інакше cert_invalid               |

`detail`:
- для кодів 7, 28 і 35: {"host": ..., "port": int} з ОСТАННЬОГО рядка `* Trying <адреса>:<порт>...`
  (IPv6 у дужках `[::1]:443`); якщо такого рядка немає, {};
- cert_expired: {"expire_date": значення з рядка `*  expire date: ...` (пробіли згорнуті до одного)} або {};
- hostname_mismatch: {"target": імʼя в одинарних лапках із повідомлення};
- untrusted_issuer: {"reason": "self-signed"} або {"reason": "unknown_issuer"};
- решта помилок (52, 56, cert_invalid): {}.
Невідомий код curl (інший за наведені): {"stage": "unknown", "cause": "unknown_error", "detail": {}}.

Без рядка `curl: (N)` (відповідь отримано), stage завжди "http", а detail містить:
`status` (число, останній статус у виводі), `redirects` (скільки відповідей 3xx було ДО останньої),
і `tls` (версія з рядка `* SSL connection using TLSv1.3 / ...`), якщо такий рядок є. cause за статусом:
2xx ok; 3xx redirect (+ `location` з останнього заголовка `< location:` / `< Location:`, якщо є);
401 і 403 unauthorized; 429 rate_limited (+ `retry_after` числом, з `< retry-after:`, якщо є); інші 4xx client_error;
502 bad_gateway; 503 service_unavailable; 504 gateway_timeout; інші 5xx server_error.
Порожній вивід або без жодного статусу й без `curl: (N)`: {"stage": "unknown", "cause": "no_signal", "detail": {}}.
"""
import re  # noqa: F401


def diagnose_curl(output: str) -> dict:
    raise NotImplementedError
