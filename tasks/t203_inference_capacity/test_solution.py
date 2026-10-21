import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from solution import api_cost_per_hour, best_batch, break_even_rps, compare, plan, tpot_at, ttft_p95

P = {"prefill_tps": 8000.0, "tpot_base": 0.02, "tpot_slope": 0.01, "max_batch": 32, "gpu_cost_per_hour": 2.5}
W = {"rps": 10.0, "input_tokens": 800.0, "output_tokens": 200.0}
S = {"ttft_p95": 0.5, "tpot_p95": 0.025}
A = {"input_price_per_mtok": 1.0, "output_price_per_mtok": 4.0}

# профіль із «круглими» двійковими числами: tpot(b) = 0.5 * (1 + 0.5 * (b - 1)): 0.5, 0.75, 1.0, 1.25 ...
Q = {"prefill_tps": 1000.0, "tpot_base": 0.5, "tpot_slope": 0.5, "max_batch": 8, "gpu_cost_per_hour": 4.0}
# профіль без деградації: час GPU на запит g = 100 / 100 + 1 * 1.0 / 1 = 2.0
R = {"prefill_tps": 100.0, "tpot_base": 1.0, "tpot_slope": 0.0, "max_batch": 1, "gpu_cost_per_hour": 1.0}
WR = {"rps": 1.0, "input_tokens": 100.0, "output_tokens": 1.0}
SR = {"ttft_p95": 10.0, "tpot_p95": 1.0}


HERE = Path(__file__).resolve().parent


