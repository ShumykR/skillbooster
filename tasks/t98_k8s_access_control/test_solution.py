import pytest

from solution import connection_allowed, isolation, pod_security_violations, rbac_allowed, rbac_audit


def pod(name, namespace="shop", **labels):
    return {"name": name, "namespace": namespace, "labels": labels}


NAMESPACES = {"shop": {"team": "store"}, "monitoring": {"team": "platform"}, "other": {}}
WEB = pod("web", app="web")
API = pod("api", app="api")
DB = pod("db", app="db")
PROM = pod("prom", "monitoring", app="prometheus")
STRANGER = pod("x", "other", app="web")


def policy(selector, *, ns="shop", ingress=None, egress=None, types=None):
    p = {"namespace": ns, "podSelector": {"matchLabels": selector} if selector is not None else {}}
    if ingress is not None:
        p["ingress"] = ingress
    if egress is not None:
        p["egress"] = egress
    if types is not None:
        p["policyTypes"] = types
    return p


def allowed(policies, src, dst, port=5432, protocol="TCP"):
    return connection_allowed(policies, NAMESPACES, src, dst, port, protocol)


# ---------- NetworkPolicy: isolation -------------------------------------------


def test_no_policies_means_everything_is_allowed():
    assert isolation([], DB) == {"ingress": False, "egress": False}
    assert allowed([], STRANGER, DB)


def test_isolation_by_selector_namespace_and_types():
    p = policy({"app": "db"}, ingress=[])
    assert isolation([p], DB) == {"ingress": True, "egress": False}
    assert isolation([p], API) == {"ingress": False, "egress": False}
    assert isolation([p], pod("db", "other", app="db"))["ingress"] is False, "політика діє лише у своєму namespace"
    with_egress = policy({"app": "db"}, egress=[])
    assert isolation([with_egress], DB) == {"ingress": True, "egress": True}, "ingress типу за замовчуванням завжди"
    only_egress = policy({"app": "db"}, egress=[], types=["Egress"])
    assert isolation([only_egress], DB) == {"ingress": False, "egress": True}


def test_empty_selector_selects_all_pods_in_namespace():
    deny_all = policy(None, types=["Ingress"])
    assert isolation([deny_all], DB)["ingress"] and isolation([deny_all], WEB)["ingress"]
    assert not isolation([deny_all], PROM)["ingress"]


# ---------- NetworkPolicy: ingress rules ---------------------------------------


def test_default_deny_then_allow_from_api():
    deny = policy(None, types=["Ingress"])
    allow_api = policy({"app": "db"}, ingress=[{"from": [{"podSelector": {"matchLabels": {"app": "api"}}}], "ports": [{"port": 5432}]}])
    policies = [deny, allow_api]
    assert allowed(policies, API, DB, 5432)
    assert not allowed(policies, WEB, DB, 5432), "web не api"
    assert not allowed(policies, API, DB, 3306), "не той порт"
    assert not allowed(policies, API, DB, 5432, "UDP"), "не той протокол"
    assert allowed(policies, DB, WEB, 80) is False, "web теж ізольований default-deny"


def test_pod_selector_peer_is_limited_to_policy_namespace():
    p = policy({"app": "db"}, ingress=[{"from": [{"podSelector": {"matchLabels": {"app": "web"}}}]}])
    assert allowed([p], WEB, DB)
    assert not allowed([p], STRANGER, DB), "app=web, але з іншого namespace"


def test_namespace_selector_alone_allows_every_pod_there():
    p = policy({"app": "db"}, ingress=[{"from": [{"namespaceSelector": {"matchLabels": {"team": "platform"}}}]}])
    assert allowed([p], PROM, DB)
    assert allowed([p], pod("anything", "monitoring"), DB)
    assert not allowed([p], STRANGER, DB)
    assert not allowed([p], WEB, DB), "shop має team=store"


def test_namespace_and_pod_selector_in_one_peer_is_and():
    one_peer = {"namespaceSelector": {"matchLabels": {"team": "platform"}}, "podSelector": {"matchLabels": {"app": "prometheus"}}}
    p = policy({"app": "db"}, ingress=[{"from": [one_peer]}])
    assert allowed([p], PROM, DB)
    assert not allowed([p], pod("grafana", "monitoring", app="grafana"), DB)
    assert not allowed([p], pod("prom", "other", app="prometheus"), DB)


