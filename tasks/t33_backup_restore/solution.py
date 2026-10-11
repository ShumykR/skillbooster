"""Завдання №33: резервні копії, PITR і політика зберігання.

Резервна копія, яку ніколи не відновлювали, це припущення, а не копія. Для PostgreSQL повне відновлення на момент часу (PITR)
складається з БАЗОВОЇ копії (`pg_basebackup`) і безперервного ланцюжка WAL-сегментів після неї. Достатньо одного пропущеного
сегмента, і все, що за ним, втрачене. Тут логіка планування; самі файли копіює окрема утиліта.

Дані (час це наївні `datetime` в UTC):
    резервна копія:  {"id": str, "taken_at": datetime, "start_seq": int, "end_seq": int}
        `start_seq` це перший WAL-сегмент, потрібний для відновлення з цієї копії, `end_seq` це сегмент, на якому копія стала
        узгодженою (відновлювати треба щонайменше до нього).
    WAL-сегмент:     {"seq": int, "ends_at": datetime}  (`seq` послідовні числа, `ends_at` це час останнього запису в сегменті)
    Списки можуть бути в довільному порядку, WAL може мати повтори одного `seq`.

`plan_restore(backups, wal, target, allow_latest=False) -> dict`
    Обирає НАЙНОВІШУ придатну копію й повертає {"backup_id": id, "wal_from": start_seq, "wal_to": seq}.
    * копія придатна, якщо `taken_at <= target`;
    * `wal_to` це найменший `seq` в архіві, що не менший за `end_seq` копії і чий `ends_at >= target` (цей сегмент містить момент `target`);
    * усі сегменти від `start_seq` до `wal_to` включно мають бути в архіві БЕЗ ПРОПУСКІВ, інакше ця копія непридатна, пробуємо старішу;
    * якщо `target` пізніше за `ends_at` останнього сегмента: RestoreImpossible; з `allow_latest=True` відновлюємо до кінця архіву
      (`wal_to` це останній `seq`, він також має бути >= `end_seq` і ланцюжок безперервний);
    * жодної придатної копії: `RestoreImpossible` (підклас ValueError), у повідомленні причина: "no backup" (усі копії новіші за target
      або списку немає), "wal gap" (є копії, але ланцюжок WAL обірваний) або "target after archive end".
    * копія з `end_seq < start_seq` це ValueError (пошкоджені метадані); `target` не datetime: TypeError.
`prune_backups(backups, now, keep_daily, keep_weekly, keep_monthly) -> list[str]`
    Політика «дід-батько-син». Повертає відсортований список id копій, які МОЖНА видалити. Зберігаються (об'єднання):
    * найновіша копія за кожен із останніх `keep_daily` календарних днів (сьогоднішній `now.date()` і попередні);
    * найновіша копія за кожен із останніх `keep_weekly` ISO-тижнів (поточний тиждень і попередні);
    * найновіша копія за кожен із останніх `keep_monthly` календарних місяців (поточний і попередні);
    * найновіша копія взагалі, завжди; копії з майбутнього (`taken_at > now`) не видаляються.
    Лічильники це int >= 0 (не bool), інакше ValueError; повторні id у `backups`: ValueError.
`removable_wal(wal, kept_backups) -> list[int]`
    Номери сегментів, які більше ніяка зі збережених копій не потребує: усі `seq` менші за найменший `start_seq` серед `kept_backups`.
    Відсортований список без повторів; якщо збережених копій немає, порожній (без копій WAL не видаляємо).
"""
import datetime as dt


class RestoreImpossible(ValueError):
    pass


def plan_restore(backups, wal, target: dt.datetime, allow_latest: bool = False) -> dict:
    raise NotImplementedError


def prune_backups(backups, now: dt.datetime, keep_daily: int, keep_weekly: int, keep_monthly: int) -> list[str]:
    raise NotImplementedError


def removable_wal(wal, kept_backups) -> list[int]:
    raise NotImplementedError
