"""Завдання №102: метрики Prometheus: Counter/Gauge/Histogram, текстовий формат і RED без вибуху кардинальності.

Реалізуй мінімальний клієнт Prometheus (без бібліотеки prometheus_client).

Registry(max_series=1000)
    .counter(name, help, labels=()) -> Counter        імʼя має закінчуватись на "_total"
    .gauge(name, help, labels=()) -> Gauge
    .histogram(name, help, labels=(), buckets=DEFAULT_BUCKETS) -> Histogram
    .render() -> str                                  текст у форматі експозиції Prometheus (завершується "\n")
    Імʼя метрики: ^[a-zA-Z_:][a-zA-Z0-9_:]*$, імʼя мітки: ^[a-zA-Z_][a-zA-Z0-9_]*$ і не починається з "__"; мітка "le" заборонена
    у histogram. Повторне імʼя метрики, дублікати міток, невалідні імена, bucket'и не за строгим зростанням або порожні (+Inf
    додається автоматично, передавати його не можна), Counter без "_total": ValueError.

    Counter.inc(amount=1, **labels)     amount < 0: ValueError.
    Gauge.set(value, **labels), Gauge.inc(amount=1, **labels), Gauge.dec(amount=1, **labels)
    Histogram.observe(value, **labels)  bucket з le=b рахує спостереження value <= b (кумулятивно).
    Мітки передаються рівно ті, що оголошені (не більше й не менше), інакше ValueError. Нова комбінація міток понад
    `max_series` для цієї метрики: ValueError (захист від вибуху кардинальності: user_id у мітці вб'є Prometheus).

Формат render(): метрики за зростанням імені. Для кожної:
    # HELP <name> <help>        (у help екрануються "\\" -> "\\\\" та переніс рядка -> "\\n")
    # TYPE <name> counter|gauge|histogram
    потім рядки зразків за зростанням кортежу значень міток: `name{a="1",b="2"} 5` (мітки у порядку оголошення; без міток: `name 5`;
    у значеннях міток екрануються "\\", `"` та переніс рядка).
    Histogram: для кожного набору міток спершу `name_bucket{...,le="<b>"} n` за зростанням b і `le="+Inf"`, потім `name_sum{...}`,
    потім `name_count{...}`.
    Число: ціле значення float друкується без ".0" ("3", не "3.0"), інакше repr (0.25); le друкується так само ("0.1", "1", "+Inf").
    Метрика без оголошених міток завжди має один зразок (спершу нульовий); з мітками: лише ті комбінації, що спостерігались.

Red(registry, buckets=DEFAULT_BUCKETS)       RED-метрики (rate, errors, duration) для HTTP:
    створює counter "http_requests_total" з мітками (method, route, status) і histogram "http_request_duration_seconds" з мітками
    (method, route). .record(method, route, status, duration): status перетворюється на рядок.
match_route(path, templates) -> str
    Шаблон маршруту замість сирого шляху (інакше /users/1, /users/2, ... створять мільйон серій). Рядок запиту (`?...`) і кінцевий "/"
    відкидаються; сегмент шаблону виду "{...}" збігається з будь-яким непорожнім сегментом, інші мають збігтися точно; кількість
    сегментів однакова. Повертається перший шаблон зі списку, що збігся, інакше "__unmatched__".
"""

DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class Counter:
    def inc(self, amount: float = 1, **labels) -> None:
        raise NotImplementedError


class Gauge:
    def set(self, value: float, **labels) -> None:
        raise NotImplementedError

    def inc(self, amount: float = 1, **labels) -> None:
        raise NotImplementedError

    def dec(self, amount: float = 1, **labels) -> None:
        raise NotImplementedError


class Histogram:
    def observe(self, value: float, **labels) -> None:
        raise NotImplementedError


class Registry:
    def __init__(self, max_series: int = 1000) -> None:
        raise NotImplementedError

    def counter(self, name: str, help: str, labels=()) -> Counter:
        raise NotImplementedError

    def gauge(self, name: str, help: str, labels=()) -> Gauge:
        raise NotImplementedError

    def histogram(self, name: str, help: str, labels=(), buckets=DEFAULT_BUCKETS) -> Histogram:
        raise NotImplementedError

    def render(self) -> str:
        raise NotImplementedError


class Red:
    def __init__(self, registry: Registry, buckets=DEFAULT_BUCKETS) -> None:
        raise NotImplementedError

    def record(self, method: str, route: str, status, duration: float) -> None:
        raise NotImplementedError


def match_route(path: str, templates: list[str]) -> str:
    raise NotImplementedError
