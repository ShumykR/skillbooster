"""Завдання №75: Збірка й публікація образу: які теги ставити.

Помилки з тегами коштують дорого: `latest` після випуску старої гілки патчів відкочує всіх користувачів назад,
тег `1.2.3` перезаписано іншим вмістом, образ з PR потрапив у реєстр. Реалізуй рішення, яке в CI приймають за подією.

image_tags(event, ref, sha, *, existing_versions=(), pr_number=None, default_branch="main") -> dict
    Повертає {"push": bool, "tags": [str, ...], "reason": str}. `event`: "push" або "pull_request".
    `ref`: "refs/heads/<гілка>" або "refs/tags/<тег>". `sha`: повний sha коміту. `existing_versions`: уже опубліковані
    СТАБІЛЬНІ версії як рядки "X.Y.Z" (без префікса v).
    * pull_request: push False, tags [f"pr-{pr_number}"], reason "pull_request" (збираємо лише для перевірки);
    * гілка default_branch: push True, tags [<гілка>, f"sha-{sha[:7]}"], reason "branch";
    * інша гілка: push False, tags [], reason "branch_not_published";
    * тег, що не відповідає `^v(\\d+)\\.(\\d+)\\.(\\d+)(-[0-9A-Za-z.-]+)?$`: push False, tags [], reason "not_semver";
    * тег-реліз (`vX.Y.Z`, стабільний, без суфікса): якщо `X.Y.Z` уже в existing_versions -> push False, tags [], reason
      "version_exists" (теги незмінні). Інакше push True і теги по порядку:
        "X.Y.Z"; "X.Y", якщо X.Y.Z найбільший серед усіх (існуючих і цього) патчів лінії X.Y; "X", якщо X.Y.Z найбільший серед
        усіх версій з майором X; "latest", якщо X.Y.Z найбільший серед усіх версій узагалі; нарешті f"sha-{sha[:7]}".
      reason "release";
    * pre-release (`vX.Y.Z-rc.1`): push True, tags [повна версія без v, f"sha-{sha[:7]}"], reason "prerelease"
      (жодних плаваючих тегів і latest). Версія перевіряється на існування лише серед existing_versions у разі збігу
      повного рядка (стабільні версії, тож не збігається).
    Порівняння версій числове (1.10.0 > 1.9.0), не рядкове.
"""
import re  # noqa: F401


def image_tags(
    event: str,
    ref: str,
    sha: str,
    *,
    existing_versions: tuple[str, ...] | list[str] = (),
    pr_number: int | None = None,
    default_branch: str = "main",
) -> dict:
    raise NotImplementedError
