"""Завдання №79: Preview-середовище на кожен PR.

Для кожного відкритого PR піднімається тимчасове середовище з власним URL, а коли PR закрито або він застарів,
середовище знищується (інакше рахунок за хмару росте). Реалізуй планувальник: він не торкається хмари, а лише
повертає список дій, які треба виконати.

preview_name(number, branch) -> str
    "pr-<number>" + "-" + slug гілки. slug: нижній регістр; усі символи, крім a-z0-9, стають "-"; повторні "-"
    згортаються в один; "-" на краях прибираються. Ім'я не довше за 40 символів: slug обрізається, і після обрізання
    кінцевий "-" знову прибирається. Порожній slug -> просто "pr-<number>".
    (DNS-мітка до 63 символів, без нижнього підкреслення й слешів у `feature/Login_Page`.)

plan_previews(open_prs, envs, now, *, ttl_hours=72, max_envs=10) -> list[dict]
    `open_prs`: [{"number": int, "branch": str, "updated_at": float, "labels": [str]}, ...] (секунди від епохи).
    `envs`: наявні середовища [{"name": str, "pr": int, "last_deploy_at": float}, ...].
    Дії {"action": "create"|"update"|"destroy"|"skip", "pr": int, "name": str, "reason": str}:
    * середовище, чий PR не серед відкритих: destroy, reason "pr_closed";
    * PR із міткою "no-preview": нове не створюється; наявне destroy, reason "opted_out";
    * наявне середовище відкритого PR, у якого `now - last_deploy_at > ttl_hours*3600` і НЕМАЄ мітки "keep-preview":
      destroy, reason "expired";
    * наявне, що лишається: якщо `updated_at > last_deploy_at`, то update (reason "new_commits"), інакше дії немає;
    * відкритий PR без середовища (і без "no-preview"): create, reason "opened", але не більше вільних слотів:
      слоти = max_envs - кількість середовищ, що ЛИШАЮТЬСЯ після destroy (update теж лишається). Претенденти йдуть від
      найновішого `updated_at` до найстарішого (за рівності від меншого номера PR); кому слота не вистачило: skip,
      reason "quota".
    Ім'я для create/skip це preview_name(number, branch), для решти це `name` наявного середовища.
    Порядок результату: destroy, update, create, skip; всередині за номером PR.
"""
import re  # noqa: F401


def preview_name(number: int, branch: str) -> str:
    raise NotImplementedError


def plan_previews(
    open_prs: list[dict],
    envs: list[dict],
    now: float,
    *,
    ttl_hours: float = 72,
    max_envs: int = 10,
) -> list[dict]:
    raise NotImplementedError
