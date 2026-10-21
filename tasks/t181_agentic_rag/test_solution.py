import copy

import pytest

from solution import agentic_rag

C1 = {"id": "c1", "text": "Zeta Phone is made by Zeta Corp."}
C2 = {"id": "c2", "text": "Zeta Corp was founded by Ada Zed in 1999."}
C3 = {"id": "c3", "text": "Ada Zed was born in Lisbon."}
C4 = {"id": "c4", "text": "The weather in Lisbon is mild."}
Q = "Who founded the company that makes Zeta Phone?"
SUBS = ["Which company makes Zeta Phone?", "Who founded {1}?"]


class Retriever:
    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, query, k):
        self.calls.append((query, k))
        return [dict(c) for c in self.table.get(query, [])]


class FakeLLM:
    """Сценарний мок: відповіді задані функціями/таблицями; усі виклики записуються."""

    def __init__(self, subs=SUBS, answer_step=None, rewrite=None, enough=None, final=None):
        self.subs = subs
        self.answer_step = answer_step or {}
        self.rewrite = list(rewrite or [])
        self.enough = enough or (lambda payload: False)
        self.final = final or (lambda payload: "FINAL: " + "; ".join(f"{q}={a}" for q, a in payload["facts"]))
        self.calls = []

    def __call__(self, task, payload):
        self.calls.append((task, copy.deepcopy(payload)))
        if task == "decompose":
            return self.subs
        if task == "answer_step":
            for key, value in self.answer_step.items():
                if key in payload["question"]:
                    result = value(payload) if callable(value) else value
                    return {"answer": result[1], "sufficient": result[0]}
            return {"answer": None, "sufficient": False}
        if task == "rewrite":
            return self.rewrite.pop(0) if self.rewrite else ""
        if task == "enough":
            return self.enough(payload)
        if task == "final":
            return self.final(payload)
        raise AssertionError(task)

    def tasks(self):
        return [t for t, _ in self.calls]


TABLE = {"Which company makes Zeta Phone?": [C1, C4], "Who founded Zeta Corp?": [C2]}
STEPS = {"Which company": (True, "Zeta Corp"), "Who founded Zeta Corp": (True, "Ada Zed")}


# --- щасливий шлях: multi-hop -------------------------------------------------------------------

def test_two_hop_question_exact_result_and_call_order():
    retrieve, llm = Retriever(TABLE), FakeLLM(answer_step=STEPS)
    result = agentic_rag(Q, retrieve, llm, k=2)
    assert result == {
        "answer": "FINAL: Which company makes Zeta Phone?=Zeta Corp; Who founded Zeta Corp?=Ada Zed",
        "status": "complete", "steps": 2,
        "facts": [{"question": "Which company makes Zeta Phone?", "answer": "Zeta Corp", "attempts": 1,
                   "queries": ["Which company makes Zeta Phone?"]},
                  {"question": "Who founded Zeta Corp?", "answer": "Ada Zed", "attempts": 1, "queries": ["Who founded Zeta Corp?"]}],
        "evidence": ["c1", "c4", "c2"], "queries": ["Which company makes Zeta Phone?", "Who founded Zeta Corp?"],
    }
    assert retrieve.calls == [("Which company makes Zeta Phone?", 2), ("Who founded Zeta Corp?", 2)]
    assert llm.tasks() == ["decompose", "answer_step", "enough", "answer_step", "final"]      # enough не після останнього
    assert llm.calls[0][1] == {"question": Q}
    assert llm.calls[1][1] == {"question": "Which company makes Zeta Phone?", "context": [C1["text"], C4["text"]]}
    assert llm.calls[2][1] == {"question": Q, "facts": [["Which company makes Zeta Phone?", "Zeta Corp"]]}
    assert llm.calls[3][1] == {"question": "Who founded Zeta Corp?", "context": [C2["text"]]}
    assert llm.calls[4][1] == {"question": Q, "facts": [["Which company makes Zeta Phone?", "Zeta Corp"],
                                                          ["Who founded Zeta Corp?", "Ada Zed"]]}


def test_defaults_are_k_3_and_inputs_are_not_mutated():
    retrieve, llm = Retriever(TABLE), FakeLLM(answer_step=STEPS)
    agentic_rag(Q, retrieve, llm)
    assert [c[1] for c in retrieve.calls] == [3, 3]
    assert llm.subs == SUBS


def test_single_subquestion_has_no_enough_check():
    llm = FakeLLM(subs=["Which company makes Zeta Phone?"], answer_step=STEPS)
    result = agentic_rag(Q, Retriever(TABLE), llm)
    assert llm.tasks() == ["decompose", "answer_step", "final"] and result["status"] == "complete"


