"""Завдання №196: guardrails-пайплайн для LLM-застосунку.

Між користувачем і моделлю стоять два ланцюжки перевірок («rails»): INPUT rails перед моделлю
й OUTPUT rails перед показом відповіді. Кожен rail може пропустити текст, ЗАМІНИТИ в ньому
небезпечні шматки (`redact`) або ЗАБЛОКУВАТИ все (`block`). Модель не є межею безпеки: усе
нижче працює звичайним кодом (Chain of Responsibility).

`Decision(action, text, reasons)`: уже реалізовано.
    action: "allow" | "redact" | "block". Підсумок ланцюжка: block сильніший за redact,
            redact сильніший за allow.
    text:   для allow це ВХІДНИЙ рядок без змін; для redact рядок із замінами; для block
            завжди "" (нічого не витікає далі).
    reasons: назви rails, що спрацювали, у порядку виконання (для block остання це rail, що
            заблокував). Якщо rail «jailbreak» заблокував через помилку класифікатора, то
            причина "jailbreak-error".

`GuardrailPipeline(jailbreak_score, *, jailbreak_threshold=0.8, max_input_chars=2000, allowed_domains=())`
    `jailbreak_score(text) -> float` це функція-параметр (мок класифікатора), значення 0..1.
    `allowed_domains`: домени, на які модель може посилатись (регістр не важливий).
    `pipeline.log`: список записів `{"stage": "input"|"output", "rail": str, "action":
    "redact"|"block", "count": int}`, по одному на кожне спрацювання rail (allow не
    логується). `count` це кількість замін, для block це 1. У журнал НІКОЛИ не потрапляє
    текст користувача чи моделі (там можуть бути секрети й PII).

`check_input(text) -> Decision`: rails у ТАКОМУ порядку, block зупиняє ланцюжок:
    1. `size`:    не `str` або `len(text) > max_input_chars` це block. Класифікатор при цьому
                  НЕ викликається (дорога операція над величезним входом).
    2. `pii`:     email замінюється на `[EMAIL]`; номер банківської картки (13..19 цифр,
                  допустимі пробіли й дефіси між цифрами, КОНТРОЛЬНА СУМА ЛУНА мусить
                  сходитись) на `[CARD]`. Послідовність цифр із хибною сумою Луна НЕ картка
                  й лишається як є (номери замовлень, дати, телефони).
    3. `jailbreak`: класифікатор отримує текст ПІСЛЯ pii-замін (PII не йде в зовнішній
                  сервіс). `score >= jailbreak_threshold` це block. Fail closed: виняток у
                  класифікаторі, результат не число (у т.ч. `bool`, `None`), `nan` чи число
                  поза 0..1 це block із причиною "jailbreak-error".

`check_output(text) -> Decision`: rails у такому порядку, block зупиняє ланцюжок:
    1. `secret`:  фрагменти, схожі на секрети, замінюються на `[SECRET]`: `sk-` і далі
                  20+ символів з `[A-Za-z0-9_-]`; `AKIA` і 16 символів `[0-9A-Z]`; `ghp_`,
                  `gho_`, `ghu_`, `ghs_`, `ghr_` і 36+ символів `[A-Za-z0-9]`; рядок
                  `-----BEGIN ... PRIVATE KEY-----` (будь-який тип між BEGIN і PRIVATE).
    2. `md_image`: ексфільтрація через Markdown: зображення, яке клієнт завантажить САМ,
                  разом з URL, куди модель могла дописати дані. Перевіряються: `![alt](url)`
                  (url може бути в `<...>` і мати `"title"`), `![alt][ref]` та `![alt][]`
                  (ref=alt) з визначенням `[ref]: url` у тексті, і HTML `<img ... src=url>`.
                  Якщо URL зображення НЕ дозволений це block (причина "md_image").
                  Невизначене посилання `![alt][nope]` не є зображенням.
    3. `url`:     будь-який інший абсолютний `http(s)://` URL, домен якого не дозволений,
                  замінюється на `[URL]` (кінцеві `.,;:!?` не входять в URL).

    URL дозволений, якщо:
      * це відносний URL без схеми й без хоста (`/img/a.png`, `a.png`);
      * схема `http` або `https`, а хост (hostname за правилами `urllib.parse`, без
        логіна, порту, у нижньому регістрі) дорівнює дозволеному домену або є його піддоменом
        (`cdn.example.com` для `example.com`, але НЕ `badexample.com` і НЕ
        `example.com.evil.net`);
      * URL, що починається з `//` (protocol-relative), розбирається як URL із хостом;
      * URL зі зворотною скісною рискою `\\`, іншою схемою (`data:`, `javascript:`, `ftp:`),
        або таким, що не розбирається, НЕ дозволений.
    Перевіряй зображення ДО заміни звичайних URL: інакше `![x](https://evil.net/?q=...)`
    стане `![x]([URL])` і виглядатиме безпечно.
    Не `str` на вході це block (rail "type").
"""
from dataclasses import dataclass, field


@dataclass
class Decision:
    action: str
    text: str
    reasons: list = field(default_factory=list)


class GuardrailPipeline:
    def __init__(self, jailbreak_score, *, jailbreak_threshold: float = 0.8, max_input_chars: int = 2000,
                 allowed_domains=()):
        raise NotImplementedError

    def check_input(self, text: str) -> Decision:
        raise NotImplementedError

    def check_output(self, text: str) -> Decision:
        raise NotImplementedError
