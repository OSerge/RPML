"""Synchronous optimization: load user debts, build instance, run RPML."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from rpml.baseline import debt_avalanche, debt_snowball

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


def _serialize_strategy_result(
    *,
    total_cost: float,
    payments,
    balances,
) -> dict:
    return {
        "total_cost": float(total_cost),
        "payments_matrix": np.asarray(payments, dtype=float).tolist(),
        "balances_matrix": np.asarray(balances, dtype=float).tolist(),
    }


def _solution_is_acceptable(solver_status: str, objective_value: float) -> bool:
    if solver_status not in ("OPTIMAL", "FEASIBLE"):
        return False
    return math.isfinite(float(objective_value))


def _build_baseline_comparison(instance, milp_total_cost: float, milp_payments, milp_balances) -> dict:
    avalanche = debt_avalanche(instance)
    snowball = debt_snowball(instance)
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
    solution = RpmlAdapter().run(instance)
    obj = float(solution.objective_value)
    if not _solution_is_acceptable(solution.status, obj):
        raise OptimizationSolverFailed(solution.status)
    payments_matrix = np.asarray(solution.payments, dtype=float).tolist()
    balances_matrix = np.asarray(solution.balances, dtype=float).tolist()
    baseline_comparison = _build_baseline_comparison(
        instance,
        obj,
        payments_matrix,
        balances_matrix,
    )
    result_json = {
        "status": solution.status,
        "total_cost": obj,
        "payments_matrix": payments_matrix,
        "balances_matrix": balances_matrix,
        "horizon_months": horizon_months,
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
    )
