"""Synchronous optimization: load user debts, build instance, run RPML."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from rpml.baseline import debt_avalanche, debt_snowball
from rpml.data_loader import with_budget_starts_next_month, with_ru_prepayment_rules
from rpml.income_monte_carlo import (
    IncomeMCConfig,
    derive_instance_seed,
    replace_instance_income,
    simulate_income_paths,
)

from server.infrastructure.db.models.optimization_run import OptimizationRunORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.infrastructure.repositories.debt_repository import DebtRepository
from server.infrastructure.rpml_adapter import RpmlAdapter, build_rios_solis_instance
from server.infrastructure.rpml_adapter.instance_builder import OptimizationInstanceError

SCENARIO_INPUT_MODE = "scenario_snapshot"
SCENARIO_ASSUMPTIONS: tuple[str, ...] = (
    "Loan terms and monthly budget are taken from persisted debts and scenario profile.",
)

MVP_INPUT_MODE = SCENARIO_INPUT_MODE
MVP_ASSUMPTIONS = SCENARIO_ASSUMPTIONS
NUMERIC_NOISE_EPS = 1e-6
BUDGET_POLICY = "starts_next_month_with_carryover"


class OptimizationSolverFailed(Exception):
    """Solver did not return an acceptable optimum (see `solver_status`)."""

    def __init__(self, solver_status: str) -> None:
        self.solver_status = solver_status
        super().__init__(solver_status)


@dataclass(frozen=True)
class SyncOptimizationResult:
    solver_status: str
    total_cost: float
    payments_matrix: list[list[float]]
    balances_matrix: list[list[float]]
    savings_vector: list[float]
    horizon_months: int
    scenario_profile_id: int
    baseline_comparison: dict
    ru_mode: bool
    mc_income: bool
    mc_summary: dict | None
    budget_policy: str
    budget_trace: list[dict]


def _serialize_strategy_result(
    *,
    total_cost: float,
    payments,
    balances,
    savings=None,
) -> dict:
    payments_matrix = _normalize_matrix(payments)
    balances_matrix = _normalize_matrix(balances)
    savings_vector = (
        np.where(np.abs(np.asarray(savings, dtype=float)) < NUMERIC_NOISE_EPS, 0.0, np.asarray(savings, dtype=float)).tolist()
        if savings is not None
        else []
    )
    return {
        "total_cost": float(total_cost),
        "payments_matrix": payments_matrix,
        "balances_matrix": balances_matrix,
        "savings_vector": savings_vector,
    }


def _solution_is_acceptable(solver_status: str, objective_value: float) -> bool:
    if solver_status not in ("OPTIMAL", "FEASIBLE"):
        return False
    return math.isfinite(float(objective_value))


def _normalize_matrix(values) -> list[list[float]]:
    matrix = np.asarray(values, dtype=float)
    matrix = np.where(np.abs(matrix) < NUMERIC_NOISE_EPS, 0.0, matrix)
    matrix[matrix == -0.0] = 0.0
    return matrix.tolist()


def _to_serializable_percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q))


def _build_implied_savings_vector(
    payments_matrix: list[list[float]],
    monthly_income: np.ndarray,
) -> list[float]:
    income = np.asarray(monthly_income, dtype=float)
    if income.ndim != 1:
        return []
    horizon = int(income.shape[0])
    month_totals = np.zeros(horizon, dtype=float)
    for row in payments_matrix:
        arr = np.asarray(row, dtype=float)
        if arr.shape[0] >= horizon:
            month_totals += arr[:horizon]
    savings = np.zeros(horizon, dtype=float)
    carry = 0.0
    for idx in range(horizon):
        available_budget = float(income[idx] + carry)
        paid_total = float(month_totals[idx])
        if paid_total > available_budget and paid_total - available_budget < 1e-5:
            paid_total = available_budget
        carry = max(0.0, available_budget - paid_total)
        savings[idx] = carry
    savings = np.where(np.abs(savings) < NUMERIC_NOISE_EPS, 0.0, savings)
    return savings.tolist()


def _build_budget_trace(
    payments_matrix: list[list[float]],
    monthly_income: np.ndarray,
    savings_vector: list[float],
) -> list[dict]:
    income = np.asarray(monthly_income, dtype=float)
    savings = np.asarray(savings_vector, dtype=float)
    if income.ndim != 1:
        return []
    horizon = int(income.shape[0])
    month_totals = np.zeros(horizon, dtype=float)
    for row in payments_matrix:
        arr = np.asarray(row, dtype=float)
        if arr.shape[0] >= horizon:
            month_totals += arr[:horizon]
    trace: list[dict] = []
    for idx in range(horizon):
        income_in = float(income[idx])
        carry_in = float(savings[idx - 1]) if idx > 0 and idx - 1 < savings.shape[0] else 0.0
        available_budget = income_in + carry_in
        paid_total = float(month_totals[idx])
        carry_out = float(savings[idx]) if idx < savings.shape[0] else max(0.0, available_budget - paid_total)
        if paid_total > available_budget and paid_total - available_budget < 1e-5:
            paid_total = available_budget
        utilization_pct = (paid_total / available_budget * 100.0) if available_budget > 0 else 0.0
        trace.append(
            {
                "month": idx + 1,
                "income_in": income_in,
                "reserve_start": carry_in,
                "carry_in": carry_in,
                "available_budget": available_budget,
                "planned_payment": paid_total,
                "paid_total": paid_total,
                "reserve_end": carry_out,
                "carry_out": carry_out,
                "utilization_pct": utilization_pct,
            }
        )
    return trace


def _build_monte_carlo_summary(instance, *, ru_mode: bool) -> dict:
    base_config = IncomeMCConfig()
    seeded_config = replace(
        base_config,
        seed=derive_instance_seed(base_config.seed, instance.name),
    )
    income_paths = simulate_income_paths(instance.monthly_income, seeded_config)
    feasible_costs: list[float] = []
    feasible_solve_times: list[float] = []
    feasible_statuses = {"OPTIMAL", "FEASIBLE"}
    for idx, scenario_income in enumerate(income_paths):
        scenario_instance = replace_instance_income(
            instance,
            scenario_income,
            str(idx),
        )
        scenario_solution = RpmlAdapter().run(scenario_instance, ru_mode=ru_mode)
        if scenario_solution.status not in feasible_statuses:
            continue
        objective = float(scenario_solution.objective_value)
        if not math.isfinite(objective):
            continue
        feasible_costs.append(objective)
        feasible_solve_times.append(float(scenario_solution.solve_time))
    n_scenarios = int(seeded_config.n_scenarios)
    feasible_scenarios = len(feasible_costs)
    infeasible_rate = 1.0 - (float(feasible_scenarios) / float(n_scenarios))
    return {
        "n_scenarios": n_scenarios,
        "feasible_scenarios": feasible_scenarios,
        "infeasible_rate": float(infeasible_rate),
        "mean_total_cost": float(np.mean(feasible_costs)) if feasible_costs else None,
        "median_total_cost": _to_serializable_percentile(feasible_costs, 50.0),
        "p90_total_cost": _to_serializable_percentile(feasible_costs, 90.0),
        "mean_solve_time": float(np.mean(feasible_solve_times)) if feasible_solve_times else None,
        "p90_solve_time": _to_serializable_percentile(feasible_solve_times, 90.0),
    }


def _build_baseline_comparison(
    instance,
    milp_total_cost: float,
    milp_payments,
    milp_balances,
    milp_savings,
    *,
    ru_mode: bool,
) -> dict:
    baseline_instance = with_ru_prepayment_rules(instance) if ru_mode else instance
    avalanche = debt_avalanche(baseline_instance)
    snowball = debt_snowball(baseline_instance)
    av_total = float(avalanche.total_cost)
    sn_total = float(snowball.total_cost)
    return {
        "milp_total_cost": milp_total_cost,
        "avalanche_total_cost": av_total,
        "snowball_total_cost": sn_total,
        "savings_vs_avalanche_abs": av_total - milp_total_cost,
        "savings_vs_avalanche_pct": ((av_total - milp_total_cost) / av_total * 100.0) if av_total else 0.0,
        "savings_vs_snowball_abs": sn_total - milp_total_cost,
        "savings_vs_snowball_pct": ((sn_total - milp_total_cost) / sn_total * 100.0) if sn_total else 0.0,
        "strategy_results": {
            "milp": _serialize_strategy_result(
                total_cost=milp_total_cost,
                payments=milp_payments,
                balances=milp_balances,
                savings=milp_savings,
            ),
            "avalanche": _serialize_strategy_result(
                total_cost=av_total,
                payments=avalanche.payments,
                balances=avalanche.balances,
                savings=avalanche.savings,
            ),
            "snowball": _serialize_strategy_result(
                total_cost=sn_total,
                payments=snowball.payments,
                balances=snowball.balances,
                savings=snowball.savings,
            ),
        },
    }


def _persist_optimization_run(
    db: Session,
    *,
    user_id: int,
    scenario_profile_id: int,
    mode: str,
    result_json: dict,
    baseline_comparison_json: dict,
    status: str,
) -> None:
    row = OptimizationRunORM(
        user_id=user_id,
        scenario_profile_id=scenario_profile_id,
        mode=mode,
        status=status,
        result_json=result_json,
        baseline_comparison_json=baseline_comparison_json,
    )
    db.add(row)
    db.commit()


def execute_run_optimization_sync(
    db: Session,
    user_id: int,
    horizon_months: int,
    *,
    mode: str = "sync",
    ru_mode: bool = True,
    mc_income: bool = False,
) -> SyncOptimizationResult:
    repo = DebtRepository(db)
    debts = repo.list_for_user(user_id)
    if not debts:
        raise OptimizationInstanceError("No debts to optimize")
    profile = db.scalars(
        select(ScenarioProfileORM)
        .where(ScenarioProfileORM.user_id == user_id)
        .order_by(ScenarioProfileORM.id.desc())
    ).first()
    if profile is None:
        raise OptimizationInstanceError("Scenario profile is required for optimization.")
    raw_instance = build_rios_solis_instance(
        debts,
        profile,
        horizon_months,
        user_id=user_id,
    )
    instance = with_budget_starts_next_month(raw_instance)
    solution = RpmlAdapter().run(instance, ru_mode=ru_mode)
    obj = float(solution.objective_value)
    if not _solution_is_acceptable(solution.status, obj):
        raise OptimizationSolverFailed(solution.status)
    payments_matrix = _normalize_matrix(solution.payments)
    balances_matrix = _normalize_matrix(solution.balances)
    savings_vector = _build_implied_savings_vector(payments_matrix, instance.monthly_income)
    baseline_comparison = _build_baseline_comparison(
        instance,
        obj,
        payments_matrix,
        balances_matrix,
        savings_vector,
        ru_mode=ru_mode,
    )
    mc_summary = _build_monte_carlo_summary(instance, ru_mode=ru_mode) if mc_income else None
    budget_trace = _build_budget_trace(payments_matrix, instance.monthly_income, savings_vector)
    result_json = {
        "status": solution.status,
        "total_cost": obj,
        "payments_matrix": payments_matrix,
        "balances_matrix": balances_matrix,
        "savings_vector": savings_vector,
        "horizon_months": horizon_months,
        "ru_mode": ru_mode,
        "mc_income": mc_income,
        "mc_summary": mc_summary,
        "budget_policy": BUDGET_POLICY,
        "budget_trace": budget_trace,
    }
    _persist_optimization_run(
        db,
        user_id=user_id,
        scenario_profile_id=profile.id,
        mode=mode,
        result_json=result_json,
        baseline_comparison_json=baseline_comparison,
        status=solution.status,
    )
    return SyncOptimizationResult(
        solver_status=solution.status,
        total_cost=obj,
        payments_matrix=payments_matrix,
        balances_matrix=balances_matrix,
        savings_vector=savings_vector,
        horizon_months=horizon_months,
        scenario_profile_id=profile.id,
        baseline_comparison=baseline_comparison,
        ru_mode=ru_mode,
        mc_income=mc_income,
        mc_summary=mc_summary,
        budget_policy=BUDGET_POLICY,
        budget_trace=budget_trace,
    )
