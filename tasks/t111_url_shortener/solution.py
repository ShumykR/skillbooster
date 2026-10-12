"""Завдання №111: URL shortener: коди base62, кастомні аліаси, TTL, лічильник кліків і шардування ключів.

encode_base62(n) -> str / decode_base62(s) -> int
    Алфавіт "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" (62 символи, у цьому порядку). 0 -> "0".
    n < 0, порожній рядок чи символ поза алфавітом: ValueError. decode(encode(n)) == n.

normalize_url(url) -> str
    Прибирає пробіли по краях, робить схему й хост малими літерами, відкидає #fragment. Дозволені лише http/https з непорожнім хостом.
    ValueError: інша схема (javascript:, ftp:, data:), порожній хост, логін/пароль в URL (user:pass@host: витік секретів і фішинг),
    пробіли чи керуючі символи всередині, довжина результату > 2048.

Shortener(*, clock, start_id=1)
    .create(url, *, alias=None, ttl=None) -> str
        Без alias: код = encode_base62(наступний id), id починається зі start_id й зростає на 1 для кожного НОВОГО автокоду; якщо
        такий код уже зайнятий аліасом, id пропускається. Той самий нормалізований URL без alias і без ttl повертає вже
        створений автокод (дедуплікація), без витрати id.
        З alias: ^[A-Za-z0-9_-]{3,32}$ (інакше ValueError); імена api, admin, health, static, docs (без урахування регістру)
        зарезервовані (ValueError); зайнятий код (аліас чи автокод) -> AliasTaken. Регістр аліасу значущий.
        ttl (секунди, > 0, інакше ValueError): посилання діє, поки clock() < created_at + ttl.
    .resolve(code) -> str   повертає URL; невідомий код: NotFound; прострочений: Expired (підклас NotFound).
    NotFound є підкласом KeyError, AliasTaken це Exception.

ClickCounter(sink, flush_every=100)
    .hit(code)   запамʼятовує клік у памʼяті; коли накопичено >= flush_every кліків (усього), викликає flush().
    .flush()     один виклик sink({код: кількість, ...}) з накопиченим і обнулення буфера; якщо буфер порожній, sink НЕ викликається.
    .pending     скільки кліків у буфері. flush_every < 1: ValueError. Жоден клік не втрачається і не рахується двічі.

ShardRing(shards=(), vnodes=64)
    Консистентне хешування. Позиція = int.from_bytes(md5(текст).digest()[:8], "big"); кожен шард займає vnodes точок, текст
    f"{shard}#{i}" для i in range(vnodes); ключ потрапляє на першу точку з позицією >= позиції ключа (за колом). md5(key.encode()).
    .add(shard), .remove(shard), .shard_for(key) -> str. Дубль шарда в add, невідомий шард у remove: ValueError; порожнє кільце:
    LookupError. Додавання/видалення шарда має переносити лише ключі цього шарда.
"""


class AliasTaken(Exception):
    pass


class NotFound(KeyError):
    pass


class Expired(NotFound):
    pass


def encode_base62(n: int) -> str:
    raise NotImplementedError


def decode_base62(s: str) -> int:
    raise NotImplementedError


def normalize_url(url: str) -> str:
    raise NotImplementedError


class Shortener:
    def __init__(self, *, clock, start_id: int = 1) -> None:
        raise NotImplementedError

    def create(self, url: str, *, alias: str | None = None, ttl: float | None = None) -> str:
        raise NotImplementedError

    def resolve(self, code: str) -> str:
        raise NotImplementedError


class ClickCounter:
    def __init__(self, sink, flush_every: int = 100) -> None:
        raise NotImplementedError

    @property
    def pending(self) -> int:
        raise NotImplementedError

    def hit(self, code: str) -> None:
        raise NotImplementedError

    def flush(self) -> None:
        raise NotImplementedError


class ShardRing:
    def __init__(self, shards=(), vnodes: int = 64) -> None:
        raise NotImplementedError

    def add(self, shard: str) -> None:
        raise NotImplementedError

    def remove(self, shard: str) -> None:
        raise NotImplementedError

    def shard_for(self, key: str) -> str:
        raise NotImplementedError
