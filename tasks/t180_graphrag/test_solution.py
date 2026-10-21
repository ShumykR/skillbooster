import copy

import pytest

from solution import (build_graph, chunks_for, communities, global_search, keyword_search, local_search, neighbors,
                      normalize, summarize_communities, theme_coverage)

TEXTS = [
    ("e1", "SolarCo supplies GridOps with solar power."),
    ("e2", "GridOps stores energy at Battery Lab."),
    ("e3", "Battery Lab tests SolarCo panels. SolarCo powers GridOps."),
    ("e4", "Wind Farm feeds GridOps. Wind Farm is funded by GenoMed."),
    ("b1", "GenoMed develops ProteinX."),
    ("b2", "ProteinX is trialed at Clinic One."),
    ("b3", "Clinic One partners with GenoMed."),
    ("b4", "GenoMed funds ProteinX trials."),
    ("s1", "OrbitWorks builds the Rocket Team."),
    ("s2", "Rocket Team launches from MoonBase."),
    ("s3", "MoonBase is operated by OrbitWorks."),
    ("s4", "OrbitWorks supplies MoonBase."),
]
CHUNKS = [{"id": i, "text": t} for i, t in TEXTS]
THEMES = {**{c: "energy" for c in ("e1", "e2", "e3", "e4")}, **{c: "biotech" for c in ("b1", "b2", "b3", "b4")},
          **{c: "space" for c in ("s1", "s2", "s3", "s4")}}
EXTRACTED = {
    TEXTS[0][1]: (["SolarCo", "GridOps"], [["SolarCo", "supplies", "GridOps"]]),
    TEXTS[1][1]: (["GridOps", "Battery Lab"], [["GridOps", "stores_at", "Battery Lab"]]),
    TEXTS[2][1]: (["Battery Lab", "SolarCo", "GridOps"], [["Battery Lab", "tests", "SolarCo"], ["SolarCo", "powers", "GridOps"]]),
    TEXTS[3][1]: (["Wind Farm", "GridOps", "GenoMed"], [["Wind Farm", "feeds", "GridOps"], ["Wind Farm", "funded_by", "GenoMed"]]),
    TEXTS[4][1]: (["GenoMed", "ProteinX"], [["GenoMed", "develops", "ProteinX"]]),
    TEXTS[5][1]: (["ProteinX", "Clinic One"], [["ProteinX", "trialed_at", "Clinic One"]]),
    TEXTS[6][1]: (["Clinic One", "GenoMed"], [["Clinic One", "partners", "GenoMed"]]),
    TEXTS[7][1]: (["GenoMed", "ProteinX"], [["GenoMed", "funds", "ProteinX"]]),
    TEXTS[8][1]: (["OrbitWorks", "Rocket Team"], [["OrbitWorks", "builds", "Rocket Team"]]),
    TEXTS[9][1]: (["Rocket Team", "MoonBase"], [["Rocket Team", "launches_from", "MoonBase"]]),
    TEXTS[10][1]: (["MoonBase", "OrbitWorks"], [["MoonBase", "operated_by", "OrbitWorks"]]),
    TEXTS[11][1]: (["OrbitWorks", "MoonBase"], [["OrbitWorks", "supplies", "MoonBase"]]),
}


def extract(text):
    entities, relations = EXTRACTED[text]
    return {"entities": list(entities), "relations": [list(r) for r in relations]}


@pytest.fixture(scope="module")
def graph():
    return build_graph(CHUNKS, extract)


def hand_graph(edges, extra_nodes=()):
    """Граф для communities/neighbors без build_graph: edges = {(a, b): weight}."""
    nodes = {n: {"name": n, "chunks": []} for pair in edges for n in pair}
    nodes.update({n: {"name": n, "chunks": []} for n in extra_nodes})
    return {"nodes": nodes, "edges": {tuple(sorted(k)): {"weight": w, "relations": [], "chunks": []} for k, w in edges.items()}}


# --- normalize ---------------------------------------------------------------------------------

def test_normalize():
    assert normalize("  Acme   Corp ") == "acme corp" and normalize("ACME") == "acme" and normalize("\tA\nB ") == "a b"
    assert normalize("   ") == "" and normalize("Київ  Столиця") == "київ столиця"


# --- build_graph -------------------------------------------------------------------------------

