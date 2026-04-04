from __future__ import annotations

from math import isclose

from rpml.baseline import debt_avalanche, debt_snowball
from rpml.data_loader import with_budget_starts_next_month, with_ru_prepayment_rules
from sqlalchemy import select

from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM
from server.infrastructure.rpml_adapter.instance_builder import build_rios_solis_instance


def _build_instance_from_db(db_session, horizon_months: int):
    debts = list(db_session.scalars(select(DebtORM).order_by(DebtORM.id)).all())
    assert debts
    profile = db_session.scalar(select(ScenarioProfileORM).order_by(ScenarioProfileORM.id.desc()))
    assert profile is not None
    instance = build_rios_solis_instance(
        debts,
        profile,
        horizon_months,
        user_id=debts[0].user_id,
    )
    return with_budget_starts_next_month(instance)


def _sum_matrix(matrix: list[list[float]]) -> float:
    return float(sum(sum(float(x) for x in row) for row in matrix))


def test_baseline_totals_match_core_baseline_ru_mode(client, auth_headers, seeded_debts, db_session):
    horizon = 12
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": horizon, "ru_mode": True, "mc_income": False},
    )
    assert res.status_code == 200
    body = res.json()
    comparison = body["baseline_comparison"]

    instance = _build_instance_from_db(db_session, horizon)
    baseline_instance = with_ru_prepayment_rules(instance)
    av = debt_avalanche(baseline_instance)
    sn = debt_snowball(baseline_instance)

    assert isclose(comparison["avalanche_total_cost"], float(av.total_cost), rel_tol=1e-9, abs_tol=1e-6)
    assert isclose(comparison["snowball_total_cost"], float(sn.total_cost), rel_tol=1e-9, abs_tol=1e-6)


def test_milp_total_cost_equals_sum_of_milp_payments_matrix(client, auth_headers, seeded_debts):
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12, "ru_mode": True, "mc_income": False},
    )
    assert res.status_code == 200
    body = res.json()
    comparison = body["baseline_comparison"]
    milp_strategy = comparison["strategy_results"]["milp"]

    total_from_matrix = _sum_matrix(milp_strategy["payments_matrix"])
    assert isclose(float(comparison["milp_total_cost"]), total_from_matrix, rel_tol=1e-9, abs_tol=1e-6)
    assert isclose(float(body["total_cost"]), total_from_matrix, rel_tol=1e-9, abs_tol=1e-6)


def test_ru_mode_reduces_baseline_cost_when_prepayment_penalty_exists(
    client,
    auth_headers,
    seeded_debts,
    db_session,
):
    debts = list(db_session.scalars(select(DebtORM).order_by(DebtORM.id)).all())
    profile = db_session.scalar(select(ScenarioProfileORM).order_by(ScenarioProfileORM.id.desc()))
    assert profile is not None
    for debt in debts:
        debt.prepay_penalty = 10000.0
    profile.monthly_income_vector = [20000.0] * int(profile.horizon_months)
    db_session.add(profile)
    db_session.commit()

    base_res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12, "ru_mode": False, "mc_income": False},
    )
    ru_res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12, "ru_mode": True, "mc_income": False},
    )

    assert base_res.status_code == 200
    assert ru_res.status_code == 200
    base_cmp = base_res.json()["baseline_comparison"]
    ru_cmp = ru_res.json()["baseline_comparison"]
    assert float(ru_cmp["avalanche_total_cost"]) <= float(base_cmp["avalanche_total_cost"])
    assert float(ru_cmp["snowball_total_cost"]) <= float(base_cmp["snowball_total_cost"])
