"""Завдання №15: SSE-брокер: реконект і backpressure.

Сервіс розсилає живі сповіщення через Server-Sent Events. Клієнти відвалюються
(мобільна мережа), реконектяться із заголовком `Last-Event-ID`, а деякі читають
повільніше, ніж ми публікуємо. Реалізуй брокер у пам'яті (без мережі і потоків).

EventBroker(history=100, max_queue=10)
- publish(data, event="message") -> Event: id зростають з 1; брокер пам'ятає останні `history` подій;
  подія потрапляє в чергу кожного відкритого підписника;
- subscribe(last_event_id=None) -> Subscription:
    * None: лише нові події, без повтору;
    * число: спершу повтор подій з id > last_event_id з історії (у порядку id), далі нові;
    * якщо частину пропущених подій уже витіснено з історії, або в чергу не вміщається весь повтор
      (лишається `max_queue` НАЙНОВІШИХ), або id із майбутнього: `needs_resync = True`
      (клієнт має перезавантажити стан цілком, бо потік неповний);
- backpressure: якщо в черзі підписника вже `max_queue` непрочитаних подій, а з'являється нова,
  підписник закривається (`closed = True`, `close_reason = "slow"`) і прибирається з брокера;
  інші підписники й publish це не зачіпає, пам'ять не росте. Що встигли поставити в чергу, ще можна дочитати;
- unsubscribe(sub): ідемпотентний; після нього події до sub не потрапляють; subscriber_count() рахує відкритих.

Subscription: get_nowait() -> Event | None (наступна подія або None), pending() -> int.

format_sse(event) -> str: рядки `id:`, `event:` (лише якщо не "message"), по рядку `data:` на кожен рядок
даних (`splitlines`; порожні дані це один `data:`), порожній рядок у кінці. Назва події з \\n або \\r
це ValueError (інакше клієнт-зловмисник чи дані користувача інʼєктують власні поля).
heartbeat() -> str: коментар `: keep-alive` + порожній рядок, щоб проксі не закривали тихе зʼєднання.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    id: int
    data: str
    event: str = "message"


class Subscription:
    closed: bool = False
    close_reason: str | None = None
    needs_resync: bool = False

    def get_nowait(self) -> Event | None:
        raise NotImplementedError

    def pending(self) -> int:
        raise NotImplementedError


class EventBroker:
    def __init__(self, history: int = 100, max_queue: int = 10) -> None:
        raise NotImplementedError

    def publish(self, data: str, event: str = "message") -> Event:
        raise NotImplementedError

    def subscribe(self, last_event_id: int | None = None) -> Subscription:
        raise NotImplementedError

    def unsubscribe(self, sub: Subscription) -> None:
        raise NotImplementedError

    def subscriber_count(self) -> int:
        raise NotImplementedError


def format_sse(event: Event) -> str:
    raise NotImplementedError


def heartbeat() -> str:
    raise NotImplementedError