def test_nodes_names_chunks_and_normalization(graph):
    assert set(graph["nodes"]) == {"solarco", "gridops", "battery lab", "wind farm", "genomed", "proteinx", "clinic one",
                                   "orbitworks", "rocket team", "moonbase"}
    assert graph["nodes"]["gridops"] == {"name": "GridOps", "chunks": ["e1", "e2", "e3", "e4"]}
    assert graph["nodes"]["genomed"]["chunks"] == ["b1", "b3", "b4", "e4"]
    assert graph["nodes"]["battery lab"] == {"name": "Battery Lab", "chunks": ["e2", "e3"]}


def test_edges_are_undirected_weighted_by_distinct_chunks(graph):
    edges = graph["edges"]
    assert set(edges) == {("gridops", "solarco"), ("battery lab", "gridops"), ("battery lab", "solarco"),
                          ("gridops", "wind farm"), ("genomed", "wind farm"), ("genomed", "proteinx"),
                          ("clinic one", "proteinx"), ("clinic one", "genomed"), ("orbitworks", "rocket team"),
                          ("moonbase", "rocket team"), ("moonbase", "orbitworks")}
    assert edges[("gridops", "solarco")] == {"weight": 2, "relations": ["powers", "supplies"], "chunks": ["e1", "e3"]}
    assert edges[("genomed", "proteinx")] == {"weight": 2, "relations": ["develops", "funds"], "chunks": ["b1", "b4"]}
    assert edges[("moonbase", "orbitworks")] == {"weight": 2, "relations": ["operated_by", "supplies"], "chunks": ["s3", "s4"]}
    assert edges[("battery lab", "gridops")] == {"weight": 1, "relations": ["stores_at"], "chunks": ["e2"]}
    assert all(a < b for a, b in edges) and all(e["weight"] == len(e["chunks"]) for e in edges.values())


def test_aliases_merge_and_first_spelling_wins():
    chunks = [{"id": "a", "text": "t1"}, {"id": "b", "text": "t2"}]
    data = {"t1": {"entities": ["ACME  Corp", "Bob"], "relations": [["Bob", "works_at", "ACME  Corp"]]},
            "t2": {"entities": ["acme corp", "Eve"], "relations": [["acme corp", "hired", "Eve"]]}}
    g = build_graph(chunks, lambda t: data[t])
    assert g["nodes"]["acme corp"] == {"name": "ACME  Corp", "chunks": ["a", "b"]}
    assert set(g["edges"]) == {("acme corp", "bob"), ("acme corp", "eve")}


def test_relation_endpoints_become_entities_and_self_loops_and_blanks_are_ignored():
    chunks = [{"id": "a", "text": "t"}]
    out = {"entities": ["  ", "X"], "relations": [["X", "likes", "x"], ["Y", "knows", "Z"], ["", "r", "Y"], ["Y", "r", "   "]]}
    g = build_graph(chunks, lambda t: out)
    assert set(g["nodes"]) == {"x", "y", "z"}
    assert set(g["edges"]) == {("y", "z")}
    assert g["nodes"]["z"]["chunks"] == ["a"]


def test_same_pair_in_both_directions_in_one_chunk_counts_once():
    out = {"entities": [], "relations": [["A", "owns", "B"], ["B", "owned_by", "A"], ["A", "owns", "B"]]}
    g = build_graph([{"id": "c", "text": "t"}], lambda t: out)
    assert g["edges"] == {("a", "b"): {"weight": 1, "relations": ["owned_by", "owns"], "chunks": ["c"]}}


def test_missing_relations_key_and_empty_corpus():
    g = build_graph([{"id": "c", "text": "t"}], lambda t: {"entities": ["Only"]})
    assert g == {"nodes": {"only": {"name": "Only", "chunks": ["c"]}}, "edges": {}}
    assert build_graph([], extract) == {"nodes": {}, "edges": {}}


@pytest.mark.parametrize("chunks", [
    None, "x", [{"id": "a"}], [{"text": "t"}], [{"id": "", "text": "t"}], [{"id": 1, "text": "t"}],
    [{"id": "a", "text": 5}], [{"id": "a", "text": "t"}, {"id": "a", "text": "u"}], ["a"],
])
def test_build_graph_validates_chunks(chunks):
    with pytest.raises(ValueError):
        build_graph(chunks, lambda t: {"entities": []})


@pytest.mark.parametrize("bad", [None, [], "x", {"entities": [], "relations": "AB"}, {"entities": [], "relations": [["a", "b"]]},
                                 {"entities": [], "relations": [["a", 1, "c"]]}, {"entities": [], "relations": [("a", "b", "c", "d")]},
                                 {"entities": [5]}])