def test_placeholders_use_every_answered_subquestion():
    table = {"Which company makes Zeta Phone?": [C1], "Who is {1} CEO?": [], "Who founded Zeta Corp?": [C2],
             "Compare Zeta Corp and Ada Zed": [C3]}
    llm = FakeLLM(subs=["Which company makes Zeta Phone?", "Who founded {1}?", "Compare {1} and {2}"],
                  answer_step={"Which company": (True, "Zeta Corp"), "Who founded": (True, "Ada Zed"), "Compare": (True, "done")})
    result = agentic_rag(Q, Retriever(table), llm)
    assert [f["question"] for f in result["facts"]] == ["Which company makes Zeta Phone?", "Who founded Zeta Corp?",
                                                        "Compare Zeta Corp and Ada Zed"]
    assert result["status"] == "complete" and result["evidence"] == ["c1", "c2", "c3"]


# --- рання зупинка -----------------------------------------------------------------------------

def test_enough_stops_the_loop_and_skips_remaining_subquestions():
    llm = FakeLLM(subs=["Which company makes Zeta Phone?", "Who founded {1}?", "Where was Ada Zed born?"],
                  answer_step=STEPS, enough=lambda p: True)
    retrieve = Retriever(TABLE)
    result = agentic_rag(Q, retrieve, llm)
    assert result["steps"] == 1 and len(result["facts"]) == 1 and result["status"] == "complete"
    assert llm.tasks() == ["decompose", "answer_step", "enough", "final"]
    assert result["answer"] == "FINAL: Which company makes Zeta Phone?=Zeta Corp"


def test_truthy_enough_value_counts():
    llm = FakeLLM(answer_step=STEPS, enough=lambda p: "yes")
    assert agentic_rag(Q, Retriever(TABLE), llm)["steps"] == 1


def test_enough_sees_only_answered_facts_so_far():
    seen = []
    llm = FakeLLM(subs=["Unknown thing?", "Which company makes Zeta Phone?", "Who founded {2}?"], answer_step=STEPS,
                  enough=lambda p: seen.append(p["facts"]) or False)
    agentic_rag(Q, Retriever({**TABLE, "Unknown thing?": [C3]}), llm)
    assert seen == [[["Which company makes Zeta Phone?", "Zeta Corp"]]]


# --- переписування запиту ----------------------------------------------------------------------

def test_insufficient_context_triggers_rewrite_and_context_accumulates_without_duplicates():
    table = {"Which company makes Zeta Phone?": [C4], "Zeta Phone manufacturer": [C4, C1]}
    llm = FakeLLM(subs=["Which company makes Zeta Phone?"], rewrite=["Zeta Phone manufacturer"],
                  answer_step={"Which company": lambda p: (len(p["context"]) > 1, "Zeta Corp")})
    retrieve = Retriever(table)
    result = agentic_rag(Q, retrieve, llm)
    assert llm.tasks() == ["decompose", "answer_step", "rewrite", "answer_step", "final"]
    assert llm.calls[2][1] == {"question": "Which company makes Zeta Phone?", "queries": ["Which company makes Zeta Phone?"]}
    assert llm.calls[3][1]["context"] == [C4["text"], C1["text"]]               # C4 не дублюється
    fact = result["facts"][0]
    assert fact["attempts"] == 2 and fact["queries"] == ["Which company makes Zeta Phone?", "Zeta Phone manufacturer"]
    assert result["queries"] == fact["queries"] and result["evidence"] == ["c4", "c1"] and result["steps"] == 2
    assert result["status"] == "complete"


@pytest.mark.parametrize("rewritten", ["", "   ", "WHICH COMPANY MAKES ZETA PHONE?", "  Which company makes Zeta Phone?  ", None, 5])
def test_useless_rewrite_fails_the_subquestion(rewritten):
    llm = FakeLLM(subs=["Which company makes Zeta Phone?"], rewrite=[rewritten], answer_step={})
    retrieve = Retriever(TABLE)
    result = agentic_rag(Q, retrieve, llm)
    assert result["status"] == "no-context" and result["answer"] == "I don't know."
    assert result["facts"] == [{"question": "Which company makes Zeta Phone?", "answer": None, "attempts": 1,
                                "queries": ["Which company makes Zeta Phone?"]}]
    assert llm.tasks() == ["decompose", "answer_step", "rewrite"] and len(retrieve.calls) == 1