def test_two_peers_in_the_list_are_or():
    ns_peer = {"namespaceSelector": {"matchLabels": {"team": "platform"}}}
    pod_peer = {"podSelector": {"matchLabels": {"app": "prometheus"}}}
    p = policy({"app": "db"}, ingress=[{"from": [ns_peer, pod_peer]}])
    assert allowed([p], pod("grafana", "monitoring", app="grafana"), DB), "через namespaceSelector"
    assert not allowed([p], pod("prom", "other", app="prometheus"), DB), "podSelector діє лише у своєму namespace"


def test_metadata_name_label_is_added_to_namespaces():
    p = policy({"app": "db"}, ingress=[{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "other"}}}]}])
    assert allowed([p], STRANGER, DB)
    assert not allowed([p], PROM, DB)


def test_rule_without_from_or_ports_matches_everything():
    assert allowed([policy({"app": "db"}, ingress=[{}])], STRANGER, DB, 1)
    assert allowed([policy({"app": "db"}, ingress=[{"from": []}])], STRANGER, DB, 1)
    port_only = policy({"app": "db"}, ingress=[{"ports": [{"port": 5432}]}])
    assert allowed([port_only], STRANGER, DB, 5432) and not allowed([port_only], STRANGER, DB, 22)


def test_empty_rule_list_denies_all_but_missing_policy_does_not():
    assert not allowed([policy({"app": "db"}, ingress=[], types=["Ingress"])], WEB, DB)
    assert not allowed([policy({"app": "db"}, types=["Ingress"])], WEB, DB)


def test_policies_are_additive():
    a = policy({"app": "db"}, ingress=[{"from": [{"podSelector": {"matchLabels": {"app": "api"}}}], "ports": [{"port": 5432}]}])
    b = policy({"app": "db"}, ingress=[{"from": [{"podSelector": {"matchLabels": {"app": "web"}}}], "ports": [{"port": 5432}]}])
    assert allowed([a, b], API, DB) and allowed([a, b], WEB, DB)
    assert not allowed([a], WEB, DB)


def test_port_ranges_and_default_protocol():
    p = policy({"app": "db"}, ingress=[{"ports": [{"port": 8000, "endPort": 8010}, {"port": 53, "protocol": "UDP"}]}])
    assert allowed([p], WEB, DB, 8000) and allowed([p], WEB, DB, 8010) and allowed([p], WEB, DB, 8005)
    assert not allowed([p], WEB, DB, 7999) and not allowed([p], WEB, DB, 8011)
    assert allowed([p], WEB, DB, 53, "UDP") and not allowed([p], WEB, DB, 53, "TCP")
    protocol_only = policy({"app": "db"}, ingress=[{"ports": [{"protocol": "UDP"}]}])
    assert allowed([protocol_only], WEB, DB, 9999, "UDP") and not allowed([protocol_only], WEB, DB, 9999)


# ---------- NetworkPolicy: egress ----------------------------------------------


def test_egress_of_source_is_checked_too():
    egress = policy({"app": "web"}, egress=[{"to": [{"podSelector": {"matchLabels": {"app": "api"}}}], "ports": [{"port": 8080}]}])
    assert allowed([egress], WEB, API, 8080)
    assert not allowed([egress], WEB, DB, 5432), "egress web до db не дозволений"
    assert not allowed([egress], WEB, PROM, 8080)
    assert allowed([egress], API, DB, 5432), "api не ізольований"


def test_both_directions_must_allow():
    egress_ok = policy({"app": "web"}, egress=[{}])
    ingress_deny = policy({"app": "api"}, ingress=[{"from": [{"podSelector": {"matchLabels": {"app": "worker"}}}]}])
    assert not allowed([egress_ok, ingress_deny], WEB, API, 80)
    ingress_ok = policy({"app": "api"}, ingress=[{}])
    assert allowed([egress_ok, ingress_ok], WEB, API, 80)


def test_egress_namespace_peer_uses_destination_namespace():
    e = policy({"app": "web"}, egress=[{"to": [{"namespaceSelector": {"matchLabels": {"team": "platform"}}}]}])
    assert allowed([e], WEB, PROM, 9090)
    assert not allowed([e], WEB, API, 80)


# ---------- RBAC ---------------------------------------------------------------