def test_build_graph_validates_extractor_output(bad):
    with pytest.raises(ValueError):
        build_graph([{"id": "a", "text": "t"}], lambda t: bad)


def test_build_graph_calls_extract_once_per_chunk_in_order():
    seen = []

    def spy(text):
        seen.append(text)
        return extract(text)

    build_graph(CHUNKS, spy)
    assert seen == [t for _, t in TEXTS]


def test_neighbors(graph):
    assert neighbors(graph, "gridops") == {"solarco": 2, "battery lab": 1, "wind farm": 1}
    assert neighbors(graph, "moonbase") == {"rocket team": 1, "orbitworks": 2}
    assert neighbors(graph, "nobody") == {}
    assert neighbors(hand_graph({}, ["lonely"]), "lonely") == {}


# --- communities -------------------------------------------------------------------------------

def test_communities_on_the_fixture_graph(graph):
    # wind farm має по ребру до gridops і genomed: рівність голосів вирішує менша за алфавітом мітка
    assert communities(graph) == [["battery lab", "gridops", "solarco"], ["clinic one", "genomed", "proteinx", "wind farm"],
                                  ["moonbase", "orbitworks", "rocket team"]]


def test_two_triangles_joined_by_a_light_bridge_stay_separate():
    g = hand_graph({("a", "b"): 3, ("b", "c"): 3, ("a", "c"): 3, ("d", "e"): 3, ("e", "f"): 3, ("d", "f"): 3, ("c", "d"): 1})
    assert communities(g) == [["a", "b", "c"], ["d", "e", "f"]]


def test_equal_weights_everywhere_collapse_into_one_community_by_smallest_label_rule():
    g = hand_graph({("a", "b"): 1, ("b", "c"): 1, ("a", "c"): 1, ("d", "e"): 1, ("e", "f"): 1, ("d", "f"): 1, ("c", "d"): 1})
    assert communities(g) == [["a", "b", "c", "d", "e", "f"]]


def test_isolated_nodes_are_singleton_communities_and_order_is_by_first_member():
    g = hand_graph({("m", "n"): 2}, extra_nodes=["z", "a"])
    assert communities(g) == [["a"], ["m", "n"], ["z"]]
    assert communities({"nodes": {}, "edges": {}}) == []


def test_weight_beats_count_of_neighbours():
    # x має трьох легких сусідів (вага 1) і одного важкого (вага 5): мітка важкого перемагає
    g = hand_graph({("x", "h"): 5, ("x", "p"): 1, ("x", "q"): 1, ("x", "r"): 1})
    comms = communities(g)
    assert any({"x", "h"} <= set(c) for c in comms)


def test_ties_choose_alphabetically_smaller_label_and_updates_are_immediate():
    # a-b, b-c: a бере b (єдиний сусід); b бачить a (мітка b) і c: {b: 1, c: 1} -> b; c бере b: усі в одній спільноті
    assert communities(hand_graph({("a", "b"): 1, ("b", "c"): 1})) == [["a", "b", "c"]]
    # зірка: центр "m", листки a, z: a бере m; m бачить {m: ?}: листок a має мітку m, z має z -> {m: 1, z: 1} -> m; z бере m
    assert communities(hand_graph({("a", "m"): 1, ("m", "z"): 1})) == [["a", "m", "z"]]


def test_result_does_not_depend_on_edge_insertion_order():
    edges = {("a", "b"): 3, ("b", "c"): 3, ("a", "c"): 3, ("d", "e"): 3, ("e", "f"): 3, ("d", "f"): 3, ("c", "d"): 1}
    reference = communities(hand_graph(edges))
    for order in (list(reversed(list(edges))), sorted(edges, key=lambda k: (k[1], k[0]))):
        assert communities(hand_graph({k: edges[k] for k in order})) == reference


def test_max_iter_limits_work_and_is_validated():
    chain = hand_graph({("a", "b"): 1, ("b", "c"): 1, ("c", "d"): 1, ("d", "e"): 1})
    assert len(communities(chain, max_iter=1)) >= 1
    for bad in (0, -1, 1.5, "3", None, True):
        with pytest.raises(ValueError):
            communities(chain, max_iter=bad)


def test_communities_does_not_mutate_graph(graph):
    snapshot = copy.deepcopy(graph)
    communities(graph)
    local_search(graph, ["solarco"])
    assert graph == snapshot