def plan_isolated(profile, workload, slo, timeout=10, **kw):
    """plan() в окремому процесі: цикл без виходу має дати збій тесту, а не зависання pytest."""
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(HERE)!r})\n"
        "from solution import plan\n"
        "a = json.loads(sys.stdin.read())\n"
        "print(json.dumps(plan(a['p'], a['w'], a['s'], **a['kw'])))\n"
    )
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", code], input=json.dumps({"p": profile, "w": workload, "s": slo, "kw": kw}),
                              capture_output=True, text=True, timeout=timeout, cwd=str(HERE))
    except subprocess.TimeoutExpired:
        pytest.fail(f"plan() не завершилась за {timeout} с: цикл за кількістю GPU не має виходу")
    assert proc.returncode == 0, proc.stderr[-400:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


# --- tpot_at / best_batch ----------------------------------------------------------------------

def test_tpot_at_formula():
    assert tpot_at(Q, 1) == 0.5 and tpot_at(Q, 2) == 0.75 and tpot_at(Q, 3) == 1.0 and tpot_at(Q, 8) == 2.25
    assert tpot_at(P, 11) == pytest.approx(0.022)
    assert tpot_at(R, 1) == 1.0


@pytest.mark.parametrize("batch", [0, -1, 9, 1.5, "2", None, True])
def test_tpot_at_validates_batch(batch):
    with pytest.raises(ValueError):
        tpot_at(Q, batch)


def test_best_batch_is_largest_with_inclusive_boundary():
    assert best_batch(Q, 1.0) == 3                    # tpot(3) == 1.0: рівність допустима
    assert best_batch(Q, 0.99) == 2
    assert best_batch(Q, 0.75) == 2 and best_batch(Q, 0.5) == 1
    assert best_batch(Q, 0.49) == 0
    assert best_batch(Q, 100) == 8                    # обмежено max_batch
    assert best_batch(P, 0.0251) == 26 and best_batch(P, 0.01) == 0
    assert best_batch(R, 1.0) == 1


def test_best_batch_with_zero_slope_uses_max_batch():
    flat = {**Q, "tpot_slope": 0}
    assert best_batch(flat, 0.5) == 8


@pytest.mark.parametrize("slo", [0, -1, "1", None, True, float("nan")])
def test_best_batch_validates_slo(slo):
    with pytest.raises(ValueError):
        best_batch(Q, slo)


# --- ttft_p95 ----------------------------------------------------------------------------------

def test_ttft_formula_and_edges():
    wl = {"rps": 1.0, "input_tokens": 500.0, "output_tokens": 10.0}
    assert ttft_p95(Q, wl, 0.0) == 0.5
    assert ttft_p95(Q, wl, 0.5) == pytest.approx(0.5 * (1 + 3.0 * 0.5 / 0.5))      # 2.0
    assert ttft_p95(Q, wl, 0.5, p95_factor=0) == 0.5
    assert ttft_p95(Q, wl, 0.5, p95_factor=1.0) == pytest.approx(1.0)
    assert ttft_p95(Q, wl, 1.0) == math.inf and ttft_p95(Q, wl, 7) == math.inf
    assert ttft_p95(Q, wl, 0.9) > ttft_p95(Q, wl, 0.5) > ttft_p95(Q, wl, 0.1)


@pytest.mark.parametrize("rho, factor", [(-0.1, 3.0), ("0.5", 3.0), (None, 3.0), (True, 3.0), (0.5, -1), (0.5, "3")])
def test_ttft_validation(rho, factor):
    with pytest.raises(ValueError):
        ttft_p95(Q, W, rho, factor)


# --- plan --------------------------------------------------------------------------------------

def test_plan_worked_example_ttft_binding():
    # g(26) = 800/8000 + 200 * 0.025 / 26 = 0.292308; n_cap = ceil(10 * g / 0.7) = 5, але TTFT при n = 5 це 0.522 > 0.5
    result = plan(P, W, S)
    assert result["feasible"] is True and result["gpus"] == 6 and result["batch"] == 26 and result["binding"] == "ttft"
    g = 800 / 8000 + 200 * 0.025 / 26
    assert result["rho"] == pytest.approx(10 * g / 6)
    assert result["ttft_p95"] == pytest.approx(0.1 * (1 + 3 * result["rho"] / (1 - result["rho"])))
    assert result["ttft_p95"] <= 0.5 < ttft_p95(P, W, 10 * g / 5)
    assert result["tpot"] == pytest.approx(0.025) and result["cost_per_hour"] == 15.0


def test_plan_capacity_binding_when_ttft_slo_is_loose():
    result = plan(P, W, {"ttft_p95": 5.0, "tpot_p95": 0.025})
    assert result["gpus"] == 5 and result["binding"] == "capacity" and result["cost_per_hour"] == 12.5


def test_plan_exact_ceiling_without_float_noise():
    # g = 2.0, rps * g / 0.5 = 4.0 рівно -> 4 GPU, rho = 0.5, TTFT = 1.0 * (1 + 3 * 0.5 / 0.5) = 4.0
    result = plan(R, WR, SR, target_util=0.5)
    assert result == {"feasible": True, "gpus": 4, "batch": 1, "rho": 0.5, "tpot": 1.0, "ttft_p95": 4.0,
                      "cost_per_hour": 4.0, "binding": "capacity"}


def test_plan_target_util_controls_headroom_and_ttft_takes_over():
    # target_util = 1.0: n_cap = 2, але rho = 1 дає TTFT = inf; при 3 GPU rho = 2/3 -> 1.0 * (1 + 3 * 2) = 7 <= 10
    full = plan(R, WR, SR, target_util=1.0)
    assert full["gpus"] == 3 and full["binding"] == "ttft" and full["ttft_p95"] == pytest.approx(7.0)
    loose = plan(R, WR, SR, target_util=0.25)
    assert loose["gpus"] == 8 and loose["binding"] == "capacity"


def test_plan_p95_factor_zero_removes_queueing_penalty():
    result = plan(P, W, S, p95_factor=0)
    assert result["gpus"] == 5 and result["binding"] == "capacity"
    assert result["ttft_p95"] == pytest.approx(0.1)
    assert plan(P, W, S, p95_factor=10)["gpus"] > 6


def test_plan_zero_rps_needs_one_gpu_at_base_ttft():
    result = plan(P, {**W, "rps": 0}, S)
    assert result["gpus"] == 1 and result["rho"] == 0.0 and result["ttft_p95"] == pytest.approx(0.1)
    assert result["cost_per_hour"] == 2.5 and result["binding"] == "capacity"


def test_plan_infeasible_tpot_checked_first():
    assert plan(P, W, {"ttft_p95": 0.5, "tpot_p95": 0.01}) == {"feasible": False, "reason": "tpot-slo-unreachable"}
    both = plan(P, {**W, "input_tokens": 80000}, {"ttft_p95": 0.5, "tpot_p95": 0.01})
    assert both["reason"] == "tpot-slo-unreachable"


def test_plan_infeasible_when_prefill_alone_exceeds_ttft_slo():
    assert plan(P, {**W, "input_tokens": 8000.0}, S) == {"feasible": False, "reason": "ttft-slo-unreachable"}


def test_plan_prefill_exactly_at_slo_is_feasible_only_without_queueing():
    at_slo = {**W, "input_tokens": 4000.0}                                       # t_p == 0.5 == SLO
    assert plan_isolated(P, at_slo, S) == {"feasible": False, "reason": "ttft-slo-unreachable"}   # з трафіком будь-яка черга порушує SLO
    idle = plan_isolated(P, {**at_slo, "rps": 0}, S)
    assert idle["feasible"] is True and idle["gpus"] == 1 and idle["ttft_p95"] == 0.5
    flat = plan_isolated(P, at_slo, S, p95_factor=0)                             # без штрафу за чергу
    assert flat["feasible"] is True and flat["ttft_p95"] == 0.5


def test_plan_ttft_is_met_and_not_overprovisioned_across_a_range_of_loads():
    previous = 0
    for rps in [0, 0.5, 1, 2, 5, 10, 20, 50, 100, 300]:
        r = plan(P, {**W, "rps": rps}, S)
        assert r["feasible"] and r["rho"] < 1 and r["ttft_p95"] <= S["ttft_p95"] + 1e-12
        assert r["gpus"] >= previous
        previous = r["gpus"]
        g = 800 / 8000 + 200 * 0.025 / 26
        n_cap = max(1, math.ceil(rps * g / 0.7))
        assert r["gpus"] >= n_cap
        if r["gpus"] > n_cap:                                                    # на одну GPU менше порушило б TTFT
            assert ttft_p95(P, {**W, "rps": rps}, rps * g / (r["gpus"] - 1)) > S["ttft_p95"]


def test_plan_more_output_tokens_cost_more_gpus():
    base = plan(P, W, S)["gpus"]
    assert plan(P, {**W, "output_tokens": 1000.0}, S)["gpus"] > base
    assert plan(P, {**W, "input_tokens": 3000.0}, S)["gpus"] > base


@pytest.mark.parametrize("target", [0, -0.1, 1.01, "0.7", None, True])
def test_plan_validates_target_util(target):
    with pytest.raises(ValueError):
        plan(P, W, S, target_util=target)


@pytest.mark.parametrize("mutate", [
    lambda p, w, s: p.pop("prefill_tps"), lambda p, w, s: p.update(extra=1), lambda p, w, s: p.update(prefill_tps=0),
    lambda p, w, s: p.update(tpot_base=-1), lambda p, w, s: p.update(tpot_slope=-0.1), lambda p, w, s: p.update(max_batch=0),
    lambda p, w, s: p.update(max_batch=2.5), lambda p, w, s: p.update(max_batch=True),
    lambda p, w, s: p.update(gpu_cost_per_hour=-1), lambda p, w, s: p.update(gpu_cost_per_hour="2"),
    lambda p, w, s: w.update(rps=-1), lambda p, w, s: w.update(input_tokens=0), lambda p, w, s: w.update(output_tokens=None),
    lambda p, w, s: w.pop("rps"), lambda p, w, s: w.update(rps=True), lambda p, w, s: w.update(rps=float("nan")),
    lambda p, w, s: s.update(ttft_p95=0), lambda p, w, s: s.update(tpot_p95=-1), lambda p, w, s: s.pop("ttft_p95"),
    lambda p, w, s: s.update(extra=1),
])
def test_plan_input_validation(mutate):
    p, w, s = copy.deepcopy(P), copy.deepcopy(W), copy.deepcopy(S)
    mutate(p, w, s)
    with pytest.raises(ValueError):
        plan(p, w, s)


def test_plan_not_a_dict_inputs():
    for bad in (None, [], "x"):
        with pytest.raises(ValueError):
            plan(bad, W, S)
        with pytest.raises(ValueError):
            plan(P, bad, S)
        with pytest.raises(ValueError):
            plan(P, W, bad)


def test_zero_slope_free_gpu_and_zero_rps_are_allowed():
    free = {**P, "tpot_slope": 0, "gpu_cost_per_hour": 0}
    assert plan(free, W, S)["cost_per_hour"] == 0.0
    assert plan(free, {**W, "rps": 0}, S)["feasible"] is True


def test_plan_does_not_mutate_inputs():
    p, w, s = copy.deepcopy(P), copy.deepcopy(W), copy.deepcopy(S)
    plan(p, w, s)
    compare(p, w, s, A)
    assert (p, w, s) == (P, W, S)


# --- api_cost_per_hour / compare ---------------------------------------------------------------

def test_api_cost_per_hour_exact():
    wl = {"rps": 10, "input_tokens": 100_000, "output_tokens": 50_000}
    assert api_cost_per_hour(wl, {"input_price_per_mtok": 2.0, "output_price_per_mtok": 8.0}) == 21600.0
    assert api_cost_per_hour({**wl, "rps": 0}, A) == 0.0
    assert api_cost_per_hour(W, A) == pytest.approx(57.6)
    assert api_cost_per_hour(W, {"input_price_per_mtok": 0, "output_price_per_mtok": 0}) == 0.0


@pytest.mark.parametrize("api", [{"input_price_per_mtok": -1, "output_price_per_mtok": 1}, {"input_price_per_mtok": 1},
                                 {"input_price_per_mtok": "1", "output_price_per_mtok": 1}, None,
                                 {"input_price_per_mtok": 1, "output_price_per_mtok": 1, "x": 2}])
def test_api_validation(api):
    with pytest.raises(ValueError):
        api_cost_per_hour(W, api)


def test_compare_hosted_cheaper_and_api_cheaper():
    result = compare(P, W, S, A)
    assert result["feasible"] and result["cheaper"] == "hosted"
    assert result["hosted_per_hour"] == 15.0 and result["api_per_hour"] == pytest.approx(57.6)
    assert result["savings_per_hour"] == pytest.approx(42.6)
    low = compare(P, {**W, "rps": 0.25}, S, A)
    assert low["cheaper"] == "api" and low["savings_per_hour"] < 0
    assert set(result) == {"feasible", "hosted_per_hour", "api_per_hour", "cheaper", "savings_per_hour"}


def test_compare_tie_only_on_exact_equality():
    rate = {"input_price_per_mtok": 40.0, "output_price_per_mtok": 0.0}
    r = {**R, "gpu_cost_per_hour": 3.6}
    result = compare(r, WR, SR, rate, target_util=0.5)              # 4 GPU * 3.6 = 14.4; API: 3600 * 100 * 40 / 1e6 = 14.4
    assert result["hosted_per_hour"] == 14.4 and result["api_per_hour"] == 14.4
    assert result["cheaper"] == "tie" and result["savings_per_hour"] == 0.0


def test_compare_passes_through_infeasibility():
    assert compare(P, W, {"ttft_p95": 0.5, "tpot_p95": 0.01}, A) == {"feasible": False, "reason": "tpot-slo-unreachable"}
    assert compare(P, {**W, "input_tokens": 9000.0}, S, A) == {"feasible": False, "reason": "ttft-slo-unreachable"}


def test_compare_respects_target_util_and_p95_factor():
    a = compare(R, WR, SR, A, target_util=0.5)
    b = compare(R, WR, SR, A, target_util=0.25)
    assert b["hosted_per_hour"] == 8.0 and a["hosted_per_hour"] == 4.0


# --- break_even_rps ----------------------------------------------------------------------------

def test_break_even_is_first_candidate_where_hosted_is_not_more_expensive():
    # API 5.76 USD/год на 1 rps; одна GPU коштує 2.5: при 0.25 rps API 1.44 (дешевше), при 0.5 rps 2.88 >= 2.5
    assert break_even_rps(P, W, S, A, [0, 0.25, 0.5, 1, 5]) == 0.5
    assert break_even_rps(P, W, S, A, [1, 5, 10]) == 1
    assert break_even_rps(P, W, S, A, [0, 0.1, 0.2]) is None


def test_break_even_ignores_workload_rps_and_does_not_mutate():
    w = {**W, "rps": 12345}
    snapshot = copy.deepcopy(w)
    assert break_even_rps(P, w, S, A, [0.25, 0.5]) == 0.5
    assert w == snapshot


def test_break_even_equality_counts_and_free_api_never_breaks_even():
    free = {"input_price_per_mtok": 0, "output_price_per_mtok": 0}
    assert break_even_rps(P, W, S, free, [0, 1, 100]) is None
    assert break_even_rps(P, W, S, free, [1, 100]) is None
    zero_gpu = {**P, "gpu_cost_per_hour": 0}
    assert break_even_rps(zero_gpu, W, S, free, [0, 1]) == 0                  # 0 <= 0
    tie_rate = {"input_price_per_mtok": 40.0, "output_price_per_mtok": 0.0}
    assert break_even_rps({**R, "gpu_cost_per_hour": 3.6}, WR, SR, tie_rate, [0.5, 1.0], target_util=0.5) == 0.5   # 2 GPU * 3.6 = 7.2 = API: рівність рахується


def test_break_even_skips_infeasible_candidates_and_returns_none_when_all_infeasible():
    assert break_even_rps(P, W, {"ttft_p95": 0.5, "tpot_p95": 0.01}, A, [1, 10]) is None
    assert break_even_rps(P, {**W, "input_tokens": 9000.0}, S, A, [1, 10]) is None


@pytest.mark.parametrize("candidates", [[], None, (1, 2), [5, 1], [-1, 2], [1, "2"], [True], "12", [float("nan")]])
def test_break_even_validates_candidates(candidates):
    with pytest.raises(ValueError):
        break_even_rps(P, W, S, A, candidates)