def test_rewrite_is_not_called_after_the_last_allowed_attempt():
    table = {"q0": [C1], "q1": [C2], "q2": [C3], "q3": [C4]}
    llm = FakeLLM(subs=["q0"], rewrite=["q1", "q2", "q3"], answer_step={})
    result = agentic_rag(Q, Retriever(table), llm, max_attempts=3)
    assert result["facts"][0]["attempts"] == 3 and result["queries"] == ["q0", "q1", "q2"]
    assert llm.tasks().count("rewrite") == 2 and llm.tasks().count("answer_step") == 3
    assert agentic_rag(Q, Retriever(table), FakeLLM(subs=["q0"], rewrite=["q1"], answer_step={}), max_attempts=1)["steps"] == 1


def test_attempt_without_new_chunks_fails_without_calling_the_model():
    table = {"q0": [C1], "q1": [C1]}
    llm = FakeLLM(subs=["q0"], rewrite=["q1"], answer_step={})
    result = agentic_rag(Q, Retriever(table), llm)
    assert llm.tasks() == ["decompose", "answer_step", "rewrite"]                # другий answer_step не викликано
    assert result["facts"][0]["attempts"] == 2 and result["status"] == "no-context"


def test_empty_retrieval_never_calls_answer_step_and_gives_idk():
    llm = FakeLLM(subs=["a?", "b?"])
    retrieve = Retriever({})
    result = agentic_rag(Q, retrieve, llm)
    assert result["answer"] == "I don't know." and result["status"] == "no-context" and result["evidence"] == []
    assert llm.tasks() == ["decompose"] and result["steps"] == 2
    assert [f["answer"] for f in result["facts"]] == [None, None]


def test_insufficient_answer_text_is_ignored():
    llm = FakeLLM(subs=["q0"], answer_step={"q0": (False, "maybe Zeta")})
    result = agentic_rag(Q, Retriever({"q0": [C1]}), llm, max_attempts=1)
    assert result["facts"][0]["answer"] is None and result["status"] == "no-context"


# --- бюджет ------------------------------------------------------------------------------------

def test_budget_exhausted_before_second_subquestion_gives_partial_answer():
    llm = FakeLLM(answer_step=STEPS)
    retrieve = Retriever(TABLE)
    result = agentic_rag(Q, retrieve, llm, max_steps=1)
    assert result["steps"] == 1 and len(retrieve.calls) == 1 and result["status"] == "partial"
    assert result["facts"][1] == {"question": "Who founded Zeta Corp?", "answer": None, "attempts": 0, "queries": []}
    assert result["answer"] == "FINAL: Which company makes Zeta Phone?=Zeta Corp"
    assert llm.tasks() == ["decompose", "answer_step", "enough", "final"]


def test_budget_exhausted_in_the_middle_of_rewrites():
    table = {"q0": [C1], "q1": [C2], "q2": [C3]}
    llm = FakeLLM(subs=["q0", "never reached"], rewrite=["q1", "q2"], answer_step={})
    result = agentic_rag(Q, Retriever(table), llm, max_steps=2, max_attempts=5)
    assert result["steps"] == 2 and result["status"] == "no-context"
    assert [f["question"] for f in result["facts"]] == ["q0"]                    # наступне підпитання не виконувалось
    assert llm.tasks() == ["decompose", "answer_step", "rewrite", "answer_step", "rewrite"]


def test_budget_counts_retrieve_calls_across_the_whole_run():
    table = {"a": [C1], "b": [C2], "c": [C3]}
    llm = FakeLLM(subs=["a", "b", "c"], answer_step={"a": (True, "A"), "b": (True, "B"), "c": (True, "C")})
    result = agentic_rag(Q, Retriever(table), llm, max_steps=3)
    assert result["steps"] == 3 and result["status"] == "complete"
    assert agentic_rag(Q, Retriever(table), llm, max_steps=2)["status"] == "partial"


# --- провалені підпитання й плейсхолдери --------------------------------------------------------

def test_failed_first_subquestion_makes_dependent_one_skipped_without_retrieval():
    llm = FakeLLM(answer_step={})                                                # ніщо не відповідає
    retrieve = Retriever(TABLE)
    result = agentic_rag(Q, retrieve, llm, max_attempts=1)
    assert result["status"] == "no-context" and result["answer"] == "I don't know."
    assert result["facts"][1] == {"question": "Who founded {1}?", "answer": None, "attempts": 0, "queries": []}
    assert len(retrieve.calls) == 1 and "final" not in llm.tasks()


def test_partial_status_when_one_subquestion_fails_but_another_is_answered():
    table = {"q0": [C1], "q1": [C2], "q2": [C3]}
    llm = FakeLLM(subs=["q0", "q1", "needs {1} and {2}"], answer_step={"q0": (False, None), "q1": (True, "B"), "needs": (True, "X")})
    result = agentic_rag(Q, Retriever(table), llm, max_attempts=1)
    assert result["status"] == "partial"
    assert [f["answer"] for f in result["facts"]] == [None, "B", None]
    assert result["facts"][2] == {"question": "needs {1} and B", "answer": None, "attempts": 0, "queries": []}   # {2} замінено, {1} лишився
    assert llm.calls[-1] == ("final", {"question": Q, "facts": [["q1", "B"]]})