# --- local_search ------------------------------------------------------------------------------

def test_local_search_one_hop_and_chunk_ranking(graph):
    result = local_search(graph, ["GenoMed"], hops=1)
    assert result == {"entities": ["clinic one", "genomed", "proteinx", "wind farm"],
                      "chunks": ["b1", "b2", "b3", "b4", "e4"], "missing": []}


def test_local_search_hops_zero_is_just_the_seed(graph):
    assert local_search(graph, ["  GRIDOPS "], hops=0) == {"entities": ["gridops"], "chunks": ["e1", "e2", "e3", "e4"], "missing": []}


def test_local_search_two_hops_normalizes_and_reports_missing(graph):
    result = local_search(graph, ["SolarCo", "nobody", "Nobody ", "ghost"], hops=2)
    assert result["entities"] == ["battery lab", "gridops", "solarco", "wind farm"]
    assert result["chunks"] == ["e3", "e1", "e2", "e4"]               # e3: 3 досягнуті сутності; e1, e2: по 2; e4: 2 (gridops, wind farm) і id більший
    assert result["missing"] == ["ghost", "nobody"]


def test_local_search_chunk_ranking_is_by_reached_entity_count_then_id():
    g = build_graph([{"id": "z", "text": "1"}, {"id": "a", "text": "2"}, {"id": "m", "text": "3"}],
                    lambda t: {"1": {"entities": ["A", "B", "C"]}, "2": {"entities": ["A"]}, "3": {"entities": ["A", "B"],
                               "relations": [["A", "r", "B"], ["B", "r", "C"]]}}[t])
    result = local_search(g, ["A"], hops=1)
    assert result["entities"] == ["a", "b"]
    assert result["chunks"] == ["m", "z", "a"]                                     # m і z згадують по 2 досягнуті сутності (a, b), a лише одну


def test_local_search_hops_expand_monotonically(graph):
    sizes = [len(local_search(graph, ["wind farm"], hops=h)["entities"]) for h in range(0, 5)]
    assert sizes == sorted(sizes) and sizes[0] == 1 and sizes[-1] == 7


def test_local_search_empty_or_unknown_input(graph):
    assert local_search(graph, []) == {"entities": [], "chunks": [], "missing": []}
    assert local_search(graph, ["x"]) == {"entities": [], "chunks": [], "missing": ["x"]}


@pytest.mark.parametrize("hops", [-1, 1.5, "1", None, True])
def test_local_search_validates_hops(graph, hops):
    with pytest.raises(ValueError):
        local_search(graph, ["gridops"], hops=hops)


# --- summarize_communities ---------------------------------------------------------------------

def test_summarize_communities_calls_and_shape(graph):
    calls = []

    def summarize(names, chunk_ids):
        calls.append((list(names), list(chunk_ids)))
        return "summary of " + ", ".join(names)

    comms = communities(graph)
    result = summarize_communities(graph, comms, summarize)
    assert [r["id"] for r in result] == ["c0", "c1", "c2"]
    assert calls[0] == (["Battery Lab", "GridOps", "SolarCo"], ["e1", "e2", "e3", "e4"])
    assert calls[2] == (["MoonBase", "OrbitWorks", "Rocket Team"], ["s1", "s2", "s3", "s4"])
    assert len(calls) == 3
    assert result[1] == {"id": "c1", "entities": ["clinic one", "genomed", "proteinx", "wind farm"],
                         "chunks": ["b1", "b2", "b3", "b4", "e4"], "summary": "summary of Clinic One, GenoMed, ProteinX, Wind Farm"}


def test_summarize_communities_empty():
    assert summarize_communities({"nodes": {}, "edges": {}}, [], lambda n, c: "x") == []


# --- global_search -----------------------------------------------------------------------------

@pytest.fixture
def summaries(graph):
    names = {"c0": "energy: solar power and storage", "c1": "biotech: protein trials", "c2": "space: rockets and moon base"}
    return [{"id": s["id"], "entities": s["entities"], "chunks": s["chunks"], "summary": names[s["id"]]}
            for s in summarize_communities(graph, communities(graph), lambda n, c: "tmp")]


class FakeLLM:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def __call__(self, stage, question, payload):
        self.calls.append((stage, question, payload))
        if stage == "map":
            topic = payload.split(":")[0]
            return self.scores.get(topic, 0), f"{topic} insight"
        return "FINAL: " + " | ".join(payload)


