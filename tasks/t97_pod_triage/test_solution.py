import pytest

from solution import diagnose, triage


def pod(statuses=(), *, phase="Running", init=(), conditions=(), images=None, **status):
    images = images or {}
    names = [s["name"] for s in list(init) + list(statuses)]
    return {
        "spec": {"containers": [{"name": n, "image": images.get(n, f"registry.example.com/{n}:1.0")} for n in names]},
        "status": {"phase": phase, "conditions": list(conditions), "containerStatuses": list(statuses),
                   "initContainerStatuses": list(init), **status},
    }


def cs(name="app", *, waiting=None, running=False, terminated=None, last=None, ready=False, restarts=0):
    state = {}
    if waiting:
        state["waiting"] = {"reason": waiting[0], "message": waiting[1] if len(waiting) > 1 else ""}
    if running:
        state["running"] = {}
    if terminated:
        state["terminated"] = terminated
    out = {"name": name, "ready": ready, "restartCount": restarts, "state": state}
    if last:
        out["lastState"] = {"terminated": last}
    return out


def unschedulable(message):
    return [{"type": "PodScheduled", "status": "False", "reason": "Unschedulable", "message": message}]


def diag(p, events=()):
    d = diagnose(p, events)
    return d["problem"], d["cause"], d["container"], d["detail"]


# ---------- Pending ------------------------------------------------------------


def test_insufficient_resources_lists_unique_sorted_resources():
    msg = "0/3 nodes are available: 1 Insufficient memory, 2 Insufficient cpu, 1 Insufficient memory."
    p = pod(phase="Pending", conditions=unschedulable(msg))
    assert diag(p) == ("Pending", "InsufficientResources", None, "cpu,memory")
    p = pod(phase="Pending", conditions=unschedulable("0/3 nodes are available: 3 Insufficient memory."))
    assert diag(p) == ("Pending", "InsufficientResources", None, "memory")


@pytest.mark.parametrize("message, cause", [
    ("0/3 nodes are available: 3 node(s) had untolerated taint {dedicated: gpu}.", "Taint"),
    ("0/3 nodes are available: 3 node(s) didn't match Pod's node affinity/selector.", "NodeSelector"),
    ("0/3 nodes are available: 3 Node Selector mismatch", "NodeSelector"),
    ("0/3 nodes are available: pod has unbound immediate PersistentVolumeClaims.", "PVCNotBound"),
    ("0/3 nodes are available: 3 node(s) had volume node affinity conflict.", "NodeSelector"),
    ("something we have not seen before", "Unschedulable"),
])
def test_pending_causes(message, cause):
    assert diag(pod(phase="Pending", conditions=unschedulable(message)))[:2] == ("Pending", cause)


def test_resources_are_checked_before_other_scheduling_hints():
    msg = "0/3 nodes are available: 1 Insufficient cpu, 2 node(s) had untolerated taint {a: b}."
    assert diag(pod(phase="Pending", conditions=unschedulable(msg)))[1] == "InsufficientResources"


def test_scheduled_pending_pod_falls_through_to_container_checks():
    conditions = [{"type": "PodScheduled", "status": "True"}]
    p = pod([cs(waiting=("ImagePullBackOff", "Back-off pulling image: not found"))], phase="Pending", conditions=conditions)
    assert diag(p)[0] == "ImagePullBackOff"


# ---------- images and config --------------------------------------------------


@pytest.mark.parametrize("reason, message, cause", [
    ("ErrImagePull", "manifest unknown: manifest unknown", "ImageNotFound"),
    ("ImagePullBackOff", "Back-off pulling image: Error: image repo/app:9 not found", "ImageNotFound"),
    ("ErrImagePull", "pull access denied for private/app, repository does not exist or may require authorization", "RegistryAuth"),
    ("ErrImagePull", "Head https://x/v2/app: unauthorized: authentication required", "RegistryAuth"),
    ("ImagePullBackOff", "dial tcp: lookup registry.corp: no such host", "RegistryUnreachable"),
    ("ErrImagePull", "Get https://registry/v2/: net/http: request canceled (Client.Timeout exceeded) i/o TIMEOUT", "RegistryUnreachable"),
    ("ImagePullBackOff", "", "ImagePull"),
    ("ErrImagePull", "Failed to pull image: Repository Not Found", "ImageNotFound"),
])
def test_image_pull_causes(reason, message, cause):
    p = pod([cs(waiting=(reason, message))], phase="Pending", images={"app": "repo/app:9"})
    assert diag(p) == ("ImagePullBackOff", cause, "app", "repo/app:9")


