import math

import pytest

from solution import DriftMonitor, bucketize, featurize, jsd, psi


def ref_psi(e, a, eps=1e-4):
    te, ta = sum(e.values()), sum(a.values())
    total = 0.0
    for k in set(e) | set(a):
        pe = max(e.get(k, 0) / te, eps)
        pa = max(a.get(k, 0) / ta, eps)
        total += (pa - pe) * math.log(pa / pe)
    return total


# ---------- psi --------------------------------------------------------------------------------------------


def test_psi_identical_distributions_is_zero_even_with_different_totals():
    assert psi({"a": 50, "b": 50}, {"a": 5, "b": 5}) == pytest.approx(0.0, abs=1e-12)
    assert psi({"a": 1}, {"a": 100}) == pytest.approx(0.0, abs=1e-12)


def test_psi_known_value():
    expected = (0.8 - 0.5) * math.log(0.8 / 0.5) + (0.2 - 0.5) * math.log(0.2 / 0.5)
    assert psi({"a": 50, "b": 50}, {"a": 80, "b": 20}) == pytest.approx(expected, rel=1e-9)
    assert expected == pytest.approx(0.4159, abs=1e-4)


def test_psi_is_symmetric_and_nonnegative():
    e, a = {"x": 70, "y": 20, "z": 10}, {"x": 40, "y": 35, "z": 25}
    assert psi(e, a) == pytest.approx(psi(a, e), rel=1e-12)
    assert psi(e, a) > 0
    assert psi(e, a) == pytest.approx(ref_psi(e, a), rel=1e-9)


def test_psi_missing_category_uses_eps_floor():
    e, a = {"a": 1, "b": 1}, {"a": 2}
    assert psi(e, a) == pytest.approx(ref_psi(e, a), rel=1e-9)
    assert psi(e, a) > 4  # finite, but huge: новий або зниклий клас це сильний сигнал
    assert psi({"a": 1}, {"a": 1, "new": 1}) == pytest.approx(ref_psi({"a": 1}, {"a": 1, "new": 1}), rel=1e-9)


def test_psi_custom_eps():
    e, a = {"a": 1, "b": 1}, {"a": 2}
    assert psi(e, a, eps=1e-2) == pytest.approx(ref_psi(e, a, eps=1e-2), rel=1e-9)
    assert psi(e, a, eps=1e-2) < psi(e, a)


def test_psi_zero_count_entries_are_allowed():
    assert psi({"a": 3, "b": 0}, {"a": 3, "b": 0}) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("bad", [{}, {"a": 0}, {"a": -1, "b": 5}, {"a": "x"}, {"a": float("nan")}, {"a": True}, None, [1, 2]])
def test_psi_and_jsd_reject_bad_distributions(bad):
    with pytest.raises(ValueError):
        psi({"a": 1}, bad)
    with pytest.raises(ValueError):
        psi(bad, {"a": 1})
    with pytest.raises(ValueError):
        jsd({"a": 1}, bad)


# ---------- jsd --------------------------------------------------------------------------------------------


def test_jsd_identical_is_zero_and_disjoint_is_one():
    assert jsd({"a": 3, "b": 1}, {"a": 30, "b": 10}) == pytest.approx(0.0, abs=1e-12)
    assert jsd({"a": 1}, {"b": 1}) == pytest.approx(1.0, rel=1e-12)


def test_jsd_known_value_base_two():
    p, q = {"a": 1.0}, {"a": 0.5, "b": 0.5}
    m = {"a": 0.75, "b": 0.25}
    expected = 0.5 * 1.0 * math.log2(1.0 / m["a"]) + 0.5 * (0.5 * math.log2(0.5 / m["a"]) + 0.5 * math.log2(0.5 / m["b"]))
    assert jsd(p, q) == pytest.approx(expected, rel=1e-9)
    assert 0 < jsd(p, q) < 1


