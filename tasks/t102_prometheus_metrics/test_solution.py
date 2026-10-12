import pytest

from solution import DEFAULT_BUCKETS, Red, Registry, match_route


def test_counter_without_labels():
    r = Registry()
    c = r.counter("jobs_total", "Jobs done")
    assert r.render() == "# HELP jobs_total Jobs done\n# TYPE jobs_total counter\njobs_total 0\n"
    c.inc()
    c.inc(2.0)
    assert r.render().endswith("jobs_total 3\n"), "ціле значення без .0"
    c.inc(0.5)
    c.inc(0)
    assert r.render().endswith("jobs_total 3.5\n")


def test_labeled_counter_is_sorted_by_label_values():
    r = Registry()
    c = r.counter("requests_total", "Requests", labels=("method", "code"))
    assert r.render() == "# HELP requests_total Requests\n# TYPE requests_total counter\n", "без спостережень зразків немає"
    c.inc(method="POST", code="200")
    c.inc(method="GET", code="500")
    c.inc(method="GET", code="200")
    c.inc(method="GET", code="200")
    assert r.render() == (
        "# HELP requests_total Requests\n# TYPE requests_total counter\n"
        'requests_total{method="GET",code="200"} 2\n'
        'requests_total{method="GET",code="500"} 1\n'
        'requests_total{method="POST",code="200"} 1\n')


def test_label_values_are_converted_to_strings():
    r = Registry()
    c = r.counter("hits_total", "h", labels=("code",))
    c.inc(code=200)
    c.inc(code="200")
    assert 'hits_total{code="200"} 2\n' in r.render()


def test_gauge():
    r = Registry()
    g = r.gauge("queue_depth", "Depth", labels=("queue",))
    g.set(2.5, queue="a")
    g.inc(queue="a")
    g.dec(0.5, queue="a")
    g.dec(queue="b")
    assert r.render() == ("# HELP queue_depth Depth\n# TYPE queue_depth gauge\n"
                          'queue_depth{queue="a"} 3\n'
                          'queue_depth{queue="b"} -1\n')


def test_histogram_is_cumulative_with_inf_sum_and_count():
    r = Registry()
    h = r.histogram("latency_seconds", "Latency", buckets=(0.5, 1))
    for v in (0.25, 0.5, 0.5, 4):
        h.observe(v)
    assert r.render() == (
        "# HELP latency_seconds Latency\n# TYPE latency_seconds histogram\n"
        'latency_seconds_bucket{le="0.5"} 3\n'
        'latency_seconds_bucket{le="1"} 3\n'
        'latency_seconds_bucket{le="+Inf"} 4\n'
        "latency_seconds_sum 5.25\n"
        "latency_seconds_count 4\n")


def test_empty_histogram_has_zero_series():
    r = Registry()
    r.histogram("h_seconds", "h", buckets=(1,))
    assert r.render().splitlines()[2:] == ['h_seconds_bucket{le="1"} 0', 'h_seconds_bucket{le="+Inf"} 0', "h_seconds_sum 0", "h_seconds_count 0"]


def test_histogram_with_labels_puts_le_last_and_groups_series():
    r = Registry()
    h = r.histogram("h_seconds", "h", labels=("route",), buckets=(0.5,))
    h.observe(0.25, route="/b")
    h.observe(1, route="/a")
    assert r.render().splitlines()[2:] == [
        'h_seconds_bucket{route="/a",le="0.5"} 0', 'h_seconds_bucket{route="/a",le="+Inf"} 1', 'h_seconds_sum{route="/a"} 1', 'h_seconds_count{route="/a"} 1',
        'h_seconds_bucket{route="/b",le="0.5"} 1', 'h_seconds_bucket{route="/b",le="+Inf"} 1', 'h_seconds_sum{route="/b"} 0.25', 'h_seconds_count{route="/b"} 1']


def test_default_buckets_are_used():
    r = Registry()
    h = r.histogram("d_seconds", "d")
    h.observe(0.003)
    text = r.render()
    assert len(DEFAULT_BUCKETS) == 11
    assert 'd_seconds_bucket{le="0.005"} 1' in text and 'd_seconds_bucket{le="10"} 1' in text and 'd_seconds_bucket{le="2.5"} 1' in text


def test_metrics_are_sorted_by_name():
    r = Registry()
    r.gauge("zzz", "z")
    r.gauge("aaa", "a")
    assert [l for l in r.render().splitlines() if l.startswith("# TYPE")] == ["# TYPE aaa gauge", "# TYPE zzz gauge"]
    assert Registry().render() == ""


