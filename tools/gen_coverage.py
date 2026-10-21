# -*- coding: utf-8 -*-
"""Будує docs/security-coverage.md з тегів `*CWE:*` у каталозі завдань.

Синтаксис тегу в рядку каталогу: `*CWE:* 862, ~200, ?916, @79`
  N   завдання повністю тренує цю слабкість (✅, якщо є автоперевірка, інакше 📝);
  ~N  часткове або непряме покриття (🟡 для автоперевірки, інакше 📝);
  ?N  у тексті каталогу згадано, але не реалізовано (📝);
  @N  лише зовнішня лабораторія (🔗).
"""
from collections import Counter

from cwe_data import CAPSTONE_GAPS, CATS, EXTRA_NAMES, GAPS, TOP25, TOP25_NA

OK, PART, DOC, LAB, NO, NA = "✅", "🟡", "📝", "🔗", "❌", "➖"
RANK = {OK: 5, PART: 4, DOC: 3, LAB: 2, NO: 1}
LEGEND = [
    (OK, "є завдання з автоперевіркою, яке тренує захист або виявлення саме цієї слабкості"),
    (PART, "часткове або непряме покриття автоперевіреним завданням (лише детектор, побічний ефект)"),
    (DOC, "описано в каталозі, але ще не реалізовано (немає коду й автоперевірки)"),
    (LAB, "лише посилання на зовнішню лабораторію (PortSwigger тощо)"),
    (NO, "у репозиторії немає нічого"),
    (NA, "не стосується Python-бекенду (керована пам'ять)"),
]


def parse_tag(tag):
    kind = ""
    if tag and tag[0] in "~?@":
        kind, tag = tag[0], tag[1:]
    return kind, int(tag)


def collect(tasks):
    """cwe -> (статус, [рядки з id завдань])"""
    best, where = {}, {}
    for t in tasks:
        for tag in t.get("cwe", []):
            kind, num = parse_tag(tag)
            if kind == "":
                s = OK if t.get("auto") else DOC
            elif kind == "~":
                s = PART if t.get("auto") else DOC
            elif kind == "?":
                s = DOC
            else:
                s = LAB
            if RANK[s] > RANK.get(best.get(num), 0):
                best[num] = s
            label = ("~" if kind == "~" else "") + t["id"] if kind in ("", "~") and t.get("auto") else \
                ("№" + str(t["n"]) if t.get("n") else t["id"])
            where.setdefault(num, [])
            if label not in where[num]:
                where[num].append(label)
    return best, where


def cwe_names():
    names = dict(EXTRA_NAMES)
    for _, _, _, rows in CATS:
        for cwe, title in rows:
            names[cwe] = title
    for _, cwe, title in TOP25:
        names.setdefault(cwe, title)
    return {str(k): v for k, v in names.items()}


