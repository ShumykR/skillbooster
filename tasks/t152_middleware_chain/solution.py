"""Завдання №152: ланцюжок middleware (Chain of Responsibility).

Middleware це функція `mw(request, call_next) -> response`. `call_next(request)` передає запит далі
по ланцюжку (наступному middleware, а в кінці обробнику) і повертає відповідь.

`build_pipeline(middlewares, handler) -> callable(request) -> response`
    * перший у списку middleware ЗОВНІШНІЙ: бачить запит першим, а відповідь останнім;
    * middleware може змінити запит (передати в `call_next` інший об'єкт), змінити відповідь, перервати
      ланцюжок (повернути відповідь, не викликавши `call_next`) або перехопити виняток від наступних ланок;
    * виняток, якого ніхто не перехопив, летить до викликача без змін;
    * `call_next` можна викликати лише ОДИН раз за прохід через цю ланку: другий виклик
      того самого `call_next` це RuntimeError("call_next called twice");
    * порожній список middleware: pipeline просто викликає `handler`;
    * готовий pipeline можна викликати багато разів, у тому числі після виняткових проходів і перерваних
      ланцюжків, і з різних потоків: стан одного проходу не повинен «протікати» в інший;
    * список `middlewares` копіюється при побудові (зміна списку потім не впливає на pipeline);
    * кожен елемент `middlewares` має бути callable, інакше TypeError одразу при побудові.
"""
from typing import Callable, Sequence


def build_pipeline(middlewares: Sequence[Callable], handler: Callable) -> Callable:
    raise NotImplementedError