def test_global_search_map_reduce_ranks_by_score_then_order(summaries):
    llm = FakeLLM({"energy": 40, "biotech": 90, "space": 40})
    result = global_search(summaries, "overview?", llm)
    assert result == {"answer": "FINAL: biotech insight | energy insight | space insight", "used": ["c1", "c0", "c2"], "calls": 4}
    assert [c[0] for c in llm.calls] == ["map", "map", "map", "reduce"]
    assert [c[2] for c in llm.calls[:3]] == [s["summary"] for s in summaries] and all(c[1] == "overview?" for c in llm.calls)
    assert llm.calls[3][2] == ["biotech insight", "energy insight", "space insight"]


def test_global_search_filters_by_min_score_inclusive(summaries):
    llm = FakeLLM({"energy": 50, "biotech": 49, "space": 0})
    assert global_search(summaries, "q", llm, min_score=50)["used"] == ["c0"]
    assert global_search(summaries, "q", FakeLLM({"energy": 50, "biotech": 49, "space": 0}))["used"] == ["c0", "c1"]
    assert global_search(summaries, "q", FakeLLM({"energy": 50, "biotech": 49, "space": 0}), min_score=0)["used"] == ["c0", "c1", "c2"]


def test_global_search_without_relevant_communities_skips_reduce(summaries):
    llm = FakeLLM({})
    result = global_search(summaries, "unrelated", llm)
    assert result == {"answer": "", "used": [], "calls": 3}
    assert [c[0] for c in llm.calls] == ["map"] * 3


def test_global_search_empty_summaries():
    llm = FakeLLM({})
    assert global_search([], "q", llm) == {"answer": "", "used": [], "calls": 0} and llm.calls == []


def test_chunks_for(summaries):
    assert chunks_for(summaries, ["c1"]) == ["b1", "b2", "b3", "b4", "e4"]
    assert chunks_for(summaries, ["c2", "c0", "c2"]) == ["e1", "e2", "e3", "e4", "s1", "s2", "s3", "s4"]   # дублікати в used не шкодять
    assert chunks_for(summaries, ["c0", "c2"]) == ["e1", "e2", "e3", "e4", "s1", "s2", "s3", "s4"]
    assert chunks_for(summaries, []) == []
    with pytest.raises(ValueError):
        chunks_for(summaries, ["c0", "c9"])


# --- keyword_search / theme_coverage: чому GraphRAG для питань «про весь корпус» -----------------

def test_keyword_search_scores_tokens_and_ties_by_id():
    chunks = [{"id": "b", "text": "solar power plant"}, {"id": "a", "text": "solar power"}, {"id": "c", "text": "unrelated"},
              {"id": "d", "text": "A of an to solar"}]
    assert keyword_search(chunks, "Solar POWER plant", 10) == ["b", "a", "d"]
    assert keyword_search(chunks, "solar power", 2) == ["a", "b"]                 # a, b мають 2; id a < b
    assert keyword_search(chunks, "of an to", 5) == []                            # слова коротші за 3 символи не рахуються
    assert keyword_search(chunks, "", 5) == []


@pytest.mark.parametrize("k", [0, -1, 1.5, "2", None, True])
def test_keyword_search_validates_k(k):
    with pytest.raises(ValueError):
        keyword_search(CHUNKS, "solar", k)


def test_theme_coverage():
    assert theme_coverage(["e1", "e2"], THEMES) == 0.3333
    assert theme_coverage(["e1", "b1", "s1", "e2"], THEMES) == 1.0
    assert theme_coverage([], THEMES) == 0.0
    assert theme_coverage(["e1", "unknown"], THEMES) == 0.3333
    assert theme_coverage(["e1", "b2"], THEMES) == 0.6667
    with pytest.raises(ValueError):
        theme_coverage(["e1"], {})


def test_global_search_covers_all_themes_where_top_k_keyword_search_covers_one(graph, summaries):
    top = keyword_search(CHUNKS, "solar power energy storage", 4)
    assert theme_coverage(top, THEMES) == 0.3333                                   # усі чотири з однієї теми
    result = global_search(summaries, "Give an overview of every topic in the corpus",
                           FakeLLM({"energy": 70, "biotech": 70, "space": 70}))
    assert theme_coverage(chunks_for(summaries, result["used"]), THEMES) == 1.0
    focused = global_search(summaries, "solar?", FakeLLM({"energy": 90}))
    assert focused["used"] == ["c0"]
