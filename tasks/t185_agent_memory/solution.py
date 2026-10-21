"""Завдання №185: памʼять агента.

Агентові потрібні два види памʼяті: КОРОТКОСТРОКОВА (останні повідомлення діалогу, обмежене
вікно) і ДОВГОСТРОКОВА (факти про користувача: місто, мова, посада). Довгострокова памʼять без
правил засмічується дублями, зберігає застарілі факти поруч із новими, не забуває нічого й
може «підмішати» чужі дані (CWE-639, CWE-200). Ти реалізуєш мінімальну памʼять з дедуплікацією,
розвʼязанням конфліктів із джерелом, TTL та «забути користувача». Час це параметр `clock()`.

`AgentMemory(clock, window=6, default_ttl=None)`
    `clock() -> float` (секунди); `window` це `int` >= 1 (кількість останніх повідомлень на
    користувача); `default_ttl` це `None` (назавжди) або число > 0. Інакше `ValueError`.

Короткострокова памʼять:
`add_message(user_id, role, text) -> None`
    `user_id`: непорожній `str`; `role` одне з `"user"`, `"assistant"`, `"system"`, `"tool"`;
    `text`: `str` (може бути порожнім). Порушення: `ValueError`.
`context(user_id) -> list[dict]`
    Останні `window` повідомлень цього користувача, від старішого до новішого, елементи
    `{"role", "text"}` (копії: зміна результату не псує памʼять). Невідомий користувач: `[]`.

Довгострокова памʼять (факти по парі `(user_id, key)`):
`remember(user_id, key, value, source, ttl=None, ts=None) -> str`
    `user_id`, `key`, `source` це непорожні `str` (джерело обовʼязкове: звідки відомо); `value` це
    будь-що, крім `None`; `ttl` це `None` або число > 0 (`None` означає `default_ttl`);
    `ts` це `None` (тоді `clock()`) або число (час події, коли факт став відомим).
    Порушення: `ValueError`. Факт живе до `ts + ttl` НЕ включно: при `clock() >= ts + ttl` він
    протермінований і вважається відсутнім (при `ttl` `None` і `default_ttl` `None` без кінця).
    Поточним вважається лише НЕпротермінований факт. Результат:
      * `"added"`: поточного факту немає (або він протермінований: стара історія цього ключа
        скидається). Запис: `{"value", "source", "ts", "expires", "confirmations": 0}`
        (`expires` це `None`, якщо без терміну);
      * `"duplicate"`: поточне `value` дорівнює новому (`==`, тип теж має збігатись: `1` і `True`
        різні). Нічого не змінюється, крім `confirmations += 1`;
      * `"stale"`: інше `value`, але `ts` нового запису СТРОГО менший за `ts` поточного: новіше
        перемагає, тож запис ігнорується (поточний факт і історія без змін);
      * `"updated"`: інше `value` і `ts` не менший за поточний: факт замінюється новим записом
        (`confirmations` скидається в 0), а попередній `{"value", "source", "ts"}` додається в кінець
        історії ключа.
`recall(user_id) -> dict`
    `{key: {"value", "source", "ts", "expires", "confirmations"}}` для всіх непротермінованих
    фактів користувача, ключі за алфавітом (копії).
`get(user_id, key) -> dict | None`
    Той самий запис одного факту чи `None` (немає або протермінований).
`history(user_id, key) -> list[dict]`
    Витіснені значення `{"value", "source", "ts"}` від найстарішого до найновішого (копії). Якщо
    поточний факт протермінований чи його немає: `[]`.
`purge() -> int`
    Фізично видаляє всі протерміновані факти (разом з їхньою історією) у всіх користувачів і
    повертає кількість видалених фактів.
`forget_user(user_id) -> dict`
    «Забути користувача»: видаляє ВСЕ про нього: факти (також протерміновані), історію й
    повідомлення. Повертає `{"facts": скільки фактів було (з протермінованими), "messages": скільки
    повідомлень було у вікні}`. Інші користувачі не зачіпаються. Повторний виклик: нулі.
`stats() -> dict`
    `{"users": кількість користувачів, у яких лишилось хоч щось (факти чи повідомлення), "facts":
    кількість зберіганих фактів (разом з протермінованими), "messages": повідомлень у вікнах}`.
"""


class AgentMemory:
    def __init__(self, clock, window: int = 6, default_ttl=None):
        raise NotImplementedError

    def add_message(self, user_id: str, role: str, text: str) -> None:
        raise NotImplementedError

    def context(self, user_id: str) -> list:
        raise NotImplementedError

    def remember(self, user_id: str, key: str, value, source: str, ttl=None, ts=None) -> str:
        raise NotImplementedError

    def recall(self, user_id: str) -> dict:
        raise NotImplementedError

    def get(self, user_id: str, key: str):
        raise NotImplementedError

    def history(self, user_id: str, key: str) -> list:
        raise NotImplementedError

    def purge(self) -> int:
        raise NotImplementedError

    def forget_user(self, user_id: str) -> dict:
        raise NotImplementedError

    def stats(self) -> dict:
        raise NotImplementedError
