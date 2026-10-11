"""Завдання №167: ін'єкція в HTTP-заголовки (CRLF).

Якщо в `Location`, `Set-Cookie` чи `Content-Disposition` потрапляє значення від користувача, а в
ньому є `\\r\\n`, атакувальник дописує власні заголовки або навіть тіло відповіді (response
splitting). Реалізуй три функції, які будують такі заголовки безпечно. Усі помилки це
`ValueError`.

`safe_header(name, value) -> tuple[str, str]`
    - `name` має бути токеном RFC 7230: непорожній, лише символи
      ``!#$%&'*+-.^_`|~``, цифри й латинські літери;
    - `value` має бути `str` без символів керування, окрім табуляції (`\\t`); тобто `\\r`, `\\n`,
      `\\x00` та інші коди < 0x20 і 0x7f заборонені; усі символи мають бути в діапазоні latin-1
      (код <= 255): HTTP-заголовки не мають юнікоду, його кодують окремо;
    - початкові й кінцеві пробіли/табуляції значення обрізаються. Повертає `(name, value)`.

`content_disposition(filename, inline=False) -> str`
    - з `filename` береться лише останній компонент шляху (розділювачі `/` і `\\`);
    - символи керування (код < 0x20 або 0x7f) будь-де в `filename`, а також порожнє імʼя, `.` та
      `..` після відкидання шляху це помилка;
    - ASCII-запасний варіант: кожен символ, що не є друкованим ASCII (0x20..0x7e), а також
      `"`, `\\`, `;`, `%`, замінюється на `_`;
    - якщо запасний варіант збігається з імʼям: `attachment; filename="<імʼя>"`;
      інакше додається `filename*` за RFC 5987 з `urllib.parse.quote(імʼя, safe="")`:
      `attachment; filename="<запасний>"; filename*=UTF-8''<quote>`;
    - тип `inline` замість `attachment`, якщо `inline=True`.

`build_set_cookie(name, value, *, max_age=None, domain=None, path="/", secure=True,
                 httponly=True, samesite="Lax") -> str`
    - `name`: токен RFC 7230 (як вище);
    - `value`: без пробілів, керувальних символів, `"`, `,`, `;`, `\\` і не-ASCII;
      порожнє значення дозволене;
    - `max_age`: `None` або невідʼємне `int` (`bool` не підходить);
    - `domain`: `None` або непорожній рядок із лише літер, цифр, `.` і `-`;
    - `path`: рядок, що починається з `/`, без `;` і керувальних символів;
    - `samesite`: "Strict", "Lax" або "None" без урахування регістру (у виході нормалізована
      форма "Strict"/"Lax"/"None"); "None" вимагає `secure=True`;
    - префікс імені `__Secure-` вимагає `secure=True`; `__Host-` вимагає `secure=True`,
      `path == "/"` і відсутнього `domain`;
    - порядок частин у виході: `name=value`, `Max-Age=N`, `Domain=d`, `Path=p`, `Secure`,
      `HttpOnly`, `SameSite=X`, розділені `"; "`; відсутні частини пропускаються.
"""


def safe_header(name: str, value: str) -> tuple[str, str]:
    raise NotImplementedError


def content_disposition(filename: str, inline: bool = False) -> str:
    raise NotImplementedError


def build_set_cookie(name, value, *, max_age=None, domain=None, path="/", secure=True,
                     httponly=True, samesite="Lax") -> str:
    raise NotImplementedError