def test_jsd_symmetric_bounded_and_zero_probabilities_do_not_break():
    p, q = {"a": 9, "b": 1, "c": 0}, {"a": 1, "b": 0, "c": 9}
    v = jsd(p, q)
    assert v == pytest.approx(jsd(q, p), rel=1e-12)
    assert 0 < v < 1


# ---------- bucketize --------------------------------------------------------------------------------------


@pytest.mark.parametrize("value, label", [(-5, "s"), (0, "s"), (9.99, "s"), (10, "m"), (50, "m"), (99, "m"), (100, "l"), (10 ** 6, "l")])
def test_bucketize_edges_belong_to_upper_bucket(value, label):
    assert bucketize(value, (10, 100), ("s", "m", "l")) == label


@pytest.mark.parametrize("edges, labels", [((), ("a",)), ((1, 1), ("a", "b", "c")), ((2, 1), ("a", "b", "c")),
                                          ((1, 2), ("a", "b")), ((1,), ("a", "b", "c"))])
def test_bucketize_validates_edges_and_labels(edges, labels):
    with pytest.raises(ValueError):
        bucketize(5, edges, labels)


@pytest.mark.parametrize("value", ["5", None, True, float("nan")])
def test_bucketize_rejects_non_numbers(value):
    with pytest.raises(ValueError):
        bucketize(value, (1,), ("a", "b"))


# ---------- featurize --------------------------------------------------------------------------------------


@pytest.mark.parametrize("n, label", [(0, "short"), (49, "short"), (50, "medium"), (199, "medium"), (200, "long"),
                                      (799, "long"), (800, "xlong"), (5000, "xlong")])
def test_featurize_length_buckets(n, label):
    assert featurize({"text": "x" * n})["length"] == label


@pytest.mark.parametrize("text, refusal", [
    ("Sorry, I can't help with that.", "yes"),
    ("I CANNOT do this", "yes"),
    ("I’m sorry, that is not possible", "yes"),
    ("I am unable to access it", "yes"),
    ("Вибачте, не знайшов", "yes"),
    ("Я не можу це зробити", "yes"),
    ("Here is the answer: 42", "no"),
    ("You can cancel at any time", "no"),
    ("", "no"),
])
def test_featurize_refusal_detection(text, refusal):
    assert featurize({"text": text})["refusal"] == refusal


@pytest.mark.parametrize("tools, expected", [
    (None, "none"), ([], "none"), (["search"], "search"), (["search", "search"], "search"),
    (["write", "search"], "search+write"), (("b", "a", "b", "c"), "a+b+c"),
])
def test_featurize_tools(tools, expected):
    response = {"text": "ok"} if tools is None else {"text": "ok", "tools": tools}
    f = featurize(response)
    assert f["tool"] == expected
    assert set(f) == {"length", "refusal", "tool"}


@pytest.mark.parametrize("bad", [{"text": 5}, {}, None, "text", {"text": "x", "tools": "search"}, {"text": "x", "tools": [1]}])
def test_featurize_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        featurize(bad)


# ---------- DriftMonitor -----------------------------------------------------------------------------------

AB = {"m": {"a": 1, "b": 1}}


def make(**kw):
    params = dict(window=4, min_samples=4, psi_warn=0.1, psi_alert=0.25, consecutive=2)
    params.update(kw)
    return DriftMonitor(AB, **params)


def feed(mon, values, metric="m"):
    out = []
    for v in values:
        out.append(mon.observe({metric: v}))
    return out


def test_no_evaluation_before_min_samples():
    mon = make()
    out = feed(mon, ["a", "a", "a"])
    assert out == [[], [], []]
    assert mon.status("m") == {"state": "insufficient", "psi": None, "jsd": None, "n": 3}


def test_stable_traffic_stays_ok():
    mon = make()
    feed(mon, ["a", "b", "a", "b"])
    st = mon.status("m")
    assert st["state"] == "ok" and st["n"] == 4
    assert st["psi"] == pytest.approx(0.0, abs=1e-12) and st["jsd"] == pytest.approx(0.0, abs=1e-12)
    assert mon.alerts == []


