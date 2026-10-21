"""Завдання №234: DPoP (RFC 9449): токени, привʼязані до ключа клієнта.

Вкрадений bearer-токен працює в кого завгодно. DPoP привʼязує access-токен до ключа клієнта: при
кожному запиті клієнт додає заголовок `DPoP: <proof>`, JWT, підписаний своїм приватним ключем, а
сервер перевіряє, що ключ у proof відповідає `cnf.jkt` у токені. Без приватного ключа вкрадений
токен марний. Асиметричні підписи тут НЕ реалізуємо: перевірку підпису передають параметром.

Формат proof: компактний JWT `<header>.<payload>.<signature>`, кожна частина base64url БЕЗ `=`;
header і payload це JSON-обʼєкти. `signing_input = (header_b64 + "." + payload_b64).encode("ascii")`.
header: `{"typ": "dpop+jwt", "alg": ..., "jwk": {публічний ключ}}`.
payload: `{"jti", "htm", "htu", "iat", "ath"?}`.

`jwk_thumbprint(jwk) -> str`
    Відбиток JWK за RFC 7638: SHA-256 від канонічного JSON (лише обовʼязкові члени, ключі за
    алфавітом, `separators=(",", ":")`, без пробілів), base64url без `=`. Обовʼязкові члени:
    `RSA`: `e`, `kty`, `n`; `EC`: `crv`, `kty`, `x`, `y`; `OKP`: `crv`, `kty`, `x`. Інший `kty`
    або відсутній обовʼязковий член: `ValueError`. Зайві члени (`kid`, `use`...) у відбиток не входять.

`DPoPError(reason)`: уже написаний, `.reason` це один із кодів нижче.

`DPoPVerifier(verify, clock, iat_window=60)`
    `verify(jwk, signing_input: bytes, signature: bytes) -> bool` перевіряє підпис ключем `jwk`.
    `clock()` повертає секунди.

`DPoPVerifier.check(proof, method, url, access_token=None, token_cnf_jkt=None) -> dict`
    `method` і `url` це метод і повний URL ЦЬОГО запиту (з query). `access_token` передають
    тоді, коли запит іде з access-токеном (ресурсний сервер), і не передають на token endpoint.
    `token_cnf_jkt` це `cnf.jkt` з access-токена. Успіх повертає `{"jkt": відбиток ключа з proof,
    "jti": jti}`. Помилка це `DPoPError` з кодом (перевіряй у цьому порядку):
    1. `malformed`: не рядок, не три частини, не base64url/JSON, header чи payload не обʼєкт;
    2. `bad_typ`: `typ` не рівно `dpop+jwt`;
    3. `bad_alg`: `alg` не з allowlist `ES256`, `ES384`, `EdDSA`, `PS256`, `RS256` (`none` і `HS*`
       заборонені: симетричний підпис нічого не привʼязує);
    4. `bad_jwk`: у header немає `jwk`-обʼєкта, або в ньому приватні члени (`d`, `p`, `q`, `dp`,
       `dq`, `qi`, `k`), або `jwk_thumbprint` піднімає `ValueError`;
    5. `bad_signature`: `verify(jwk, signing_input, signature)` (jwk саме з header, підпис це
       декодовані байти третьої частини) повернув не `True` або кинув виняток (fail closed).
       Жоден claim не довіряється до успішної перевірки підпису;
    6. `bad_claims`: `jti` не непорожній рядок; `htm`, `htu` не рядки; `iat` не число (`bool` це
       не число);
    7. `htm_mismatch`: `htm != method` (порівняння точне, регістр має значення);
    8. `htu_mismatch`: `htu` містить `?` чи `#`, або не дорівнює URL запиту без query і fragment
       після нормалізації: схема й хост у нижній регістр, порт за замовчуванням (`:443` для https,
       `:80` для http) відкидається, порожній шлях це `/`, шлях порівнюється точно;
    9. `expired`: `abs(clock() - iat) > iat_window` (і давні, і «з майбутнього»; межа включно);
    10. `bad_ath`: якщо `access_token` передано: `ath` має дорівнювати
        `base64url(sha256(access_token.encode("ascii")))` без `=` (порівняння за постійний час);
        відсутній `ath` теж `bad_ath`;
    11. `unbound_token`: `access_token` передано, а `token_cnf_jkt is None` (токен не привʼязаний
        до ключа, ресурс його не приймає за DPoP);
    12. `key_mismatch`: `token_cnf_jkt` задано (не `None`), і він не дорівнює відбитку ключа з proof
        (порівняння за постійний час);
    13. `replay`: такий самий `jti` від того самого ключа вже приймали, і його proof ще в межах вікна.
    Лише повністю прийнятий proof записується в память для виявлення повторів (відхилений не
    «спалює» jti). Записи, чий `iat` вийшов за вікно, можна забути: такий proof і так дасть `expired`.
"""


class DPoPError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def jwk_thumbprint(jwk: dict) -> str:
    raise NotImplementedError


class DPoPVerifier:
    def __init__(self, verify, clock, iat_window: int = 60):
        raise NotImplementedError

    def check(self, proof, method, url, access_token=None, token_cnf_jkt=None) -> dict:
        raise NotImplementedError
