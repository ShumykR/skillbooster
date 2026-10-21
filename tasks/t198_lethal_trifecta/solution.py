"""Завдання №198: аналізатор lethal trifecta.

«Lethal trifecta» (Simon Willison, 2025): агент стає вразливим до крадіжки даних через prompt
injection, коли В ОДНІЙ СЕСІЇ одночасно є три можливості:
    private_data       доступ до приватних даних (пошта, файли, БД);
    untrusted_content  вхід, який контролює не користувач (веб-сторінка, лист, issue, PDF);
    exfiltration       канал назовні (надіслати лист, HTTP-запит, коміт, посилання з даними).
Достатньо розвести ці можливості по різних сесіях (агентах), і атака не складається. Ти пишеш
аналізатор конфігурації, що знаходить небезпечні сесії й пропонує, що розвести.

Конфіг:
    {"tools": {імʼя: {"private_data": bool, "untrusted_content": bool, "exfiltration": bool}, ...},
     "sessions": {id_сесії: [імена інструментів]}}            # "sessions" необовʼязкове
* `CAPS = ("private_data", "untrusted_content", "exfiltration")` (порядок важливий).
* Прапор, якого немає в інструменту, це `False`. Невідомий ключ (опечатка `exfiltraton` зробила б
  інструмент «безпечним»: fail open), прапор не `bool`, інструмент не dict, порожнє чи не-рядкове
  імʼя, `tools` не dict: `ValueError`. Конфіг не dict: `ValueError`.
* Без "sessions" це одна сесія `"default"` з усіма інструментами (у порядку `tools`).
  `sessions` має бути непорожнім dict зі списками; невідомий інструмент у списку, дубль в одному
  списку, не-список: `ValueError`. Порожній список дозволений (сесія без можливостей).

`analyze(config) -> dict`
    {"sessions": {id: {"capabilities": {cap: [імена інструментів сесії з цим прапором, за алфавітом]},
                       "count": скільки з трьох можливостей присутні в сесії (0..3),
                       "risk": "critical" (count == 3) | "high" (count == 2) | "low"}},
     "findings": [...], "recommendations": [...], "safe": bool}
    `capabilities` містить усі три ключі (порожні списки, якщо немає).
    findings, у такому порядку:
      * по одному `{"rule": "tool-trifecta", "tool": імʼя}` на КОЖЕН інструмент (за порядком
        `tools`), що сам має всі три прапори (його не розвести сесіями, його треба розділити);
        інструмент враховується, навіть якщо він не входить в жодну сесію;
      * по одному `{"rule": "lethal-trifecta", "session": id, "tools": [...]}` на кожну сесію з
        count == 3 (за порядком сесій); `tools` це відсортований за алфавітом перелік інструментів
        сесії, що мають хоч один прапор.
    recommendations: по одному на кожну сесію з count == 3 (за порядком сесій):
      {"session": id, "remove_capability": cap, "from_tools": [...]}, де `cap` це можливість з
      НАЙМЕНШОЮ кількістю інструментів у цій сесії (рівність: перша за порядком `CAPS`), а
      `from_tools` це ці інструменти за алфавітом.
    safe: `True`, лише коли findings порожній.

`plan_split(config) -> dict`
    Скільки сесій потрібно, щоб жодна не мала всіх трьох можливостей, і хто куди. Береться лише
    `tools` (sessions ігнорується, але валідація та сама). Сесія «без cap» це сесія, у якій жоден
    інструмент не має цього прапора. Шукається НАЙМЕНША кількість таких сесій, що вміщують усі
    інструменти; з однакових за розміром варіантів береться перший за порядком: спершу розмір 1
    (без private_data; без untrusted_content; без exfiltration), далі розмір 2 у порядку
    (без private, без untrusted), (без private, без exfiltration), (без untrusted, без
    exfiltration), далі розмір 3. Інструмент потрапляє в ПЕРШУ з обраних сесій (за порядком CAPS),
    що його вміщує; інструмент без прапорів теж іде в першу. Усередині сесії інструменти в порядку
    `tools`.
    {"possible": bool, "sessions": [{"lacks": cap, "tools": [...]}, ...], "unsplittable": [...]}
    Якщо є інструменти з усіма трьома прапорами: `possible` False, `sessions` `[]`,
    `unsplittable` це їхні імена в порядку `tools`. Порожній `tools`: possible True, sessions `[]`.
"""

CAPS = ("private_data", "untrusted_content", "exfiltration")


def analyze(config: dict) -> dict:
    raise NotImplementedError


def plan_split(config: dict) -> dict:
    raise NotImplementedError