ROLES = [
    {"kind": "Role", "namespace": "other", "name": "pod-reader", "rules": [{"resources": ["secrets"], "verbs": ["get"]}]},
    {"kind": "Role", "namespace": "shop", "name": "pod-reader", "rules": [{"resources": ["pods", "pods/log"], "verbs": ["get", "list"]}]},
    {"kind": "ClusterRole", "name": "node-viewer", "rules": [{"resources": ["nodes"], "verbs": ["get", "list"]}]},
    {"kind": "ClusterRole", "name": "deployer", "rules": [
        {"resources": ["deployments", "deployments/*"], "verbs": ["*"]},
        {"resources": ["configmaps"], "verbs": ["get", "update"], "resourceNames": ["app-config"]}]},
]
BINDINGS = [
    {"kind": "RoleBinding", "name": "alice-reads", "namespace": "shop", "roleRef": {"kind": "Role", "name": "pod-reader"},
     "subjects": [{"kind": "User", "name": "alice"}]},
    {"kind": "ClusterRoleBinding", "name": "ops-nodes", "roleRef": {"kind": "ClusterRole", "name": "node-viewer"},
     "subjects": [{"kind": "Group", "name": "ops"}]},
    {"kind": "RoleBinding", "name": "ci-deploys", "namespace": "shop", "roleRef": {"kind": "ClusterRole", "name": "deployer"},
     "subjects": [{"kind": "ServiceAccount", "name": "ci", "namespace": "tools"}]},
]
CI = "system:serviceaccount:tools:ci"


def can(user, verb, resource, namespace=None, name=None, groups=()):
    return rbac_allowed(ROLES, BINDINGS, user, list(groups), verb, resource, namespace, name)


def test_role_binding_is_namespaced():
    assert can("alice", "get", "pods", "shop")
    assert can("alice", "list", "pods", "shop")
    assert not can("alice", "delete", "pods", "shop"), "verb"
    assert not can("alice", "get", "pods", "other"), "інший namespace"
    assert not can("alice", "get", "pods"), "кластерний запит RoleBinding не покриває"
    assert not can("bob", "get", "pods", "shop")


def test_role_is_looked_up_in_the_binding_namespace():
    assert not can("alice", "get", "secrets", "shop"), "secrets дає однойменна Role в other, не в shop"


def test_subresources_need_explicit_rules():
    assert can("alice", "get", "pods/log", "shop")
    assert not can("alice", "get", "pods/exec", "shop")
    assert can(CI, "create", "deployments/scale", "shop"), "deployments/* покриває підресурси"
    assert not can(CI, "create", "pods/exec", "shop")


def test_cluster_role_binding_applies_everywhere_and_to_cluster_resources():
    assert can("carol", "list", "nodes", groups=["ops"])
    assert can("carol", "get", "nodes", "shop", groups=["ops"])
    assert not can("carol", "list", "nodes", groups=["dev"])
    assert not can("carol", "delete", "nodes", groups=["ops"])


def test_role_binding_to_cluster_role_is_limited_to_the_binding_namespace():
    assert can(CI, "delete", "deployments", "shop")
    assert not can(CI, "delete", "deployments", "other")
    assert not can(CI, "delete", "deployments")


def test_service_account_identity_includes_namespace():
    assert not can("system:serviceaccount:shop:ci", "delete", "deployments", "shop")
    assert not can("ci", "delete", "deployments", "shop")


def test_resource_names_restrict_by_object():
    assert can(CI, "get", "configmaps", "shop", "app-config")
    assert not can(CI, "get", "configmaps", "shop", "other-config")
    assert not can(CI, "get", "configmaps", "shop"), "list без імені не покривається resourceNames"
    assert not can(CI, "delete", "configmaps", "shop", "app-config")


def test_missing_role_is_ignored():
    bindings = [{"kind": "ClusterRoleBinding", "name": "x", "roleRef": {"kind": "ClusterRole", "name": "ghost"},
                 "subjects": [{"kind": "User", "name": "alice"}]}]
    assert rbac_allowed(ROLES, bindings, "alice", [], "get", "pods", "shop") is False


def test_wildcard_resources_and_verbs():
    roles = [{"kind": "ClusterRole", "name": "admin", "rules": [{"resources": ["*"], "verbs": ["*"]}]}]
    bindings = [{"kind": "ClusterRoleBinding", "name": "b", "roleRef": {"kind": "ClusterRole", "name": "admin"},
                 "subjects": [{"kind": "User", "name": "root"}]}]
    assert rbac_allowed(roles, bindings, "root", [], "delete", "pods/exec", "kube-system")
    assert rbac_allowed(roles, bindings, "root", [], "get", "nodes")
    assert not rbac_allowed(roles, bindings, "alice", [], "get", "nodes")


