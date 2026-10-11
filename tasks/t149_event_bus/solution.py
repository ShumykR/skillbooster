"""Завдання №149: Observer / шина подій.

`EventBus`
    subscribe(event_type, handler) -> unsubscribe
        Підписує `handler(event)` на події типу `event_type` (клас). Повертає функцію без аргументів, що
        скасовує САМЕ ЦЮ підписку (повторний виклик нічого не робить). Не клас у `event_type` або
        не-callable `handler`: TypeError.
        Той самий handler, підписаний двічі, викликається двічі (це дві окремі підписки).
    publish(event) -> None
        Викликає обробники подій `type(event)` та ВСІХ його батьківських класів (крім `object`).
        Порядок: спершу точний тип, далі базові класи за MRO; усередині одного типу за порядком підписки.
        * обробники працюють на ЗНІМКУ: підписка/відписка під час publish діє лише з наступного publish;
        * виняток одного обробника НЕ зупиняє решту; після того як усі відпрацювали, піднімається
          `ExceptionGroup("handlers failed", [винятки за порядком виклику])`; без помилок нічого не піднімається;
        * подія, на яку ніхто не підписаний, це не помилка.
    handlers_count(event_type) -> int   кількість підписок саме на цей тип (без базових)
"""
from typing import Callable


class EventBus:
    def subscribe(self, event_type: type, handler: Callable) -> Callable[[], None]:
        raise NotImplementedError

    def publish(self, event: object) -> None:
        raise NotImplementedError

    def handlers_count(self, event_type: type) -> int:
        raise NotImplementedError
