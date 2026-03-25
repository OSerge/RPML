from sqlalchemy import select

from server.infrastructure.db.models.debt import DebtORM
from server.infrastructure.db.models.scenario_profile import ScenarioProfileORM


def test_dashboard_returns_kpi_debts_and_baseline_reference(client, auth_headers, seeded_debts):
    res = client.get("/api/v1/dashboard", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert "kpis" in body
    assert "debts" in body
    assert "baseline_reference" in body
    assert "scenario" in body
    assert body["kpis"]["active_debts"] >= 2
    assert body["scenario"]["code"] == "test_scenario"


def test_dashboard_includes_last_optimization_summary(client, auth_headers, seeded_debts):
    run = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert run.status_code == 200
    res = client.get("/api/v1/dashboard", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["last_optimization"] is not None
    assert body["last_optimization"]["mode"] in ("sync", "async")
    assert "baseline_comparison_json" in body["last_optimization"]


def test_dashboard_kpi_ignores_credit_card_fixed_payment_sentinels(
    client,
    auth_headers,
    db_session,
    demo_user,
):
    db_session.add(
        DebtORM(
            user_id=demo_user.id,
            name="card_0",
            loan_type="credit_card",
            principal=5000.0,
            fixed_payment=100000000000000.0,
            min_payment_pct=0.08,
            prepay_penalty=1000000000000.0,
            interest_rate_monthly=0.01,
            default_rate_monthly=0.02,
            stipulated_amount=4.0,
            release_time=0,
        )
    )
    db_session.add(
        DebtORM(
            user_id=demo_user.id,
            name="bank_0",
            loan_type="bank_loan",
            principal=7000.0,
            fixed_payment=250.0,
            min_payment_pct=0.05,
            prepay_penalty=1000000000000.0,
            interest_rate_monthly=0.02,
            default_rate_monthly=0.03,
            stipulated_amount=20.0,
            release_time=0,
        )
    )
    db_session.add(
        ScenarioProfileORM(
            user_id=demo_user.id,
            code="credit_card_scenario",
            horizon_months=12,
            monthly_income_vector=[5000.0] * 12,
            source_json={
                "principals": [5000.0, 7000.0],
                "fixedPayment": [100000000000000.0, 250.0],
                "minPaymentPct": [0.08, 0.05],
                "prepayPenalty": [1000000000000.0, 1000000000000.0],
                "stipulatedAmount": [4.0, 20.0],
                "loanTypes": ["credit_card", "bank_loan"],
                "releaseTimeByLoan": [0, 0],
            },
            baseline_reference={},
        )
    )
    db_session.commit()

    res = client.get("/api/v1/dashboard", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["kpis"]["monthly_required_payment"] == 250.0

    debts = body["debts"]
    by_name = {row["name"]: row for row in debts}
    assert by_name["card_0"]["fixed_payment"] == 100000000000000.0
    assert by_name["bank_0"]["fixed_payment"] == 250.0