def test_image_detail_is_the_image_of_the_failing_container():
    p = pod([cs("sidecar", running=True, ready=True), cs("worker", waiting=("ErrImagePull", "not found"))],
            phase="Pending", images={"sidecar": "s:1", "worker": "w:2"})
    assert diag(p) == ("ImagePullBackOff", "ImageNotFound", "worker", "w:2")


def test_missing_secret_configmap_and_bad_config():
    secret = pod([cs(waiting=("CreateContainerConfigError", 'secret "db-credentials" not found'))], phase="Pending")
    assert diag(secret) == ("CreateContainerConfigError", "MissingSecret", "app", "db-credentials")
    cm = pod([cs(waiting=("CreateContainerConfigError", 'configmap "app-settings" not found'))], phase="Pending")
    assert diag(cm) == ("CreateContainerConfigError", "MissingConfigMap", "app", "app-settings")
    key = pod([cs(waiting=("CreateContainerConfigError", 'couldn\'t find key DB_URL in Secret default/db'))], phase="Pending")
    assert diag(key) == ("CreateContainerConfigError", "BadConfig", "app", None)


def test_failed_mount_event():
    p = pod([cs(waiting=("ContainerCreating",))], phase="Pending")
    events = [{"reason": "Scheduled", "message": "ok"}, {"reason": "FailedMount", "message": 'MountVolume.SetUp failed: secret "tls" not found'}]
    assert diag(p, events) == ("ContainerCreating", "MountFailed", "app", None)
    assert diag(p, events[:1])[0] == "Unknown", "без події FailedMount це просто ще створюється"


# ---------- crashes ------------------------------------------------------------


def crash(last, **kw):
    return pod([cs(waiting=("CrashLoopBackOff", "back-off 5m0s restarting failed container"), last=last, restarts=7, **kw)])


@pytest.mark.parametrize("code, cause", [
    (1, "AppError"), (2, "AppError"), (126, "NotExecutable"), (127, "CommandNotFound"),
    (137, "Killed"), (139, "Segfault"), (143, "Terminated"), (0, "ExitedCleanly"),
])
def test_crashloop_by_exit_code(code, cause):
    p = crash({"reason": "Error", "exitCode": code})
    assert diag(p) == ("CrashLoopBackOff", cause, "app", str(code))


def test_oomkilled_in_last_state_beats_crashloop():
    p = crash({"reason": "OOMKilled", "exitCode": 137})
    assert diag(p) == ("OOMKilled", "MemoryLimit", "app", None)


def test_oomkilled_right_after_the_kill():
    p = pod([cs(terminated={"reason": "OOMKilled", "exitCode": 137}, restarts=1)])
    assert diag(p) == ("OOMKilled", "MemoryLimit", "app", None)


def test_liveness_probe_failure_is_a_cause_of_crashloop():
    events = [{"reason": "Unhealthy", "message": "Liveness probe failed: HTTP probe failed with statuscode: 500"},
              {"reason": "Killing", "message": "Container app failed liveness probe, will be restarted"}]
    assert diag(crash({"reason": "Error", "exitCode": 137}), events) == ("CrashLoopBackOff", "LivenessProbe", "app", None)


def test_oom_beats_liveness_events():
    events = [{"reason": "Unhealthy", "message": "Liveness probe failed: timeout"}]
    assert diag(crash({"reason": "OOMKilled", "exitCode": 137}), events)[0] == "OOMKilled"


def test_crashloop_without_last_state():
    assert diag(crash(None)) == ("CrashLoopBackOff", "AppError", "app", None)


def test_failed_pod_with_restart_policy_never():
    p = pod([cs(terminated={"reason": "Error", "exitCode": 2})], phase="Failed")
    assert diag(p) == ("Error", "AppError", "app", "2")
    p = pod([cs(terminated={"reason": "Error", "exitCode": 127})], phase="Failed")
    assert diag(p)[:2] == ("Error", "CommandNotFound")


def test_first_problem_container_wins():
    p = pod([cs("web", running=True, ready=True), cs("worker", waiting=("CrashLoopBackOff",), last={"exitCode": 1}),
             cs("cache", waiting=("ErrImagePull", "not found"))])
    assert diag(p)[:3] == ("CrashLoopBackOff", "AppError", "worker")


# ---------- init containers ----------------------------------------------------


