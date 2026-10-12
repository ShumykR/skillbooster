"""Завдання №46: N+1 у GraphQL/REST-резолверах і DataLoader.

Резолвер поля `author` викликається для кожного допису окремо: 50 дописів дають
1 запит за списком і ще 50 за авторами (N+1). DataLoader збирає всі `load(key)`,
що трапились в одному «тіку» event loop, у ОДИН пакетний виклик.

DataLoader(batch_fn, *, max_batch_size=None, cache=True)
- `batch_fn(keys: list) -> awaitable list` отримує унікальні ключі в порядку першої появи і
  повертає список значень тієї ж довжини в тому ж порядку. Елемент-виняток (екземпляр Exception) це
  помилка саме цього ключа: `load` для нього кидає цей виняток, а решта ключів успішні;
- `await load(key)`: усі виклики, зроблені до того, як event loop дійде до наступної ітерації
  (типово: `asyncio.gather(*(loader.load(k) for k in keys))`), потрапляють в один пакет;
  однаковий ключ у пакеті запитується один раз; `max_batch_size` ділить пакет на частини;
- кеш (`cache=True`): повторний `load` того ж ключа, навіть до завершення першого, не викликає
  `batch_fn` знову і віддає той самий результат. Невдалий ключ (виняток) з кешу прибирається, щоб
  наступна спроба могла вдатись. `cache=False` кешу не має, але дедуплікація всередині пакета лишається;
- `load_many(keys) -> list`: як `gather(load...)`, повертає значення за порядком ключів;
- `clear(key=None)`: прибрати ключ із кешу (або весь кеш); `prime(key, value)`: покласти значення в кеш,
  якщо ключа ще немає;
- якщо `batch_fn` кинув виняток, він іде всім ключам цього пакета (і кеш для них очищається);
  якщо повернув список не тієї довжини: `DataLoaderError` усім ключам пакета.

`posts_with_authors(db)`: повертає список дописів, кожен із полем `author` (словник користувача або None,
якщо автора немає). Зараз це N+1: перепиши через DataLoader над `db.users_by_ids`. Усього має бути 2 запити
до БД на будь-яку кількість дописів.
"""
import asyncio  # noqa: F401
from typing import Any, Awaitable, Callable


class DataLoaderError(Exception):
    pass


class DataLoader:
    def __init__(
        self,
        batch_fn: Callable[[list], Awaitable[list]],
        *,
        max_batch_size: int | None = None,
        cache: bool = True,
    ) -> None:
        raise NotImplementedError

    async def load(self, key: Any) -> Any:
        raise NotImplementedError

    async def load_many(self, keys: list) -> list:
        raise NotImplementedError

    def clear(self, key: Any = None) -> None:
        raise NotImplementedError

    def prime(self, key: Any, value: Any) -> None:
        raise NotImplementedError


async def posts_with_authors(db) -> list[dict]:
    posts = await db.list_posts()
    for post in posts:
        author = await db.get_user(post["author_id"])  # N+1: по запиту на кожен допис
        post["author"] = author
    return posts
