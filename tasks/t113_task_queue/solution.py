"""Завдання №113: черга завдань із гарантіями: at-least-once, visibility timeout, dead-letter, ідемпотентність.

Брокер не вміє «рівно один раз»: він гарантує «щонайменше раз», тобто завдання можуть прийти повторно, і споживач мусить це витримати.
Реалізуй чергу (як SQS у мініатюрі) і ідемпотентного споживача. Час приходить із `clock()`.

TaskQueue(clock, visibility_timeout=30, max_attempts=3)
    .enqueue(payload, *, key=None, delay=0) -> task_id (рядок "t1", "t2", ...; номер зростає на 1 для кожного НОВОГО завдання)
        key: ключ ідемпотентності продюсера. Поки завдання з таким key активне (не підтверджене і не в dead-letter), повторний
        enqueue з тим самим key повертає id наявного завдання й нічого не створює. delay < 0: ValueError.
        Завдання доступне з моменту available_at = clock() + delay.
    .receive(n=1) -> list[dict]
        Віддає до n доступних завдань за порядком (available_at, номер створення). Кожне повертається як
        {"id", "payload", "attempt", "receipt"}: attempt це скільки разів завдання видавали, враховуючи цей раз (1, 2, ...),
        receipt новий унікальний рядок ("r1", "r2", ...; лічильник один на чергу). Завдання стає невидимим до clock() + visibility_timeout.
        Невидиме завдання, чий час вийшов (clock() >= invisible_until) і яке не підтвердили, знову доступне (available_at =
        invisible_until), якщо його attempt < max_attempts; інакше воно йде в dead-letter й не віддається.
    .ack(receipt) -> bool    підтвердити виконання: True, лише якщо receipt поточний для завдання в польоті й clock() <
                             invisible_until. Прострочений або застарілий receipt (завдання вже видали повторно): False.
    .nack(receipt, delay=0) -> bool    повернути в чергу з затримкою (available_at = clock() + delay); умови валідності як в ack.
                             Якщо attempt >= max_attempts, завдання йде в dead-letter.
    .extend(receipt, seconds) -> bool  heartbeat: invisible_until = clock() + seconds; умови валідності як в ack; seconds <= 0: ValueError.
    .dead_letters() -> list[dict]      [{"id", "payload", "attempts"}, ...] за порядком потрапляння в dead-letter.
    .redrive(task_id) -> bool          повернути завдання з dead-letter у чергу: attempts скидається, available_at = clock(), True;
                                       невідомий id: False.
    .stats() -> dict                   {"ready": доступні зараз, "delayed": ще не настав available_at, "in_flight": невидимі,
                                        "dead": у dead-letter}. Прострочені невидимі завдання вважаються ready (або dead).

process(queue, handler, n=1, *, backoff_base=1, backoff_cap=60) -> list[tuple[str, str]]
    receive(n); для кожного завдання handler(payload). Успіх: ack, результат (id, "done"). Виняток: nack з затримкою
    min(backoff_base * 2 ** (attempt - 1), backoff_cap); результат (id, "retry") або (id, "dead"), якщо завдання потрапило в dead-letter.

consume_once(processed, message_id, fn) -> bool
    Ідемпотентний споживач: якщо message_id уже в множині `processed`, fn не викликається, результат False. Інакше fn()
    викликається; якщо вона не кинула виняток, message_id додається в processed і результат True. Виняток fn летить нагору
    і message_id НЕ запамʼятовується (повторна спроба має виконатись).
"""


class TaskQueue:
    def __init__(self, clock, visibility_timeout: float = 30, max_attempts: int = 3) -> None:
        raise NotImplementedError

    def enqueue(self, payload, *, key: str | None = None, delay: float = 0) -> str:
        raise NotImplementedError

    def receive(self, n: int = 1) -> list[dict]:
        raise NotImplementedError

    def ack(self, receipt: str) -> bool:
        raise NotImplementedError

    def nack(self, receipt: str, delay: float = 0) -> bool:
        raise NotImplementedError

    def extend(self, receipt: str, seconds: float) -> bool:
        raise NotImplementedError

    def dead_letters(self) -> list[dict]:
        raise NotImplementedError

    def redrive(self, task_id: str) -> bool:
        raise NotImplementedError

    def stats(self) -> dict:
        raise NotImplementedError


def process(queue: TaskQueue, handler, n: int = 1, *, backoff_base: float = 1, backoff_cap: float = 60) -> list[tuple[str, str]]:
    raise NotImplementedError


def consume_once(processed: set, message_id: str, fn) -> bool:
    raise NotImplementedError
