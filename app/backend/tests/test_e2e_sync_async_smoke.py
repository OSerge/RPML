"""Integration smoke: login, debts, sync optimization, async task + plan (API-level e2e)."""

import time
import uuid

import pytest

from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM


def test_smoke_login_debts_sync_async_poll_plan(client, demo_user, db_session):
    p1, p2 = 1000.0, 2000.0
    for i, principal in enumerate((p1, p2)):
        db_session.add(
            DebtORM(
                user_id=demo_user.id,
                name=f"loan_{i}",
                loan_type="bank_loan",
                principal=principal,
                fixed_payment=100.0 * (i + 1),
                min_payment_pct=0.1,
                prepay_penalty=0.0,
                interest_rate_monthly=0.01,
                default_rate_monthly=0.05,
                stipulated_amount=50.0,
                release_time=0,
            )
        )
    db_session.add(
        ScenarioProfileORM(
            user_id=demo_user.id,
            code="e2e_scenario",
            horizon_months=120,
            monthly_income_vector=[5000.0] * 120,
            source_json={
                "principals": [p1, p2],
                "fixedPayment": [100.0, 200.0],
                "minPaymentPct": [0.1, 0.1],
                "prepayPenalty": [0.0, 0.0],
                "stipulatedAmount": [50.0, 50.0],
                "loanTypes": ["bank_loan", "bank_loan"],
                "releaseTimeByLoan": [0, 0],
            },
            baseline_reference={},
        )
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": demo_user.email, "password": "secret"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token
    headers = {"Authorization": f"Bearer {token}"}

    sync = client.post(
        "/api/v1/optimization/run",
        headers=headers,
        json={"horizon_months": 12},
    )
    assert sync.status_code == 200
    sync_body = sync.json()
    assert "total_cost" in sync_body
    assert "payments_matrix" in sync_body

    create = client.post(
        "/api/v1/optimization/tasks",
        headers=headers,
        json={"horizon_months": 24},
    )
    assert create.status_code == 202
    task_id = create.json()["task_id"]
    uuid.UUID(task_id)

    plan_id = None
    for _ in range(200):
        st = client.get(f"/api/v1/optimization/tasks/{task_id}", headers=headers)
        assert st.status_code == 200
        body = st.json()
        if body["status"] == "completed":
            plan_id = body["plan_id"]
            break
        if body["status"] == "failed":
            pytest.fail(body.get("error") or "async task failed")
        time.sleep(0.05)

    assert plan_id
    plan = client.get(f"/api/v1/optimization/plans/{plan_id}", headers=headers)
    assert plan.status_code == 200
    plan_body = plan.json()
    assert "total_cost" in plan_body
    assert "payments_matrix" in plan_body
