"""Завдання №116: event streaming у стилі Kafka: партиції, порядок, consumer groups, offset і replay.

Topic(num_partitions)
    .produce(key, value) -> (partition, offset)
        key не None: partition = zlib.crc32(key.encode()) % num_partitions (той самий ключ завжди в ту саму партицію, тож порядок подій
        одного ключа зберігається); key None: round-robin по всіх повідомленнях без ключа: 0, 1, 2, ..., num_partitions - 1, 0, ...
        (один лічильник на топік, стартує з 0). offset це порядковий номер у партиції з 0.
    .end_offsets() -> list[int]      скільки повідомлень у кожній партиції.
    .read(partition, offset, max_records) -> list[dict]   записи {"partition", "offset", "key", "value"} з offset (включно), не більше
                                     max_records; порожній список, якщо там нічого немає. Невідома партиція: ValueError.
    num_partitions < 1: ValueError.

ConsumerGroup(topic, group_id)
    Група ділить партиції між учасниками: кожна партиція належить рівно одному учаснику.
    .join(member), .leave(member)    змінюють склад і запускають rebalance (join наявного учасника та leave відсутнього нічого не роблять
                                     і rebalance не запускають). .generation: починається з 0, збільшується на 1 при кожному rebalance.
    .assignment() -> dict[str, list[int]]   партиція p належить учаснику sorted(members)[p % len(members)]; у словнику всі учасники
                                     (у кого немає партицій, порожній список), партиції за зростанням. Без учасників: {}.
    .poll(member, max_records=10) -> list[dict]
        Записи з партицій учасника (партиції за зростанням), кожна читається з поточної позиції учасника (position) далі, не більше
        max_records ЗАГАЛОМ. Позиція зсувається на кількість повернутих записів. Не учасник: ValueError.
    .commit(member)                  зберігає у групі committed offset = поточна позиція для кожної партиції учасника. Не учасник: ValueError.
    .seek(member, partition, offset) встановлює позицію (replay: перечитати старе; offset >= 0). Партиція не належить учаснику
                                     або offset < 0: ValueError.
    .committed() -> dict[int, int]   {партиція: committed offset} для ВСІХ партицій топіка (0, якщо ще не фіксували).
    .lag() -> dict                   {"partitions": {p: end_offset - committed}, "total": сума}.
    Позиція партиції, яку учасник щойно отримав (на старті й після rebalance), дорівнює committed offset цієї партиції групи:
    усе, що було прочитано, але не закомічено, буде прочитано знову (at-least-once). Rebalance скидає позиції ВСІХ учасників.
"""


class Topic:
    def __init__(self, num_partitions: int) -> None:
        raise NotImplementedError

    def produce(self, key: str | None, value) -> tuple[int, int]:
        raise NotImplementedError

    def end_offsets(self) -> list[int]:
        raise NotImplementedError

    def read(self, partition: int, offset: int, max_records: int) -> list[dict]:
        raise NotImplementedError


class ConsumerGroup:
    def __init__(self, topic: Topic, group_id: str) -> None:
        raise NotImplementedError

    @property
    def generation(self) -> int:
        raise NotImplementedError

    def join(self, member: str) -> None:
        raise NotImplementedError

    def leave(self, member: str) -> None:
        raise NotImplementedError

    def assignment(self) -> dict[str, list[int]]:
        raise NotImplementedError

    def poll(self, member: str, max_records: int = 10) -> list[dict]:
        raise NotImplementedError

    def commit(self, member: str) -> None:
        raise NotImplementedError

    def seek(self, member: str, partition: int, offset: int) -> None:
        raise NotImplementedError

    def committed(self) -> dict[int, int]:
        raise NotImplementedError

    def lag(self) -> dict:
        raise NotImplementedError
