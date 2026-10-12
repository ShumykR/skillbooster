"""Завдання №80: Semantic versioning і автоматичний changelog (як release-please).

Умовні коміти (Conventional Commits): `type(scope)!: опис`, тіло, футери.

parse_commit(message) -> dict | None
    Перший рядок має вигляд `type: опис` або `type(scope): опис` (після двокрапки пробіл), а `!` перед двокрапкою (`feat!:`,
    `feat(api)!:`) це breaking change. type це маленькі латинські літери, scope це символи `A-Za-z0-9_./-`, не порожній.
    Не за форматом -> None.
    Результат: {"type", "scope" (str | None), "description", "breaking": bool, "note": str | None}.
    Також breaking, якщо у футері (рядок тіла, що починається з) `BREAKING CHANGE:` або `BREAKING-CHANGE:`; тоді
    `note` це текст після двокрапки (обрізаний), інакше для `!` note дорівнює опису. Розділ між першим рядком і
    футером може містити будь-які рядки. Пробіли навколо опису обрізаються; порожній опис -> None.

next_version(current, messages) -> str | None
    `current` це "X.Y.Z" (інакше ValueError); `messages` список повних повідомлень комітів. Повертає наступну версію або None,
    якщо немає жодного релізного коміту. Беремо НАЙВИЩИЙ рівень серед усіх комітів, що розпізнались:
    * major >= 1: breaking -> major (+1.0.0), feat -> minor (+0.1.0), fix або perf -> patch (+0.0.1);
    * major == 0 (нестабільна версія): breaking -> minor, feat -> patch, fix або perf -> patch (major не росте сам);
    * решта типів (docs, chore, ci, test, refactor, style, build, revert...) релізу не дають, якщо не breaking
      (breaking у будь-якого типу дає свій рівень).

changelog(version, date, commits) -> str
    `commits` це список пар (sha, message). Markdown, секції в такому порядку, а запис у секції в порядку commits:
        ## 1.3.0 (2026-01-02)

        ### ⚠ BREAKING CHANGES

        * **api:** текст note (a1b2c3d)

        ### Features

        * **api:** опис (abc1234)

        ### Bug Fixes

        ### Performance Improvements
    Секція з'являється лише якщо в ній є записи. Features це type feat, Bug Fixes це fix, Performance Improvements це perf;
    інші типи в changelog не потрапляють (але breaking з будь-якого типу йде в BREAKING CHANGES, і також у свою секцію,
    якщо це feat/fix/perf). Запис: `* **scope:** текст (sha7)` або без `**scope:** `, якщо scope немає; sha обрізається до
    7 символів. Між секціями одна порожня лінія, рядок завершується одним "\\n". Коміти, що не розпізнались, пропускаються.
    Якщо записів немає взагалі, повертається лише заголовок `## version (date)\\n`.
"""
import re  # noqa: F401


def parse_commit(message: str) -> dict | None:
    raise NotImplementedError


def next_version(current: str, messages: list[str]) -> str | None:
    raise NotImplementedError


def changelog(version: str, date: str, commits: list[tuple[str, str]]) -> str:
    raise NotImplementedError