def test_alert_after_consecutive_evaluations_once_then_resolved():
    mon = make()
    feed(mon, ["a", "b", "a", "b"])
    out = feed(mon, ["a", "a", "a", "a", "b", "b"])
    # вікна: [b,a,b,a] ok; [a,b,a,a] alert-рівень (1); [b,a,a,a] alert-рівень (2) -> алерт; [a,a,a,a] без повтору;
    # [a,a,a,b] без повтору; [a,a,b,b] ok -> resolved
    assert out[0] == [] and out[1] == []
    assert len(out[2]) == 1
    alert = out[2][0]
    assert alert["type"] == "alert" and alert["metric"] == "m" and alert["n"] == 4
    expected_psi = ref_psi({"a": 1, "b": 1}, {"a": 3, "b": 1})
    assert alert["psi"] == pytest.approx(expected_psi, rel=1e-9)
    assert alert["psi"] >= 0.25
    assert alert["jsd"] == pytest.approx(jsd({"a": 1, "b": 1}, {"a": 3, "b": 1}), rel=1e-9)
    assert alert["top_category"] == "a"
    assert out[3] == [] and out[4] == []
    assert len(out[5]) == 1 and out[5][0]["type"] == "resolved" and out[5][0]["metric"] == "m"
    assert out[5][0]["psi"] == pytest.approx(0.0, abs=1e-12)
    assert [e["type"] for e in mon.alerts] == ["alert", "resolved"]


def test_status_transitions_warn_then_alert_then_ok():
    mon = make()
    feed(mon, ["a", "b", "a", "b"])
    feed(mon, ["a"])
    assert mon.status("m")["state"] == "ok"
    feed(mon, ["a"])  # [a,b,a,a]: рівень alert, але серія 1 < 2
    assert mon.status("m")["state"] == "warn"
    feed(mon, ["a"])
    assert mon.status("m")["state"] == "alert"
    feed(mon, ["b", "b"])
    st = mon.status("m")
    assert st["state"] == "ok" and st["psi"] == pytest.approx(0.0, abs=1e-12)


def test_single_spike_does_not_alert():
    mon = make()
    feed(mon, ["a", "b", "a", "b"])
    out = feed(mon, ["a", "a", "b", "a", "b", "a", "b"])
    assert all(e == [] for e in out)
    assert mon.alerts == []


def test_streak_resets_after_ok_evaluation():
    mon = make()
    feed(mon, ["a", "b", "a", "b", "a"])
    out = feed(mon, ["a",           # [a,b,a,a] alert-рівень, серія 1
                     "b",           # [b,a,a,b] ok, серія скинута
                     "a"])          # [a,a,b,a] alert-рівень, серія 1: ще не алерт
    assert out == [[], [], []]
    assert mon.status("m")["state"] == "warn"


def test_alert_can_fire_again_after_resolution():
    mon = make()
    feed(mon, ["a", "b", "a", "b"])
    feed(mon, ["a", "a", "a"])          # перший алерт
    feed(mon, ["b", "b"])               # resolved
    feed(mon, ["b", "b"])               # [a,b,b,b] серія 1, [b,b,b,b] серія 2: другий алерт
    types = [e["type"] for e in mon.alerts]
    assert types[:2] == ["alert", "resolved"]
    assert types.count("alert") == 2 and types[-1] == "alert"


def test_window_is_sliding_old_observations_are_evicted():
    mon = make(window=4, min_samples=4)
    feed(mon, ["a", "a", "a", "a"])
    assert mon.status("m")["n"] == 4
    feed(mon, ["b", "b", "a", "b"] * 5)
    st = mon.status("m")
    assert st["n"] == 4
    assert st["psi"] == pytest.approx(ref_psi({"a": 1, "b": 1}, {"a": 1, "b": 3}), rel=1e-9)


