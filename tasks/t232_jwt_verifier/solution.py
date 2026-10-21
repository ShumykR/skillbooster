"""Завдання №232: JWT-верифікатор без пасток.

Бібліотеки JWT роками мали однакові діри: `alg: none`, підміна RS256 на HS256 з публічним ключем
як секретом, довіра до `kid` з токена, ігнорування `aud`/`iss`. Тут ти пишеш верифікатор, який
перевіряє все сам і відмовляє з ЧИТАБЕЛЬНИМ кодом причини (`JwtError.code`). Годинник і
завантаження JWKS передаються ззовні, мережі немає.

Алгоритми: `HS256` (HMAC-SHA256 зі stdlib), `RS256` і `ES256` (асиметричний підпис НЕ
реалізуємо: його перевіряє функція `verify(key_material, signing_input: bytes, signature: bytes)
-> bool`, яку передає викликач; результат лише строго `True` це успіх, виняток це невдача).
`signing_input` це `ASCII(header_b64 + "." + payload_b64)` у вигляді bytes, `signature` це
розкодований (base64url) третій сегмент.

JWKS: `jwks_fetch() -> {"keys": [ {"kid", "kty", "alg", "key"}, ... ]}`. `kty` для `HS256` це
`"oct"` (`key` це bytes-секрет), для `RS256` `"RSA"`, для `ES256` `"EC"` (`key` це непрозорий
обʼєкт відкритого ключа, який ти передаєш у `verify`). Запис без будь-якого з чотирьох полів
ігнорується. Якщо в одному JWKS два запити з однаковим `kid`, цей `kid` не довіряється
(двозначність).

`class JwtError(Exception)`: має атрибут `code` (рядок).

`class JwtVerifier(jwks_fetch, *, issuer, audience, algorithms, clock, verify=None, leeway=30,
typ="at+jwt", jwks_ttl=300, min_refetch_interval=30, supported_crit=())`
    * `algorithms` це allowlist; елемент не з `HS256/RS256/ES256` (зокрема `"none"`) це
      `ValueError` при створенні. Якщо в allowlist є не-HS256, а `verify` не передано, теж
      `ValueError`. `clock()` повертає секунди (float).
`verify_token(token) -> dict`
    Повертає claims (payload) або піднімає `JwtError`. Перевірки У ЦЬОМУ ПОРЯДКУ, перша
    невдала дає код:
    1. `malformed`: `token` не str; не рівно три сегменти через `.`; сегмент не base64url
       (лише `A-Za-z0-9_-`, без `=`); перші два сегменти не порожні й це JSON-обʼєкти; третій
       сегмент МОЖЕ бути порожнім (токен `alg: none`) і тоді відмова прийде з кроку 2.
    2. `alg_not_allowed`: `alg` у заголовку не рядок або не входить в `algorithms` (порівняння
       точне: `"hs256"` і `"None"` не збігаються).
    3. заголовок `crit`: якщо є, то це непорожній список рядків і кожне імʼя є ключем заголовка,
       інакше `malformed`; імʼя не з `supported_crit` це `crit_unsupported`.
    4. `bad_typ`: заголовок `typ` відсутній, не рядок або не збігається з `typ` без урахування
       регістру.
    5. `unknown_kid`: `kid` відсутній чи порожній; або ключа з таким `kid` немає в JWKS (див.
       кеш нижче). `jwks_unavailable`: ключі потрібно завантажити, а `jwks_fetch` кидає виняток
       чи повертає непридатну структуру, або кеш прострочений, а завантажити не можна.
    6. `key_mismatch`: `alg` ключа в JWKS не дорівнює `alg` токена, або `kty` ключа не той, що
       потрібен алгоритму (так ловиться підміна RS256 на HS256: токен каже HS256, ключ у JWKS
       RSA), або для HS256 `key` не bytes. Алгоритм обирає КЛЮЧ, а не токен.
    7. `bad_signature`: підпис не збігається (HMAC порівнюй за постійний час). Підпис
       перевіряється ДО claims: підроблений токен із простроченим `exp` дає `bad_signature`.
    8. claims: `exp` відсутній це `missing_claim`; `exp`/`nbf` не число (і не bool) це
       `malformed`; `expired`, якщо `now >= exp + leeway`; `not_yet_valid` (лише якщо `nbf`
       є), якщо `now + leeway < nbf`; `bad_issuer`, якщо `iss` не дорівнює `issuer` точно;
       `bad_audience`, якщо `aud` (рядок або список рядків) не містить `audience` точно
       (підрядок не збігається, відсутній `aud` це відмова).

    Кеш JWKS (`now = clock()`):
    * ключі «свіжі», доки `now - fetched_at < jwks_ttl` (час останнього УСПІШНОГО завантаження).
      Відомий `kid` зі свіжого кешу обслуговується без виклику `jwks_fetch`.
    * Завантаження дозволене, якщо спроб ще не було, або з моменту останньої СПРОБИ (успішної чи
      ні) минуло `>= min_refetch_interval`. Інакше: свіжий кеш без цього `kid` це `unknown_kid`
      (нова спроба ЗАБОРОНЕНА: так атакувальник випадковими `kid` не змусить сервер
      заспамити JWKS-ендпоінт), прострочений кеш це `jwks_unavailable`.
    * Після успішного завантаження кеш повністю замінюється; після невдалого лишається як був.
"""


class JwtError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


class JwtVerifier:
    def __init__(self, jwks_fetch, *, issuer, audience, algorithms, clock, verify=None, leeway=30,
                 typ="at+jwt", jwks_ttl=300, min_refetch_interval=30, supported_crit=()):
        raise NotImplementedError

    def verify_token(self, token) -> dict:
        raise NotImplementedError
