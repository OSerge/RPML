"""Retrieve a persisted optimization plan by id."""

from __future__ import annotations

from rpml.income_monte_carlo import IncomeMCConfig
from dataclasses import dataclass

from sqlalchemy.orm import Session

from server.application.use_cases.run_optimization_sync import MVP_INPUT_MODE
from server.infrastructure.db.models.optimization_plan import OptimizationPlanORM


@dataclass(frozen=True)
class PlanResult:
    status: str
    total_cost: float
    debts: list[dict]
    payments_matrix: list[list[float]]
    balances_matrix: list[list[float]]
    savings_vector: list[float]
    horizon_months: int
    baseline_comparison: dict | None
    input_mode: str
    instance_name: str | None
    assumptions: list[str]
    ru_mode: bool
    mc_income: bool
    mc_summary: dict | None
    mc_config: IncomeMCConfig | None
    budget_policy: str | None
    budget_trace: list[dict]


def execute_get_plan(db: Session, user_id: int, plan_id: str) -> PlanResult | None:
    row = db.get(OptimizationPlanORM, plan_id)
    if row is None or row.user_id != user_id:
        return None
    payload = row.result_json if isinstance(row.result_json, dict) else {}
    raw_assumptions = payload.get("assumptions", row.assumptions)
    assumptions = (
        raw_assumptions
        if isinstance(raw_assumptions, list)
        else list(raw_assumptions) if raw_assumptions is not None else []
    )
    return PlanResult(
        status=str(payload.get("status", row.solver_status)),
        total_cost=float(payload.get("total_cost", row.total_cost)),
        debts=[
            item
            for item in payload.get("debts", [])
            if isinstance(item, dict)
        ],
        payments_matrix=(
            payload["payments_matrix"]
            if isinstance(payload.get("payments_matrix"), list)
            else row.payments_matrix
        ),
        balances_matrix=(
            payload["balances_matrix"]
            if isinstance(payload.get("balances_matrix"), list)
            else []
        ),
        savings_vector=[
            float(item)
            for item in payload.get("savings_vector", [])
            if isinstance(item, int | float)
        ],
        horizon_months=int(payload.get("horizon_months", row.horizon_months)),
        baseline_comparison=(
            row.baseline_comparison_json
            if isinstance(row.baseline_comparison_json, dict)
            else None
        ),
        input_mode=str(payload.get("input_mode", row.input_mode or MVP_INPUT_MODE)),
        instance_name=(
            str(payload["instance_name"])
            if payload.get("instance_name") is not None
            else row.instance_name
        ),
        assumptions=[str(x) for x in assumptions],
        ru_mode=bool(payload.get("ru_mode", row.ru_mode)),
        mc_income=bool(payload.get("mc_income", row.mc_income)),
        mc_summary=(
            payload["mc_summary"]
            if isinstance(payload.get("mc_summary"), dict)
            else (row.mc_summary if isinstance(row.mc_summary, dict) else None)
        ),
        mc_config=(
            IncomeMCConfig(
                **(
                    payload["mc_config"]
                    if isinstance(payload.get("mc_config"), dict)
                    else row.mc_config_json
                )
            )
            if isinstance(row.mc_config_json, dict)
            or isinstance(payload.get("mc_config"), dict)
            else None
        ),
        budget_policy=(
            str(payload["budget_policy"])
            if payload.get("budget_policy") is not None
            else None
        ),
        budget_trace=[
            item
            for item in payload.get("budget_trace", [])
            if isinstance(item, dict)
        ],
    )