def test_moderate_shift_is_warn_not_alert():
    mon = DriftMonitor(AB, window=16, min_samples=16, psi_warn=0.1, psi_alert=0.25, consecutive=1)
    out = feed(mon, list("aab" * 5 + "a"))
    assert all(e == [] for e in out)
    st = mon.status("m")
    assert st["state"] == "warn"
    assert st["psi"] == pytest.approx(ref_psi({"a": 1, "b": 1}, {"a": 11, "b": 5}), rel=1e-9)
    assert 0.1 <= st["psi"] < 0.25


def test_threshold_is_inclusive_for_alert_and_warn():
    base = {"m": {"a": 3, "b": 1}}
    threshold = psi(base["m"], {"a": 1, "b": 3})
    mon = DriftMonitor(base, window=4, min_samples=4, psi_warn=threshold / 2, psi_alert=threshold, consecutive=1)
    out = feed(mon, ["a", "b", "b", "b"])
    assert len(out[-1]) == 1 and out[-1][0]["type"] == "alert"
    mon = DriftMonitor(base, window=4, min_samples=4, psi_warn=threshold, psi_alert=threshold * 2, consecutive=1)
    feed(mon, ["a", "b", "b", "b"])
    assert mon.status("m")["state"] == "warn"


def test_consecutive_one_alerts_immediately():
    mon = make(consecutive=1)
    feed(mon, ["a", "b", "a", "b"])
    out = feed(mon, ["a", "a"])
    assert out[0] == [] and len(out[1]) == 1 and out[1][0]["type"] == "alert"


def test_min_samples_smaller_than_window():
    mon = make(window=10, min_samples=2, consecutive=1)
    out = feed(mon, ["a", "a"])
    assert out[0] == [] and out[1][0]["type"] == "alert"


def test_unseen_category_in_window_counts_as_drift():
    mon = make(consecutive=1)
    feed(mon, ["a", "b", "a"])
    out = feed(mon, ["zzz"])
    assert len(out[0]) == 1
    assert out[0][0]["psi"] == pytest.approx(ref_psi({"a": 1, "b": 1}, {"a": 2, "b": 1, "zzz": 1}), rel=1e-9)
    assert out[0][0]["top_category"] == "b"  # b і zzz зсунулись на .25 однаково: за алфавітом b


def test_top_category_is_largest_absolute_shift_ties_alphabetically():
    mon = DriftMonitor({"m": {"x": 1, "y": 1, "z": 2}}, window=4, min_samples=4, consecutive=1, psi_warn=0.01, psi_alert=0.02)
    # окно: p = x .5, y .5, z 0 (z зник): базові .25 .25 .5 -> зсуви .25 .25 .5 -> top = z
    out = feed(mon, ["x", "y", "x", "y"])
    assert out[-1][0]["top_category"] == "z"
    mon2 = DriftMonitor({"m": {"x": 1, "y": 1, "z": 2}}, window=4, min_samples=4, consecutive=1, psi_warn=0.01, psi_alert=0.02)
    out2 = feed(mon2, ["z", "z", "z", "z"])
    assert out2[-1][0]["top_category"] == "z"
    mon3 = DriftMonitor({"m": {"x": 1, "y": 1}}, window=4, min_samples=4, consecutive=1, psi_warn=0.01, psi_alert=0.02)
    out3 = feed(mon3, ["q", "r", "q", "r"])  # q і r мають однаковий зсув .5; x і y теж .5: за алфавітом q
    assert out3[-1][0]["top_category"] == "q"