# ---------- RBAC audit ---------------------------------------------------------


def test_audit_finds_dangerous_bindings():
    roles = [
        {"kind": "ClusterRole", "name": "admin", "rules": [{"resources": ["*"], "verbs": ["*"]}]},
        {"kind": "ClusterRole", "name": "secret-reader", "rules": [{"resources": ["secrets"], "verbs": ["get", "list"]}]},
        {"kind": "ClusterRole", "name": "debugger", "rules": [{"resources": ["pods", "pods/exec"], "verbs": ["get", "create"]}]},
        {"kind": "ClusterRole", "name": "escalator", "rules": [{"resources": ["clusterroles"], "verbs": ["bind", "get"]}]},
        {"kind": "ClusterRole", "name": "viewer", "rules": [{"resources": ["pods"], "verbs": ["get", "list"]}]},
        {"kind": "ClusterRole", "name": "actor", "rules": [{"resources": ["users"], "verbs": ["impersonate"]}]},
    ]
    sa = {"kind": "ServiceAccount", "name": "default", "namespace": "shop"}
    bindings = [
        {"kind": "ClusterRoleBinding", "name": "all", "roleRef": {"kind": "ClusterRole", "name": "admin"}, "subjects": [{"kind": "User", "name": "u"}]},
        {"kind": "ClusterRoleBinding", "name": "secrets", "roleRef": {"kind": "ClusterRole", "name": "secret-reader"}, "subjects": [{"kind": "User", "name": "u"}]},
        {"kind": "RoleBinding", "name": "local-secrets", "namespace": "shop", "roleRef": {"kind": "ClusterRole", "name": "secret-reader"},
         "subjects": [{"kind": "User", "name": "u"}]},
        {"kind": "RoleBinding", "name": "exec", "namespace": "shop", "roleRef": {"kind": "ClusterRole", "name": "debugger"}, "subjects": [{"kind": "User", "name": "u"}]},
        {"kind": "ClusterRoleBinding", "name": "esc", "roleRef": {"kind": "ClusterRole", "name": "escalator"}, "subjects": [{"kind": "Group", "name": "g"}]},
        {"kind": "RoleBinding", "name": "default-view", "namespace": "shop", "roleRef": {"kind": "ClusterRole", "name": "viewer"}, "subjects": [sa]},
        {"kind": "ClusterRoleBinding", "name": "act", "roleRef": {"kind": "ClusterRole", "name": "actor"}, "subjects": [{"kind": "User", "name": "u"}]},
        {"kind": "RoleBinding", "name": "fine", "namespace": "shop", "roleRef": {"kind": "ClusterRole", "name": "viewer"}, "subjects": [{"kind": "User", "name": "u"}]},
        {"kind": "RoleBinding", "name": "ghost", "namespace": "shop", "roleRef": {"kind": "ClusterRole", "name": "nope"}, "subjects": [sa]},
    ]
    assert rbac_audit(roles, bindings) == [
        ("act", "ESCALATION"),
        ("all", "POD_EXEC"), ("all", "SECRETS_READ"), ("all", "WILDCARD"),
        ("default-view", "DEFAULT_SA"),
        ("esc", "ESCALATION"),
        ("exec", "POD_EXEC"),
        ("ghost", "DEFAULT_SA"),
        ("secrets", "SECRETS_READ"),
    ]


def test_audit_of_empty_input():
    assert rbac_audit([], []) == []


# ---------- Pod Security Standards --------------------------------------------


def good_container(name="app", **sc):
    base = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}}
    base.update(sc)
    return {"name": name, "securityContext": base}


def test_privileged_level_allows_anything():
    assert pod_security_violations({"hostNetwork": True, "containers": [{"name": "a", "securityContext": {"privileged": True}}]}, "privileged") == []


def test_unknown_level():
    with pytest.raises(ValueError):
        pod_security_violations({}, "strict")