def build(tasks, auto_count, catalog_count):
    best, where = collect(tasks)
    out = []
    w = out.append
    w("# Покриття OWASP Top 10:2025 і CWE (зіставлення з навчальним шляхом)\n")
    w("> Файл **генерується** командою `python tools/gen_data.py` з тегів `*CWE:*` у `docs/tasks-catalog.md` "
      "і довідника `tools/cwe_data.py`. Руками не правити.\n")
    w(f"Стан: {auto_count} завдань з автоперевіркою, {catalog_count} завдань у каталозі, capstone M0–M11.\n")
    w("## Джерела й обмеження\n")
    w("- **OWASP Top 10:2025** (восьма редакція, листопад 2025): сторінки категорій на https://top10.owasp.org/2025, розділ «List of Mapped CWEs». "
      "Усього змаплено 249 записів (інші джерела пишуть 248; розбіжність не досліджувалась).")
    w("- **CWE Top 25 (MITRE, 2025)**: https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html. Це рейтинг MITRE, а не OWASP, але він найближчий до «найпоширеніших CWE».")
    w("- Списки CWE зчитані зі сторінок інструментом вибірки тексту; номери варто звіряти з першоджерелом перед цитуванням.")
    w("- Усі 249 CWE не розписані: частина це Java/ASP.NET/Struts-специфіка. Нижче **ключова вибірка** для Python + AWS + K8s + LLM; **вибір зроблено автором проєкту, не OWASP**.")
    w("- У OWASP Top 10:2025 SSRF більше не окрема категорія (злитий в A01), з'явилися A03 Software Supply Chain Failures і A10 Mishandling of Exceptional Conditions.\n")
    w("## Позначки\n")
    for k, v in LEGEND:
        w(f"- {k} {v}")
    w("")

    rows_all = []
    w("## Підсумок за категоріями OWASP Top 10:2025\n")
    w("| Категорія | CWE в категорії (owasp.org) | Ключових у вибірці | ✅ | 🟡 | 📝 | 🔗 | ❌ |")
    w("|---|---|---|---|---|---|---|---|")
    for cid, name, n, rows in CATS:
        c = Counter(best.get(cwe, NO) for cwe, _ in rows)
        rows_all += [best.get(cwe, NO) for cwe, _ in rows]
        w(f"| {cid} {name} | {n} | {len(rows)} | {c[OK]} | {c[PART]} | {c[DOC]} | {c[LAB]} | {c[NO]} |")
    c = Counter(rows_all)
    tot = sum(n for _, _, n, _ in CATS)
    w(f"| **Разом** | {tot} | **{len(rows_all)}** | **{c[OK]}** | **{c[PART]}** | **{c[DOC]}** | **{c[LAB]}** | **{c[NO]}** |\n")
    w(f"З {len(rows_all)} ключових CWE: повноцінно покрито {c[OK]} ({round(100 * c[OK] / len(rows_all))}%), "
      f"частково {c[PART]}, лише в каталозі {c[DOC]}, лише зовнішня лабораторія {c[LAB]}, немає взагалі {c[NO]}.\n")

    for cid, name, n, rows in CATS:
        w(f"### {cid}:2025 {name} ({n} CWE на owasp.org)\n")
        w("| CWE | Назва | Статус | Де |")
        w("|---|---|---|---|")
        for cwe, title in rows:
            w(f"| CWE-{cwe} | {title} | {best.get(cwe, NO)} | {', '.join(where.get(cwe, [])) or '—'} |")
        w("")

    w("## CWE Top 25 (MITRE, 2025)\n")
    w("| № | CWE | Назва | Статус | Де |")
    w("|---|---|---|---|---|")
    stats = Counter()
    for rank, cwe, title in TOP25:
        st = NA if cwe in TOP25_NA else best.get(cwe, NO)
        stats[st] += 1
        w(f"| {rank} | CWE-{cwe} | {title} | {st} | {', '.join(where.get(cwe, [])) or '—'} |")
    rel = len(TOP25) - stats[NA]
    w("")
    w(f"З 25 слабкостей {stats[NA]} стосуються пам'яті C/C++ (➖, для Python не актуальні). З решти {rel}: "
      f"✅ {stats[OK]}, 🟡 {stats[PART]}, 📝 {stats[DOC]}, 🔗 {stats[LAB]}, ❌ {stats[NO]}.\n")
    missing = [f"CWE-{cwe} ({title})" for _, cwe, title in TOP25 if cwe not in TOP25_NA and best.get(cwe, NO) in (NO, LAB)]
    if missing:
        w("**Без власної практики з Top 25:** " + "; ".join(missing) + ".\n")

    w("## Прогалини й пропоновані завдання\n")
    w("| Пріоритет | Що закриває | Ідея завдання з автоперевіркою |")
    w("|---|---|---|")
    for p, what, idea in GAPS:
        w(f"| {p} | {what} | {idea} |")
    w("")
    w("## Прогалини в наскрізному проєкті (capstone)\n")
    w("| Віха | Чого бракує |")
    w("|---|---|")
    for m, text in CAPSTONE_GAPS:
        w(f"| {m} | {text} |")
    w("")
    return "\n".join(out)
