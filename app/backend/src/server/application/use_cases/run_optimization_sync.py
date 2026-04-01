"""Synchronous optimization: load user debts, build instance, run RPML."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from rpml.baseline import debt_avalanche, debt_snowball
from rpml.data_loader import with_ru_prepayment_rules
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
    horizon_months: int
    scenario_profile_id: int
    baseline_comparison: dict
    ru_mode: bool
    mc_income: bool
    mc_summary: dict | None


def _serialize_strategy_result(
    *,
    total_cost: float,
    payments,
    balances,
) -> dict:
    payments_matrix = _normalize_matrix(payments)
    balances_matrix = _normalize_matrix(balances)
    return {
        "total_cost": float(total_cost),
        "payments_matrix": payments_matrix,
        "balances_matrix": balances_matrix,
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
            ),
            "avalanche": _serialize_strategy_result(
                total_cost=av_total,
                payments=avalanche.payments,
                balances=avalanche.balances,
            ),
            "snowball": _serialize_strategy_result(
                total_cost=sn_total,
                payments=snowball.payments,
                balances=snowball.balances,
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
    profiles = list(
        db.scalars(select(ScenarioProfileORM).where(ScenarioProfileORM.user_id == user_id)).all()
    )
    if len(profiles) != 1:
        raise OptimizationInstanceError(
            "Exactly one scenario profile is required for optimization."
        )
    instance = build_rios_solis_instance(
        debts,
        profiles[0],
        horizon_months,
        user_id=user_id,
    )
    solution = RpmlAdapter().run(instance, ru_mode=ru_mode)
    obj = float(solution.objective_value)
    if not _solution_is_acceptable(solution.status, obj):
        raise OptimizationSolverFailed(solution.status)
    payments_matrix = _normalize_matrix(solution.payments)
    balances_matrix = _normalize_matrix(solution.balances)
    baseline_comparison = _build_baseline_comparison(
        instance,
        obj,
        payments_matrix,
        balances_matrix,
        ru_mode=ru_mode,
    )
    mc_summary = _build_monte_carlo_summary(instance, ru_mode=ru_mode) if mc_income else None
    result_json = {
        "status": solution.status,
        "total_cost": obj,
        "payments_matrix": payments_matrix,
        "balances_matrix": balances_matrix,
        "horizon_months": horizon_months,
        "ru_mode": ru_mode,
        "mc_income": mc_income,
        "mc_summary": mc_summary,
    }
    _persist_optimization_run(
        db,
        user_id=user_id,
        scenario_profile_id=profiles[0].id,
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
        horizon_months=horizon_months,
        scenario_profile_id=profiles[0].id,
        baseline_comparison=baseline_comparison,
        ru_mode=ru_mode,
        mc_income=mc_income,
        mc_summary=mc_summary,
    )
