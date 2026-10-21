#!/usr/bin/env python3
"""Запускає тести завдань і записує прогрес для сайту SkillBooster.

Приклади:
    python check.py            # усі завдання
    python check.py t02 t37    # лише вибрані (за префіксом імені папки)
    python check.py --open     # і одразу відкрити сайт, щоб відмітити пройдені

Після запуску створюються skillbooster-sync.html і skillbooster-progress.json.
Відкрий skillbooster-sync.html (або запусти з --open): сайт запропонує позначити
пройдені завдання як «перевірено тестами». Запасний шлях: «Налаштування» →
«Імпорт JSON». Решта прогресу не змінюється.
Сайт не на file://, а за адресою (GitHub Pages, http.server)? Задай SKILLBOOSTER_URL.
"""
import html
import json
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def task_dirs(filters):
    dirs = sorted(p for p in ROOT.iterdir() if p.is_dir() and re.match(r"t\d+_", p.name))
    if filters:
        dirs = [d for d in dirs if any(d.name.startswith(f) for f in filters)]
    return dirs


def run_task(d):
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider", str(d)],
        cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout + proc.stderr


def main():
    filters = [a for a in sys.argv[1:] if not a.startswith("-")]
    dirs = task_dirs(filters)
    if not dirs:
        print("Завдань не знайдено.")
        return 1
    passed = {}
    for d in dirs:
        code, out = run_task(d)
        task_id = "t" + re.match(r"t(\d+)_", d.name).group(1).lstrip("0")
        ok = code == 0
        print(("✅" if ok else "❌"), d.name)
        if ok:
            passed[task_id] = "done"
        else:
            tail = "\n".join(out.strip().splitlines()[-12:])
            print("   " + tail.replace("\n", "\n   "))
    (ROOT / "skillbooster-progress.json").write_text(
        json.dumps({"mode": "merge", "tasks": passed}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nПройдено {len(passed)} з {len(dirs)}.")
    if passed:
        sync = write_sync_page(list(passed))
        print(f"Відмітити на сайті: відкрий tasks/{sync.name} (або запусти з --open)")
        if "--open" in sys.argv:
            webbrowser.open(sync.as_uri())
    return 0


def write_sync_page(ids):
    """HTML-перехідник: Windows губить #фрагмент у file://-посиланнях, а JS-редирект ні."""
    site = os.environ.get("SKILLBOOSTER_URL") or (ROOT.parent / "index.html").as_uri()
    target = site.split("#")[0] + "#/sync/" + ",".join(ids)
    page = ROOT / "skillbooster-sync.html"
    js_target = json.dumps(target).replace("<", "\\u003c")
    page.write_text(
        '<!doctype html><meta charset="utf-8"><title>SkillBooster sync</title>'
        f"<script>location.replace({js_target});</script>"
        f'<a href="{html.escape(target)}">Відкрити SkillBooster</a>\n',
        encoding="utf-8",
    )
    return page


if __name__ == "__main__":
    sys.exit(main())
