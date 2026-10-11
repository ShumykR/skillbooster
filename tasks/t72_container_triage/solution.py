"""Завдання №72: діагностика контейнера, що «падає».

`diagnose(state) -> str` повертає ОДИН вердикт (код з таблиці) за станом контейнера.
`state` це словник, усі ключі необовʼязкові:
    reason            рядок із статусу pod: "OOMKilled", "Error", "ImagePullBackOff", ...
    exit_code         int або None (контейнер ще не завершувався)
    restart_policy    "Always" (за замовчуванням), "OnFailure", "Never"
    memory_limit_mb   ліміт памʼяті або None
    peak_memory_mb    пік споживання або None
    events            список рядків із `kubectl describe pod`
    log               останні рядки логу (рядок)

Порядок перевірок, береться ПЕРШЕ збігле правило (регістр у `events` і `log` ігноруй):
 1. reason у {"ErrImagePull", "ImagePullBackOff", "InvalidImageName"}  -> "IMAGE_PULL"
 2. reason == "CreateContainerConfigError" (немає ConfigMap/Secret)     -> "MISSING_CONFIG"
 3. exit_code is None (контейнер не завершувався)                       -> "NO_FAILURE"
 4. reason == "OOMKilled", або exit_code == 137 і peak_memory_mb >= 90% memory_limit_mb
    (обидва значення задані; порівнюй без дробів: peak * 10 >= limit * 9) -> "OOM_KILLED"
 5. exit_code у {137, 143} і в events є "liveness probe failed"         -> "LIVENESS_KILLED"
 6. за кодом виходу: 137 "KILLED_SIGKILL", 143 "SIGTERM", 126 "NOT_EXECUTABLE",
    127 "COMMAND_NOT_FOUND", 139 "SEGFAULT"
 7. exit_code == 0: "EXITED_CLEANLY", якщо restart_policy == "Always" (процес не тримає
    foreground і kubelet його перезапускає), інакше "NO_FAILURE"
 8. інший код виходу: шукай у `log` підрядки в такому порядку, перший збіг виграє:
    "address already in use" або "eaddrinuse" -> "PORT_IN_USE"
    "exec format error"                        -> "EXEC_FORMAT"
    "no module named" або "cannot find module" -> "MISSING_DEPENDENCY"
    "permission denied"                        -> "PERMISSION_DENIED"
    "connection refused" або "name or service not known" -> "DEPENDENCY_UNAVAILABLE"
    "is not set" або "missing required"        -> "MISSING_CONFIG"
 9. інакше -> "APP_ERROR"

`crashloop_backoff(restart_count) -> int`: пауза kubelet перед наступним перезапуском у
секундах: 10, 20, 40, ... подвоєння, не більше 300. `restart_count` це кількість вже
зроблених перезапусків; для 0 і менше пауза 0, для 1 це 10.

`recommend_memory_limit(samples_mb, headroom_pct=25, step_mb=64) -> int`: ліміт памʼяті за
вибіркою піків: максимум зі `samples_mb`, плюс `headroom_pct` відсотків, округлений ВГОРУ до
кратного `step_mb`. Без дробів (цілочисельна арифметика). Порожня вибірка, не додатні
значення, `headroom_pct < 0` або `step_mb <= 0` це `ValueError`.
"""


def diagnose(state: dict) -> str:
    raise NotImplementedError


def crashloop_backoff(restart_count: int) -> int:
    raise NotImplementedError


def recommend_memory_limit(samples_mb, headroom_pct=25, step_mb=64) -> int:
    raise NotImplementedError
