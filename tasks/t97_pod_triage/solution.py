"""Завдання №97: налагодження pod'ів: CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled.

Вхід це JSON, який дає `kubectl get pod -o json` (спрощений), та події `kubectl get events` для цього pod'а:
    pod = {"spec": {"containers": [{"name": "app", "image": "ghcr.io/me/app:1.2"}], ...},
           "status": {"phase": "Pending|Running|Succeeded|Failed", "reason": "Evicted" (необовʼязково), "message": "...",
                      "conditions": [{"type": "PodScheduled", "status": "False", "reason": "Unschedulable", "message": "..."}],
                      "initContainerStatuses": [...], "containerStatuses": [
                          {"name": "app", "ready": bool, "restartCount": int,
                           "state": {"waiting": {"reason": "...", "message": "..."}} | {"running": {}} | {"terminated": {"reason", "exitCode"}},
                           "lastState": {"terminated": {"reason": "OOMKilled", "exitCode": 137}}}]}}
    events = [{"reason": "Unhealthy", "message": "Liveness probe failed: ..."}, ...]

diagnose(pod, events=()) -> {"problem", "cause", "container", "detail"}
    `problem` це заголовок для людини, `cause` корінна причина, `container` імʼя контейнера (None, коли проблема на рівні pod'а),
    `detail` додаткова деталь (рядок або None). Перше правило, що спрацювало, перемагає:
    1. status.reason == "Evicted": problem "Evicted"; cause "NodePressure", якщо в status.message є "memory", "ephemeral-storage"
       або "disk" (detail = перше з цих слів у такому порядку: memory, ephemeral-storage, disk), інакше cause "Evicted" (detail None).
    2. phase "Pending" і умова PodScheduled зі status "False": problem "Pending"; cause за message умови:
         "Insufficient cpu/memory" -> "InsufficientResources", detail = унікальні ресурси через кому, відсортовані ("cpu,memory");
         "untolerated taint" -> "Taint"; "node affinity" або "node selector" (регістр не важливий) -> "NodeSelector";
         "persistentvolumeclaim" (регістр не важливий) -> "PVCNotBound"; інакше "Unschedulable". (container None)
    3. Контейнери: спершу initContainerStatuses (проблема тоді отримує префікс "Init:", напр. "Init:CrashLoopBackOff"), потім
       containerStatuses; береться перший за порядком контейнер із проблемою:
         * waiting.reason "ErrImagePull" або "ImagePullBackOff": problem "ImagePullBackOff", detail = image контейнера зі spec;
           cause: у message є "not found" або "manifest unknown" -> "ImageNotFound"; "unauthorized", "denied" або
           "authentication required" -> "RegistryAuth"; "no such host" або "timeout" -> "RegistryUnreachable"; інакше "ImagePull"
           (message порівнюється без урахування регістру);
         * waiting.reason "CreateContainerConfigError": problem те саме; cause "MissingSecret" (message містить `secret "<name>" not found`),
           "MissingConfigMap" (`configmap "<name>" not found`), інакше "BadConfig"; detail = <name> або None;
         * waiting.reason "ContainerCreating" і серед подій є reason "FailedMount": problem "ContainerCreating", cause "MountFailed";
         * waiting.reason "CrashLoopBackOff" або стан terminated із reason "OOMKilled" (також перевіряй lastState.terminated):
             - останній вихід був "OOMKilled": problem "OOMKilled", cause "MemoryLimit";
             - серед подій є повідомлення з "Liveness probe failed": problem "CrashLoopBackOff", cause "LivenessProbe";
             - інакше problem "CrashLoopBackOff", cause за exitCode останнього виходу: 126 "NotExecutable", 127 "CommandNotFound",
               137 "Killed", 139 "Segfault", 143 "Terminated", 0 "ExitedCleanly", інші "AppError"; detail = str(exitCode);
         * state.terminated з exitCode != 0 без waiting (restartPolicy Never): problem "Error", cause за тією ж таблицею exitCode;
         * state.running, ready False: problem "NotReady"; cause "ReadinessProbe", якщо серед подій є "Readiness probe failed", інакше "Starting".
    4. phase "Succeeded": problem "Completed" (cause None, container None, detail None).
       Усі контейнери running і ready (phase "Running"): problem "Healthy". Інакше problem "Unknown".
    Поля cause/container/detail, яких немає в правилі, це None.

triage(pods) -> dict[str, list[str]]
    `pods`: {імʼя: (pod, events)}. Результат: {problem: [відсортовані імена]} лише для problem, що зустрілись; "Healthy" та
    "Completed" не включаються.
"""


def diagnose(pod: dict, events=()) -> dict:
    raise NotImplementedError


def triage(pods: dict[str, tuple[dict, list[dict]]]) -> dict[str, list[str]]:
    raise NotImplementedError
