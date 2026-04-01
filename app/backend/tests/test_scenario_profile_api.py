from sqlalchemy import select

from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM


def test_get_scenario_profile_returns_latest(client, auth_headers, seeded_debts):
    res = client.get("/api/v1/scenario/profile", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["horizon_months"] == 120
    assert isinstance(body["monthly_income_vector"], list)
    assert len(body["monthly_income_vector"]) == 120


def test_put_scenario_profile_updates_income_vector(client, auth_headers, seeded_debts):
    payload = {
        "horizon_months": 12,
        "monthly_income_vector": [35000.0] * 12,
    }
    res = client.put("/api/v1/scenario/profile", headers=auth_headers, json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["horizon_months"] == 12
    assert body["monthly_income_vector"] == [35000.0] * 12


def test_estimate_available_budget_updates_profile_and_supports_optimization(
    client,
    auth_headers,
    seeded_debts,
):
    est = client.post(
        "/api/v1/scenario/profile/estimate-available-budget",
        headers=auth_headers,
        json={
            "horizon_months": 24,
            "monthly_income": 120000.0,
            "mandatory_expenses": 70000.0,
            "variable_expenses": 10000.0,
            "safety_buffer_pct": 0.1,
        },
    )
    assert est.status_code == 200
    est_body = est.json()
    assert est_body["monthly_available_budget"] == 36000.0
    assert est_body["scenario_profile"]["horizon_months"] == 24
    assert est_body["scenario_profile"]["monthly_income_vector"] == [36000.0] * 24

    run = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 24, "ru_mode": True, "mc_income": True},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["mc_income"] is True
    assert body["mc_summary"] is not None


def test_optimization_uses_latest_profile_when_multiple_exist(client, auth_headers, seeded_debts, db_session):
    existing = db_session.scalar(select(ScenarioProfileORM).order_by(ScenarioProfileORM.id.asc()))
    assert existing is not None
    db_session.add(
        ScenarioProfileORM(
            user_id=existing.user_id,
            code="manual_v2",
            horizon_months=36,
            monthly_income_vector=[42000.0] * 36,
            source_json=None,
            baseline_reference={"origin": "manual"},
        )
    )
    db_session.commit()

    run = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 36},
    )
    assert run.status_code == 200

    latest = db_session.scalar(select(ScenarioProfileORM).order_by(ScenarioProfileORM.id.desc()))
    assert latest is not None