def test_metrics_are_independent_and_event_subset_allowed():
    mon = DriftMonitor({"len": {"s": 1, "l": 1}, "tool": {"none": 1, "search": 1}}, window=4, min_samples=4,
                       psi_warn=0.1, psi_alert=0.25, consecutive=1)
    for v in ("s", "l", "s", "l"):
        mon.observe({"len": v})
    assert mon.status("len")["state"] == "ok"
    assert mon.status("tool")["state"] == "insufficient" and mon.status("tool")["n"] == 0
    out = []
    for _ in range(4):
        out += mon.observe({"len": "s", "tool": "none"})
    types = [(e["metric"], e["type"]) for e in out]
    assert ("tool", "alert") in types and ("len", "alert") in types
    assert types == [("len", "alert"), ("tool", "alert")]


def test_invalid_event_changes_nothing():
    mon = DriftMonitor({"m": {"a": 1, "b": 1}, "k": {"x": 1}}, window=4, min_samples=4)
    with pytest.raises(ValueError):
        mon.observe({"m": "a", "unknown": "z"})
    with pytest.raises(ValueError):
        mon.observe({"m": "a", "k": 5})
    with pytest.raises(ValueError):
        mon.observe({})
    with pytest.raises(ValueError):
        mon.observe("m")
    assert mon.status("m")["n"] == 0 and mon.status("k")["n"] == 0


def test_status_unknown_metric():
    with pytest.raises(ValueError):
        make().status("nope")


def test_alerts_property_returns_a_copy():
    mon = make(consecutive=1)
    feed(mon, ["a", "b", "a", "a"])
    snap = mon.alerts
    assert len(snap) == 1
    snap.clear()
    assert len(mon.alerts) == 1


@pytest.mark.parametrize("kw", [dict(window=3, min_samples=4), dict(min_samples=0), dict(psi_warn=0.3, psi_alert=0.25),
                                dict(psi_warn=0), dict(psi_warn=0.25, psi_alert=0.25), dict(consecutive=0)])
def test_constructor_validates_params(kw):
    with pytest.raises(ValueError):
        make(**kw)


@pytest.mark.parametrize("baseline", [{}, {"m": {}}, {"m": {"a": 0}}, {"m": {"a": -1}}, None])
def test_constructor_validates_baseline(baseline):
    with pytest.raises(ValueError):
        DriftMonitor(baseline)


def test_baseline_is_copied():
    base = {"m": {"a": 1, "b": 1}}
    mon = DriftMonitor(base, window=4, min_samples=4, consecutive=1)
    base["m"]["a"] = 1000
    feed(mon, ["a", "b", "a", "b"])
    assert mon.status("m")["psi"] == pytest.approx(0.0, abs=1e-12)


def test_end_to_end_refusal_rate_drift_with_featurize():
    mon = DriftMonitor({"refusal": {"no": 95, "yes": 5}, "tool": {"none": 6, "search": 4}},
                       window=40, min_samples=20, psi_warn=0.1, psi_alert=0.25, consecutive=3)
    tools = ["none", "none", "none", "search", "none", "search", "none", "none", "search", "search"]  # 6 none : 4 search

    def reply(i, refuse_every):
        text = "Sorry, I can't help with that." if refuse_every and i % refuse_every == 0 else "Here is your answer."
        return featurize({"text": text, "tools": [] if tools[i % 10] == "none" else ["search"]})

    events = []
    for i in range(200):  # стабільний період: відмова кожен 20-й (5%)
        f = reply(i, 20)
        events += mon.observe({"refusal": f["refusal"], "tool": f["tool"]})
    assert events == [] and mon.alerts == []
    assert mon.status("refusal")["state"] == "ok"
    for i in range(100):  # після зміни моделі відмова кожен 3-й (33%)
        f = reply(i, 3)
        events += mon.observe({"refusal": f["refusal"], "tool": f["tool"]})
    alerts = [e for e in events if e["type"] == "alert"]
    assert len(alerts) == 1 and alerts[0]["metric"] == "refusal" and alerts[0]["top_category"] == "yes"
    assert not [e for e in events if e["type"] == "resolved"]
    assert mon.status("refusal")["state"] == "alert"
    assert mon.status("tool")["state"] == "ok"