def test_init_container_problems_get_a_prefix_and_come_first():
    init = [cs("migrate", waiting=("CrashLoopBackOff",), last={"reason": "Error", "exitCode": 1}, restarts=4)]
    main = [cs("app", waiting=("PodInitializing",))]
    p = pod(main, init=init, phase="Pending")
    assert diag(p) == ("Init:CrashLoopBackOff", "AppError", "migrate", "1")


def test_init_container_is_reported_before_a_broken_main_container():
    init = [cs("migrate", waiting=("CrashLoopBackOff",), last={"exitCode": 1})]
    main = [cs("app", waiting=("ErrImagePull", "not found"))]
    assert diag(pod(main, init=init, phase="Pending"))[:3] == ("Init:CrashLoopBackOff", "AppError", "migrate")


def test_init_image_pull_and_oom():
    p = pod([cs("app", waiting=("PodInitializing",))], init=[cs("wait-db", waiting=("ErrImagePull", "unauthorized"))], phase="Pending",
            images={"wait-db": "busybox:1"})
    assert diag(p) == ("Init:ImagePullBackOff", "RegistryAuth", "wait-db", "busybox:1")
    p = pod([cs("app", waiting=("PodInitializing",))], init=[cs("seed", terminated={"reason": "OOMKilled", "exitCode": 137})], phase="Pending")
    assert diag(p)[:2] == ("Init:OOMKilled", "MemoryLimit")


def test_finished_init_containers_are_not_a_problem():
    init = [cs("migrate", terminated={"reason": "Completed", "exitCode": 0})]
    p = pod([cs("app", running=True, ready=True)], init=init)
    assert diag(p)[0] == "Healthy"


# ---------- eviction and readiness --------------------------------------------


def test_evicted_pods():
    p = pod(phase="Failed", reason="Evicted", message="The node was low on resource: memory. Container app was using 2Gi.")
    assert diag(p) == ("Evicted", "NodePressure", None, "memory")
    p = pod(phase="Failed", reason="Evicted", message="Pod ephemeral local storage usage exceeds the total limit. ephemeral-storage 1Gi, disk")
    assert diag(p)[3] == "ephemeral-storage"
    p = pod(phase="Failed", reason="Evicted", message="The node was low on resource: disk.")
    assert diag(p)[3] == "disk"
    assert diag(pod(phase="Failed", reason="Evicted", message="node drained")) == ("Evicted", "Evicted", None, None)


def test_evicted_wins_over_container_states():
    p = pod([cs(waiting=("CrashLoopBackOff",), last={"exitCode": 1})], phase="Failed", reason="Evicted", message="low on memory")
    assert diag(p)[0] == "Evicted"


def test_not_ready_running_container():
    p = pod([cs(running=True, ready=False)])
    assert diag(p) == ("NotReady", "Starting", "app", None)
    events = [{"reason": "Unhealthy", "message": "Readiness probe failed: connection refused"}]
    assert diag(p, events) == ("NotReady", "ReadinessProbe", "app", None)


# ---------- healthy / unknown / triage ----------------------------------------


def test_healthy_completed_and_unknown():
    assert diag(pod([cs(running=True, ready=True), cs("side", running=True, ready=True)])) == ("Healthy", None, None, None)
    assert diag(pod([cs(terminated={"reason": "Completed", "exitCode": 0})], phase="Succeeded")) == ("Completed", None, None, None)
    assert diag(pod(phase="Pending"))[0] == "Unknown"
    assert diag({})[0] == "Unknown"


def test_events_can_be_any_iterable():
    p = pod([cs(running=True, ready=False)])
    events = ({"reason": "Unhealthy", "message": "Readiness probe failed"} for _ in range(1))
    assert diag(p, events)[1] == "ReadinessProbe"


def test_triage_groups_by_problem_and_skips_healthy():
    bad_image = pod([cs(waiting=("ErrImagePull", "not found"))], phase="Pending")
    oom = crash({"reason": "OOMKilled", "exitCode": 137})
    pods = {
        "web-b": (bad_image, []), "web-a": (bad_image, []), "ok": (pod([cs(running=True, ready=True)]), []),
        "job": (pod([cs(terminated={"exitCode": 0})], phase="Succeeded"), []), "worker": (oom, []),
    }
    assert triage(pods) == {"ImagePullBackOff": ["web-a", "web-b"], "OOMKilled": ["worker"]}
    assert triage({}) == {}