def test_baseline_catches_host_access_and_privileges():
    spec = {
        "hostNetwork": True, "hostPID": True, "hostIPC": False,
        "volumes": [{"name": "docker", "hostPath": {"path": "/var/run/docker.sock"}}, {"name": "cfg", "configMap": {"name": "x"}}, {"name": "nfs", "nfs": {}}],
        "containers": [
            {"name": "a", "securityContext": {"privileged": True}, "ports": [{"containerPort": 80, "hostPort": 80}]},
            {"name": "b", "securityContext": {"capabilities": {"add": ["SYS_ADMIN"]}}, "ports": [{"containerPort": 80, "hostPort": 0}]},
            {"name": "c", "securityContext": {"capabilities": {"add": ["NET_BIND_SERVICE", "CHOWN"]}}},
        ],
        "initContainers": [{"name": "init", "securityContext": {"privileged": True}}],
    }
    assert pod_security_violations(spec, "baseline") == [
        "capabilities:b", "hostNetwork", "hostPID", "hostPath:docker", "hostPort:a", "privileged:a", "privileged:init"]


def test_baseline_does_not_require_hardening():
    assert pod_security_violations({"containers": [{"name": "a"}]}, "baseline") == []
    assert pod_security_violations({}, "baseline") == []


def test_restricted_requires_full_hardening():
    assert pod_security_violations({"containers": [good_container()]}, "restricted") == []
    assert pod_security_violations({"containers": [{"name": "a"}]}, "restricted") == [
        "allowPrivilegeEscalation:a", "capabilitiesDrop:a", "runAsNonRoot:a", "seccomp:a"]


def test_restricted_pod_level_defaults_and_container_overrides():
    spec = {"securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [good_container("a", runAsNonRoot=None, seccompProfile=None), good_container("b", runAsNonRoot=False)]}
    spec["containers"][0]["securityContext"].pop("runAsNonRoot")
    spec["containers"][0]["securityContext"].pop("seccompProfile")
    assert pod_security_violations(spec, "restricted") == ["runAsNonRoot:b"]
    spec["containers"][1]["securityContext"]["runAsNonRoot"] = True
    spec["containers"][1]["securityContext"]["seccompProfile"] = {"type": "Unconfined"}
    assert pod_security_violations(spec, "restricted") == ["seccomp:b"]


@pytest.mark.parametrize("profile, ok", [("RuntimeDefault", True), ("Localhost", True), ("Unconfined", False)])
def test_restricted_seccomp_types(profile, ok):
    violations = pod_security_violations({"containers": [good_container(seccompProfile={"type": profile})]}, "restricted")
    assert violations == ([] if ok else ["seccomp:app"])


def test_restricted_escalation_must_be_explicitly_false():
    assert pod_security_violations({"containers": [good_container(allowPrivilegeEscalation=True)]}, "restricted") == ["allowPrivilegeEscalation:app"]
    c = good_container()
    del c["securityContext"]["allowPrivilegeEscalation"]
    assert pod_security_violations({"containers": [c]}, "restricted") == ["allowPrivilegeEscalation:app"]


def test_restricted_capabilities():
    only_bind = good_container(capabilities={"drop": ["ALL"], "add": ["NET_BIND_SERVICE"]})
    assert pod_security_violations({"containers": [only_bind]}, "restricted") == []
    chown = good_container(capabilities={"drop": ["ALL"], "add": ["CHOWN"]})
    assert pod_security_violations({"containers": [chown]}, "restricted") == ["capabilities:app"]
    assert pod_security_violations({"containers": [chown]}, "baseline") == [], "CHOWN дозволений у baseline"
    no_drop = good_container(capabilities={"drop": ["NET_RAW"]})
    assert pod_security_violations({"containers": [no_drop]}, "restricted") == ["capabilitiesDrop:app"]


def test_restricted_volume_types_and_init_containers():
    spec = {
        "volumes": [{"name": "data", "persistentVolumeClaim": {}}, {"name": "tmp", "emptyDir": {}}, {"name": "disk", "gcePersistentDisk": {}},
                    {"name": "host", "hostPath": {}}, {"name": "tok", "projected": {}}],
        "initContainers": [{"name": "init"}], "containers": [good_container()],
    }
    assert pod_security_violations(spec, "restricted") == [
        "allowPrivilegeEscalation:init", "capabilitiesDrop:init", "hostPath:host", "runAsNonRoot:init", "seccomp:init", "volumeType:disk"]
    assert pod_security_violations(spec, "baseline") == ["hostPath:host"], "в baseline нетипові volume допустимі"