def test_escaping_in_help_and_label_values():
    r = Registry()
    c = r.counter("x_total", "line1\nline2 \\ end", labels=("path",))
    c.inc(path='a"b\\c\nd')
    lines = r.render().splitlines()
    assert lines[0] == "# HELP x_total line1\\nline2 \\\\ end"
    assert lines[2] == 'x_total{path="a\\"b\\\\c\\nd"} 1'


def test_cardinality_limit():
    r = Registry(max_series=3)
    c = r.counter("u_total", "u", labels=("user",))
    for u in ("a", "b", "c"):
        c.inc(user=u)
    c.inc(user="a")
    with pytest.raises(ValueError):
        c.inc(user="d")
    assert 'u_total{user="a"} 2' in r.render() and 'user="d"' not in r.render()


def test_cardinality_limit_is_per_metric():
    r = Registry(max_series=1)
    a = r.counter("a_total", "a", labels=("x",))
    b = r.counter("b_total", "b", labels=("x",))
    a.inc(x="1")
    b.inc(x="1")
    with pytest.raises(ValueError):
        a.inc(x="2")


def test_label_mismatch_and_negative_counter():
    r = Registry()
    c = r.counter("c_total", "c", labels=("a",))
    for bad in ({}, {"a": "1", "b": "2"}, {"b": "1"}):
        with pytest.raises(ValueError):
            c.inc(**bad)
    with pytest.raises(ValueError):
        c.inc(-1, a="1")
    with pytest.raises(ValueError):
        r.gauge("g", "g", labels=("a",)).set(1)


@pytest.mark.parametrize("call", [
    lambda r: r.counter("no_suffix", "x"),
    lambda r: r.gauge("1bad", "x"),
    lambda r: r.gauge("bad-name", "x"),
    lambda r: r.gauge("g", "x", labels=("bad-label",)),
    lambda r: r.gauge("g", "x", labels=("__reserved",)),
    lambda r: r.gauge("g", "x", labels=("a", "a")),
    lambda r: r.histogram("h", "x", labels=("le",)),
    lambda r: r.histogram("h", "x", buckets=()),
    lambda r: r.histogram("h", "x", buckets=(1, 1, 2)),
    lambda r: r.histogram("h", "x", buckets=(2, 1)),
    lambda r: r.histogram("h", "x", buckets=(1, float("inf"))),
])
def test_invalid_definitions(call):
    with pytest.raises(ValueError):
        call(Registry())


def test_duplicate_names():
    r = Registry()
    r.gauge("dup", "x")
    with pytest.raises(ValueError):
        r.gauge("dup", "y")
    with pytest.raises(ValueError):
        r.histogram("dup", "y")


def test_red_metrics():
    r = Registry()
    red = Red(r, buckets=(0.5, 1))
    red.record("GET", "/users/{id}", 200, 0.25)
    red.record("GET", "/users/{id}", 200, 2)
    red.record("GET", "/users/{id}", 500, 0.5)
    text = r.render()
    assert 'http_requests_total{method="GET",route="/users/{id}",status="200"} 2' in text
    assert 'http_requests_total{method="GET",route="/users/{id}",status="500"} 1' in text
    assert 'http_request_duration_seconds_bucket{method="GET",route="/users/{id}",le="0.5"} 2' in text
    assert 'http_request_duration_seconds_bucket{method="GET",route="/users/{id}",le="+Inf"} 3' in text
    assert 'http_request_duration_seconds_sum{method="GET",route="/users/{id}"} 2.75' in text
    assert 'http_request_duration_seconds_count{method="GET",route="/users/{id}"} 3' in text


# ---------- match_route -------------------------------------------------------

ROUTES = ["/", "/users", "/users/{id}", "/users/{id}/orders/{order_id}", "/health"]


@pytest.mark.parametrize("path, expected", [
    ("/", "/"),
    ("/users", "/users"),
    ("/users/", "/users"),
    ("/users/42", "/users/{id}"),
    ("/users/42/", "/users/{id}"),
    ("/users/42?expand=orders", "/users/{id}"),
    ("/users?page=2", "/users"),
    ("/health?x=/y/z", "/health"),
    ("/users/42/orders/7", "/users/{id}/orders/{order_id}"),
    ("/health", "/health"),
    ("/users/42/orders", "__unmatched__"),
    ("/admin/secret", "__unmatched__"),
    ("/users//orders/7", "__unmatched__"),
    ("/healthz", "__unmatched__"),
])
def test_match_route(path, expected):
    assert match_route(path, ROUTES) == expected


def test_match_route_returns_the_first_matching_template():
    assert match_route("/files/new", ["/files/{name}", "/files/new"]) == "/files/{name}"
    assert match_route("/files/new", ["/files/new", "/files/{name}"]) == "/files/new"
