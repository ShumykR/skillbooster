import pytest

from solution import audit_manifests

GOOD = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  selector:
    matchLabels: {app: api}
  template:
    metadata:
      labels: {app: api, tier: web}
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: api
          image: ghcr.io/acme/api:1.4.2
          resources:
            requests: {cpu: 100m, memory: 128Mi}
            limits: {cpu: 500m, memory: 256Mi}
          readinessProbe: {httpGet: {path: /ready, port: 8000}}
          livenessProbe: {httpGet: {path: /health, port: 8000}}
---
apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector: {app: api}
  ports:
    - port: 80
      targetPort: 8000
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: cfg
data: {a: b}
"""


def deployment(container_extra="", pod_extra="", replicas="replicas: 2", image="app:1.0", resources=True,
               readiness=True, liveness=True, labels="{app: web}"):
    res = (
        "          resources:\n"
        "            requests: {cpu: 100m, memory: 64Mi}\n"
        "            limits: {cpu: 200m, memory: 128Mi}\n"
        if resources
        else ""
    )
    probes = ""
    if readiness:
        probes += "          readinessProbe: {tcpSocket: {port: 80}}\n"
    if liveness:
        probes += "          livenessProbe: {tcpSocket: {port: 80}}\n"
    return (
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\nspec:\n"
        f"  {replicas}\n"
        "  template:\n"
        f"    metadata:\n      labels: {labels}\n"
        "    spec:\n"
        f"{pod_extra}"
        "      containers:\n"
        "        - name: c\n"
        f"          image: {image}\n"
        f"{res}{probes}{container_extra}"
    )


NONROOT_POD = "      securityContext:\n        runAsNonRoot: true\n"


def ok(**kw):
    kw.setdefault("pod_extra", NONROOT_POD)
    return deployment(**kw)


def test_good_manifests_are_clean():
    assert audit_manifests(GOOD) == []


def test_helper_baseline_is_clean():
    assert audit_manifests(ok()) == []


def test_empty_input_and_empty_documents():
    assert audit_manifests("") == []
    assert audit_manifests("---\n---\n") == []
    assert audit_manifests("---\n" + ok() + "---\n") == []


@pytest.mark.parametrize(
    "image, bad",
    [("app", True), ("app:latest", True), ("registry:5000/app", True), ("registry:5000/app:2", False),
     ("app:1.0", False), ("app@sha256:" + "c" * 64, False)],
)
def test_latest_tag(image, bad):
    assert audit_manifests(ok(image=image)) == (["latest_tag:Deployment/web"] if bad else [])


def test_no_resources_missing_section_or_value():
    assert audit_manifests(ok(resources=False)) == ["no_resources:Deployment/web"]
    only_requests = ok(resources=False, container_extra="          resources:\n            requests: {cpu: 1, memory: 1Mi}\n")
    assert audit_manifests(only_requests) == ["no_resources:Deployment/web"]
    no_memory_limit = ok(
        resources=False,
        container_extra="          resources:\n            requests: {cpu: 1, memory: 1Mi}\n            limits: {cpu: 2}\n",
    )
    assert audit_manifests(no_memory_limit) == ["no_resources:Deployment/web"]


def test_probes_are_independent():
    assert audit_manifests(ok(readiness=False)) == ["no_readiness_probe:Deployment/web"]
    assert audit_manifests(ok(liveness=False)) == ["no_liveness_probe:Deployment/web"]
    assert audit_manifests(ok(readiness=False, liveness=False)) == [
        "no_liveness_probe:Deployment/web",
        "no_readiness_probe:Deployment/web",
    ]


def test_privileged_container():
    extra = "          securityContext:\n            privileged: true\n            runAsNonRoot: true\n"
    assert audit_manifests(ok(container_extra=extra)) == ["privileged:Deployment/web"]


def test_run_as_non_root_levels():
    assert audit_manifests(deployment()) == ["may_run_as_root:Deployment/web"]
    pod_false = "      securityContext:\n        runAsNonRoot: false\n"
    assert audit_manifests(deployment(pod_extra=pod_false)) == ["may_run_as_root:Deployment/web"]
    container_only = "          securityContext:\n            runAsNonRoot: true\n"
    assert audit_manifests(deployment(container_extra=container_only)) == []


def test_container_overrides_pod_for_run_as_non_root():
    container_false = "          securityContext:\n            runAsNonRoot: false\n"
    assert audit_manifests(ok(container_extra=container_false)) == ["may_run_as_root:Deployment/web"]


@pytest.mark.parametrize("replicas, bad", [("replicas: 1", True), ("replicas: 0", True), ("replicas: 2", False), ("paused: false", True)])
def test_single_replica_only_for_deployment(replicas, bad):
    assert audit_manifests(ok(replicas=replicas)) == (["single_replica:Deployment/web"] if bad else [])


def test_statefulset_is_checked_but_replicas_rule_is_not_applied():
    text = ok(replicas="replicas: 1", image="db").replace("kind: Deployment", "kind: StatefulSet")
    assert audit_manifests(text) == ["latest_tag:StatefulSet/web"]


def test_daemonset_without_replicas_is_fine():
    text = ok(replicas="minReadySeconds: 5").replace("kind: Deployment", "kind: DaemonSet")
    assert audit_manifests(text) == []


def test_findings_across_several_containers_are_deduplicated():
    text = (
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: multi}\n"
        "spec:\n  replicas: 2\n  template:\n    metadata: {labels: {app: m}}\n    spec:\n"
        "      securityContext: {runAsNonRoot: true}\n"
        "      containers:\n"
        "        - {name: a, image: x}\n"
        "        - {name: b, image: y}\n"
    )
    assert audit_manifests(text) == [
        "latest_tag:Deployment/multi",
        "no_liveness_probe:Deployment/multi",
        "no_readiness_probe:Deployment/multi",
        "no_resources:Deployment/multi",
    ]


def service(selector, name="svc"):
    return f"---\napiVersion: v1\nkind: Service\nmetadata:\n  name: {name}\nspec:\n  selector: {selector}\n  ports: [{{port: 80}}]\n"


def test_orphan_service_typo_in_selector():
    assert audit_manifests(ok() + service("{app: wev}")) == ["orphan_service:Service/svc"]


def test_orphan_service_partial_selector_matches():
    assert audit_manifests(ok(labels="{app: web, tier: front}") + service("{app: web}")) == []


def test_orphan_service_selector_with_extra_pair_does_not_match():
    text = ok(labels="{app: web}") + service("{app: web, tier: front}")
    assert audit_manifests(text) == ["orphan_service:Service/svc"]


def test_service_matching_any_workload_is_fine():
    other = ok(labels="{app: other}").replace("name: web", "name: other")
    assert audit_manifests(ok() + "---\n" + other + service("{app: other}")) == []


def test_service_without_selector_is_ignored():
    text = "apiVersion: v1\nkind: Service\nmetadata: {name: ext}\nspec:\n  type: ExternalName\n  externalName: a.example.com\n"
    assert audit_manifests(text) == []


def test_other_kinds_ignored_and_order_independent():
    assert audit_manifests(service("{app: web}") + "---\n" + ok()) == []


def test_everything_wrong_is_sorted():
    text = (
        "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: bad}\n"
        "spec:\n  template:\n    metadata: {labels: {app: bad}}\n    spec:\n"
        "      containers:\n"
        "        - name: c\n          image: bad\n          securityContext: {privileged: true}\n"
    ) + service("{app: nope}", name="lost")
    assert audit_manifests(text) == [
        "latest_tag:Deployment/bad",
        "may_run_as_root:Deployment/bad",
        "no_liveness_probe:Deployment/bad",
        "no_readiness_probe:Deployment/bad",
        "no_resources:Deployment/bad",
        "orphan_service:Service/lost",
        "privileged:Deployment/bad",
        "single_replica:Deployment/bad",
    ]
