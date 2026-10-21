"""Завдання №240: інтерпретатори в коді: виправ.

Нижче п'ять місць, де дані користувача потрапляють у ІНТЕРПРЕТАТОР: `pickle`, YAML-завантажувач,
`eval`, `str.format` і регулярний вираз. Усе працює на чесних даних, а зловмисник виконує код,
читає секрети чи вішає процес. Перепиши функції за правилами, публічний API лишається.
Усі «погані» входи дають `ValueError` (не `TypeError`, не `yaml.YAMLError`, не `SyntaxError`).

1. Cookie сесії (CWE-502).
   `dump_session(data: dict, secret: bytes) -> str`
   `load_session(cookie: str, secret: bytes) -> dict`
   Формат: `<payload>.<tag>`, де `payload` це base64url БЕЗ `=` від
   `json.dumps(data, separators=(",", ":"), sort_keys=True)` у UTF-8, а `tag` це малий hex
   `HMAC-SHA256(secret, payload)` (HMAC рахується від рядка `payload` у ASCII). `load_session`
   спершу перевіряє тег за постійний час, і лише потім розбирає payload. Не-рядок, відсутня
   крапка, не-ASCII, неправильний тег, не-JSON чи JSON не-обʼєкт це `ValueError`.
   Зараз: base64 від `pickle.dumps(...)` без підпису.

2. Конфігурація (CWE-502, CWE-20).
   `load_config(text: str) -> dict`
   Розбирає YAML-мапу лише з простих типів. Теги `!!python/...` та інші небезпечні конструкції
   це `ValueError`. Не-мапа, помилка синтаксису, текст довший за 65536 символів це `ValueError`.
   Зараз: `yaml.load(text, Loader=yaml.Loader)`.

3. Калькулятор (CWE-95).
   `calc(expr: str) -> int | float`
   Дозволено: числові літерали (`int`, `float`; не `bool`, не `complex`, не рядки), бінарні
   `+ - * / // % **`, унарні `+ -`, дужки. Усе інше (імена, виклики, атрибути, індекси,
   порівняння, `<<`, `~`, умовні й лямбда-вирази, включення (comprehensions)) це `ValueError`. Пробіли по краях ігноруються. Семантика
   Python: `/` повертає float, `//` і `%` як у Python. Ліміти: довжина `expr` <= 200 символів;
   показник степеня за модулем <= 1000; жоден проміжний `int` не має бути за модулем >= 2**1024;
   результат float має бути скінченним, `complex` (`(-8)**0.5`) це `ValueError`; ділення на нуль теж `ValueError`.
   Зараз: `eval(expr)`.

4. Шаблон листа (CWE-1336, CWE-134).
   `render_email(template: str, user: dict) -> str`
   Плейсхолдер це РІВНО `{name}`, `{email}` або `{plan}` (значення береться з `user` і
   перетворюється на `str`). `{{` і `}}` дають літеральні `{` і `}`. Усе інше в фігурних
   дужках (`{user.x}`, `{name!r}`, `{name:>10}`, `{0}`, `{}`, `{unknown}`, незакритий `{`) та
   відсутнє в `user` поле це `ValueError`. Підстановка робиться ОДИН раз: значення
   користувача, що містить `{email}`, лишається як є.
   Зараз: `template.format(user=User(**user))` (доступ до `{user.__init__.__globals__}`).

5. Валідація email (CWE-1333).
   `validate_email(addr: str) -> bool`
   Правила (лише ASCII): довжина <= 254; рівно один `@`; локальна частина 1..64 символи з
   `A-Za-z0-9`, розділені одиночними `.`, `_`, `+` чи `-` (розділювач не на краях і не
   подвійний); домен це >= 2 міток через `.`, кожна 1..63 символи `A-Za-z0-9-` без `-` на краях,
   остання мітка лише літери й довжиною >= 2. Це `fullmatch`: `"a@b.co\\n"` не валідний.
   Не-рядок це `False`. На ЖОДНОМУ вході (до 100000 символів) функція не має працювати
   довше за мілісекунди: тест запускає її в окремому процесі з таймаутом.
   Зараз: вкладені квантифікатори (катастрофічний backtracking).
"""
import base64
import pickle
import re

import yaml

SECRET_KEY = "sk_live_DO_NOT_LEAK_8f3a"


def dump_session(data: dict, secret: bytes) -> str:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return base64.urlsafe_b64encode(pickle.dumps(data)).decode()


def load_session(cookie: str, secret: bytes) -> dict:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return pickle.loads(base64.urlsafe_b64decode(cookie))


def load_config(text: str) -> dict:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return yaml.load(text, Loader=yaml.Loader)


def calc(expr: str):
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return eval(expr)


class User:
    def __init__(self, name, email, plan):
        self.name, self.email, self.plan = name, email, plan


def render_email(template: str, user: dict) -> str:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return template.format(user=User(user["name"], user["email"], user["plan"]), **user)


_EMAIL_RE = re.compile(r"^([a-zA-Z0-9]+[._+-]?)+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$")


def validate_email(addr: str) -> bool:
    # НАЇВНА ВРАЗЛИВА РЕАЛІЗАЦІЯ: перепиши.
    return bool(_EMAIL_RE.match(addr))