def test_forward_reference_is_skipped():
    llm = FakeLLM(subs=["first needs {2}", "second"], answer_step={"second": (True, "S"), "first": (True, "F")})
    result = agentic_rag(Q, Retriever({"second": [C1]}), llm)
    assert result["facts"][0] == {"question": "first needs {2}", "answer": None, "attempts": 0, "queries": []}
    assert result["status"] == "partial" and result["steps"] == 1


def test_enough_is_not_called_after_a_failed_subquestion():
    llm = FakeLLM(subs=["q0", "q1", "q2"], answer_step={"q1": (True, "B"), "q2": (True, "C")}, enough=lambda p: False)
    agentic_rag(Q, Retriever({"q0": [C1], "q1": [C2], "q2": [C3]}), llm, max_attempts=1)
    assert llm.tasks() == ["decompose", "answer_step", "answer_step", "enough", "answer_step", "final"]


# --- evidence, дедуплікація, контекст ----------------------------------------------------------

def test_evidence_is_unique_in_first_seen_order_across_subquestions():
    table = {"a": [C2, C1], "b": [C1, C3, C2]}
    llm = FakeLLM(subs=["a", "b"], answer_step={"a": (True, "A"), "b": (True, "B")})
    result = agentic_rag(Q, Retriever(table), llm)
    assert result["evidence"] == ["c2", "c1", "c3"]
    assert llm.calls[3][1]["context"] == [C1["text"], C3["text"], C2["text"]]      # контекст другого підпитання повний, не лише «нові» глобально


def test_duplicate_chunks_inside_one_result_are_not_repeated_in_context():
    llm = FakeLLM(subs=["a"], answer_step={"a": (True, "A")})
    agentic_rag(Q, Retriever({"a": [C1, C1, C2]}), llm)
    assert llm.calls[1][1]["context"] == [C1["text"], C2["text"]]


def test_answer_step_context_is_a_snapshot():
    contexts = []
    llm = FakeLLM(subs=["q0"], rewrite=["q1"], answer_step={"q0": lambda p: contexts.append(p["context"]) or (len(contexts) > 1, "ok")})
    agentic_rag(Q, Retriever({"q0": [C1], "q1": [C2]}), llm)
    assert contexts == [[C1["text"]], [C1["text"], C2["text"]]]


# --- валідація ---------------------------------------------------------------------------------

@pytest.mark.parametrize("question", ["", "   ", None, 5, ["q"]])
def test_question_validation(question):
    llm = FakeLLM()
    with pytest.raises(ValueError):
        agentic_rag(question, Retriever(TABLE), llm)
    assert llm.calls == []


@pytest.mark.parametrize("kw", [{"max_steps": 0}, {"max_steps": -1}, {"max_steps": 1.5}, {"max_steps": True}, {"k": 0}, {"k": "3"},
                                {"max_attempts": 0}, {"max_attempts": None}, {"max_attempts": False}])
def test_parameter_validation_happens_before_any_call(kw):
    llm = FakeLLM()
    retrieve = Retriever(TABLE)
    with pytest.raises(ValueError):
        agentic_rag(Q, retrieve, llm, **kw)
    assert llm.calls == [] and retrieve.calls == []


@pytest.mark.parametrize("subs", [None, [], "q", ["a", ""], ["a", "  "], ["a", 5], [None], ["q"] * 6, ("a", "b")])
def test_bad_decomposition_is_value_error(subs):
    with pytest.raises(ValueError):
        agentic_rag(Q, Retriever(TABLE), FakeLLM(subs=subs))


def test_five_subquestions_are_allowed():
    llm = FakeLLM(subs=["q"] * 5)
    assert agentic_rag(Q, Retriever({}), llm)["steps"] == 5


@pytest.mark.parametrize("bad", [None, "yes", [], {"answer": "a"}, {"sufficient": True}, {"answer": "a", "sufficient": 1},
                                 {"answer": "a", "sufficient": "yes"}, {"answer": None, "sufficient": True},
                                 {"answer": 5, "sufficient": True}])
def test_bad_answer_step_output_is_value_error(bad):
    class Bad(FakeLLM):
        def __call__(self, task, payload):
            if task == "answer_step":
                self.calls.append((task, payload))
                return bad
            return super().__call__(task, payload)

    with pytest.raises(ValueError):
        agentic_rag(Q, Retriever(TABLE), Bad(subs=["Which company makes Zeta Phone?"]))
