"""Завдання №115: тайм-лайн (стрічка): fan-out on write, fan-out on read і гібрид.

Стрічка користувача це пости тих, на кого він підписаний (і його власні), від нових до старих. Є дві стратегії, і кожна ламається:
  * "push" (fan-out on write): при публікації пост додається в «вхідну скриньку» кожного підписника. Читання миттєве, але автор з
    мільйоном підписників викликає мільйон записів на один пост;
  * "pull" (fan-out on read): пости лежать лише в автора, а стрічка збирається при читанні зі списків усіх, на кого підписаний.
    Запис дешевий, читання дороге, якщо підписок багато;
  * "hybrid": звичайних авторів розсилаємо (push), «зірок» (мають багато підписників) не розсилаємо, а читачі підтягують їхні пости
    при читанні (pull) і зливають із власною скринькою.
Усі три стратегії повинні давати ОДНАКОВУ стрічку; відрізняється лише вартість.

Timeline(strategy="push", celebrity_threshold=100)       strategy: "push" | "pull" | "hybrid", інакше ValueError.
    .post(author, text) -> int        id = 1, 2, 3, ... глобальний лічильник, один на всіх. Повертає id.
    .get_post(post_id) -> dict        {"id", "author", "text"}; невідомий id: KeyError.
    .follow(user, author)             user == author: ValueError. Підписка починає діяти з поточного моменту: у стрічці лише пости з
                                      id БІЛЬШИМИ за останній id на момент підписки. Повторна підписка на того самого автора, на
                                      якого вже підписані, нічого не змінює (момент підписки не оновлюється).
    .unfollow(user, author)           пости автора зникають зі стрічки; відписка без підписки нічого не робить. Нова підписка
                                      після відписки починає відлік заново.
    .feed(user, limit=20, cursor=None) -> dict
        Пости: власні пости користувача + пости авторів, на яких він підписаний (з урахуванням моменту підписки), від більших id
        до менших, без дублікатів. cursor (id): лише пости з id < cursor. limit < 1: ValueError.
        {"posts": [id, ...] (не більше limit),
         "next_cursor": id останнього повернутого поста, якщо за ним у стрічці є ще пости, інакше None}.
    .stats -> {"fanout_writes": int}      скільки записів у вхідні скриньки зроблено при публікаціях.
        push: при кожному пості +кількість підписників автора в цей момент (власна стрічка автора не рахується: власні пости
        читач бере зі списку автора). pull: завжди 0. hybrid: автор, у якого підписників >= celebrity_threshold у момент публікації,
        стає «зіркою» назавжди (статус не знімається), його пости не розсилаються (0 записів), а читачі підтягують їх при читанні;
        для решти авторів як у push.
"""


class Timeline:
    def __init__(self, strategy: str = "push", celebrity_threshold: int = 100) -> None:
        raise NotImplementedError

    def post(self, author: str, text: str) -> int:
        raise NotImplementedError

    def get_post(self, post_id: int) -> dict:
        raise NotImplementedError

    def follow(self, user: str, author: str) -> None:
        raise NotImplementedError

    def unfollow(self, user: str, author: str) -> None:
        raise NotImplementedError

    def feed(self, user: str, limit: int = 20, cursor: int | None = None) -> dict:
        raise NotImplementedError

    @property
    def stats(self) -> dict:
        raise NotImplementedError
