"""Завдання №203: capacity planning для inference.

Скільки GPU потрібно, щоб тримати p95 SLO на TTFT (time to first token) і TPOT (time per output
token), і коли власний inference дешевший за API? Реальна відповідь залежить від вимірювань, тут
це проста детермінована модель continuous batching. Усі формули нижче обовʼязкові.

Вхідні дані (dict, числа це `int`/`float`, не `bool`; недодатні, відсутні чи невідомі ключі це
`ValueError`, якщо не сказано інше):
    profile  = {"prefill_tps": токенів промпта за секунду на GPU (> 0),
                "tpot_base": секунд на токен при batch = 1 (> 0),
                "tpot_slope": >= 0 (дозволено 0), "max_batch": int >= 1,
                "gpu_cost_per_hour": >= 0 (дозволено 0)}
    workload = {"rps": >= 0 (дозволено 0), "input_tokens": > 0, "output_tokens": > 0}
    slo      = {"ttft_p95": > 0, "tpot_p95": > 0}   (секунди)
    api      = {"input_price_per_mtok": >= 0, "output_price_per_mtok": >= 0}   (USD за 1 млн токенів)

Модель:
    TPOT при batch b:      tpot(b) = tpot_base * (1 + tpot_slope * (b - 1))
    час GPU на запит:      g(b) = input_tokens / prefill_tps + output_tokens * tpot(b) / b
        (префіл блокує GPU; декод ділиться між b послідовностями)
    p95 TTFT при утилізації rho (0 <= rho):
        t_p = input_tokens / prefill_tps
        rho >= 1: float("inf"); інакше  t_p * (1 + p95_factor * rho / (1 - rho))

`tpot_at(profile, batch) -> float`
    tpot(batch); `batch` це `int` від 1 до `max_batch`, інакше `ValueError`.
`best_batch(profile, tpot_slo) -> int`
    Найбільший `b` у `1..max_batch`, для якого `tpot(b) <= tpot_slo` (рівність допустима);
    `0`, якщо навіть `b = 1` порушує SLO. Більший batch це більша пропускна здатність.
`ttft_p95(profile, workload, rho, p95_factor=3.0) -> float`
    Формула вище. `rho` < 0 чи не число: `ValueError`; `p95_factor` >= 0.
`plan(profile, workload, slo, target_util=0.7, p95_factor=3.0) -> dict`
    `target_util` це число в (0, 1], інакше `ValueError`. Кроки:
      1. `b = best_batch(profile, slo["tpot_p95"])`; `b == 0`: повернути
         `{"feasible": False, "reason": "tpot-slo-unreachable"}`;
      2. `t_p = input_tokens / prefill_tps`; якщо `t_p > slo["ttft_p95"]` (навіть без черги), АБО
         `t_p == slo["ttft_p95"]` при `rps > 0` і `p95_factor > 0` (будь-яка черга вже перевищує SLO):
         `{"feasible": False, "reason": "ttft-slo-unreachable"}`;
      3. за пропускною здатністю: `n_cap = max(1, ceil(rps * g(b) / target_util))`;
      4. `n = n_cap`; `rho = rps * g(b) / n`; поки `ttft_p95(..., rho) > slo["ttft_p95"]`: `n += 1`
         і перерахувати `rho` (після кроку 2 закінчується: при `rho -> 0` TTFT прямує до `t_p`, що менше за SLO);
      5. результат `{"feasible": True, "gpus": n, "batch": b, "rho": rho, "tpot": tpot(b),
         "ttft_p95": ttft_p95(..., rho), "cost_per_hour": n * gpu_cost_per_hour,
         "binding": "ttft" якщо n > n_cap, інакше "capacity"}`.
`api_cost_per_hour(workload, api) -> float`
    `rps * 3600 * (input_tokens * input_price + output_tokens * output_price) / 1e6`.
`compare(profile, workload, slo, api, target_util=0.7, p95_factor=3.0) -> dict`
    Для `plan(...)` нездійсненного: `{"feasible": False, "reason": ...}` (те саме, що в `plan`).
    Інакше: `{"feasible": True, "hosted_per_hour", "api_per_hour", "cheaper": "hosted" | "api" |
    "tie", "savings_per_hour": api_per_hour - hosted_per_hour}` (`"tie"` лише при точній
    рівності; додатна економія означає, що дешевше власне).
`break_even_rps(profile, workload, slo, api, candidates, target_util=0.7, p95_factor=3.0) -> float | None`
    `candidates` це непорожній список `rps` за зростанням (інакше `ValueError`; кожен >= 0).
    Повертає ПЕРШИЙ `rps` зі списку, для якого з `workload` із підставленим `rps` власний
    inference здійсненний і не дорожчий за API (`hosted_per_hour <= api_per_hour`); `None`, якщо
    такого немає. `workload["rps"]` у вхідному dict ігнорується й не змінюється.
Входи не мутуються.
"""
import math  # noqa: F401  (знадобиться)


def tpot_at(profile: dict, batch: int) -> float:
    raise NotImplementedError


def best_batch(profile: dict, tpot_slo: float) -> int:
    raise NotImplementedError


def ttft_p95(profile: dict, workload: dict, rho: float, p95_factor: float = 3.0) -> float:
    raise NotImplementedError


def plan(profile: dict, workload: dict, slo: dict, target_util: float = 0.7, p95_factor: float = 3.0) -> dict:
    raise NotImplementedError


def api_cost_per_hour(workload: dict, api: dict) -> float:
    raise NotImplementedError


def compare(profile: dict, workload: dict, slo: dict, api: dict, target_util: float = 0.7,
            p95_factor: float = 3.0) -> dict:
    raise NotImplementedError


def break_even_rps(profile: dict, workload: dict, slo: dict, api: dict, candidates: list,
                   target_util: float = 0.7, p95_factor: float = 3.0):
    raise NotImplementedError
