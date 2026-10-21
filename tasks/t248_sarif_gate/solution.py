r"""Завдання №248: security gate на SARIF.

CI запускає кілька сканерів (SAST, секрети, IaC, залежності), і кожен віддає звіт SARIF 2.1.0
(словник, уже розібраний із JSON). Gate зливає звіти, відсікає старі знахідки (baseline), враховує
винятки з власником і терміном і вирішує pass/fail з поясненням.

1. `merge_sarif(docs: list[dict]) -> list[dict]`
   Повертає знахідки `{"fingerprint", "tool", "rule", "severity", "path", "line", "message"}`,
   відсортовані за `(path, line, rule, tool, fingerprint)`.
   * Некоректний документ (не `dict`, `version` не `"2.1.0"`, `runs` не список) це `ValueError`.
   * `tool` = `run.tool.driver.name` (немає: `"unknown"`). `rule` = `result.ruleId`, а якщо його
     немає, то `driver.rules[result.ruleIndex].id` (немає й цього: `"unknown"`).
   * `path` = `locations[0].physicalLocation.artifactLocation.uri`, нормалізований: `%XX`
     декодується (`urllib.parse.unquote`), префікс `file://` прибирається, зворотний слеш стає `/`, на
     початку прибираються `./` і `/`. `line` = `region.startLine` (немає локації: `path=""`, `line=0`).
   * `message` = `result.message.text` (немає: `""`).
   * Результати з непорожнім `suppressions` (прийняті в коді) пропускаються.
   * `severity` один із `critical|high|medium|low|info`. Спершу `security-severity`
     (число або рядок із числом) із `result.properties`, інакше з `properties` правила (`driver.rules`
     за id): `>= 9.0` critical, `>= 7.0` high, `>= 4.0` medium, `> 0` low, `0` info. Немає чи не
     число: за `level` результату, інакше за `defaultConfiguration.level` правила, інакше
     `warning`; `error` high, `warning` medium, `note` low, `none` info.
   * `fingerprint` стабільний при зсуві рядків і перейменуванні звіту: перші 16 hex-символів
     `sha256` від `"\x1f".join([tool, rule, path, text])`, де `text` це нормалізований фрагмент
     (`region.snippet.text`, а якщо його немає, то `message`): `" ".join(text.split())`.
     Рядок `line` у хеш НЕ входить. Якщо кілька знахідок мають однакову четвірку (tool, rule, path,
     text), то в порядку зростання `line` перша лишає базовий відбиток, а N-та отримує суфікс
     `"#N"` (наприклад `"ab12...#2"`): друге однакове порушення не ховається за baseline першого.
   * Один і той самий результат, що повторюється в двох документах від ТОГО САМОГО tool з тим
     самим `(rule, path, line, text)`, зливається в одну знахідку; різні tools не зливаються.

2. `evaluate_gate(findings, baseline, waivers, policy, today) -> dict`
   `baseline`: множина відбитків. `waivers`: список `{"fingerprint", "owner", "reason",
   "expires"}` (`expires` ISO-дата `YYYY-MM-DD`). `policy`: `{"block_on": "high",
   "max_waiver_days": 90}` (обидва ключі необовʼязкові; незнайоме імʼя severity це
   `ValueError`). `today`: `datetime.date`.
   Для кожної знахідки по порядку:
   1. severity нижче `block_on` це «ignored» (лише лічильник);
   2. відбиток у `baseline` це «baselined»;
   3. є ДІЙСНИЙ виняток для відбитка це «waived»;
   4. інакше блокує (`blocking`).
   Виняток дійсний, коли: `owner` і `reason` непорожні (після `strip`), `expires` розбирається
   як ISO-дата, `today <= expires` (останній день включно) і `expires - today <= max_waiver_days`.
   Виняток оцінюється лише для знахідок, що дійшли до кроку 3 (не ignored і не baselined).
   Недійсний виняток не звільняє знахідку, а додається в `problems` одним записом
   `{"fingerprint", "problem"}`, де `problem` це `no-owner`, `no-reason`, `bad-date`, `expired`
   чи `too-long` (перевіряй у цьому порядку, перший, що спрацював). Якщо знахідка заблокована
   через недійсний виняток, її `reason` це `"waiver <problem>"`, інакше `"new finding"`.
   Якщо для відбитка кілька винятків, береться той, що спливає найпізніше.
   Результат:
       {"passed": bool,
        "blocking": [{"fingerprint", "severity", "rule", "path", "line", "reason"}, ...],
        "waived": [відбитки, відсортовані],
        "baselined": [відбитки, відсортовані],
        "ignored": int,
        "problems": [...],            # за відбитком
        "unused_waivers": [відбитки винятків, яким не відповідає жодна знахідка, відсортовані],
        "explanation": str}
   `blocking` відсортований за (severity від найвищої, path, line, fingerprint). `passed` це
   `not blocking`. `explanation` починається з `"PASS"` чи `"FAIL"`; при FAIL містить
   кількість блокуючих знахідок і відбиток кожної.
"""
import datetime


def merge_sarif(docs: list[dict]) -> list[dict]:
    raise NotImplementedError


def evaluate_gate(findings: list[dict], baseline: set, waivers: list[dict], policy: dict,
                  today: datetime.date) -> dict:
    raise NotImplementedError
