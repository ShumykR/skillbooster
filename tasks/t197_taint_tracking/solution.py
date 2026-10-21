"""Завдання №197: taint tracking у стилі CaMeL.

Prompt injection неможливо надійно «відфільтрувати», зате можна обмежити, ЩО саме недовірені
дані можуть робити. Ідея CaMeL (Google DeepMind, 2025): довірена («privileged») модель бачить
лише запит користувача й будує ПЛАН; недовірені дані (сторінка, лист, відповідь інструмента)
обробляє ізольована («quarantined») модель БЕЗ доступу до інструментів; звичайний код
інтерпретатора стежить, звідки кожне значення, і не дає недовіреному керувати потоком
виконання чи чутливими аргументами (адресат листа, URL). Ти пишеш цей шар «значення з
походженням» і виконавця плану. Це НЕ спроба перехопити довільний Python: лише API нижче.

Джерела (labels) це рядки. Довірені: `TRUSTED_SOURCES = {"user", "system", "plan"}`. Усе інше
(`"web"`, `"doc:42"`, `"tool:fetch_url"`, `"email"`) недовірене.

`Tainted(value, sources=())`
    Обгортка: `.value` (будь-що) і `.sources` (`frozenset[str]`). `sources` може бути рядком
    (один label), ітерабельним набором labels або порожнім (значення з коду, довірене).
    `.untrusted` (властивість): є хоч один label поза `TRUSTED_SOURCES`.
    * `bool(t)`, `iter(t)`, `str(t)` і `format(t)` (отже f-рядки): для НЕДОВІРЕНОГО піднімають
      `TaintError` (це керування потоком або обхід відстеження; користуйся `fmt`); для довіреного
      працюють як з `.value`.
    * `t + x`, `x + t` (`x` звичайне значення або `Tainted`): `Tainted(сума значень, обʼєднання
      sources)`.
`derive(fn, *args, **kwargs) -> Tainted`
    Викликає `fn` зі ЗВИЧАЙНИМИ значеннями (кожен `Tainted` аргумент верхнього рівня
    розгортається в `.value`) і повертає `Tainted(результат, обʼєднання sources усіх Tainted-аргументів)`.
`join(parts, sep="") -> Tainted`: `sep.join` значень (`parts` це `str` або `Tainted`), sources обʼєднані.
`fmt(template, *args, **kwargs) -> Tainted`
    `str.format` над розгорнутими значеннями, sources обʼєднані. `template` ОБОВʼЯЗКОВО звичайний
    `str` (`Tainted` це `TypeError`: недовірений формат-рядок це вже атака). Поле заміни з `.` чи `[`
    в імені (`{a.__class__}`, `{a[0]}`) або з `{` у специфікації формату це `ValueError`.
`get(t, key) -> Tainted`: `t.value[key]` із sources `t` (і `key`, якщо він `Tainted`).

`TaintError(Exception)`, `PolicyViolation(Exception)` (атрибути `.tool`, `.arg`, `.sources`: відсортований
список НЕДОВІРЕНИХ labels; текст винятку не містить самого значення), `PlanError(ValueError)`.

`ToolRegistry`
    `register(name, fn, *, sensitive_args=(), trusted_result=False)`: повторна реєстрація імені
    це `ValueError`. `sensitive_args` це імена аргументів, які НЕ МОЖУТЬ бути недовіреними.
    `call(name, /, **args) -> Tainted` (імʼя інструмента лише позиційно, щоб аргумент інструмента міг зватись `name`):
      * невідомий інструмент це `KeyError`;
      * для кожного чутливого аргументу (за зростанням імені), присутнього у виклику: якщо в ньому
        є недовірений `Tainted` (на верхньому рівні, у `list`/`tuple`/`set`/`frozenset` чи значеннях
        `dict` на будь-якій глибині) це `PolicyViolation`, а `fn` НЕ викликається;
      * звичайні (не `Tainted`) значення довірені; нечутливі аргументи можуть бути недовіреними;
      * `fn` отримує лише розгорнуті звичайні значення (Tainted замінені на `.value` на будь-якій глибині);
      * результат: `Tainted(fn(...), U)`, де `U` це обʼєднання sources усіх Tainted-аргументів
        (на будь-якій глибині) плюс `"tool:<name>"` (якщо `trusted_result=False`);
      * `registry.audit`: список записів `{"tool": name, "allowed": True}` або
        `{"tool": name, "allowed": False, "arg": імʼя_аргументу}` для кожного виклику.

`run_agent(query, planner, registry, quarantined) -> dict[str, Tainted]`
    1. `plan = planner(query)`: РІВНО один виклик, і лише з рядком `query` (довірена модель не бачить
       даних інструментів). 2. ПОВНА валідація плану ДО будь-якого виконання (`PlanError`):
       `plan` це список словників; кожен має унікальний `"id"` (непорожній `str`) і РІВНО один із
       `"tool"` (зареєстроване імʼя) чи `"llm"` (рядок-інструкція). Крок `tool` має `"args"` (dict
       імʼя -> специфікація); крок `llm` має `"input"` (специфікація). Специфікація це dict з РІВНО
       одним ключем: `{"lit": значення}` або `{"ref": id}`, де `id` це РАНІШИЙ крок (не
       самопосилання й не наступний). 3. Виконання по порядку: `lit` це `Tainted(значення, {"plan"})`;
       `ref` це результат кроку. Крок `tool` це `registry.call(tool, **args)`. Крок `llm` це
       `quarantined(інструкція, дані)`, де `дані` це РОЗГОРНУТЕ значення входу (звичайний обʼєкт, не
       `Tainted`); результат `Tainted(відповідь, sources входу)`: ізольована модель не підвищує
       довіру й не знижує її. 4. Повертає словник `id -> Tainted` усіх кроків. `PolicyViolation`
       піднімається одразу, наступні кроки не виконуються.
"""

TRUSTED_SOURCES = frozenset({"user", "system", "plan"})


class TaintError(Exception):
    pass


class PolicyViolation(Exception):
    def __init__(self, tool, arg, sources):
        super().__init__(f"tool {tool!r}: argument {arg!r} is derived from untrusted sources {sources}")
        self.tool = tool
        self.arg = arg
        self.sources = sources


class PlanError(ValueError):
    pass


class Tainted:
    def __init__(self, value, sources=()):
        raise NotImplementedError


def derive(fn, *args, **kwargs):
    raise NotImplementedError


def join(parts, sep=""):
    raise NotImplementedError


def fmt(template, *args, **kwargs):
    raise NotImplementedError


def get(t, key):
    raise NotImplementedError


class ToolRegistry:
    def __init__(self):
        raise NotImplementedError

    def register(self, name, fn, *, sensitive_args=(), trusted_result=False):
        raise NotImplementedError

    def call(self, name, /, **args):
        raise NotImplementedError


def run_agent(query, planner, registry, quarantined):
    raise NotImplementedError
