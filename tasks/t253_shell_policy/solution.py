"""Завдання №253: політика shell-команд для coding-агента (allow / ask / deny).

Агент пропонує shell-команду, а політика (код, не модель) вирішує ДО запуску: `allow` (виконати),
`ask` (спитати людину) чи `deny` (заборонити). Команду НЕ виконуємо, лише розбираємо текст.
Принципи: `deny` має пріоритет над `ask`, `ask` над `allow`; усе невідоме це `ask`
(fail closed); складні конструкції розбираються, а не відхиляються оптом.

`decide(command, *, cwd, workspace, allowed_hosts=(), home="/home/dev") -> dict`
    Повертає `{"decision": "allow"|"ask"|"deny", "rule": str, "reason": str}`.
    `reason` це непорожній людський опис, що містить імʼя команди, через яку ухвалено рішення.
    `cwd` це поточна тека агента, `workspace` корінь проєкту, `home` домашня тека. Усі шляхи
    абсолютні, POSIX. «Всередині workspace» означає: нормалізований шлях (`posixpath.normpath`)
    дорівнює `workspace` або лежить під ним. Символічні посилання не розглядаємо.

    Розбір (як у shell):
    * команди розділяють `;`, `&&`, `||`, `&`, `|`, перенос рядка й дужки `( )`; лапки `'...'`
      і `"..."` та `\\`-екранування поважаються (оператор у лапках це звичайний текст);
    * вкладені команди `$(...)`, зворотні лапки `` `...` ``, `<(...)`, `>(...)` оцінюються
      як окремі команди в тому ж `cwd`, а слово з такою вставкою вважається «динамічним»
      (його значення невідоме, шлях із нього НЕ можна довести як безпечний);
    * `bash -c '...'`, `sh -c`, `zsh -c`, `dash -c`, `ksh -c` (прапорець `c` у групі, як `-lc`)
      і `eval '...'` рекурсивно розбирають свій рядок як нову команду;
    * присвоєння `NAME=value` на початку й обгортки `env`, `command`, `nohup`, `time`, `nice [-n N]`,
      `timeout [прапорці] ДОВЖИНА` знімаються: оцінюється команда всередині;
    * імʼя команди це `basename` (`/bin/rm` це `rm`);
    * `~` на початку слова, `$HOME` і `${HOME}` це `home`; будь-яка інша змінна (`$X`) робить слово
      динамічним; коментар `# ...` ігнорується; `<<` (heredoc) і незакриті лапки це `ask`/`unparseable`;
    * перенаправлення `>`, `>>`, `&>`, `<` (і з номером дескриптора, як `2>`) мають ціль-шлях;
      `2>&1` не має. Цілі `/dev/null`, `/dev/stdout`, `/dev/stderr` завжди дозволені.
    * `cd ТЕКА` у послідовності (`;`, `&&`, `||`, новий рядок) змінює `cwd` для наступних команд;
      `cd -` чи динамічна тека роблять `cwd` невідомим, а відносні шляхи після цього
      «невідомими» (вважаються поза workspace). Усередині конвеєра `cd` `cwd` не змінює.

    Правила. Загальна оцінка це НАЙСУВОРІШЕ рішення з усіх команд (включно з вкладеними).
    Якщо правил кілька з однаковою суворістю, `rule` це той, що раніше в списку нижче.

    DENY (за порядком пріоритету):
    | rule                      | коли |
    |---------------------------|------|
    | `secret-read`             | будь-яка команда має операнд чи ціль перенаправлення, що є секретом: імʼя файлу починається з `.env`, окрім `.env.example`, `.env.sample`, `.env.template`; або шлях (з `~`) лежить у `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.kube`, `~/.config/gh` чи це `~/.netrc`, `~/.npmrc`, `~/.pypirc`. Операнд перевіряється, якщо виглядає як шлях (містить `/`, починається з `~` чи `.`) або його імʼя починається з `.env`. Те саме для `@файл` у `curl -d @файл` / `-F x=@файл` |
    | `privilege-escalation`    | `sudo`, `su`, `doas` |
    | `pipe-to-shell`           | інтерпретатор (`sh bash zsh dash ksh python python3 perl ruby node`) без скрипта й без `-c`, який у конвеєрі читає stdin після `curl`, `wget`, `base64`, `xxd` або `openssl` (`curl ... \\| sh`, `base64 -d \\| bash`); АБО `bash/sh/eval/source/.` чи інтерпретатор, чий операнд містить вставку з `curl`/`wget` (`sh -c "$(curl ...)"`, `bash <(curl ...)`) |
    | `git-force-push`          | `git push` з `--force`, `--mirror`, коротким прапорцем, що містить `f` (`-f`, `-fu`), або refspec з `+` (`+main`). Глобальні опції git перед підкомандою (`-C dir`, `-c k=v`) пропускаються. `--force-with-lease` НЕ вважається силовим |
    | `rm-outside-workspace`    | `rm` (з будь-якими прапорцями) має операнд поза workspace або невідомий/динамічний. Операнди після `--` теж шляхи |
    | `write-outside-workspace` | `mkdir touch cp mv tee` мають операнд поза workspace/невідомий; ціль `>`, `>>`, `&>` поза workspace/невідома; `curl -o/--output`, `wget -O/-P` ведуть поза workspace |
    | `network-host`            | `curl`/`wget` має URL (операнд зі `://` або після `--url`), хост якого (`urllib.parse.urlparse(url).hostname`, нижній регістр, без порту й `user@`) НЕ входить до `allowed_hosts`, або URL динамічний |
    | `network-tool`            | `nc ncat telnet ssh scp sftp ftp rsync socat` |

    ASK (за порядком пріоритету):
    `unparseable` (незакриті лапки, heredoc, надто глибоке вкладення), `eval-dynamic` (`eval` чи `sh -c` з динамічним рядком),
    `run-script` (оболонка з файлом-скриптом чи `-c` без рядка; інтерпретатор зі скриптом), `run-interpreter`
    (`python/perl/ruby/node` зі скриптом/`-c`/`-e` або без нічого, крім `python -m pytest|ruff|mypy`, що `allow`),
    `pipe-to-interpreter` (інтерпретатор у конвеєрі після будь-чого іншого), `source` (`source`, `.`),
    `network-upload` (`curl`/`wget` вивантажують дані: `-T`, `--upload-file`, `-d @x`, `-F a=@x`, `--post-file`),
    `network-no-target` (`curl`/`wget` без URL зі схемою), `git-push` (звичайний push), `git-other`
    (будь-яка підкоманда git поза списком allow), `rm-in-workspace` (`rm` лише всередині workspace),
    `find-exec` (`find` з `-exec -execdir -ok -okdir -delete -fprint -fprintf`), `outside-workspace`
    (команда читання з операндом поза workspace чи невідомим, `cd` поза workspace чи в невідому теку, ціль `<` поза workspace),
    `unknown-command` (будь-яка інша команда), `empty` (порожній рядок).

    ALLOW (`rule` = `"allow"`):
    * читання: `ls cat head tail wc grep rg find tree diff sort uniq stat file du`, якщо ВСІ операнди-не-прапорці
      всередині workspace (без операндів перевіряється `cwd`);
    * `pwd echo date true false whoami which printf sleep` (шляхи не перевіряються, лише `secret-read`);
    * `pytest ruff mypy` та `python|python3 -m pytest|ruff|mypy`;
    * `git status|diff|log|show|add|commit|rev-parse|ls-files|blame`;
    * `mkdir touch cp mv tee` з операндами всередині workspace;
    * `cd` усередину workspace;
    * `curl`/`wget` до хостів з `allowed_hosts` без вивантаження даних;
    * присвоєння змінних без команди.
"""


def decide(command: str, *, cwd: str, workspace: str, allowed_hosts=(), home: str = "/home/dev") -> dict:
    raise NotImplementedError
